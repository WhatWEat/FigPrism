import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import httpx
import pytest
from figprism.auth import create_user
from figprism.auth_protection import rate_limit
from figprism.config import get_settings
from figprism.db import connect, init_db

PASSWORD='long-enough-password'

def enable():
    from figprism.config import TurnstileConfig
    get_settings().turnstile=TurnstileConfig(enabled=True,site_key='public-site',secret_key='private-secret',allowed_hostnames=['figprism.ai4any.com'])

def response(result):
    return httpx.Response(200,json=result,request=httpx.Request('POST','https://challenges.cloudflare.com/turnstile/v0/siteverify'))

def valid(action='login'):
    return {'success':True,'hostname':'figprism.ai4any.com','action':action}


def test_login_requires_server_challenge_and_blocks_replay(client,monkeypatch):
    create_user('alice',PASSWORD);enable();calls=[]
    # Patch only the separate validation client, not FastAPI's TestClient.post.
    original=httpx.Client.send
    def send(self,request,**kwargs):
        if request.url.host=='challenges.cloudflare.com':
            import json
            calls.append(json.loads(request.content));return response(valid())
        return original(self,request,**kwargs)
    monkeypatch.setattr(httpx.Client,'send',send)
    config=client.get('/api/auth/challenge-config')
    assert config.json()=={'enabled':True,'site_key':'public-site'}
    assert config.headers['cache-control']=='private, no-store' and 'private-secret' not in config.text
    body={'username':'alice','password':PASSWORD}
    assert client.post('/api/auth/login',json=body).status_code==403
    body['turnstile_token']='a-token'
    assert client.post('/api/auth/login',json=body).status_code==200
    assert client.post('/api/auth/login',json=body).status_code==403
    assert len(calls)==1 and calls[0]['secret']=='private-secret'
    init_db()
    assert client.post('/api/auth/login',json=body).status_code==403


@pytest.mark.parametrize('result',[{'success':False},valid('register'),{**valid(),'hostname':'evil.test'},None])
def test_failed_challenges_never_authenticate(client,monkeypatch,result):
    create_user('alice',PASSWORD);enable();original=httpx.Client.send
    def send(self,request,**kwargs):
        if request.url.host=='challenges.cloudflare.com':
            if result is None:raise httpx.ConnectTimeout('unavailable')
            return response(result)
        return original(self,request,**kwargs)
    monkeypatch.setattr(httpx.Client,'send',send)
    outcome=client.post('/api/auth/login',json={'username':'alice','password':PASSWORD,'turnstile_token':'bad'})
    assert outcome.status_code==(503 if result is None else 403)
    assert client.get('/api/auth/me').json()['user'] is None


def test_challenge_required_for_registration_does_not_spend_invite(client,monkeypatch):
    uid=create_user('admin',PASSWORD,'admin')
    with connect() as db:db.execute("INSERT INTO invite_codes(code,created_by,expires_at,max_uses) VALUES('test',?,datetime('now','+1 day'),2)",(uid,))
    enable();original=httpx.Client.send
    def send(self,request,**kwargs):
        if request.url.host=='challenges.cloudflare.com':return response(valid('register'))
        return original(self,request,**kwargs)
    monkeypatch.setattr(httpx.Client,'send',send)
    body={'username':'new-user','password':PASSWORD,'invite_code':'test'}
    assert client.post('/api/auth/register',json=body).status_code==403
    with connect() as db:assert db.execute("SELECT used_count FROM invite_codes WHERE code='test'").fetchone()[0]==0
    body['turnstile_token']='registration-token'
    assert client.post('/api/auth/register',json=body).status_code==200


def test_replayed_token_race_allows_only_one_request(client,monkeypatch):
    create_user('alice',PASSWORD);enable();barrier=Barrier(2);original=httpx.Client.send
    def send(self,request,**kwargs):
        if request.url.host=='challenges.cloudflare.com':
            barrier.wait(timeout=5);return response(valid())
        return original(self,request,**kwargs)
    monkeypatch.setattr(httpx.Client,'send',send)
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes=list(pool.map(lambda _:client.post('/api/auth/login',json={'username':'alice','password':PASSWORD,'turnstile_token':'same'}).status_code,range(2)))
    assert sorted(codes)==[200,403]


def test_rate_limit_is_atomic_persistent_and_expires(client):
    with ThreadPoolExecutor(max_workers=12) as pool:
        waits=list(pool.map(lambda _:rate_limit('ip','same'),range(12)))
    assert waits.count(0)==10 and len([x for x in waits if x>0])==2
    init_db()
    assert rate_limit('ip','same')>0
    assert rate_limit('ip','different')==0
    with connect() as db:db.execute('UPDATE auth_rate_limits SET created_at=?',(time.time()-61,))
    assert rate_limit('ip','same')==0


def test_spoofed_forwarding_headers_do_not_bypass_app_limit(client):
    for _ in range(10):
        assert client.post('/api/auth/login',json={'username':'unknown','password':PASSWORD}).status_code==401
    denied=client.post('/api/auth/login',json={'username':'unknown','password':PASSWORD},headers={'X-Forwarded-For':'203.0.113.1','CF-Connecting-IP':'203.0.113.2'})
    assert denied.status_code==429 and denied.headers['Retry-After']
    assert denied.headers['cache-control']=='private, no-store'
