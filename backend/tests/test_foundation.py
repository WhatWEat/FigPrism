from figprism.auth import create_user
from figprism.db import connect
from figprism.domains import match_domains
from figprism.storage import Storage
import pytest

def test_auth_session_logout_and_csrf(client):
    create_user('alice', 'long-enough-password')
    assert client.get('/api/auth/me').json()['user'] is None
    assert client.post('/api/auth/login', json={'username':'alice','password':'incorrect-password'}).status_code == 401
    response = client.post('/api/auth/login', json={'username':'alice','password':'long-enough-password'})
    assert response.status_code == 200
    assert 'HttpOnly' in response.headers['set-cookie']
    assert response.headers['cache-control'] == 'private, no-store'
    old = client.cookies.get('figprism_session')
    assert client.get('/api/auth/me').json()['user']['username'] == 'alice'
    assert client.post('/api/auth/logout', headers={'Origin':'https://evil.invalid'}).status_code == 403
    client.post('/api/auth/logout')
    client.cookies.set('figprism_session', old)
    assert client.get('/api/auth/me').json()['user'] is None

def test_invite_single_use(client):
    uid = create_user('admin', 'long-enough-password', 'admin')
    with connect() as db:
        db.execute("INSERT INTO invite_codes(code,created_by,expires_at) VALUES('one-time',?,datetime('now','+1 day'))", (uid,))
    data={'username':'bob','password':'long-enough-password','invite_code':'one-time'}
    assert client.post('/api/auth/register', json=data).status_code == 200
    data['username']='eve'
    assert client.post('/api/auth/register', json=data).status_code == 403

def test_domain_boundaries_and_exclusions():
    configs=[{'slug':'memory','phrases':['neural memory'],'acronyms':['TTT'],'exclude_terms':['DRAM']}]
    assert match_domains('TTT for LLMs',configs)==['memory']
    assert match_domains('ttt or XTTTX',configs)==[]
    assert match_domains('TTT DRAM',configs)==[]
    assert match_domains('neural memory DRAM',configs)==['memory']

def test_storage_traversal(client):
    for key in ('../secret','/etc/passwd','a/../../b','a\\b'):
        with pytest.raises(ValueError): Storage().local(key)
