import asyncio
import hashlib
import json
import re
import uuid
from urllib.parse import urlparse, parse_qs
import fitz
from defusedxml import ElementTree as ET
from .config import get_settings
from .db import connect, event
from .domains import match_domains, all_domains
from .extraction import pdf_title, layout_type, render, Crop, snap
from .network import fetch
from .storage import Storage
from .tex import unpack, figures, merge_crops
from .vision import judge
from .locking import serialized

ARXIV_RE = r"(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?"
PAPER_JSON = ("authors", "source_urls", "domains")
FIGURE_JSON = ("bbox", "fonts", "palette", "color_buckets", "subitems", "sub_tags")


def update_job(jid, progress, message, status="running"):
    if not jid:
        return
    with connect() as db:
        db.execute(
            "UPDATE jobs SET progress=?,message=?,status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (progress, message, status, jid),
        )


def new_job(uid, kind, payload=None):
    jid = uuid.uuid4().hex
    with connect() as db:
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
                f"https://export.arxiv.org/api/query?id_list={aid}", 2 * 1024**2
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
    storage = storage or Storage()
    with connect() as db:
        p = dict(db.execute("SELECT * FROM papers WHERE id=?", (paper_id,)).fetchone())
        fs = [
            dict(r)
            for r in db.execute("SELECT * FROM figures WHERE paper_id=?", (paper_id,))
        ]
    p.pop("uploaded_by", None)
    key = p["webdav_pdf_path"].rsplit("/", 1)[0] + "/metadata.json"
    await storage.put(
        key,
        json.dumps(
            {"schema_version": 1, "paper": p, "figures": fs}, ensure_ascii=False
        ).encode(),
        "application/json",
    )


async def persist_crop(
    paper_id, base, crop, rendered, verdict, storage, figure_id=None
):
    fid = figure_id or uuid.uuid4().hex
    version = hashlib.sha256(rendered["hd"]).hexdigest()[:16]
    asset = f"{base}/figures/{fid}_{version}"
    subitems = []
    for sub in rendered["subitems"]:
        sub = dict(sub)
        raw = sub.pop("raw", None)
        if raw:
            sub["raw_path"] = asset + "_sub_" + sub["id"] + "_raw.pdf"
            await storage.put(sub["raw_path"], raw, "application/pdf")
        subitems.append(sub)
    await asyncio.gather(
        *(
            storage.put(
                asset + "_" + suffix + (".pdf" if suffix == "raw" else ".webp"),
                rendered[suffix],
                mime,
            )
            for suffix, mime in [
                ("thumb", "image/webp"),
                ("hd", "image/webp"),
                ("raw", "application/pdf"),
            ]
        )
    )
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
    row = {
        "id": fid,
        "paper_id": paper_id,
        "fig_label": crop.label,
        "page_number": crop.page,
        "bbox": crop.bbox,
        "caption": crop.caption,
        "archetype": verdict.archetype if verdict else fallback,
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


@serialized
async def ingest_pdf(
    data,
    metadata=None,
    user_id=None,
    job_id=None,
    vision_driver=None,
    source_data=None,
    collection_id=None,
):
    metadata = metadata or {}
    storage = Storage()
    if len(data) > get_settings().max_pdf_bytes:
        raise ValueError("PDF 不能超过 50MB")
    if not data.lstrip().startswith(b"%PDF"):
        raise ValueError("文件不是有效 PDF")
    sha = hashlib.sha256(data).hexdigest()
    with connect() as db:
        existing = db.execute(
            "SELECT id,ingest_status FROM papers WHERE file_sha256=?", (sha,)
        ).fetchone()
        if (
            existing
            and existing["ingest_status"] == "completed"
            and db.execute(
                "SELECT id FROM figures WHERE paper_id=?", (existing["id"],)
            ).fetchone()
        ):
            update_job(job_id, 100, "这篇论文已入库，无需重复上传", "completed")
            return existing["id"]
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        if doc.is_encrypted or not len(doc):
            raise ValueError("PDF 已加密或没有页面")
        if len(doc) > 150:
            raise ValueError("PDF 最多支持 150 页")
        metadata.setdefault("title", pdf_title(doc))
        metadata.setdefault("doc_uid", "local_" + uuid.uuid4().hex)
        metadata.setdefault("authors", [])
        metadata.setdefault(
            "domains",
            match_domains(
                metadata["title"]
                + " "
                + metadata.get("abstract", "")
                + " "
                + doc[0].get_text()
            ),
        )
        aid = metadata.get("arxiv_id")
        if not aid:
            m = re.search(r"arXiv:\s*(" + ARXIV_RE + ")", doc[0].get_text())
            if m:
                aid = m[1]
                metadata["arxiv_id"] = aid
        update_job(job_id, 8, "PDF 已接收，正在解析源码与页面布局")
        source_figures = []
        if aid and source_data is None:
            try:
                source_data = await fetch(
                    f"https://export.arxiv.org/e-print/{aid}", 50 * 1024**2
                )
            except Exception:
                source_data = None
        if source_data:
            try:
                source_figures = await asyncio.to_thread(
                    lambda: figures(unpack(source_data))
                )
            except Exception:
                pass
        crops = await asyncio.to_thread(merge_crops, doc, source_figures)
        if not crops:
            raise ValueError(
                "未识别到带图注的图表，请检查 PDF 是否为扫描件或使用其他论文"
            )
        pid = existing["id"] if existing else uuid.uuid4().hex
        base = f"papers/{metadata.get('venue_year') or 'uploads'}/{pid}"
        if not existing:
            update_job(
                job_id, 9, f"正在上传原文至 WebDAV · {len(data) / 1024**2:.1f} MB"
            )
            await storage.put(base + "/paper.pdf", data, "application/pdf")
        row = {
            "id": pid,
            "file_sha256": sha,
            "doc_uid": metadata["doc_uid"],
            "title": metadata["title"],
            "authors": metadata["authors"],
            "abstract": metadata.get("abstract", ""),
            "source_type": metadata.get("source_type", "upload"),
            "arxiv_id": metadata.get("arxiv_id"),
            "venue": metadata.get("venue", "Preprint"),
            "venue_year": metadata.get("venue_year"),
            "venue_tier": metadata.get("venue_tier"),
            "hf_upvotes": metadata.get("hf_upvotes", 0),
            "layout_type": layout_type(doc),
            "source_urls": metadata.get("source_urls", {}),
            "domains": metadata["domains"],
            "ingest_status": "processing",
            "uploaded_by": user_id,
            "webdav_pdf_path": base + "/paper.pdf",
        }
        with connect() as db:
            if not existing:
                db.execute(
                    "INSERT INTO papers("
                    + ",".join(row)
                    + ") VALUES("
                    + ",".join("?" for _ in row)
                    + ")",
                    tuple(
                        json.dumps(v, ensure_ascii=False) if k in PAPER_JSON else v
                        for k, v in row.items()
                    ),
                )
        judge_unavailable = False
        count = 0
        for i, crop in enumerate(crops):
            if existing:
                with connect() as db:
                    done = db.execute(
                        "SELECT id FROM figures WHERE paper_id=? AND fig_label=? AND page_number=?",
                        (pid, crop.label, crop.page),
                    ).fetchone()
                if done:
                    count += 1
                    continue
            update_job(
                job_id,
                10 + int(i / len(crops) * 85),
                f"正在拆解 {crop.label} · 已切出 {i}/{len(crops)} 张",
            )
            rendered = await asyncio.to_thread(render, doc, crop)
            verdict = None
            if not judge_unavailable:
                try:
                    verdict = await judge(
                        rendered["thumb"], crop.caption, all_domains(), vision_driver
                    )
                except Exception:
                    judge_unavailable = True
            fid = await persist_crop(pid, base, crop, rendered, verdict, storage)
            if collection_id:
                with connect() as db:
                    owned = db.execute(
                        "SELECT id FROM collections WHERE id=? AND user_id=?",
                        (collection_id, user_id),
                    ).fetchone()
                    if owned:
                        db.execute(
                            "INSERT OR IGNORE INTO collection_items(id,collection_id,figure_id) VALUES(?,?,?)",
                            (uuid.uuid4().hex, collection_id, fid),
                        )
            count += 1
        with connect() as db:
            db.execute("UPDATE papers SET ingest_status='completed' WHERE id=?", (pid,))
        await backup(pid, storage)
        update_job(
            job_id,
            100,
            f"完成 · {count} 张图表"
            + ("；视觉模型不可用，已加入复核队列" if judge_unavailable else ""),
            "completed",
        )
        return pid
    finally:
        doc.close()


@serialized
async def recrop(fid, page_number, bbox, do_snap=True):
    with connect() as db:
        row = db.execute(
            "SELECT f.*,p.webdav_pdf_path FROM figures f JOIN papers p ON p.id=f.paper_id WHERE f.id=?",
            (fid,),
        ).fetchone()
    if not row:
        raise ValueError("图表不存在")
    storage = Storage()
    data = await storage.get(row["webdav_pdf_path"])
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        if not 1 <= page_number <= len(doc):
            raise ValueError("页码超出范围")
        page = doc[page_number - 1]
        if (
            len(bbox) != 4
            or not all(0 <= v <= 1 for v in bbox)
            or bbox[0] >= bbox[2]
            or bbox[1] >= bbox[3]
        ):
            raise ValueError("无效裁切坐标")
        absolute = [
            bbox[0] * page.rect.width,
            bbox[1] * page.rect.height,
            bbox[2] * page.rect.width,
            bbox[3] * page.rect.height,
        ]
        crop = Crop(
            page_number,
            snap(page, absolute) if do_snap else absolute,
            row["fig_label"],
            row["caption"],
            1,
        )
        result = await asyncio.to_thread(render, doc, crop)
        from .vision import Verdict

        verdict = Verdict(
            archetype=row["archetype"],
            crop_ok=True,
            confidence=1,
            sub_tags=json.loads(row["sub_tags"]),
            reason="Human corrected",
        )
        await persist_crop(
            row["paper_id"],
            row["webdav_pdf_path"].rsplit("/", 1)[0],
            crop,
            result,
            verdict,
            storage,
            fid,
        )
        with connect() as db:
            db.execute(
                "UPDATE repair_queue SET status='completed' WHERE figure_id=? AND status='pending'",
                (fid,),
            )
    finally:
        doc.close()


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
        message = (
            str(exc)
            if isinstance(exc, (ValueError, RuntimeError))
            else "论文处理失败，请检查源文件或远端连接后重试"
        )
        update_job(job_id, 0, message, "failed")


async def rebuild():
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
