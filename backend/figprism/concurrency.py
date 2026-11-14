"""Cross-process stage budgets shared by API, CLI and timers through the data volume.

Kernel flock ownership is released even after crashes. Only same-resource writes
serialize; stage slots never hold a SQLite transaction across network I/O.
"""

import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import os
import random
import time
import fcntl
from .config import get_settings

STAGES = ("metadata", "download", "papers", "cpu", "vision", "upload", "figures")


def lock_path(namespace, key):
    root = get_settings().data_dir / ".pipeline" / namespace
    root.mkdir(parents=True, exist_ok=True)
    return root / (hashlib.sha256(str(key).encode()).hexdigest() + ".lock")


@asynccontextmanager
async def resource_lock(namespace, key, shared=False):
    file = lock_path(namespace, key).open("a+")
    try:
        while True:
            try:
                fcntl.flock(
                    file.fileno(),
                    (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB,
                )
                break
            except BlockingIOError:
                await asyncio.sleep(0.03)
        yield file
    finally:
        file.close()


@asynccontextmanager
async def stage(name):
    if name not in STAGES:
        raise ValueError("Unknown pipeline stage")
    capacity = getattr(get_settings().pipeline, name)
    held = None
    try:
        while held is None:
            for index in range(capacity):
                file = lock_path("slots", f"{name}:{index}").open("a+")
                try:
                    fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    file.close()
                    continue
                file.seek(0)
                file.truncate()
                json.dump({"pid": os.getpid(), "started_at": time.time()}, file)
                file.flush()
                held = file
                break
            if held is None:
                await asyncio.sleep(0.03 + random.random() * 0.02)
        yield
    finally:
        if held is not None:
            held.close()


async def pace(name, interval):
    """Reserve request start times across processes, including container/host CLIs."""
    async with resource_lock("rates", name) as file:
        file.seek(0)
        try:
            previous = float(file.read())
        except ValueError:
            previous = 0
        await asyncio.sleep(max(0, previous + interval - time.monotonic()))
        file.seek(0)
        file.truncate()
        file.write(str(time.monotonic()))
        file.flush()


async def bounded_map(function, items, concurrency):
    """Only N workers/tasks, ordered results, cancellation drains all running work."""
    items = list(items)
    output = [None] * len(items)
    iterator = iter(enumerate(items))

    async def worker():
        for index, item in iterator:
            output[index] = await function(item)

    async with asyncio.TaskGroup() as group:
        for _ in range(min(concurrency, len(items))):
            group.create_task(worker())
    return output


def snapshot():
    result = {}
    for name in STAGES:
        capacity = getattr(get_settings().pipeline, name)
        busy = 0
        for index in range(capacity):
            with lock_path("slots", f"{name}:{index}").open("a+") as file:
                try:
                    fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    busy += 1
        result[name] = {"limit": capacity, "active": busy}
    return result
