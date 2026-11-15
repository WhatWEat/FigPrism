"""Main-conference CVPR discovery from the Computer Vision Foundation repository."""

import asyncio
import hashlib
import re
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from .concurrency import bounded_map
from .config import get_settings
from .domains import match_domains
from .network import fetch_metadata

BASE = "https://openaccess.thecvf.com"


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.meta = {}
        self.abstract = []
        self.anchor = None
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            self.meta.setdefault(attrs.get("name", ""), []).append(
                attrs.get("content", "")
            )
        if tag == "a":
            self.anchor = [attrs.get("href", ""), []]
        if tag == "div":
            if attrs.get("id") == "abstract":
                self.depth = 1
            elif self.depth:
                self.depth += 1

    def handle_data(self, data):
        if self.anchor is not None:
            self.anchor[1].append(data)
        if self.depth:
            self.abstract.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor is not None:
            href, parts = self.anchor
            self.links.append((href, " ".join("".join(parts).split())))
            self.anchor = None
        if tag == "div" and self.depth:
            self.depth -= 1


def parse_index(data, year):
    page = Page()
    page.feed(data.decode("utf-8") if isinstance(data, bytes) else data)
    found = {}
    for href, title in page.links:
        url = urljoin(BASE, href)
        p = urlparse(url)
        if (
            p.scheme == "https"
            and p.netloc == "openaccess.thecvf.com"
            and re.fullmatch(
                rf"/content/CVPR{year}/html/[^/]+_CVPR_{year}_paper\.html", p.path
            )
            and title
        ):
            found[url] = {"title": title, "url": url}
    return list(found.values())


def parse_paper(data, url, year):
    if not re.fullmatch(
        rf"https://openaccess\.thecvf\.com/content/CVPR{year}/html/[^/]+\.html", url
    ):
        raise ValueError("不是 CVF 官方 CVPR 主会论文页")
    page = Page()
    page.feed(data.decode("utf-8") if isinstance(data, bytes) else data)
    meta = page.meta
    title = (meta.get("citation_title") or [""])[0]
    date = (meta.get("citation_publication_date") or [""])[0]
    pdf = (meta.get("citation_pdf_url") or [""])[0]
    conference = (meta.get("citation_conference_title") or [""])[0]
    if (
        not title
        or not date.startswith(str(year))
        or "Computer Vision and Pattern Recognition" not in conference
        or re.search("findings|workshop", conference, re.IGNORECASE)
    ):
        raise ValueError("CVPR 会议元数据不完整或不是主会")
    if not re.fullmatch(
        rf"https://openaccess\.thecvf\.com/content/CVPR{year}/papers/[^/]+\.pdf", pdf
    ):
        raise ValueError("CVPR PDF 来源不合法")
    p = {
        "doc_uid": "cvf:" + urlparse(url).path,
        "title": title,
        "abstract": " ".join(" ".join(page.abstract).split()),
        "authors": meta.get("citation_author", []),
        "source_type": "cvf",
        "venue": "CVPR",
        "venue_year": year,
        "venue_tier": "poster",
        "source_urls": {"pdf": pdf, "cvf": url, "html": url},
        "venue_verified": True,
    }
    for href, _ in page.links:
        m = re.fullmatch(r"https://arxiv\.org/abs/(\d{4}\.\d{4,5})(?:v\d+)?", href)
        if m:
            p["arxiv_id"] = p["doc_uid"] = m[1]
            p["source_urls"]["arxiv"] = href
            break
    return p


async def cached_page(url, max_bytes):
    root = get_settings().data_dir / ".pipeline" / "discovery" / "cvf"
    path = root / (hashlib.sha256(url.encode()).hexdigest() + ".html")
    if path.exists() and time.time() - path.stat().st_mtime < 86400:
        return path.read_bytes()
    data = await fetch_metadata(url, max_bytes)
    root.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_bytes(data)
    temp.replace(path)
    return data


async def discover(configs, years, limit=5):
    output = []
    for year in years:
        index = parse_index(
            await cached_page(f"{BASE}/CVPR{year}?day=all", 24 * 1024**2), year
        )
        # CVF pages provide authoritative acceptance; inspect topic-bearing titles
        # instead of waiting on OpenReview/DBLP for thousands of unrelated papers.
        pool = [
            p
            for p in index
            if match_domains(p["title"], configs)
            or re.search(
                r"hallucinat|\bmemory\b|reasoning|post.training|test.time|data (selection|curation|pruning)",
                p["title"],
                re.IGNORECASE,
            )
        ]
        pool.sort(
            key=lambda p: (
                not bool(
                    re.search(
                        "hallucinat|vision.language|agent memory",
                        p["title"],
                        re.IGNORECASE,
                    )
                ),
                p["title"],
            )
        )
        counts = {d["slug"]: 0 for d in configs}

        async def inspect(item, year=year):
            try:
                async with asyncio.timeout(20):
                    p = parse_paper(
                        await cached_page(item["url"], 1024**2), item["url"], year
                    )
                text = p["title"] + " " + p["abstract"]
                # Treat ordinary plural spellings as the same domain vocabulary.
                text = re.sub(r"\b(VLM|LVLM|MLLM)s\b", r"\1", text)
                text = re.sub(
                    r"vision-language models\b",
                    "vision-language model",
                    text,
                    flags=re.IGNORECASE,
                )
                p["domains"] = match_domains(text, configs)
                return p if p["domains"] else None
            except (httpx.HTTPError, TimeoutError, ValueError, OSError):
                return None

        # Small waves bound page requests and fill domain quotas without scanning
        # every abstract before returning a useful first batch.
        for start in range(0, min(len(pool), 100), 8):
            for p in await bounded_map(
                inspect, pool[start : start + 8], get_settings().pipeline.metadata
            ):
                if p and any(counts[d] < limit for d in p["domains"]):
                    output.append(p)
                    for d in p["domains"]:
                        counts[d] += 1
            if all(n >= limit for n in counts.values()):
                break
    return output
