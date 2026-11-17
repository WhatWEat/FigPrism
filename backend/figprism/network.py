"""Allowlisted scholarly downloads with separate budgets and shared arXiv pacing."""

from urllib.parse import urlparse, urljoin
import httpx
from .config import get_settings
from .concurrency import stage, pace
from .retry import retry

HOSTS = {
    "arxiv.org",
    "export.arxiv.org",
    "huggingface.co",
    "openreview.net",
    "api2.openreview.net",
    "dblp.org",
    "api.openalex.org",
    "openaccess.thecvf.com",
    "aclanthology.org",
}


async def fetch(url, max_bytes=None, budget="download"):
    max_bytes = max_bytes or get_settings().max_pdf_bytes
    for _ in range(5):
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in HOSTS
            or parsed.username
            or parsed.port not in (None, 443)
        ):
            raise ValueError("仅支持白名单内的学术论文官方链接")

        async def request():
            async with stage(budget):
                if parsed.hostname in ("arxiv.org", "export.arxiv.org"):
                    await pace("arxiv", get_settings().pipeline.arxiv_interval)
                async with httpx.AsyncClient(
                    timeout=90,
                    follow_redirects=False,
                    headers={"User-Agent": "FigPrism/0.2 (research figure library)"},
                ) as client:
                    async with client.stream("GET", url) as response:
                        if response.is_redirect:
                            return None, urljoin(url, response.headers["location"])
                        response.raise_for_status()
                        if int(response.headers.get("content-length", 0)) > max_bytes:
                            raise ValueError("文件超过大小限制")
                        chunks = []
                        size = 0
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > max_bytes:
                                raise ValueError("文件超过大小限制")
                            chunks.append(chunk)
                        return b"".join(chunks), None

        data, redirect = await retry(request)
        if redirect:
            url = redirect
        else:
            return data
    raise ValueError("链接重定向次数过多")


async def fetch_metadata(url, max_bytes=3 * 1024**2):
    return await fetch(url, max_bytes, budget="metadata")
