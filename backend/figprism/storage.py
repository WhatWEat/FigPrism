"""WebDAV is the durable asset store; local thumbnails and bounded HD cache are disposable."""
import asyncio
import os
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlparse
import httpx
from defusedxml import ElementTree
from .config import get_settings

class Storage:
    def __init__(self):
        self.settings = get_settings()
        self.config = self.settings.webdav

    def validate(self, key):
        p = PurePosixPath(key)
        if p.is_absolute() or '..' in p.parts or not p.parts or '\\' in key:
            raise ValueError('Invalid asset key')
        return str(p)

    def url(self, key=''):
        return self.config.url.rstrip('/') + '/' + quote(self.config.root.strip('/') + ('/' + self.validate(key) if key else ''), safe='/')

    def client(self):
        return httpx.AsyncClient(auth=(self.config.username, self.config.password.get_secret_value()), timeout=90, follow_redirects=False)

    def local(self, key):
        self.validate(key)
        layer = 'thumb_mirror' if key.endswith('_thumb.webp') else 'hd_lru_cache'
        return self.settings.data_dir / layer / key

    async def mkdirs(self, client, key):
        parts = (self.config.root.strip('/') + '/' + key).split('/')[:-1]
        for i in range(1, len(parts)+1):
            res = await client.request('MKCOL', self.config.url.rstrip('/') + '/' + quote('/'.join(parts[:i]), safe='/'))
            if res.status_code not in (201, 204, 405):
                res.raise_for_status()

    async def put(self, key, data, content_type='application/octet-stream'):
        self.validate(key)
        if not self.config.url:
            raise RuntimeError('WebDAV is not configured')
        async with self.client() as client:
            await self.mkdirs(client, key)
            res = await client.put(self.url(key), content=data, headers={'Content-Type': content_type})
            res.raise_for_status()
        await self.cache(key, data)

    async def cache(self, key, data):
        path = self.local(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + '.' + os.urandom(4).hex() + '.tmp')
        temp.write_bytes(data)
        temp.replace(path)
        if not key.endswith('_thumb.webp'):
            await asyncio.to_thread(self.evict)
        return path

    def evict(self):
        root = self.settings.data_dir / 'hd_lru_cache'
        files = []
        for p in root.rglob('*'):
            try:
                if p.is_file() and not p.name.endswith('.tmp'):
                    stat = p.stat()
                    files.append((stat.st_mtime, stat.st_size, p))
            except FileNotFoundError:
                pass
        total = sum(x[1] for x in files)
        for _, size, p in sorted(files):
            if total <= self.settings.cache_max_bytes:
                break
            p.unlink(missing_ok=True)
            total -= size

    async def get(self, key):
        path = self.local(key)
        try:
            data = path.read_bytes()
            path.touch()
            return data
        except FileNotFoundError:
            pass
        async with self.client() as client:
            res = await client.get(self.url(key))
            res.raise_for_status()
            data = res.content
        await self.cache(key, data)
        return data

    async def list(self, key=''):
        async with self.client() as client:
            res = await client.request('PROPFIND', self.url(key), headers={'Depth': '1'}, content=b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>')
            res.raise_for_status()
        base = unquote(urlparse(self.url()).path).rstrip('/') + '/'
        items = []
        for entry in ElementTree.fromstring(res.content).findall('{DAV:}response'):
            href = unquote(urlparse(entry.findtext('{DAV:}href', '')).path)
            if href.startswith(base):
                relative = href[len(base):].strip('/')
                if relative and relative != key.strip('/'):
                    items.append({'key': self.validate(relative), 'directory': entry.find('.//{DAV:}collection') is not None})
        return items
