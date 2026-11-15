import asyncio
import hashlib
import json

import httpx
import pytest
from figprism.config import get_settings
from figprism.db import connect
from figprism.storage import Storage
from figprism.uploads import status, upload_one


@pytest.fixture
def store(client):
    get_settings().webdav.url = "https://dav.example.test"
    get_settings().favorite_cache_bytes = 0
    return Storage()


@pytest.mark.asyncio
async def test_offline_ingest_publishes_durable_local_assets(
    client, store, monkeypatch
):
    from figprism import ingest
    from figprism.extraction import Crop

    async def cpu(op, path, **kwargs):
        if op == "inspect":
            return {
                "title": "Local durable paper",
                "layout_type": "single",
                "first_page_text": "",
            }
        if op == "plan":
            return [Crop(1, [0, 0, 400, 100], "Fig. 1", "local caption", 0.9)]
        return {
            "thumb": b"local-thumb",
            "hd": b"local-hd",
            "raw": b"%PDF-local",
            "width": 400,
            "height": 100,
            "aspect_ratio": 4,
            "blurhash": None,
            "fonts": [],
            "subitems": [],
            "palette": {"colors": [], "pairs": [], "neutrals": [], "buckets": []},
        }

    async def judge(*args):
        return None

    async def offline(*args):
        raise AssertionError("Ingest must not contact WebDAV")

    monkeypatch.setattr(ingest, "cpu_call", cpu)
    monkeypatch.setattr(ingest, "judge", judge)
    monkeypatch.setattr(Storage, "upload", offline)
    pid = await asyncio.wait_for(ingest.ingest_pdf(b"%PDF local", source_data=b""), 2)
    with connect() as db:
        row = db.execute("SELECT * FROM papers WHERE id=?", (pid,)).fetchone()
        assert row["ingest_status"] == "completed" and row["pdf_uploaded"] == 0
    result = client.get("/api/figures?q=local").json()["items"][0]
    assert client.get(result["thumb_url"]).content == b"local-thumb"
    assert client.get(result["raw_url"]).content == b"%PDF-local"
    assert status()["pending"] == 5
    with pytest.raises(ValueError, match="等待远端备份"):
        await ingest.rebuild()
    sent = {}

    async def upload(self, key, data, content_type):
        sent[key] = data

    monkeypatch.setattr(Storage, "upload", upload)
    while await upload_one(store):
        pass
    with connect() as db:
        assert (
            db.execute("SELECT pdf_uploaded FROM papers WHERE id=?", (pid,)).fetchone()[
                0
            ]
            == 1
        )
    manifest = next(
        json.loads(data) for key, data in sent.items() if key.endswith("/metadata.json")
    )
    assert manifest["paper"]["pdf_uploaded"] == 1
    assert manifest["paper"]["ingest_status"] == "completed"
    assert len(manifest["figures"]) == 1


@pytest.mark.asyncio
async def test_failed_upload_retains_bytes_and_restart_retries(store, monkeypatch):
    key = "papers/test/blob"
    await store.put(key, b"important")

    async def fail(*args):
        raise httpx.ReadTimeout("test")

    monkeypatch.setattr(Storage, "upload", fail)
    assert await upload_one(store)
    with connect() as db:
        row = db.execute("SELECT * FROM asset_transfers").fetchone()
        assert row["attempts"] == 1 and not row["synced"] and row["last_error"]
        db.execute("UPDATE asset_transfers SET next_attempt=0")
    assert await Storage().get(key) == b"important"
    sent = []

    async def success(self, key, data, content_type):
        sent.append((key, data))

    monkeypatch.setattr(Storage, "upload", success)
    assert await upload_one(Storage())
    assert sent == [(key, b"important")]
    assert status()["pending"] == 0


@pytest.mark.asyncio
async def test_pending_bytes_survive_capacity_pressure_then_resume(store, monkeypatch):
    get_settings().cache_max_bytes = 10
    await store.put("first", b"aaaaaa")
    full = asyncio.Event()
    original = store.make_room

    def make_room(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        except Exception:
            full.set()
            raise

    monkeypatch.setattr(store, "make_room", make_room)
    task = asyncio.create_task(store.put("second", b"bbbbbb"))
    try:
        await asyncio.wait_for(full.wait(), 1)
        assert not task.done()
        assert await store.get("first") == b"aaaaaa"
        assert status()["used_bytes"] == 6
        with connect() as db:
            db.execute("UPDATE asset_transfers SET synced=1 WHERE key=?", ("first",))
        await asyncio.wait_for(task, 2)
        assert await store.get("second") == b"bbbbbb"
        assert status()["used_bytes"] <= 10
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_new_generation_is_not_acknowledged_by_old_upload(store, monkeypatch):
    await store.put("mutable", b"version1")
    entered, release = asyncio.Event(), asyncio.Event()
    remote = {}

    async def slow(self, key, data, content_type):
        entered.set()
        await release.wait()
        remote[key] = data

    monkeypatch.setattr(Storage, "upload", slow)
    task = asyncio.create_task(upload_one(store))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.wait_for(store.put("mutable", b"version2"), 1)
    finally:
        release.set()
        await task
    with connect() as db:
        row = db.execute("SELECT * FROM asset_transfers").fetchone()
        assert not row["synced"]
        assert row["digest"] == hashlib.sha256(b"version2").hexdigest()
    await upload_one(store)
    assert remote["mutable"] == b"version2"
    assert status()["pending"] == 0


@pytest.mark.asyncio
async def test_manifest_waits_for_all_referenced_assets(store, monkeypatch):
    prefix = "papers/2026/a/"
    await store.put(prefix + "metadata.json", b"manifest")
    await store.put(prefix + "paper.pdf", b"%PDF original")
    await store.put(prefix + "figures/hd.webp", b"image")
    sent = []

    async def upload(self, key, data, content_type):
        sent.append(key)

    monkeypatch.setattr(Storage, "upload", upload)
    for _ in range(3):
        assert await upload_one(store)
    assert sent[-1] == prefix + "metadata.json"


@pytest.mark.asyncio
async def test_legacy_thumbnails_share_budget_and_download_can_skip_cache(
    store, monkeypatch
):
    get_settings().cache_max_bytes = 10
    legacy = store.legacy("old_thumb.webp")
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"old-cache")
    await store.put("pending", b"1234567890")
    assert not legacy.exists()
    assert status()["used_bytes"] == 10

    async def handler(request):
        return httpx.Response(200, content=b"remote-file")

    monkeypatch.setattr(
        Storage,
        "client",
        lambda self: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await store.get("not-cached") == b"remote-file"
    assert status()["used_bytes"] == 10
    assert await store.get("pending") == b"1234567890"


@pytest.mark.asyncio
async def test_cancelled_upload_releases_lock_and_keeps_queue(store, monkeypatch):
    await store.put("cancel", b"bytes")
    entered = asyncio.Event()

    async def block(*args):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(Storage, "upload", block)
    task = asyncio.create_task(upload_one(store))
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert status()["pending"] == 1

    async def success(*args):
        pass

    monkeypatch.setattr(Storage, "upload", success)
    assert await upload_one(store)
    assert status()["pending"] == 0


@pytest.mark.asyncio
async def test_concurrent_writes_do_not_exceed_budget(store):
    get_settings().cache_max_bytes = 20
    tasks = [asyncio.create_task(store.put(str(i), bytes([i]) * 6)) for i in range(10)]
    try:

        async def admitted():
            while status()["pending"] < 3:
                await asyncio.sleep(0.01)

        await asyncio.wait_for(admitted(), 1)
        assert status()["used_bytes"] == 18
        assert sum(t.done() for t in tasks) == 3
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_read_cache_never_overwrites_pending_version(store):
    await store.put("key", b"new-local")
    await store.cache("key", b"old-remote")
    assert await store.get("key", refresh=True) == b"new-local"


def test_budget_cannot_be_configured_above_three_gb():
    from figprism.config import Settings
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(secret_key="x" * 40, cache_max_bytes=3_000_000_001)


@pytest.mark.asyncio
async def test_missing_blob_is_reported_without_starving_other_uploads(
    store, monkeypatch
):
    await store.put("broken", b"missing")
    store.local("broken").unlink()
    await store.put("healthy", b"kept")
    sent = []

    async def upload(self, key, data, content_type):
        sent.append(key)

    monkeypatch.setattr(Storage, "upload", upload)
    assert await upload_one(store)
    assert status()["retrying"] == 1
    assert await upload_one(store)
    assert sent == ["healthy"]


def test_storage_status_requires_admin_and_is_not_publicly_cached(client, store):
    from figprism.auth import create_user

    assert client.get("/api/admin/pipeline").status_code == 401
    create_user("viewer", "long-enough-password")
    client.post(
        "/api/auth/login",
        json={"username": "viewer", "password": "long-enough-password"},
    )
    assert client.get("/api/admin/pipeline").status_code == 403
    client.post("/api/auth/logout")
    create_user("operator", "long-enough-password", "admin")
    client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "long-enough-password"},
    )
    response = client.get("/api/admin/pipeline")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json()["storage"]["limit_bytes"] == 3_000_000_000


@pytest.mark.asyncio
async def test_hot_images_remain_until_pressure_and_exports_evict_first(store):
    get_settings().cache_max_bytes = 18
    for key, data in [
        ("paper.pdf", b"pppppp"),
        ("a_hd.webp", b"hhhhhh"),
        ("a_thumb.webp", b"tttttt"),
    ]:
        await store.put(key, data)
    with connect() as db:
        db.execute("UPDATE asset_transfers SET synced=1")
    assert status()["used_bytes"] == 18
    await store.get("paper.pdf")  # even a recent export ranks below images
    await store.put("b_hd.webp", b"bbbbbb")
    assert not store.local("paper.pdf").exists()
    assert store.local("a_hd.webp").exists()
    assert store.local("a_thumb.webp").exists()
    assert status()["used_bytes"] == 18


@pytest.mark.asyncio
async def test_same_key_misses_coalesce_and_hits_do_not_wait_for_write_lock(
    store, monkeypatch
):
    from figprism.concurrency import resource_lock

    calls = []

    async def handler(request):
        calls.append(1)
        await asyncio.sleep(0.02)
        return httpx.Response(200, content=b"shared-image")

    monkeypatch.setattr(
        Storage,
        "client",
        lambda self: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    data = await asyncio.gather(*(Storage().get("shared_hd.webp") for _ in range(8)))
    assert all(x == b"shared-image" for x in data)
    assert len(calls) == 1
    async with resource_lock("cache", "assets"):
        assert (
            await asyncio.wait_for(store.get("shared_hd.webp"), 0.2) == b"shared-image"
        )


def add_favorite(base="favorite", figure_id="fav"):
    with connect() as db:
        db.execute(
            "INSERT OR IGNORE INTO users(id,username,password_hash,role) VALUES(1,'cache-user','unused','user')"
        )
        db.execute(
            "INSERT OR IGNORE INTO papers(id,doc_uid,file_sha256,title,webdav_pdf_path) VALUES('fav-paper','fav-doc','fav-sha','Favorite paper','papers/fav/paper.pdf')"
        )
        db.execute(
            "INSERT INTO figures(id,paper_id,fig_label,page_number,bbox,width,height,aspect_ratio,palette,asset_base,version_hash) VALUES(?,'fav-paper','Fig. 1',1,'[]',100,100,1,'{}',?,'v1')",
            (figure_id, base),
        )
        db.execute(
            "INSERT OR IGNORE INTO collections(id,user_id,name) VALUES('favorites',1,'Favorites')"
        )
        db.execute(
            "INSERT INTO collection_items(id,collection_id,figure_id) VALUES(?,'favorites',?)",
            ("item-" + figure_id, figure_id),
        )


@pytest.mark.asyncio
async def test_reserved_favorite_pool_is_isolated_from_ordinary_pressure(store):
    get_settings().cache_max_bytes = 18
    get_settings().favorite_cache_bytes = 6
    add_favorite()
    await store.cache("favorite_hd.webp", b"ffffff")
    await store.cache("old_hd.webp", b"oooooooo")
    await store.cache("new_hd.webp", b"nnnn")
    assert status()["used_bytes"] == 18
    assert status()["favorite_used_bytes"] == 6
    assert status()["normal_used_bytes"] == 12
    await store.cache("another_hd.webp", b"aaaaaa")
    assert store.local("favorite_hd.webp").exists()
    assert not store.local("old_hd.webp").exists()
    assert status()["favorite_used_bytes"] <= 6
    assert status()["used_bytes"] <= 18


@pytest.mark.asyncio
async def test_favorite_pool_has_its_own_lru_and_cancel_returns_to_ordinary(store):
    get_settings().cache_max_bytes = 20
    get_settings().favorite_cache_bytes = 8
    add_favorite("first", "first")
    add_favorite("second", "second")
    await store.cache("ordinary_hd.webp", b"oooo")
    await store.cache("first_hd.webp", b"111111")
    await store.cache("second_hd.webp", b"222222")
    assert not store.local("first_hd.webp").exists()
    assert store.local("ordinary_hd.webp").exists()
    assert status()["favorite_used_bytes"] == 6
    with connect() as db:
        db.execute("DELETE FROM collection_items WHERE figure_id='second'")
    assert not store.favorite_key("second_hd.webp")
    assert status()["favorite_used_bytes"] == 0
    assert store.local("second_hd.webp").exists()


@pytest.mark.asyncio
async def test_favorite_warmer_and_invalid_filename_repair(store, monkeypatch):
    from figprism.maintenance import repair_invalid_names, warm_favorite_once

    get_settings().cache_max_bytes = 100
    get_settings().favorite_cache_bytes = 20
    add_favorite()

    async def handler(request):
        return httpx.Response(200, content=b"image")

    monkeypatch.setattr(
        Storage,
        "client",
        lambda self: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await warm_favorite_once(store)
    assert store.local("favorite_thumb.webp").exists()
    bad = "papers/fav/figures/test_sub_|_raw.pdf"
    await store.put(bad, b"%PDF sub")
    with connect() as db:
        db.execute(
            "UPDATE figures SET subitems=? WHERE id='fav'",
            (json.dumps([{"id": "|", "raw_path": bad}]),),
        )
    # The manifest is larger than this tiny test budget; validate the repair independently.
    from figprism import ingest

    async def backup(*args):
        pass

    monkeypatch.setattr(ingest, "backup", backup)
    repaired = await repair_invalid_names()
    assert len(repaired) == 1 and "|" not in repaired[0]["new"]
    assert await store.get(repaired[0]["new"]) == b"%PDF sub"
    with connect() as db:
        assert (
            db.execute("SELECT 1 FROM asset_transfers WHERE key=?", (bad,)).fetchone()
            is None
        )
        assert (
            json.loads(
                db.execute("SELECT subitems FROM figures WHERE id='fav'").fetchone()[0]
            )[0]["raw_path"]
            == repaired[0]["new"]
        )
