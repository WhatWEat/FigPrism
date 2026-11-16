from concurrent.futures import ThreadPoolExecutor
import pytest
from figprism.auth import create_user
from figprism.db import connect, init_db

PASSWORD = 'long-enough-password'

def admin(client):
    uid = create_user('invite-admin', PASSWORD, 'admin')
    assert client.post('/api/auth/login', json={'username':'invite-admin','password':PASSWORD}).status_code == 200
    return uid

def register(client, code, name):
    return client.post('/api/auth/register', json={'username':name,'password':PASSWORD,'invite_code':code})


def test_invite_limit_and_failed_registration_do_not_spend_slots(client):
    uid=admin(client)
    response=client.post('/api/admin/invites', json={'max_uses':2})
    assert response.status_code == 200
    data=response.json();code=data['code']
    assert (data['max_uses'],data['used_count'],data['remaining_uses'])==(2,0,2)
    assert response.headers['cache-control']=='private, no-store'
    assert register(client, code, 'invite-admin').status_code == 409
    assert register(client, code, 'short').status_code == 200
    assert register(client, code, 'short').status_code == 409
    assert register(client, code, 'second').status_code == 200
    assert register(client, code, 'third').status_code == 403
    with connect() as db:
        assert db.execute('SELECT used_count FROM invite_codes WHERE code=?',(code,)).fetchone()[0] == 2
    client.post('/api/auth/login', json={'username':'invite-admin','password':PASSWORD})
    listing=client.get('/api/admin/invites')
    assert listing.headers['cache-control']=='private, no-store'
    item=next(x for x in listing.json()['items'] if x['code']==code)
    assert item['remaining_uses']==0 and item['status']=='exhausted'


def test_last_invite_slot_is_atomic(client):
    admin(client)
    code=client.post('/api/admin/invites').json()['code']
    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes=list(pool.map(lambda n:register(client,code,f'parallel-{n}').status_code, range(4)))
    assert sorted(outcomes)==[200,403,403,403]
    with connect() as db:
        assert db.execute('SELECT COUNT(*) FROM users WHERE username LIKE ?',('parallel-%',)).fetchone()[0]==1
        assert db.execute('SELECT used_count FROM invite_codes WHERE code=?',(code,)).fetchone()[0]==1


def test_expired_invites_and_validation_and_privileges(client):
    assert client.get('/api/admin/invites').status_code==401
    assert client.post('/api/admin/invites',json={'max_uses':10}).status_code==401
    admin(client)
    for value in [0,-1,1001,1.5,True,'2']:
        assert client.post('/api/admin/invites',json={'max_uses':value}).status_code==422
    data=client.post('/api/admin/invites').json()
    assert data['max_uses']==1
    with connect() as db:
        db.execute("UPDATE invite_codes SET expires_at=datetime('now','-1 second') WHERE code=?",(data['code'],))
    item=client.get('/api/admin/invites').json()['items'][0]
    assert item['status']=='expired' and item['remaining_uses']==0
    assert register(client,data['code'],'late-user').status_code==403
    create_user('member',PASSWORD)
    client.post('/api/auth/login',json={'username':'member','password':PASSWORD})
    assert client.get('/api/admin/invites').status_code==403
    assert client.post('/api/admin/invites',json={'max_uses':2}).status_code==403


def test_legacy_migration_preserves_spent_invites_and_is_idempotent(client):
    uid=admin(client)
    with connect() as db:
        db.execute('DROP TABLE invite_codes')
        db.execute('CREATE TABLE invite_codes (code TEXT PRIMARY KEY,created_by INTEGER,used_by INTEGER,expires_at TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
        db.execute("INSERT INTO invite_codes(code,created_by,used_by,expires_at) VALUES('old-used',?,?,datetime('now','+1 day'))",(uid,uid))
        db.execute("INSERT INTO invite_codes(code,created_by,expires_at) VALUES('old-unused',?,datetime('now','+1 day'))",(uid,))
    init_db()
    with connect() as db:
        assert tuple(db.execute("SELECT max_uses,used_count FROM invite_codes WHERE code='old-used'").fetchone())==(1,1)
        assert tuple(db.execute("SELECT max_uses,used_count FROM invite_codes WHERE code='old-unused'").fetchone())==(1,0)
        db.execute("UPDATE invite_codes SET max_uses=5,used_count=3 WHERE code='old-used'")
    init_db()
    with connect() as db:
        assert tuple(db.execute("SELECT max_uses,used_count FROM invite_codes WHERE code='old-used'").fetchone())==(5,3)
    assert register(client,'old-unused','legacy-user').status_code==200
