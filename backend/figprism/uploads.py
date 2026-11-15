"""Restartable asset backup workers; kernel locks prevent duplicate key transfers."""

import asyncio
import fcntl
import hashlib
import logging
import time

import httpx

from .concurrency import lock_path, resource_lock
from .config import get_settings
from .db import connect
from .retry import error_message
from .storage import CacheFull, Storage

log = logging.getLogger(__name__)


def status():
    storage = Storage()
    with connect() as db:
        summary = dict(
            db.execute(
                "SELECT COUNT(*) AS pending,COALESCE(SUM(size),0) AS pending_bytes,"
                "COALESCE(SUM(attempts>0),0) AS retrying FROM asset_transfers WHERE synced=0"
            ).fetchone()
        )
        errors = [
            dict(r)
            for r in db.execute(
                "SELECT key,attempts,last_error,next_attempt FROM asset_transfers "
                "WHERE synced=0 AND last_error<>'' ORDER BY updated_at DESC LIMIT 5"
            )
        ]
    normal_limit, favorite_limit = storage.budgets()
    with connect() as db:
        pinned = {
            storage.blob(r[0])
            for r in db.execute(
                "SELECT DISTINCT digest FROM asset_transfers WHERE synced=0"
            )
        }
    favorites = storage.favorite_paths() - pinned
    files = storage.files()
    used = sum(size for _, size, _ in files)
    favorite_used = sum(size for _, size, path in files if path in favorites)
    summary.update(
        favorite_limit_bytes=favorite_limit,
        normal_limit_bytes=normal_limit,
        favorite_used_bytes=favorite_used,
        normal_used_bytes=used - favorite_used,
        used_bytes=used,
        limit_bytes=storage.settings.cache_max_bytes,
        errors=errors,
    )
    return summary


def manifest_ready(key):
    if not key.endswith("/metadata.json"):
        return True
    prefix = key.rsplit("/", 1)[0] + "/"
    with connect() as db:
        return not db.execute(
            "SELECT 1 FROM asset_transfers WHERE synced=0 AND key<>? "
            "AND substr(key,1,?)=? LIMIT 1",
            (key, len(prefix), prefix),
        ).fetchone()


async def upload_one(storage=None):
    storage = storage or Storage()
    with connect() as db:
        candidates = db.execute(
            "SELECT key FROM asset_transfers WHERE synced=0 AND next_attempt<=? "
            "ORDER BY key LIKE '%/metadata.json',updated_at,key LIMIT 200",
            (time.time(),),
        ).fetchall()
    for candidate in candidates:
        key = candidate["key"]
        file = lock_path("asset-upload", key).open("a+")
        try:
            try:
                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                continue
            if not manifest_ready(key):
                continue
            with connect() as db:
                row = db.execute(
                    "SELECT * FROM asset_transfers WHERE key=?", (key,)
                ).fetchone()
            if not row or row["synced"] or row["next_attempt"] > time.time():
                continue
            try:
                async with resource_lock("cache", "assets"):
                    # Snapshot bytes while eviction is excluded. Newer generations can
                    # queue immediately and are never marked synced by this transfer.
                    data = storage.blob(row["digest"]).read_bytes()
                if hashlib.sha256(data).hexdigest() != row["digest"]:
                    raise ValueError("待上传资产内容校验失败")
                await storage.upload(key, data, row["content_type"])
                with connect() as db:
                    updated = db.execute(
                        "UPDATE asset_transfers SET synced=1,attempts=0,next_attempt=0,"
                        "last_error='',updated_at=CURRENT_TIMESTAMP WHERE key=? AND digest=?",
                        (key, row["digest"]),
                    ).rowcount
                    paper = None
                    if updated and key.endswith("/paper.pdf"):
                        paper = db.execute(
                            "SELECT id FROM papers WHERE webdav_pdf_path=?", (key,)
                        ).fetchone()
                        db.execute(
                            "UPDATE papers SET pdf_uploaded=1 WHERE webdav_pdf_path=?",
                            (key,),
                        )
                async with resource_lock("cache", "assets"):
                    try:
                        storage.make_room()
                    except CacheFull:
                        pass
                if paper:
                    from .ingest import backup

                    await backup(paper["id"], storage)
                log.info("Backed up %s (%d bytes)", key, len(data))
            except (
                httpx.HTTPError,
                OSError,
                ValueError,
                RuntimeError,
                TimeoutError,
            ) as exc:
                attempts = row["attempts"] + 1
                message = error_message(exc)
                with connect() as db:
                    db.execute(
                        "UPDATE asset_transfers SET attempts=?,next_attempt=?,last_error=?,updated_at=CURRENT_TIMESTAMP "
                        "WHERE key=? AND digest=? AND synced=0",
                        (
                            attempts,
                            time.time() + min(30 * 2 ** min(attempts - 1, 7), 3600),
                            message,
                            key,
                            row["digest"],
                        ),
                    )
                log.warning("Backup deferred: %s: %s", key, message)
            return True
        finally:
            file.close()
    return False


async def worker():
    async with resource_lock("cache", "assets"):
        try:
            Storage().make_room()
        except CacheFull:
            # A lowered budget must not prevent the worker freeing pinned bytes.
            pass

    async def run_slot():
        async with Storage() as storage:
            while True:
                try:
                    worked = await upload_one(storage)
                except Exception:
                    log.exception("Backup worker iteration failed")
                    worked = False
                if not worked:
                    await asyncio.sleep(2)

    async def warm_favorites():
        from .maintenance import warm_favorite_once

        async with Storage() as storage:
            while True:
                try:
                    await warm_favorite_once(storage)
                except Exception:
                    log.exception("Favorite cache warming failed")
                await asyncio.sleep(5)

    async with asyncio.TaskGroup() as group:
        group.create_task(warm_favorites())
        for _ in range(get_settings().pipeline.upload):
            group.create_task(run_slot())
