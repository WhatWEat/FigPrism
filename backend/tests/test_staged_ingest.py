"""Concurrency assertions use barriers instead of relying on speed/timing guesses."""

import asyncio
import json
from pathlib import Path
import httpx
import pytest
from figprism import ingest as module
from figprism.db import connect
from figprism.config import get_settings
from figprism.concurrency import stage, snapshot
from figprism.extraction import Crop
from figprism.storage import Storage
from figprism.vision import Verdict


@pytest.fixture
def staged(monkeypatch):
    state = {"blobs": {}, "originals": 0, "active": {}, "peak": {}, "calls": []}

    async def cpu(operation, path, **kwargs):
        async with stage("cpu"):
            marker = Path(path).read_bytes().decode().split()[-1]
            state["calls"].append((marker, operation))
            if operation == "inspect":
                return {"title": marker, "layout_type": "single", "first_page_text": ""}
            if operation == "plan":
                return [
                    Crop(1, [0, 0, 400, 100], f"Fig. {n}", "caption", 0.9)
                    for n in range(1, 4)
                ]
            await asyncio.sleep(0.01)
            return {
                "hd": (marker + kwargs["crop"].label).encode(),
                "thumb": b"thumb",
                "raw": b"%PDF-raw",
                "width": 400,
                "height": 100,
                "aspect_ratio": 4,
                "blurhash": None,
                "fonts": [],
                "subitems": [],
                "palette": {"colors": [], "pairs": [], "neutrals": [], "buckets": []},
            }

    async def judge(*args):
        async with stage("vision"):
            await asyncio.sleep(0.01)
            return Verdict(
                archetype="Pipeline",
                crop_ok=True,
                confidence=0.9,
                sub_tags=[],
                reason="test",
            )

    async def put(self, key, data, content_type="application/octet-stream"):
        async with stage("upload"):
            if key.endswith("/paper.pdf"):
                state["originals"] += 1
            await asyncio.sleep(0.005)
            state["blobs"][key] = data

    monkeypatch.setattr(module, "cpu_call", cpu)
    monkeypatch.setattr(module, "judge", judge)
    monkeypatch.setattr(Storage, "put", put)
    return state


@pytest.mark.asyncio
async def test_other_paper_publishes_while_first_original_upload_is_blocked(
    client, staged, monkeypatch
):
    blocked = asyncio.Event()
    release = asyncio.Event()
    original = Storage.put

    async def put(self, key, data, content_type="application/octet-stream"):
        if key.endswith("/paper.pdf") and data.endswith(b"slow"):
            blocked.set()
            await release.wait()
        await original(self, key, data, content_type)

    monkeypatch.setattr(Storage, "put", put)
    slow = asyncio.create_task(module.ingest_pdf(b"%PDF slow", {"doc_uid": "slow"}))
    try:
        await asyncio.wait_for(blocked.wait(), 2)
        fast = await asyncio.wait_for(
            module.ingest_pdf(b"%PDF fast", {"doc_uid": "fast"}), 3
        )
        with connect() as db:
            assert (
                db.execute(
                    "SELECT COUNT(*) FROM figures WHERE paper_id=?", (fast,)
                ).fetchone()[0]
                == 3
            )
            assert (
                db.execute(
                    "SELECT COUNT(*) FROM figures f JOIN papers p ON p.id=f.paper_id WHERE p.doc_uid='slow'"
                ).fetchone()[0]
                == 0
            )
        assert ("slow", "render") in staged[
            "calls"
        ]  # compute overlapped the pending original transfer
    finally:
        release.set()
        await slow
    assert all(v["active"] == 0 for v in snapshot().values())


@pytest.mark.asyncio
async def test_same_pdf_concurrent_requests_share_one_import(client, staged):
    ids = await asyncio.gather(
        *(module.ingest_pdf(b"%PDF duplicate", {"doc_uid": "same"}) for _ in range(5))
    )
    assert len(set(ids)) == 1 and staged["originals"] == 1
    with connect() as db:
        assert db.execute("SELECT COUNT(*) FROM figures").fetchone()[0] == 3


@pytest.mark.asyncio
async def test_slow_figure_does_not_block_next_and_manifest_contains_all(
    client, staged, monkeypatch
):
    blocked = asyncio.Event()
    release = asyncio.Event()
    original = Storage.put

    async def put(self, key, data, content_type="application/octet-stream"):
        if key.endswith("_hd.webp") and data.endswith(b"Fig. 1"):
            blocked.set()
            await release.wait()
        await original(self, key, data, content_type)

    monkeypatch.setattr(Storage, "put", put)
    task = asyncio.create_task(module.ingest_pdf(b"%PDF composite"))
    try:
        await asyncio.wait_for(blocked.wait(), 2)

        async def second_published():
            while True:
                with connect() as db:
                    if db.execute(
                        "SELECT id FROM figures WHERE fig_label='Fig. 2'"
                    ).fetchone():
                        return
                await asyncio.sleep(0.01)

        await asyncio.wait_for(second_published(), 2)
    finally:
        release.set()
        pid = await task
    manifests = [
        json.loads(value)
        for key, value in staged["blobs"].items()
        if key.endswith("/metadata.json")
    ]
    assert len(manifests) == 1
    assert manifests[0]["paper"]["ingest_status"] == "completed"
    assert {f["fig_label"] for f in manifests[0]["figures"]} == {
        "Fig. 1",
        "Fig. 2",
        "Fig. 3",
    }


@pytest.mark.asyncio
async def test_partial_failure_retry_and_cancel_reconcile_status(
    client, staged, monkeypatch
):
    original = Storage.put

    async def broken(self, key, data, content_type="application/octet-stream"):
        if key.endswith("_hd.webp") and data.endswith(b"Fig. 2"):
            await asyncio.sleep(0.1)
            httpx.Response(
                403, request=httpx.Request("PUT", "https://example.com")
            ).raise_for_status()
        await original(self, key, data, content_type)

    monkeypatch.setattr(Storage, "put", broken)
    jid = module.new_job(None, "ingest")
    with pytest.raises(httpx.HTTPStatusError):
        await module.ingest_pdf(b"%PDF retry", job_id=jid)
    with connect() as db:
        assert db.execute("SELECT ingest_status FROM papers").fetchone()[0] == "failed"
        assert (
            db.execute("SELECT status FROM jobs WHERE id=?", (jid,)).fetchone()[0]
            == "failed"
        )
        retained = {r[0] for r in db.execute("SELECT id FROM figures")}
    assert retained
    monkeypatch.setattr(Storage, "put", original)
    await module.ingest_pdf(b"%PDF retry", job_id=jid)
    with connect() as db:
        rows = {r[0] for r in db.execute("SELECT id FROM figures")}
        assert len(rows) == 3 and retained <= rows
        assert (
            db.execute("SELECT ingest_status FROM papers").fetchone()[0] == "completed"
        )
    entered = asyncio.Event()

    async def blocked(self, *args, **kwargs):
        entered.set()
        await asyncio.sleep(10)

    monkeypatch.setattr(Storage, "put", blocked)
    task = asyncio.create_task(module.ingest_pdf(b"%PDF cancelled"))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with connect() as db:
        assert (
            db.execute(
                "SELECT ingest_status FROM papers WHERE title='cancelled'"
            ).fetchone()[0]
            == "failed"
        )
    assert all(v["active"] == 0 for v in snapshot().values())
