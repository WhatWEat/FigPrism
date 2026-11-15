"""Conservative, repeatable repairs for this application's durable asset queue."""

import hashlib
import json
import re
from datetime import UTC
from pathlib import PurePosixPath

from .concurrency import resource_lock
from .db import connect
from .storage import CacheFull, Storage
from .uploads import status


async def repair_invalid_names():
    repaired = []
    papers = set()
    with connect() as db:
        keys = [
            r[0] for r in db.execute("SELECT key FROM asset_transfers WHERE synced=0")
        ]
    for key in keys:
        path = PurePosixPath(key)
        if "_sub_" not in path.name or not re.search(r'[<>:"|?*]', path.name):
            continue
        clean = re.sub(r'[<>:"|?*]', "_", path.stem)
        new_key = str(
            path.with_name(
                clean + "_" + hashlib.sha256(key.encode()).hexdigest()[:8] + path.suffix
            )
        )
        async with resource_lock("asset-upload", key), resource_lock("cache", "assets"):
            with connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT digest FROM asset_transfers WHERE key=? AND synced=0",
                    (key,),
                ).fetchone()
                if (
                    not row
                    or db.execute(
                        "SELECT 1 FROM asset_transfers WHERE key=?", (new_key,)
                    ).fetchone()
                ):
                    continue
                changes = []
                for figure in db.execute(
                    "SELECT id,paper_id,subitems FROM figures WHERE subitems LIKE ?",
                    ("%" + key + "%",),
                ):
                    subs = json.loads(figure["subitems"])
                    changed = False
                    for sub in subs:
                        if sub.get("raw_path") == key:
                            sub["raw_path"] = new_key
                            changed = True
                    if changed:
                        changes.append((json.dumps(subs), figure["id"]))
                        papers.add(figure["paper_id"])
                if not changes:
                    continue
                db.executemany("UPDATE figures SET subitems=? WHERE id=?", changes)
                db.execute(
                    "UPDATE asset_transfers SET key=?,attempts=0,next_attempt=0,last_error='',updated_at=CURRENT_TIMESTAMP WHERE key=?",
                    (new_key, key),
                )
                repaired.append({"old": key, "new": new_key})
    from .ingest import backup

    for pid in papers:
        await backup(pid)
    return repaired


async def audit():
    repaired = await repair_invalid_names()
    storage = Storage()
    warnings = []
    async with resource_lock("cache", "assets"):
        try:
            storage.make_room()
        except CacheFull as exc:
            warnings.append(str(exc))
        with connect() as db:
            missing = [
                r["key"]
                for r in db.execute(
                    "SELECT key,digest FROM asset_transfers WHERE synced=0"
                )
                if not storage.blob(r["digest"]).is_file()
            ]
    if missing:
        warnings.append("待备份本地资产缺失，需要人工恢复：" + ", ".join(missing[:5]))
    return {"repaired_names": repaired, "warnings": warnings, "storage": status()}


async def warm_favorite_once(storage):
    """Fill unused reserved space without endlessly cycling an oversized library."""
    import asyncio
    from datetime import datetime

    _, limit = storage.budgets()
    if not limit:
        return False
    favorites = storage.favorite_paths()
    files = [(t, size) for t, size, path in storage.files() if path in favorites]
    used = sum(size for _, size in files)
    oldest = min((t for t, _ in files), default=0)
    with connect() as db:
        rows = db.execute(
            "SELECT f.asset_base,MAX(c.created_at) AS saved_at FROM figures f "
            "JOIN collection_items c ON c.figure_id=f.id GROUP BY f.id ORDER BY saved_at DESC LIMIT 200"
        ).fetchall()
    for row in rows:
        saved_at = (
            datetime.fromisoformat(row["saved_at"]).replace(tzinfo=UTC).timestamp()
        )
        for kind, estimate in [("thumb", 128 * 1024), ("hd", 2 * 1024**2)]:
            key = row["asset_base"] + "_" + kind + ".webp"
            if storage.local(key).exists():
                continue
            with connect() as db:
                asset = db.execute(
                    "SELECT size,synced FROM asset_transfers WHERE key=?", (key,)
                ).fetchone()
            if asset and not asset["synced"]:
                continue
            size = asset["size"] if asset else estimate
            if used + size > limit and saved_at <= oldest:
                continue
            try:
                async with asyncio.timeout(120):
                    await storage.get(key)
                return True
            except (OSError, RuntimeError, TimeoutError):
                return False
    return False
