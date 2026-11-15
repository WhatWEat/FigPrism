"""Durable local asset staging, bounded read cache, and asynchronous WebDAV backup."""

import asyncio
import hashlib
import os
from contextlib import asynccontextmanager
from pathlib import PurePosixPath
from urllib.parse import quote, unquote, urlparse

import httpx
from defusedxml import ElementTree

from .concurrency import resource_lock, stage
from .config import get_settings
from .db import connect
from .retry import retry


class CacheFull(Exception):
    """All remaining cache space is occupied by assets awaiting backup."""


class Storage:
    def __init__(self):
        self.settings = get_settings()
        self.config = self.settings.webdav
        self._directories = set()
        self._client = None
        self._mkdir_lock = asyncio.Lock()
        self.cache_status = "MISS"

    async def __aenter__(self):
        self._client = self.client()
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()
        self._client = None

    @asynccontextmanager
    async def connection(self):
        if self._client is not None:
            yield self._client
        else:
            async with self.client() as client:
                yield client

    def validate(self, key):
        p = PurePosixPath(key)
        if p.is_absolute() or ".." in p.parts or not p.parts or "\\" in key:
            raise ValueError("Invalid asset key")
        return str(p)

    def url(self, key=""):
        return (
            self.config.url.rstrip("/")
            + "/"
            + quote(
                self.config.root.strip("/") + ("/" + self.validate(key) if key else ""),
                safe="/",
            )
        )

    def client(self):
        return httpx.AsyncClient(
            auth=(self.config.username, self.config.password.get_secret_value()),
            timeout=httpx.Timeout(180, connect=20, write=180, pool=30),
            follow_redirects=False,
        )

    def legacy(self, key):
        self.validate(key)
        layer = "thumb_mirror" if key.endswith("_thumb.webp") else "hd_lru_cache"
        return self.settings.data_dir / layer / key

    def blob(self, digest):
        return self.settings.data_dir / "asset_cache" / digest

    def local(self, key):
        self.validate(key)
        with connect() as db:
            row = db.execute(
                "SELECT digest FROM asset_transfers WHERE key=?", (key,)
            ).fetchone()
        return self.blob(row["digest"]) if row else self.legacy(key)

    def files(self):
        files = []
        for layer in ("asset_cache", "thumb_mirror", "hd_lru_cache"):
            for path in (self.settings.data_dir / layer).rglob("*"):
                try:
                    if path.is_file():
                        stat = path.stat()
                        files.append((stat.st_mtime, stat.st_size, path))
                except FileNotFoundError:
                    pass
        return files

    def budgets(self):
        favorite = min(
            self.settings.favorite_cache_bytes, self.settings.cache_max_bytes
        )
        return self.settings.cache_max_bytes - favorite, favorite

    def favorite_paths(self):
        paths = set()
        with connect() as db:
            for row in db.execute(
                "SELECT DISTINCT f.asset_base FROM figures f JOIN collection_items c ON c.figure_id=f.id"
            ):
                for kind in ("thumb", "hd"):
                    key = row["asset_base"] + "_" + kind + ".webp"
                    asset = db.execute(
                        "SELECT digest,synced FROM asset_transfers WHERE key=?", (key,)
                    ).fetchone()
                    if asset:
                        if asset["synced"]:
                            paths.add(self.blob(asset["digest"]))
                    else:
                        paths.add(self.legacy(key))
        return paths

    def favorite_key(self, key):
        with connect() as db:
            return bool(
                db.execute(
                    "SELECT 1 FROM collection_items c JOIN figures f ON f.id=c.figure_id "
                    "WHERE ? IN (f.asset_base||'_hd.webp',f.asset_base||'_thumb.webp') LIMIT 1",
                    (key,),
                ).fetchone()
            )

    def make_room(self, extra=0, protect=(), favorite=False):
        # Caller holds the shared cross-process cache mutation lock.
        normal_limit, favorite_limit = self.budgets()
        with connect() as db:
            pending = {
                self.blob(r[0])
                for r in db.execute(
                    "SELECT DISTINCT digest FROM asset_transfers WHERE synced=0"
                )
            }
        favorites = self.favorite_paths() - pending if favorite_limit else set()
        favorite = favorite and bool(favorite_limit)
        if favorite:
            favorites.update(protect)
        pinned = pending | set(protect)
        files = self.files()
        favorite_total = sum(size for _, size, path in files if path in favorites) + (
            extra if favorite else 0
        )
        normal_total = sum(size for _, size, path in files if path not in favorites) + (
            0 if favorite else extra
        )
        priorities = {}
        with connect() as db:
            for row in db.execute("SELECT digest,key FROM asset_transfers"):
                rank = (
                    2
                    if row["key"].endswith("_thumb.webp")
                    else 1
                    if row["key"].endswith("_hd.webp")
                    else 0
                )
                path = self.blob(row["digest"])
                priorities[path] = max(priorities.get(path, 0), rank)

        def eviction_order(item):
            touched, _, path = item
            if path in favorites:
                return 0, touched  # strict LRU inside the reserved favorite pool
            rank = priorities.get(
                path,
                2
                if path.name.endswith("_thumb.webp")
                else 1
                if path.name.endswith("_hd.webp")
                else 0,
            )
            return rank, touched

        for _, size, path in sorted(files, key=eviction_order):
            if normal_total <= normal_limit and favorite_total <= favorite_limit:
                break
            if path in pinned:
                continue
            if path in favorites:
                if favorite_total <= favorite_limit:
                    continue
                favorite_total -= size
            else:
                if normal_total <= normal_limit:
                    continue
                normal_total -= size
            path.unlink(missing_ok=True)
        if normal_total > normal_limit or favorite_total > favorite_limit:
            raise CacheFull("本地缓存已满，正在等待远端备份腾出空间")

    @staticmethod
    def sync_directory(path):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    async def store_local(self, key, data, content_type, pending):
        self.validate(key)
        if len(data) > self.settings.cache_max_bytes:
            raise ValueError("单个资产超过本地缓存容量限制")
        digest = hashlib.sha256(data).hexdigest()
        path = self.blob(digest)
        async with resource_lock("cache", "assets"):
            with connect() as db:
                current = db.execute(
                    "SELECT * FROM asset_transfers WHERE key=?", (key,)
                ).fetchone()
            # A remote cache fill must never replace a newer, locally staged version.
            if not pending and current and not current["synced"]:
                return self.blob(current["digest"])
            self.make_room(
                0 if path.exists() else len(data),
                protect=(path,),
                favorite=not pending and self.favorite_key(key),
            )
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                self.sync_directory(path.parent.parent)
                temp = path.with_name(digest + "." + os.urandom(4).hex() + ".tmp")
                try:
                    with temp.open("xb") as file:
                        file.write(data)
                        file.flush()
                        os.fsync(file.fileno())
                    temp.replace(path)
                    self.sync_directory(path.parent)
                finally:
                    temp.unlink(missing_ok=True)
            else:
                os.utime(path, None)
            # Bytes are durable before queue commit; crash leftovers can be reclaimed.
            with connect() as db:
                db.execute(
                    "INSERT INTO asset_transfers(key,digest,size,content_type,synced) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(key) DO UPDATE SET digest=excluded.digest,size=excluded.size,"
                    "content_type=excluded.content_type,synced=excluded.synced,attempts=0,"
                    "next_attempt=0,last_error='',updated_at=CURRENT_TIMESTAMP "
                    "WHERE asset_transfers.digest<>excluded.digest",
                    (key, digest, len(data), content_type, int(not pending)),
                )
            return path

    async def mkdirs(self, client, key):
        parts = (self.config.root.strip("/") + "/" + key).split("/")[:-1]
        for i in range(1, len(parts) + 1):
            directory = "/".join(parts[:i])
            if directory in self._directories:
                continue
            res = await client.request(
                "MKCOL", self.config.url.rstrip("/") + "/" + quote(directory, safe="/")
            )
            if res.status_code not in (201, 204, 405):
                res.raise_for_status()
            self._directories.add(directory)

    async def put(self, key, data, content_type="application/octet-stream"):
        if not self.config.url:
            raise RuntimeError("WebDAV is not configured")
        # Backpressure retains unbacked assets; no network or paper slot is needed
        # by the independent uploader to free space.
        while True:
            try:
                return await self.store_local(key, data, content_type, pending=True)
            except CacheFull:
                await asyncio.sleep(0.5)

    async def upload(self, key, data, content_type="application/octet-stream"):
        """Only the background worker calls the remote write path."""
        self.validate(key)

        async def transfer():
            async with stage("upload"), self.connection() as client:
                async with self._mkdir_lock:
                    await self.mkdirs(client, key)

                async def chunks():
                    for offset in range(0, len(data), 32 * 1024):
                        yield data[offset : offset + 32 * 1024]

                async with asyncio.timeout(1800):
                    response = await client.put(
                        self.url(key),
                        content=chunks(),
                        headers={
                            "Content-Type": content_type,
                            "Content-Length": str(len(data)),
                        },
                    )
                    response.raise_for_status()

        await retry(transfer)

    async def cache(self, key, data):
        return await self.store_local(
            key, data, "application/octet-stream", pending=False
        )

    def read_local(self, key, refresh=False):
        with connect() as db:
            row = db.execute(
                "SELECT * FROM asset_transfers WHERE key=?", (key,)
            ).fetchone()
        path = self.blob(row["digest"]) if row else self.legacy(key)
        if refresh and not (row and not row["synced"]):
            return None
        try:
            # An open file descriptor remains valid if eviction unlinks the file.
            # Cache hits never wait for the global write/eviction lock.
            with path.open("rb") as file:
                os.utime(file.fileno(), None)
                return file.read()
        except FileNotFoundError:
            if row and not row["synced"]:
                raise RuntimeError("待备份资产的本地文件缺失，请检查磁盘")
            return None

    async def get(self, key, refresh=False):
        self.validate(key)
        data = self.read_local(key, refresh)
        if data is not None:
            self.cache_status = "HIT"
            return data
        # One remote fetch per key across requests and processes. Followers use
        # the first completed cache fill rather than downloading the same HD again.
        async with resource_lock("asset-download", key):
            if not refresh:
                data = self.read_local(key)
                if data is not None:
                    self.cache_status = "COALESCED"
                    return data
            async with self.connection() as client:
                res = await client.get(self.url(key))
                res.raise_for_status()
                data = res.content
            self.cache_status = "MISS"
            try:
                await self.cache(key, data)
            except (CacheFull, ValueError):
                pass
            return data

    async def list(self, key=""):
        async with self.connection() as client:
            res = await client.request(
                "PROPFIND",
                self.url(key),
                headers={"Depth": "1"},
                content=b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>',
            )
            res.raise_for_status()
        base = unquote(urlparse(self.url()).path).rstrip("/") + "/"
        items = []
        for entry in ElementTree.fromstring(res.content).findall("{DAV:}response"):
            href = unquote(urlparse(entry.findtext("{DAV:}href", "")).path)
            if href.startswith(base):
                relative = href[len(base) :].strip("/")
                if relative and relative != key.strip("/"):
                    items.append(
                        {
                            "key": self.validate(relative),
                            "directory": entry.find(".//{DAV:}collection") is not None,
                        }
                    )
        return items
