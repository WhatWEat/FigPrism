"""Anonymous scholarly discovery and conservative venue verification."""

import asyncio
import hashlib
import os
import time
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from defusedxml import ElementTree as ET
from .network import fetch, fetch_metadata
from .concurrency import bounded_map, resource_lock
from .domains import all_domains, match_domains
from .config import get_settings
from .db import connect
from .ingest import ingest_pdf, update_job, resolve

VENUES = ("ICML", "ICLR", "CVPR", "ACL", "EMNLP", "NeurIPS")
NS = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}


def normalized(title):
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", title)).casefold()


def venue_from_text(text, allow_workshop=False):
    if re.search(
        r"submitted to|under review|under submission|preprint|rejected|withdrawn",
        text,
        re.I,
    ):
        return None
    if not allow_workshop and re.search(
        r"workshop|findings|demo(?:nstration)?|student research", text, re.I
    ):
        return None
    m = re.search(
        r"\b(ICML|ICLR|CVPR|ACL|EMNLP|NeurIPS|NIPS)\b[^\d]{0,15}(20\d{2})", text, re.I
    )
    if not m:
        m2 = re.search(
            r"(20\d{2})[^\w]{0,10}\b(ICML|ICLR|CVPR|ACL|EMNLP|NeurIPS)\b", text, re.I
        )
        if not m2:
            return None
        venue, year = m2[2], m2[1]
    else:
        venue, year = m[1], m[2]
    venue = "NeurIPS" if venue.lower() in ("nips", "neurips") else venue.upper()
    tier = (
        "oral"
        if re.search(r"\boral\b", text, re.I)
        else "spotlight"
        if re.search(r"\bspotlight\b", text, re.I)
        else "poster"
    )
    return {"venue": venue, "venue_year": int(year), "venue_tier": tier}


def parse_arxiv(data):
    root = ET.fromstring(data)
    papers = []
    for e in root.findall("a:entry", NS):
        aid = e.findtext("a:id", "", NS).split("/abs/")[-1]
        if not re.fullmatch(r"\d{4}\.\d{4,5}(?:v\d+)?", aid):
            continue
        title = " ".join(e.findtext("a:title", "", NS).split())
        paper = {
            "arxiv_id": aid,
            "doc_uid": aid,
            "title": title,
            "abstract": e.findtext("a:summary", "", NS).strip(),
            "authors": [
                a.findtext("a:name", "", NS) for a in e.findall("a:author", NS)
            ],
            "source_type": "arxiv",
            "published": e.findtext("a:published", "", NS),
            "source_urls": {
                "pdf": f"https://arxiv.org/pdf/{aid}",
                "html": f"https://arxiv.org/html/{aid}",
            },
        }
        v = venue_from_text(
            e.findtext("x:comment", "", NS) + " " + e.findtext("x:journal_ref", "", NS)
        )
        if v:
            paper.update(v)
        papers.append(paper)
    return papers


async def arxiv_search(domain, days=3, years=None, max_results=80):
    phrases = domain.get("phrases", [])[:10]
    terms = " OR ".join('all:"' + p.replace('"', "") + '"' for p in phrases)
    cats = " OR ".join(
        "cat:" + c for c in domain.get("arxiv_cats", ["cs.AI", "cs.CL", "cs.LG"])
    )
    if years:
        start = f"{min(years) - 1}01010000"
        end = f"{max(years)}12312359"
    else:
        start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
            "%Y%m%d0000"
        )
        end = datetime.now(timezone.utc).strftime("%Y%m%d2359")
    query = f"({terms}) AND ({cats}) AND submittedDate:[{start} TO {end}]"
    return parse_arxiv(
        await fetch_metadata(
            "https://export.arxiv.org/api/query?"
            + urlencode(
                {
                    "search_query": query,
                    "max_results": max_results,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                }
            ),
            6 * 1024**2,
        )
    )


async def hf_daily(days=3):
    papers = {}

    async def day(n):
        date = (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%d")
        data = json.loads(
            await fetch_metadata(
                "https://huggingface.co/api/daily_papers?"
                + urlencode({"date": date, "limit": 50}),
                5 * 1024**2,
            )
        )
        for entry in data:
            p = entry.get("paper", entry)
            aid = p.get("id", "")
            if not re.fullmatch(r"\d{4}\.\d{4,5}", aid):
                continue
            previous = papers.get(aid, {})
            papers[aid] = {
                "arxiv_id": aid,
                "doc_uid": aid,
                "title": p.get("title", ""),
                "abstract": p.get("summary", ""),
                "authors": [a.get("name", "") for a in p.get("authors", [])],
                "hf_upvotes": max(
                    previous.get("hf_upvotes", 0),
                    p.get("upvotes", entry.get("upvotes", 0)),
                ),
                "source_type": "hf",
                "keywords": " ".join(p.get("ai_keywords", [])),
                "source_urls": {
                    "pdf": f"https://arxiv.org/pdf/{aid}",
                    "html": f"https://arxiv.org/html/{aid}",
                    "hf": f"https://huggingface.co/papers/{aid}",
                },
            }

    await bounded_map(day, range(min(days, 14)), get_settings().pipeline.metadata)
    return list(papers.values())


def content_value(content, key, default=""):
    v = content.get(key, default)
    return v.get("value", default) if isinstance(v, dict) else v


async def verify_openreview(title):
    data = json.loads(
        await fetch_metadata(
            "https://api2.openreview.net/notes?"
            + urlencode({"content.title": title, "limit": 10}),
            3 * 1024**2,
        )
    )
    for note in data.get("notes", []):
        c = note.get("content", {})
        if normalized(content_value(c, "title")) != normalized(title):
            continue
        vid = content_value(c, "venueid")
        venue = content_value(c, "venue")
        # Accepted venueid is the conference root, not /Submission, /Rejected or a workshop.
        m = re.fullmatch(r"(ICLR\.cc|ICML\.cc|NeurIPS\.cc)/(20\d{2})/Conference", vid)
        if not m:
            continue
        v = venue_from_text(venue) or {
            "venue": m[1].split(".")[0],
            "venue_year": int(m[2]),
            "venue_tier": "poster",
        }
        v["openreview"] = "https://openreview.net/forum?id=" + note["id"]
        return v
    return None


async def verify_dblp(title):
    data = json.loads(
        await fetch_metadata(
            "https://dblp.org/search/publ/api?"
            + urlencode({"q": title, "format": "json", "h": 5}),
            3 * 1024**2,
        )
    )
    hits = data.get("result", {}).get("hits", {}).get("hit", [])
    if isinstance(hits, dict):
        hits = [hits]
    for hit in hits:
        info = hit["info"]
        if normalized(info.get("title", "")) != normalized(title):
            continue
        key = info.get("key", "")
        if not re.match(r"conf/(?:icml|iclr|cvpr|acl|emnlp|nips)/", key):
            continue
        venue = info.get("venue", "")
        if isinstance(venue, list):
            venue = " ".join(venue)
        v = venue_from_text(venue + " " + str(info.get("year", "")))
        if v:
            return v
    return None


async def verified(paper):
    if paper.get("venue") in VENUES:
        return paper
    for verifier in (verify_openreview, verify_dblp):
        try:
            async with asyncio.timeout(10):
                v = await verifier(paper["title"])
        except Exception:
            continue
        if v:
            or_url = v.pop("openreview", None)
            paper.update(v)
            if or_url:
                paper.setdefault("source_urls", {})["openreview"] = or_url
            return paper
    return (
        paper if paper.get("hf_upvotes", 0) >= get_settings().hf_min_upvotes else None
    )


async def openalex_growth(title):
    try:
        data = json.loads(
            await fetch_metadata(
                "https://api.openalex.org/works?"
                + urlencode({"search": title, "per-page": 3}),
                2 * 1024**2,
            )
        )
        for w in data.get("results", []):
            if normalized(w["title"]) == normalized(title):
                year = datetime.now(timezone.utc).year
                return sum(
                    c["cited_by_count"]
                    for c in w.get("counts_by_year", [])
                    if c["year"] >= year - 1
                )
    except Exception:
        pass
    return 0


VERIFICATION_TIMEOUT = 25


async def cached_verification(paper):
    root = get_settings().data_dir / ".pipeline" / "discovery" / "verification"
    key = hashlib.sha256(normalized(paper["title"]).encode()).hexdigest()
    path = root / (key + ".json")
    if path.exists():
        cached = json.loads(path.read_text())
        ttl = 86400 if cached["paper"] else 3600
        if time.time() - cached["at"] < ttl:
            if not cached["paper"]:
                return None
            result = dict(paper)
            for field in ("venue", "venue_year", "venue_tier"):
                if field in cached["paper"]:
                    result[field] = cached["paper"][field]
            result["source_urls"] = {
                **paper.get("source_urls", {}),
                **cached["paper"].get("source_urls", {}),
            }
            return result
    async with asyncio.timeout(VERIFICATION_TIMEOUT):
        result = await verified(paper)
    root.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix("." + os.urandom(4).hex() + ".tmp")
    temp.write_text(
        json.dumps({"at": time.time(), "paper": result}, ensure_ascii=False)
    )
    temp.replace(path)
    return result


async def _sync(
    source="all",
    days=3,
    backfill=False,
    years=(2025, 2026),
    domain="all",
    limit=50,
    job_id=None,
    user_id=None,
    vision_driver=None,
):
    from .ingest import new_job
    from .retry import error_message

    configs = [
        d for d in all_domains() if domain == "all" or d["slug"] in domain.split(",")
    ]
    if not configs:
        raise ValueError("没有匹配的激活领域")
    limits = get_settings().pipeline
    counts = {d["slug"]: 0 for d in configs}
    completed = failed = checked = 0
    errors = []
    seen = set()
    with connect() as db:
        done_titles = {
            normalized(r[0])
            for r in db.execute(
                "SELECT title FROM papers WHERE ingest_status='completed'"
            )
        }

    def quota_open():
        return any(n < limit for n in counts.values())

    async def ingest(p):
        nonlocal completed, failed
        child = new_job(
            user_id, "ingest", {"input": p["source_urls"]["pdf"], "batch_id": job_id}
        )
        try:
            update_job(child, 3, "正在下载论文 PDF")
            data = await fetch(p["source_urls"]["pdf"])
            await ingest_pdf(
                data,
                p,
                user_id,
                child,
                vision_driver=vision_driver,
                source_data=b""
                if p.get("source_type") == "cvf" and not p.get("arxiv_id")
                else None,
            )
            completed += 1
        except Exception as exc:
            failed += 1
            update_job(child, 0, error_message(exc), "failed")
        update_job(
            job_id,
            30,
            f"边核验边入库 · 完成 {completed} / 失败 {failed} / 已核验 {checked}",
        )

    async def publish(batch):
        chosen = []
        for p in sorted(
            batch,
            key=lambda p: (
                {"oral": 3, "spotlight": 2, "poster": 1}.get(p.get("venue_tier"), 0),
                p.get("hf_upvotes", 0),
            ),
            reverse=True,
        ):
            title = normalized(p["title"])
            if title in seen or title in done_titles:
                continue
            p["domains"] = [d for d in p.get("domains", []) if d in counts]
            if not any(counts[d] < limit for d in p["domains"]):
                continue
            seen.add(title)
            chosen.append(p)
            for d in p["domains"]:
                counts[d] += 1
        await bounded_map(ingest, chosen, limits.papers + 1)

    # Proceedings are indexed by conference year, so CVPR is not lost behind
    # November arXiv papers or the preprint's submission year.
    if backfill and source in ("all", "cvf"):
        update_job(job_id, 2, "正在召回 CVF 官方 CVPR 主会论文")
        try:
            from .cvf import discover as cvf_discover

            official = await cvf_discover(configs, years, limit)
            checked += len(official)
            await publish(official)
        except Exception as exc:
            errors.append("CVF 目录暂时不可用：" + error_message(exc))

    if source != "cvf" and quota_open():

        async def discover(d):
            try:
                async with asyncio.timeout(60):
                    if d is None:
                        return await hf_daily(days)
                    return await arxiv_search(
                        d, days, years if backfill else None, max(50, limit * 3)
                    )
            except Exception:
                errors.append(
                    ("HF Daily" if d is None else d["slug"] + " arXiv") + " 暂时不可用"
                )
                return []

        update_job(job_id, 5, f"已入库 {completed} 篇，正在召回补充候选")
        requests = ([None] if source in ("all", "hf") and not backfill else []) + (
            configs if source in ("all", "arxiv") else []
        )
        candidates = []
        for batch in await bounded_map(discover, requests, limits.metadata):
            candidates.extend(batch)
        dedup = {}
        for p in candidates:
            key = re.sub(r"v\d+$", "", p.get("arxiv_id") or p["doc_uid"])
            if key in dedup:
                old = dedup[key]
                p["hf_upvotes"] = max(p.get("hf_upvotes", 0), old.get("hf_upvotes", 0))
                p["source_urls"] = {
                    **old.get("source_urls", {}),
                    **p.get("source_urls", {}),
                }
                for field in ("venue", "venue_year", "venue_tier"):
                    if field not in p and field in old:
                        p[field] = old[field]
            dedup[key] = p

        async def verify(p):
            nonlocal checked
            if normalized(p["title"]) in done_titles or normalized(p["title"]) in seen:
                return None
            domains = match_domains(
                p["title"] + " " + p.get("abstract", "") + " " + p.get("keywords", ""),
                configs,
            )
            if not any(counts[d] < limit for d in domains):
                return None
            try:
                p = p if p.get("venue") in VENUES else await cached_verification(p)
                if not p or (backfill and p.get("venue_year") not in years):
                    return None
                p["domains"] = domains
                return p
            except (TimeoutError, ValueError):
                return None
            finally:
                checked += 1
                update_job(
                    job_id,
                    10,
                    f"补充核验 {checked} 篇 · 已入库 {completed} / 失败 {failed}",
                )

        # Known accepted papers are ingested before slow external verification.
        known = [p for p in dedup.values() if p.get("venue") in VENUES]
        unknown = [p for p in dedup.values() if p.get("venue") not in VENUES]
        await publish(
            [p for p in await bounded_map(verify, known, limits.metadata) if p]
        )
        width = limits.metadata * 2
        for start in range(0, len(unknown), width):
            if not quota_open():
                break
            batch = await bounded_map(
                verify, unknown[start : start + width], limits.metadata
            )
            await publish([p for p in batch if p])
    state = (
        "failed"
        if (failed and not completed) or (not completed and errors)
        else "completed"
    )
    update_job(
        job_id,
        100,
        f"入库 {completed} 篇，失败 {failed} 篇"
        + ("；" + "；".join(errors) if errors else ""),
        state,
    )
    return {"completed": completed, "failed": failed, "source_errors": errors}


async def sync(**kwargs):
    async with resource_lock("batch", "discovery"):
        try:
            return await _sync(**kwargs)
        except BaseException as exc:
            from .retry import error_message

            update_job(
                kwargs.get("job_id"),
                0,
                "任务中断，可恢复已有进度"
                if isinstance(exc, asyncio.CancelledError)
                else error_message(exc),
                "failed",
            )
            raise
