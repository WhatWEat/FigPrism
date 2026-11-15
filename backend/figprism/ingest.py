import asyncio
import hashlib
import json
import re
import uuid
from pathlib import Path
import tempfile
from urllib.parse import urlparse, parse_qs
import httpx
from defusedxml import ElementTree as ET
from .config import get_settings
from .db import connect, event
from .domains import match_domains, all_domains
from .network import fetch
from .storage import Storage
from .vision import judge, normalize_taxonomy
from .concurrency import stage, resource_lock, bounded_map
from .processing import cpu_call
from .retry import error_message, root_error

ARXIV_RE = r"(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?"
PAPER_JSON = ("authors", "source_urls", "domains")
FIGURE_JSON = (
    "bbox",
    "fonts",
    "palette",
    "color_buckets",
    "subitems",
    "sub_tags",
    "craft_badges_json",
)


def update_job(jid, progress, message, status="running"):
    if not jid:
        return
    with connect() as db:
        db.execute(
            "UPDATE jobs SET progress=?,message=?,status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (progress, message, status, jid),
        )


class JobQueueFull(Exception):
    pass


def new_job(uid, kind, payload=None):
    jid = uuid.uuid4().hex
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if uid is not None and not (payload or {}).get("batch_id"):
            queued = "status IN ('queued','running') AND json_extract(payload,'$.batch_id') IS NULL"
            if (
                db.execute(
                    "SELECT COUNT(*) FROM jobs WHERE user_id=? AND " + queued, (uid,)
                ).fetchone()[0]
                >= 3
            ):
                raise JobQueueFull("最多同时排队 3 个任务")
            if (
                db.execute("SELECT COUNT(*) FROM jobs WHERE " + queued).fetchone()[0]
                >= get_settings().pipeline.pending_jobs
            ):
                raise JobQueueFull("处理队列已满，请稍后再试")
        db.execute(
            "INSERT INTO jobs(id,user_id,kind,payload) VALUES(?,?,?,?)",
            (jid, uid, kind, json.dumps(payload or {})),
        )
    return jid


def arxiv_id(value):
    value = value.strip()
    if re.fullmatch(ARXIV_RE, value):
        return value
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in (
        "arxiv.org",
        "export.arxiv.org",
        "huggingface.co",
    ):
        return None
    m = re.search(
        r"/(?:abs|pdf|html|papers)/(" + ARXIV_RE + r")(?:\.pdf)?/?$", parsed.path
    )
    return m[1] if m else None


async def resolve(value):
    aid = arxiv_id(value)
    if aid:
        meta = {
            "arxiv_id": aid,
            "doc_uid": aid,
            "source_type": "arxiv",
            "source_urls": {
                "pdf": f"https://arxiv.org/pdf/{aid}",
                "html": f"https://arxiv.org/html/{aid}",
                "hf": f"https://huggingface.co/papers/{aid}",
            },
        }
        try:
            data = await fetch(
                f"https://export.arxiv.org/api/query?id_list={aid}",
                2 * 1024**2,
                budget="metadata",
            )
            root = ET.fromstring(data)
            entry = root.find("{http://www.w3.org/2005/Atom}entry")
            if entry is not None:
                meta["title"] = " ".join(
                    entry.findtext("{http://www.w3.org/2005/Atom}title", "").split()
                )
                meta["abstract"] = entry.findtext(
                    "{http://www.w3.org/2005/Atom}summary", ""
                ).strip()
                meta["authors"] = [
                    a.findtext("{http://www.w3.org/2005/Atom}name", "")
                    for a in entry.findall("{http://www.w3.org/2005/Atom}author")
                ]
        except Exception:
            pass
        return f"https://arxiv.org/pdf/{aid}", meta
    p = urlparse(value)
    if (
        p.scheme == "https"
        and p.hostname == "openreview.net"
        and p.path in ("/forum", "/pdf")
    ):
        nid = parse_qs(p.query).get("id", [""])[0]
        if not re.fullmatch(r"[A-Za-z0-9_-]{5,100}", nid):
            raise ValueError("无效的 OpenReview 编号")
        return "https://openreview.net/pdf?id=" + nid, {
            "doc_uid": "or_" + nid,
            "source_type": "openreview",
            "source_urls": {
                "openreview": "https://openreview.net/forum?id=" + nid,
                "pdf": "https://openreview.net/pdf?id=" + nid,
            },
        }
    raise ValueError("请提供有效的 arXiv 编号、arXiv/HF/OpenReview 链接")


async def backup(paper_id, storage=None):
    # Snapshot inside the lock, so an older upload cannot replace a newer manifest.
    async with resource_lock("manifest", paper_id):
        storage = storage or Storage()
        with connect() as db:
            p = dict(
                db.execute("SELECT * FROM papers WHERE id=?", (paper_id,)).fetchone()
            )
            fs = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM figures WHERE paper_id=? ORDER BY id", (paper_id,)
                )
            ]
        p.pop("uploaded_by", None)
        data = json.dumps(
            {"schema_version": 1, "paper": p, "figures": fs},
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
        digest = hashlib.sha256(data).hexdigest()
        checkpoint = get_settings().data_dir / ".pipeline" / "manifests" / paper_id
        if checkpoint.exists() and checkpoint.read_text() == digest:
            return
        await storage.put(
            p["webdav_pdf_path"].rsplit("/", 1)[0] + "/metadata.json",
            data,
            "application/json",
        )
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(digest)


async def persist_crop(
    paper_id,
    base,
    crop,
    rendered,
    verdict,
    storage,
    figure_id=None,
    publication_barrier=None,
    taxonomy_locked=0,
):
    fid = (
        figure_id
        or uuid.uuid5(
            uuid.NAMESPACE_URL, f"figprism:{paper_id}:{crop.page}:{crop.label}"
        ).hex
    )
    version = hashlib.sha256(rendered["hd"]).hexdigest()[:16]
    asset = f"{base}/figures/{fid}_{version}"
    subitems = []
    for sub in rendered["subitems"]:
        sub = dict(sub)
        raw = sub.pop("raw", None)
        if raw:
            label = sub["id"]
            safe_label = label if re.fullmatch(r"[A-Za-z0-9_-]+", label) else hashlib.sha256(label.encode()).hexdigest()[:16]
            sub["raw_path"] = asset + "_sub_" + safe_label + "_raw.pdf"
            await storage.put(sub["raw_path"], raw, "application/pdf")
        subitems.append(sub)
    async with asyncio.TaskGroup() as uploads:
        for suffix, mime in [
            ("thumb", "image/webp"),
            ("hd", "image/webp"),
            ("raw", "application/pdf"),
        ]:
            uploads.create_task(
                storage.put(
                    asset + "_" + suffix + (".pdf" if suffix == "raw" else ".webp"),
                    rendered[suffix],
                    mime,
                )
            )
    if publication_barrier is not None:
        await asyncio.shield(publication_barrier)
    status = (
        "ok"
        if verdict
        and verdict.crop_ok
        and min(crop.confidence, verdict.confidence) > 0.75
        else "needs_review"
    )
    # Conservative heuristic only when the configured judge cannot provide a verdict.
    fallback = (
        "Curve"
        if re.search(
            r"\b(accuracy|performance|scaling|loss|ablation)\b", crop.caption, re.I
        )
        else "Pipeline"
    )
    tax = (
        normalize_taxonomy(
            macro_category=verdict.macro_category,
            sub_type=verdict.sub_type,
            archetype=verdict.archetype,
            primary_style=verdict.primary_style,
            secondary_style=verdict.secondary_style,
            layout_topology=verdict.layout_topology,
            craft_badges=verdict.craft_badges,
            chart_layout=verdict.chart_layout,
        )
        if verdict
        else normalize_taxonomy(archetype=fallback)
    )
    row = {
        "id": fid,
        "paper_id": paper_id,
        "fig_label": crop.label,
        "page_number": crop.page,
        "bbox": crop.bbox,
        "caption": crop.caption,
        "archetype": tax["archetype"],
        "macro_category": tax["macro_category"],
        "sub_type": tax["sub_type"],
        "primary_style": tax["primary_style"],
        "secondary_style": tax["secondary_style"],
        "layout_topology": tax["layout_topology"],
        "craft_badges_json": tax["craft_badges"],
        "chart_layout": tax["chart_layout"],
        "style_confidence": verdict.style_confidence if verdict else None,
        "style_reason": verdict.style_reason if verdict else None,
        "taxonomy_locked": int(bool(taxonomy_locked)),
        "span_type": "full" if (crop.bbox[2] - crop.bbox[0]) > 360 else "column",
        "width": rendered["width"],
        "height": rendered["height"],
        "aspect_ratio": rendered["aspect_ratio"],
        "blurhash": rendered["blurhash"],
        "fonts": rendered["fonts"],
        "palette": rendered["palette"],
        "color_buckets": rendered["palette"]["buckets"],
        "subitems": subitems,
        "tikz_code": crop.tikz,
        "extract_method": "tex_raw" if crop.raw else "pdf_snap_crop",
        "confidence": min(crop.confidence, verdict.confidence)
        if verdict
        else crop.confidence,
        "review_status": status,
        "asset_base": asset,
        "version_hash": version,
        "sub_tags": verdict.sub_tags if verdict else [],
    }
    serialized = {
        k: json.dumps(v, ensure_ascii=False) if k in FIGURE_JSON else v
        for k, v in row.items()
    }
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if figure_id:
            db.execute(
                "UPDATE figures SET "
                + ",".join(k + "=?" for k in serialized if k != "id")
                + " WHERE id=?",
                tuple(v for k, v in serialized.items() if k != "id") + (fid,),
            )
            db.execute("DELETE FROM figures_fts WHERE figure_id=?", (fid,))
        else:
            db.execute(
                "INSERT INTO figures("
                + ",".join(serialized)
                + ") VALUES("
                + ",".join("?" for _ in serialized)
                + ")",
                tuple(serialized.values()),
            )
        title = db.execute(
            "SELECT title FROM papers WHERE id=?", (paper_id,)
        ).fetchone()[0]
        db.execute(
            "INSERT INTO figures_fts VALUES(?,?,?,?)",
            (fid, title, crop.caption, " ".join(rendered["fonts"])),
        )
        event(db, "figure.updated" if figure_id else "figure.created", {"id": fid})
    await backup(paper_id, storage)
    return fid


async def ingest_pdf(
    data,
    metadata=None,
    user_id=None,
    job_id=None,
    vision_driver=None,
    source_data=None,
    collection_id=None,
):
    metadata = dict(metadata or {})
    if len(data) > get_settings().max_pdf_bytes:
        raise ValueError("PDF 不能超过 50MB")
    if not data.lstrip().startswith(b"%PDF"):
        raise ValueError("文件不是有效 PDF")
    sha = hashlib.sha256(data).hexdigest()
    # Lock duplicate identities before admission; waiting duplicates consume no paper slot.
    async with (
        resource_lock("maintenance", "library", shared=True),
        resource_lock("document", metadata.get("doc_uid", sha)),
        resource_lock("sha", sha),
    ):
        async with stage("papers"), Storage() as storage:
            with connect() as db:
                existing = db.execute(
                    "SELECT * FROM papers WHERE file_sha256=?", (sha,)
                ).fetchone()
                if existing and existing["ingest_status"] == "completed":
                    attach_collection(existing["id"], collection_id, user_id)
                    update_job(job_id, 100, "这篇论文已入库，无需重复上传", "completed")
                    return existing["id"]
            root = get_settings().data_dir / ".pipeline" / "work"
            root.mkdir(parents=True, exist_ok=True)
            pid = existing["id"] if existing else uuid.uuid4().hex
            try:
                with tempfile.TemporaryDirectory(dir=root) as work:
                    pdf = Path(work) / "paper.pdf"
                    pdf.write_bytes(data)
                    update_job(job_id, 5, "正在读取论文信息")
                    info = await cpu_call("inspect", pdf)
                    metadata.setdefault("title", info["title"])
                    metadata.setdefault("doc_uid", "local_" + sha)
                    metadata.setdefault("authors", [])
                    metadata.setdefault(
                        "domains",
                        match_domains(
                            metadata["title"]
                            + " "
                            + metadata.get("abstract", "")
                            + " "
                            + info["first_page_text"]
                        ),
                    )
                    aid = metadata.get("arxiv_id")
                    if not aid:
                        match = re.search(
                            r"arXiv:\s*(" + ARXIV_RE + ")", info["first_page_text"]
                        )
                        if match:
                            aid = match[1]
                            metadata["arxiv_id"] = aid
                    base = (
                        existing["webdav_pdf_path"].rsplit("/", 1)[0]
                        if existing
                        else f"papers/{metadata.get('venue_year') or 'uploads'}/{pid}"
                    )
                    row = {
                        "id": pid,
                        "file_sha256": sha,
                        "doc_uid": metadata["doc_uid"],
                        "title": metadata["title"],
                        "authors": metadata["authors"],
                        "abstract": metadata.get("abstract", ""),
                        "source_type": metadata.get("source_type", "upload"),
                        "arxiv_id": aid,
                        "venue": metadata.get("venue", "Preprint"),
                        "venue_year": metadata.get("venue_year"),
                        "venue_tier": metadata.get("venue_tier"),
                        "hf_upvotes": metadata.get("hf_upvotes", 0),
                        "layout_type": info["layout_type"],
                        "source_urls": metadata.get("source_urls", {}),
                        "domains": metadata["domains"],
                        "ingest_status": "processing",
                        "pdf_uploaded": 0,
                        "uploaded_by": user_id,
                        "webdav_pdf_path": base + "/paper.pdf",
                    }
                    with connect() as db:
                        if existing:
                            db.execute(
                                "UPDATE papers SET ingest_status='processing' WHERE id=?",
                                (pid,),
                            )
                        else:
                            db.execute(
                                "INSERT INTO papers("
                                + ",".join(row)
                                + ") VALUES("
                                + ",".join("?" for _ in row)
                                + ")",
                                tuple(
                                    json.dumps(v, ensure_ascii=False)
                                    if k in PAPER_JSON
                                    else v
                                    for k, v in row.items()
                                ),
                            )

                    async def store_pdf():
                        if not existing or not existing["pdf_uploaded"]:
                            await storage.put(
                                base + "/paper.pdf", data, "application/pdf"
                            )

                    async def plan():
                        source = source_data
                        if aid and source is None:
                            try:
                                source = await fetch(
                                    f"https://export.arxiv.org/e-print/{aid}",
                                    50 * 1024**2,
                                )
                            except Exception:
                                source = None
                        source_path = None
                        if source:
                            source_path = str(Path(work) / "source")
                            Path(source_path).write_bytes(source)
                        return await cpu_call("plan", pdf, source_path=source_path)

                    # Local PDF staging and layout overlap. Publish only after the
                    # original and all figure assets are durable in the local queue.
                    async with asyncio.TaskGroup() as group:
                        original = group.create_task(store_pdf())
                        planned = group.create_task(plan())
                        crops = await planned
                        crops = list({(c.label, c.page): c for c in crops}.values())
                        if not crops:
                            raise ValueError(
                                "未识别到带图注的图表，请检查 PDF 是否为扫描件"
                            )
                        with connect() as db:
                            done = {
                                (r["fig_label"], r["page_number"])
                                for r in db.execute(
                                    "SELECT fig_label,page_number FROM figures WHERE paper_id=?",
                                    (pid,),
                                )
                            }
                        todo = [c for c in crops if (c.label, c.page) not in done]
                        counts = {
                            "total": len(crops),
                            "resumed": len(crops) - len(todo),
                            "rendered": 0,
                            "judged": 0,
                            "published": 0,
                            "review_fallbacks": 0,
                        }

                        def progress():
                            published = counts["resumed"] + counts["published"]
                            message = f"并行处理 · 渲染 {counts['rendered']}/{len(todo)} · 判图 {counts['judged']}/{len(todo)} · 入库 {published}/{len(crops)}"
                            update_job(
                                job_id, 10 + int(85 * published / len(crops)), message
                            )
                            if job_id:
                                with connect() as db:
                                    db.execute(
                                        "UPDATE jobs SET payload=json_set(payload,'$.pipeline',json(?)) WHERE id=?",
                                        (json.dumps(counts), job_id),
                                    )

                        progress()

                        async def process(crop):
                            async with stage("figures"):
                                rendered = await cpu_call("render", pdf, crop=crop)
                                counts["rendered"] += 1
                                progress()
                                verdict = None
                                try:
                                    verdict = await judge(
                                        rendered["thumb"],
                                        crop.caption,
                                        all_domains(),
                                        vision_driver,
                                    )
                                except Exception:
                                    counts["review_fallbacks"] += 1
                                counts["judged"] += 1
                                progress()
                                fid = await persist_crop(
                                    pid,
                                    base,
                                    crop,
                                    rendered,
                                    verdict,
                                    storage,
                                    publication_barrier=original,
                                )
                                attach_collection(
                                    pid, collection_id, user_id, figure_id=fid
                                )
                                counts["published"] += 1
                                progress()

                        group.create_task(
                            bounded_map(
                                process, todo, get_settings().pipeline.per_paper_figures
                            )
                        )
                    with connect() as db:
                        db.execute(
                            "UPDATE papers SET ingest_status='completed' WHERE id=?",
                            (pid,),
                        )
                    attach_collection(pid, collection_id, user_id)
                    await backup(pid, storage)
                    update_job(
                        job_id,
                        100,
                        f"完成 · {len(crops)} 张图表（远端备份由后台队列处理）"
                        + (
                            "；部分视觉判图不可用，已加入复核队列"
                            if counts["review_fallbacks"]
                            else ""
                        ),
                        "completed",
                    )
                    return pid
            except BaseException as exc:
                with connect() as db:
                    db.execute(
                        "UPDATE papers SET ingest_status='failed' WHERE id=?", (pid,)
                    )
                update_job(
                    job_id,
                    0,
                    "任务中断，可恢复已有进度"
                    if isinstance(exc, asyncio.CancelledError)
                    else error_message(exc),
                    "failed",
                )
                if isinstance(exc, asyncio.CancelledError):
                    raise
                raise root_error(exc)


def attach_collection(pid, collection_id, user_id, figure_id=None):
    if not collection_id:
        return
    with connect() as db:
        if not db.execute(
            "SELECT id FROM collections WHERE id=? AND user_id=?",
            (collection_id, user_id),
        ).fetchone():
            return
        ids = (
            [figure_id]
            if figure_id
            else [
                r[0]
                for r in db.execute("SELECT id FROM figures WHERE paper_id=?", (pid,))
            ]
        )
        for fid in ids:
            db.execute(
                "INSERT OR IGNORE INTO collection_items(id,collection_id,figure_id) VALUES(?,?,?)",
                (uuid.uuid4().hex, collection_id, fid),
            )
        db.execute(
            "UPDATE collections SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (collection_id,),
        )


async def recrop(fid, page_number, bbox, do_snap=True):
    async with (
        resource_lock("maintenance", "library", shared=True),
        resource_lock("figure", fid),
        Storage() as storage,
    ):
        with connect() as db:
            row = db.execute(
                "SELECT f.*,p.webdav_pdf_path FROM figures f JOIN papers p ON p.id=f.paper_id WHERE f.id=?",
                (fid,),
            ).fetchone()
        if not row:
            raise ValueError("图表不存在")
        data = await storage.get(row["webdav_pdf_path"])
        root = get_settings().data_dir / ".pipeline" / "work"
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as work:
            path = Path(work) / "paper.pdf"
            path.write_bytes(data)
            crop, result = await cpu_call(
                "recrop",
                path,
                page=page_number,
                bbox=bbox,
                snap=do_snap,
                label=row["fig_label"],
                caption=row["caption"],
            )
        from .vision import Verdict

        verdict = Verdict(
            macro_category=row["macro_category"],
            sub_type=row["sub_type"],
            archetype=row["archetype"],
            primary_style=row["primary_style"],
            secondary_style=row["secondary_style"],
            layout_topology=row["layout_topology"],
            craft_badges=json.loads(row["craft_badges_json"] or "[]"),
            chart_layout=row["chart_layout"],
            crop_ok=True,
            confidence=1,
            style_confidence=row["style_confidence"],
            sub_tags=json.loads(row["sub_tags"]),
            reason="Human corrected",
            style_reason=row["style_reason"],
        )
        await persist_crop(
            row["paper_id"],
            row["webdav_pdf_path"].rsplit("/", 1)[0],
            crop,
            result,
            verdict,
            storage,
            fid,
            taxonomy_locked=row["taxonomy_locked"],
        )
        with connect() as db:
            db.execute(
                "UPDATE repair_queue SET status='completed' WHERE figure_id=? AND status='pending'",
                (fid,),
            )


async def run_ingest(
    job_id, user_id, data=None, value=None, metadata=None, collection_id=None
):
    try:
        if value:
            url, meta = await resolve(value)
            meta.update(metadata or {})
            metadata = meta
            update_job(job_id, 3, "正在下载论文 PDF")
            data = await fetch(url)
        return await ingest_pdf(
            data, metadata, user_id, job_id, collection_id=collection_id
        )
    except Exception as exc:
        update_job(job_id, 0, error_message(exc), "failed")


async def rebuild():
    async with resource_lock("maintenance", "library"):
        return await _rebuild()


async def _rebuild():
    with connect() as db:
        if db.execute("SELECT 1 FROM asset_transfers WHERE synced=0 LIMIT 1").fetchone():
            raise ValueError("仍有资产等待远端备份，请在备份完成后恢复索引")
    storage = Storage()
    stack = ["papers"]
    count = 0
    while stack:
        key = stack.pop()
        for item in await storage.list(key):
            if item["directory"]:
                stack.append(item["key"])
                continue
            if not item["key"].endswith("/metadata.json"):
                continue
            data = json.loads(await storage.get(item["key"], refresh=True))
            if data.get("schema_version") != 1:
                continue
            p = data["paper"]
            p["uploaded_by"] = None
            fs = data["figures"]
            # Fetch assets before the DB transaction: metadata never points to absent thumbnails.
            for f in fs:
                await storage.get(f["asset_base"] + "_thumb.webp")
            with connect() as db:
                pcols = {r["name"] for r in db.execute("PRAGMA table_info(papers)")}
                p = {k: v for k, v in p.items() if k in pcols}
                db.execute(
                    "INSERT OR IGNORE INTO papers("
                    + ",".join(p)
                    + ") VALUES("
                    + ",".join("?" for _ in p)
                    + ")",
                    tuple(p.values()),
                )
                fcols = {r["name"] for r in db.execute("PRAGMA table_info(figures)")}
                for f in fs:
                    f = {k: v for k, v in f.items() if k in fcols}
                    db.execute(
                        "INSERT INTO figures("
                        + ",".join(f)
                        + ") VALUES("
                        + ",".join("?" for _ in f)
                        + ") ON CONFLICT(id) DO UPDATE SET "
                        + ",".join(k + "=excluded." + k for k in f if k != "id"),
                        tuple(f.values()),
                    )
                    db.execute("DELETE FROM figures_fts WHERE figure_id=?", (f["id"],))
                    db.execute(
                        "INSERT INTO figures_fts VALUES(?,?,?,?)",
                        (
                            f["id"],
                            p["title"],
                            f["caption"],
                            " ".join(json.loads(f["fonts"])),
                        ),
                    )
                    count += 1
                event(db, "library.rebuilt", {"paper_id": p["id"]})
    return count


async def retag_taxonomy(
    scope: str = "all",
    concurrency: int = 8,
    vision_driver: str | None = "openai_mini",
    on_progress=None,
):
    clauses = ["COALESCE(taxonomy_locked, 0) = 0"]
    args: list = []
    if scope == "method":
        clauses.append("macro_category = 'method'")
    elif scope == "data_chart":
        clauses.append("macro_category = 'data_chart'")
    elif scope == "untagged":
        clauses.append(
            "((macro_category = 'method' AND primary_style IS NULL) OR (macro_category = 'data_chart' AND chart_layout IS NULL))"
        )
    elif scope != "all":
        raise ValueError(f"Unsupported scope: {scope}")

    with connect() as db:
        skipped_locked = db.execute(
            "SELECT COUNT(*) FROM figures WHERE COALESCE(taxonomy_locked, 0) = 1"
        ).fetchone()[0]
        rows = [
            dict(r)
            for r in db.execute(
                "SELECT id, paper_id, caption, asset_base FROM figures WHERE "
                + " AND ".join(clauses)
                + " ORDER BY created_at DESC",
                args,
            ).fetchall()
        ]

    sem = asyncio.Semaphore(max(1, concurrency))
    summary = {
        "scope": scope,
        "total": len(rows),
        "updated": 0,
        "failed": 0,
        "skipped_locked": skipped_locked,
    }
    touched_papers: set[str] = set()
    driver = vision_driver or "openai_mini"

    async with Storage() as storage, httpx.AsyncClient(
        timeout=120,
        limits=httpx.Limits(
            max_connections=max(8, concurrency * 2),
            max_keepalive_connections=max(4, concurrency),
        ),
    ) as vlm_client:
        async def worker(item: dict):
            async with sem:
                try:
                    try:
                        img = await storage.get(item["asset_base"] + "_thumb.webp")
                    except Exception:
                        img = await storage.get(item["asset_base"] + "_hd.webp")
                    verdict = await judge(
                        img,
                        item["caption"] or "",
                        domains=None,
                        driver=driver,
                        use_stage=False,
                        http_client=vlm_client,
                    )
                    if not verdict:
                        summary["failed"] += 1
                        return
                    with connect() as db:
                        cur = db.execute(
                            """
                            UPDATE figures SET
                              macro_category=?, sub_type=?, archetype=?,
                              primary_style=?, secondary_style=?, layout_topology=?,
                              craft_badges_json=?, chart_layout=?,
                              style_confidence=?, style_reason=?
                            WHERE id=? AND COALESCE(taxonomy_locked, 0)=0
                            """,
                            (
                                verdict.macro_category,
                                verdict.sub_type,
                                verdict.archetype,
                                verdict.primary_style,
                                verdict.secondary_style,
                                verdict.layout_topology,
                                json.dumps(verdict.craft_badges, ensure_ascii=False),
                                verdict.chart_layout,
                                verdict.style_confidence,
                                verdict.style_reason,
                                item["id"],
                            ),
                        )
                        if cur.rowcount:
                            summary["updated"] += 1
                            touched_papers.add(item["paper_id"])
                            event(db, "figure.updated", {"id": item["id"]})
                        else:
                            summary["skipped_locked"] += 1
                except Exception:
                    summary["failed"] += 1
                finally:
                    if on_progress:
                        on_progress(summary)

        await asyncio.gather(*(worker(r) for r in rows))
        for pid in sorted(touched_papers):
            try:
                await backup(pid, storage)
            except Exception:
                pass

    return summary
