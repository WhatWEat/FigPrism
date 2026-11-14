"""Allowlisted public scholarly endpoints, bounded downloads and arXiv pacing."""

import asyncio
import time
from urllib.parse import urlparse, urljoin
import httpx
from .config import get_settings

HOSTS = {
    "arxiv.org",
    "export.arxiv.org",
    "huggingface.co",
    "openreview.net",
    "api2.openreview.net",
    "dblp.org",
    "api.openalex.org",
}
_last_arxiv = 0.0
_arxiv_lock = asyncio.Lock()


async def fetch(url, max_bytes=None):
    global _last_arxiv
    max_bytes = max_bytes or get_settings().max_pdf_bytes
    for _ in range(5):
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in HOSTS
            or parsed.username
            or parsed.port not in (None, 443)
        ):
            raise ValueError("仅支持 arXiv、Hugging Face 与 OpenReview 官方论文链接")
        if "arxiv.org" in parsed.hostname:
            async with _arxiv_lock:
                await asyncio.sleep(max(0, 3 - (time.monotonic() - _last_arxiv)))
                _last_arxiv = time.monotonic()
        async with httpx.AsyncClient(
            timeout=90,
            follow_redirects=False,
            headers={"User-Agent": "FigPrism/0.1 (research figure library)"},
        ) as client:
            async with client.stream("GET", url) as r:
                if r.is_redirect:
                    url = urljoin(url, r.headers["location"])
                    continue
                r.raise_for_status()
                if int(r.headers.get("content-length", 0)) > max_bytes:
                    raise ValueError("文件超过大小限制")
                chunks = []
                size = 0
                async for b in r.aiter_bytes():
                    size += len(b)
                    if size > max_bytes:
                        raise ValueError("文件超过大小限制")
                    chunks.append(b)
                return b"".join(chunks)
    raise ValueError("链接重定向次数过多")
