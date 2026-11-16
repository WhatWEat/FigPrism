import asyncio
import pytest
from figprism.auth import create_user
from figprism.db import connect
from figprism.storage import Storage
from figprism.resource_insights import insights, scan_remote, start_scan
from test_feed import library

PASSWORD = "long-enough-password"
def login(client, name):
    assert client.post('/api/auth/login', json={'username':name,'password':PASSWORD}).status_code == 200


def test_admin_user_details_permissions_counts_and_pagination(library):
    client = library
    admin = create_user('manager', PASSWORD, 'admin')
    alice = create_user('alice', PASSWORD)
    bob = create_user('bob', PASSWORD)
    with connect() as db:
        db.executemany('INSERT INTO collections(id,user_id,name) VALUES(?,?,?)', [('a',alice,'A'),('b',alice,'B'),('c',bob,'C')])
        db.executemany('INSERT INTO collection_items(id,collection_id,figure_id) VALUES(?,?,?)', [('1','a','a1'),('2','b','a1'),('3','b','b1')])
    urls = ['/api/admin/users',f'/api/admin/users/{alice}','/api/admin/storage/insights']
    for url in urls:
        assert client.get(url).status_code == 401
    login(client, 'alice')
    for url in urls:
        assert client.get(url).status_code == 403
    assert client.post('/api/admin/storage/scan').status_code == 403
    login(client, 'manager')
    overview = client.get('/api/admin/users')
    assert overview.headers['cache-control'] == 'private, no-store'
    assert overview.json()['summary'] == {'users':3,'active_users':3,'boards':3,'items':3,'figures':2}
    detail = client.get(f'/api/admin/users/{alice}?limit=1').json()
    assert (detail['user']['item_count'],detail['user']['figure_count'],detail['user']['paper_count']) == (3,2,2)
    assert len(detail['items']) == 1 and detail['next_offset'] == 1
    second = client.get(f'/api/admin/users/{alice}?limit=1&offset=1').json()
    assert detail['items'][0]['item_id'] != second['items'][0]['item_id']
    assert client.get(f'/api/admin/users/{alice}?collection_id=b').json()['total'] == 2
    assert client.get(f'/api/admin/users/{alice}?collection_id=c').status_code == 404
    assert client.get('/api/admin/users/999999').status_code == 404
    assert client.get(f'/api/admin/users/{bob}').json()['items'] == []
    assert 'password_hash' not in str(detail) and 'session' not in str(detail)
    assert client.get(f'/api/admin/users/{admin}?offset=-1').status_code == 422


def test_asset_cache_counters_are_persistent_and_ignore_invalid_versions(library, monkeypatch):
    outcomes = iter(['HIT','MISS','COALESCED'])
    async def get(self, key):
        self.cache_status = next(outcomes)
        return b'image'
    monkeypatch.setattr(Storage, 'get', get)
    for _ in range(3):
        assert library.get('/api/assets/hd/a1.webp?v=v1').status_code == 200
    assert library.get('/api/assets/hd/a1.webp?v=old').status_code == 404
    counts = insights()['cache']
    assert counts['requests'] == 3 and counts['hits'] == counts['misses'] == counts['coalesced'] == 1
    assert counts['hit_rate'] == pytest.approx(1/3)
    from figprism.db import init_db
    init_db()
    assert insights()['cache']['requests'] == 3


@pytest.mark.asyncio
async def test_inventory_union_and_failed_scan_preserves_snapshot(client, monkeypatch, tmp_path):
    store = Storage()
    store.settings.webdav.url = "https://dav.example.test"
    await store.put('papers/shared', b'x'*20)
    await store.put('papers/local', b'y'*30)
    tree = {'':[{'key':'papers','directory':True}], 'papers':[{'key':'papers/shared','directory':False,'size':10},{'key':'papers/remote','directory':False,'size':40}]}
    async def listing(self, key='', include_sizes=False):
        assert include_sizes
        return tree[key]
    monkeypatch.setattr(Storage, 'list', listing)
    assert insights()['resources']['total_bytes'] is None
    assert insights()['cache']['hit_rate'] is None
    await scan_remote((tmp_path/'lock').open('w'))
    result = insights()
    assert result['resources']['remote_bytes'] == 50
    assert result['resources']['local_bytes'] == 50
    assert result['resources']['total_bytes'] == 90
    assert result['resources']['total_files'] == 3
    completed = result['scan']['completed_at']
    async def failed(*args, **kwargs):
        raise RuntimeError('not public credentials')
    monkeypatch.setattr(Storage, 'list', failed)
    await scan_remote((tmp_path/'lock').open('w'))
    result = insights()
    assert result['scan']['status'] == 'error' and result['scan']['completed_at'] == completed
    assert result['resources']['remote_bytes'] == 50
    assert 'credentials' not in result['scan']['error']


@pytest.mark.asyncio
async def test_inventory_single_flight_and_stale_restart(client, monkeypatch):
    from figprism import api
    jobs = []
    monkeypatch.setattr(api, 'launch', lambda coro: jobs.append(asyncio.create_task(coro)))
    async def empty(self, key='', include_sizes=False):
        return []
    monkeypatch.setattr(Storage, 'list', empty)
    with connect() as db:
        db.execute("UPDATE resource_scan SET status='running'")
    assert start_scan()  # No kernel lock: prior process was interrupted.
    assert not start_scan(force=True)
    await jobs[0]
    assert insights()['scan']['status'] == 'ready'
    assert not start_scan()

@pytest.mark.asyncio
async def test_webdav_inventory_requires_successful_file_lengths(client):
    import httpx
    store = Storage()
    store.settings.webdav.url = 'https://dav.example.test'
    xml = '''<d:multistatus xmlns:d="DAV:"><d:response><d:href>/figprism/papers/</d:href><d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response><d:response><d:href>/figprism/empty.pdf</d:href><d:propstat><d:prop><d:resourcetype/><d:getcontentlength>0</d:getcontentlength></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response></d:multistatus>'''
    async def respond(request):
        assert request.headers['Depth'] == '1'
        return httpx.Response(207, text=xml)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        store._client = http
        result = await store.list(include_sizes=True)
        assert result == [{'key':'papers','directory':True},{'key':'empty.pdf','directory':False,'size':0}]
        xml = xml.replace('<d:getcontentlength>0</d:getcontentlength>', '')
        with pytest.raises(ValueError, match='文件大小'):
            await store.list(include_sizes=True)
