import asyncio
import multiprocessing
import os
import fcntl
import pytest
from figprism.config import get_settings
from figprism.concurrency import stage, snapshot, lock_path, bounded_map, resource_lock
from figprism.retry import retry
import httpx


def occupy(path, ready, release):
    with open(path, "a+") as file:
        fcntl.flock(file.fileno(), fcntl.LOCK_EX)
        ready.set()
        release.wait(10)


@pytest.mark.asyncio
async def test_limits_are_shared_across_processes_and_release_after_cancel(client):
    get_settings().pipeline.upload = 1
    ctx = multiprocessing.get_context("spawn")
    ready = ctx.Event()
    release = ctx.Event()
    path = lock_path("slots", "upload:0")
    process = ctx.Process(target=occupy, args=(str(path), ready, release))
    process.start()
    assert await asyncio.to_thread(ready.wait, 5)
    entered = asyncio.Event()

    async def task():
        async with stage("upload"):
            entered.set()

    waiting = asyncio.create_task(task())
    try:
        await asyncio.sleep(0.12)
        assert not entered.is_set()
        assert snapshot()["upload"]["active"] == 1
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        release.set()
        await asyncio.to_thread(process.join, 5)
        async with stage("upload"):
            assert snapshot()["upload"]["active"] == 1
        assert snapshot()["upload"]["active"] == 0
    finally:
        release.set()
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join()


@pytest.mark.asyncio
async def test_bounded_workers_and_independent_stages(client):
    get_settings().pipeline.vision = 2
    active = 0
    peak = 0

    async def work(i):
        nonlocal active, peak
        async with stage("vision"):
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.02)
            active -= 1
            return i * 2

    async with stage("upload"):
        result = await bounded_map(work, range(12), 4)
    assert result == [i * 2 for i in range(12)]
    assert peak == 2


@pytest.mark.asyncio
async def test_group_failure_drains_siblings_and_tokens(client):
    stopped = asyncio.Event()
    started = asyncio.Event()

    async def work(i):
        async with stage("figures"):
            if i == 0:
                started.set()
                try:
                    await asyncio.sleep(10)
                finally:
                    stopped.set()
            else:
                await started.wait()
                raise ValueError("bad input")

    with pytest.raises(ExceptionGroup):
        await bounded_map(work, [0, 1], 2)
    assert stopped.is_set()
    assert snapshot()["figures"]["active"] == 0


@pytest.mark.asyncio
async def test_retry_transient_http_but_not_bad_credentials(client, monkeypatch):
    calls = 0
    sleeps = []

    async def sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr("figprism.retry.asyncio.sleep", sleep)

    async def operation():
        nonlocal calls
        calls += 1
        if calls < 3:
            r = httpx.Response(
                503,
                headers={"Retry-After": "2"},
                request=httpx.Request("PUT", "https://example.com"),
            )
            r.raise_for_status()
        return "ok"

    assert await retry(operation) == "ok"
    assert calls == 3 and sleeps == [2, 2]
    calls = 0

    async def forbidden():
        nonlocal calls
        calls += 1
        httpx.Response(
            403, request=httpx.Request("PUT", "https://example.com")
        ).raise_for_status()

    with pytest.raises(httpx.HTTPStatusError):
        await retry(forbidden)
    assert calls == 1


def test_job_admission_is_atomic_and_batch_children_do_not_use_user_quota(client):
    from concurrent.futures import ThreadPoolExecutor
    from figprism.auth import create_user
    from figprism.ingest import new_job, JobQueueFull

    uid = create_user("parallel", "long-enough-password")

    def submit(i):
        try:
            return new_job(uid, "ingest")
        except JobQueueFull:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(submit, range(8)))
    assert sum(x is not None for x in ids) == 3
    assert new_job(uid, "ingest", {"batch_id": "parent"})


@pytest.mark.asyncio
async def test_cancelled_native_worker_is_reaped_before_releasing_cpu_slot(
    client, monkeypatch, tmp_path
):
    import sys
    from figprism.processing import cpu_call

    real = asyncio.create_subprocess_exec
    children = []
    started = asyncio.Event()

    async def spawn(*args, **kwargs):
        process = await real(
            sys.executable, "-c", "import time;time.sleep(30)", **kwargs
        )
        children.append(process)
        started.set()
        return process

    monkeypatch.setattr("figprism.processing.asyncio.create_subprocess_exec", spawn)
    task = asyncio.create_task(cpu_call("inspect", tmp_path / "paper.pdf"))
    await started.wait()
    assert snapshot()["cpu"]["active"] == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert children[0].returncode is not None
    assert snapshot()["cpu"]["active"] == 0
    assert not list((get_settings().data_dir / ".pipeline" / "cpu").iterdir())


def test_rolling_startup_preserves_legacy_batches_but_recovers_abandoned_jobs(client):
    from figprism.auth import create_user
    from figprism.ingest import new_job
    from figprism.db import connect, init_db

    uid = create_user("rolling", "long-enough-password")
    parent = new_job(uid, "backfill")
    child = new_job(uid, "ingest", {"batch_id": parent})
    abandoned = new_job(uid, "ingest")
    init_db(recover_jobs=True, preserve_job_ids=[parent])
    with connect() as db:
        statuses = {
            r["id"]: r["status"] for r in db.execute("SELECT id,status FROM jobs")
        }
    assert statuses[parent] == "queued" and statuses[child] == "queued"
    assert statuses[abandoned] == "failed"
