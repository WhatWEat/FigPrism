"""Durable cache counters and non-blocking WebDAV inventory snapshots."""
import asyncio
import fcntl
import logging
from fastapi import APIRouter, Depends
from .auth import require_admin
from .concurrency import bounded_map, lock_path, stage
from .db import connect
from .storage import Storage

router = APIRouter(prefix="/admin/storage")
log = logging.getLogger(__name__)


def record_cache_access(result):
    column = {"HIT": "hits", "MISS": "misses", "COALESCED": "coalesced"}.get(result)
    if column:
        try:
            with connect() as db:
                db.execute(f"UPDATE cache_metrics SET {column}={column}+1 WHERE id=1")
        except Exception:
            # Telemetry must not turn a successfully retrieved image into an error.
            log.exception("Could not persist cache access counter")


def insights():
    storage = Storage()
    with connect() as db:
        db.execute("BEGIN")
        counters = dict(db.execute("SELECT * FROM cache_metrics WHERE id=1").fetchone())
        scan = dict(db.execute("SELECT * FROM resource_scan WHERE id=1").fetchone())
        remote = {r["key"]: r["size"] for r in db.execute("SELECT key,size FROM remote_assets")}
        transfers = list(db.execute("SELECT key,digest FROM asset_transfers"))
    files = storage.files()
    physical = {path: size for _, size, path in files}
    local = {r["key"]: physical[storage.blob(r["digest"]) ] for r in transfers if storage.blob(r["digest"]) in physical}
    for _, size, path in files:
        for layer in ("thumb_mirror", "hd_lru_cache"):
            root = storage.settings.data_dir / layer
            if path.is_relative_to(root):
                local.setdefault(path.relative_to(root).as_posix(), size)
    requests = counters["hits"] + counters["misses"] + counters["coalesced"]
    counters.update(requests=requests, hit_rate=counters["hits"] / requests if requests else None)
    complete = scan["completed_at"] is not None
    return {"cache": counters, "scan": scan, "resources": {
        "remote_bytes": sum(remote.values()) if complete else None,
        "remote_files": len(remote) if complete else None,
        "local_bytes": sum(physical.values()),
        "local_only_bytes": sum(size for key, size in local.items() if key not in remote) if complete else None,
        "total_bytes": sum((remote | local).values()) if complete else None,
        "total_files": len(remote | local) if complete else None,
    }}


async def scan_remote(lock):
    try:
        inventory = {}
        seen = set()
        pending = [""]
        async with asyncio.timeout(1800), Storage() as storage:
            async def listing(key):
                # Share the existing WebDAV stage budget with upload workers.
                async with stage("upload"):
                    return await storage.list(key, include_sizes=True)
            while pending:
                batch, pending = pending[:4], pending[4:]
                results = await bounded_map(listing, batch, 4)
                seen.update(batch)
                for parent, children in zip(batch, results):
                    for item in children:
                        key = item["key"]
                        # Accept only direct descendants of the directory requested.
                        if key.rpartition("/")[0] != parent:
                            raise ValueError("WebDAV 返回目录范围外的文件")
                        if item["directory"]:
                            if key not in seen and key not in pending:
                                pending.append(key)
                        else:
                            inventory[key] = item["size"]
                if len(seen) + len(pending) > 20000 or len(inventory) > 500000:
                    raise ValueError("资源目录过大，请检查 WebDAV 根目录")
                with connect() as db:
                    db.execute("UPDATE resource_scan SET directories=?,files=? WHERE id=1", (len(seen), len(inventory)))
        # Publish only a complete snapshot. Failed scans leave the old inventory intact.
        with connect() as db:
            db.execute("DELETE FROM remote_assets")
            db.executemany("INSERT INTO remote_assets(key,size) VALUES(?,?)", inventory.items())
            db.execute("UPDATE resource_scan SET status='ready',completed_at=CURRENT_TIMESTAMP,error='' WHERE id=1")
    except BaseException as exc:
        with connect() as db:
            db.execute("UPDATE resource_scan SET status='error',error=? WHERE id=1",
                       ("盘点中断，请重试" if isinstance(exc, asyncio.CancelledError) else "WebDAV 盘点失败，请检查远端连接和文件属性后重试",))
        if isinstance(exc, asyncio.CancelledError):
            raise
        log.warning("WebDAV inventory failed: %s", type(exc).__name__)
    finally:
        lock.close()


def start_scan(force=False):
    lock = lock_path("inventory", "webdav").open("a+")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return False
    try:
        with connect() as db:
            state = db.execute("SELECT status FROM resource_scan WHERE id=1").fetchone()[0]
            if not force and state in ("ready", "error"):
                lock.close()
                return False
            # A leftover 'running' row with an unlocked kernel file is a stale scan.
            db.execute("UPDATE resource_scan SET status='running',started_at=CURRENT_TIMESTAMP,error='',directories=0,files=0 WHERE id=1")
        from .api import launch
        launch(scan_remote(lock))
        return True
    except BaseException:
        lock.close()
        raise


@router.get("/insights")
async def storage_insights(user=Depends(require_admin)):
    start_scan()
    return await asyncio.to_thread(insights)


@router.post("/scan")
async def refresh_scan(user=Depends(require_admin)):
    return {"started": start_scan(force=True)}
