import asyncio
import io
import json
import re
import secrets
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Literal
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    UploadFile,
    File,
    Form,
    Query,
)
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from .auth import require_user, require_admin, current_user, create_user
from .config import get_settings
from .db import connect
from .domains import all_domains, save_domains
from .storage import Storage
from .ingest import (
    FIGURE_JSON,
    PAPER_JSON,
    new_job,
    run_ingest,
    recrop,
    resolve,
    update_job,
    rebuild,
)
from .vision import ARCHETYPES
from .concurrency import snapshot, resource_lock
from .processing import cpu_call
from pathlib import Path
import tempfile
from .retry import error_message

router = APIRouter(prefix="/api")
_tasks = set()


def launch(coro):
    task = asyncio.create_task(coro)
    _tasks.add(task)

    def finished(task):
        _tasks.discard(task)
        if not task.cancelled():
            task.exception()

    task.add_done_callback(finished)


async def stop_tasks():
    pending = list(_tasks)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


@router.get("/admin/pipeline")
def pipeline_status(user=Depends(require_admin)):
    return {"stages": snapshot(), "configuration": get_settings().pipeline.model_dump()}


def deserialize(row):
    d = dict(row)
    for key in FIGURE_JSON + PAPER_JSON:
        if key in d and isinstance(d[key], str):
            d[key] = json.loads(d[key])
    if "asset_base" in d:
        d.pop("asset_base", None)
        d["thumb_url"] = f"/api/assets/thumb/{d['id']}.webp?v={d['version_hash']}"
        d["hd_url"] = f"/api/assets/hd/{d['id']}.webp?v={d['version_hash']}"
        d["raw_url"] = f"/api/assets/raw/{d['id']}.pdf?v={d['version_hash']}"
    for s in d.get("subitems", []):
        s["has_raw"] = bool(s.pop("raw_path", None))
    d.pop("webdav_pdf_path", None)
    return d


SELECT = "SELECT f.*,p.title,p.authors,p.abstract,p.venue,p.venue_year,p.venue_tier,p.hf_upvotes,p.layout_type,p.source_urls,p.domains,p.arxiv_id FROM figures f JOIN papers p ON p.id=f.paper_id "


def figure(fid):
    with connect() as db:
        r = db.execute(SELECT + "WHERE f.id=?", (fid,)).fetchone()
    if not r:
        raise HTTPException(404, "图表不存在")
    return deserialize(r)


@router.get("/stats")
def stats():
    with connect() as db:
        return {
            "figures": db.execute("SELECT COUNT(*) FROM figures").fetchone()[0],
            "papers": db.execute("SELECT COUNT(*) FROM papers").fetchone()[0],
            "domains": db.execute(
                "SELECT COUNT(*) FROM domains WHERE is_active=1"
            ).fetchone()[0],
            "updated_at": db.execute("SELECT MAX(created_at) FROM figures").fetchone()[
                0
            ],
        }


def figure_conditions(
    q,
    domain,
    sub_tags,
    tag_mode,
    venue,
    layout,
    span,
    archetype,
    color,
    view,
    honors,
    show_cases,
):
    where = []
    args = []

    def add(clause, *values):
        where.append(clause)
        args.extend(values)

    if q:
        font = re.search(r'font:(?:"([^"]+)"|(\S+))', q)
        if font:
            add("f.fonts LIKE ?", "%" + (font[1] or font[2]) + "%")
            q = q.replace(font[0], "")
        ratio = re.search(r"ratio:([<>]=?|=)?(\d+(?:\.\d+)?)", q)
        if ratio:
            add("f.aspect_ratio " + (ratio[1] or "=") + " ?", float(ratio[2]))
            q = q.replace(ratio[0], "")
        words = re.findall(r"[\w-]+", q, flags=re.UNICODE)
        if words:
            add(
                "f.id IN (SELECT figure_id FROM figures_fts WHERE figures_fts MATCH ?)",
                " AND ".join('"' + w.replace('"', "") + '"*' for w in words[:15]),
            )
    for field, value in [
        ("p.venue", venue),
        ("p.layout_type", layout),
        ("f.span_type", span),
        ("f.archetype", archetype),
    ]:
        if value:
            if value == "HF 高热":
                add("p.hf_upvotes>=?", get_settings().hf_min_upvotes)
            else:
                add(field + "=?", value)
    if domain:
        add("EXISTS (SELECT 1 FROM json_each(p.domains) WHERE value=?)", domain)
    if color:
        add("EXISTS (SELECT 1 FROM json_each(f.color_buckets) WHERE value=?)", color)
    tags = [t for t in sub_tags.split("|") if t]
    if tags:
        clauses = [
            "EXISTS (SELECT 1 FROM json_each(f.sub_tags) WHERE value=?)" for _ in tags
        ]
        add("(" + (" AND " if tag_mode == "all" else " OR ").join(clauses) + ")", *tags)
    if honors:
        add("p.venue_tier IN ('oral','spotlight')")
    if view == "method":
        add("f.archetype IN ('Teaser','Pipeline','Micro-Mechanism')")
    if view == "data":
        add("f.archetype IN ('Curve','Bar','Scatter/Radar','Heatmap')")
    if not show_cases:
        add("f.archetype!='Case Study'")
    suffix = "WHERE " + " AND ".join(where) if where else ""
    return suffix, args


@router.get("/figures")
def list_figures(
    q: str = "",
    domain: str = "",
    sub_tags: str = "",
    tag_mode: Literal["any", "all"] = "any",
    venue: str = "",
    layout: str = "",
    span: str = "",
    archetype: str = "",
    color: str = "",
    view: Literal["all", "method", "data"] = "all",
    honors: bool = False,
    show_cases: bool = False,
    sort: Literal["newest", "popular"] = "newest",
    offset: int = Query(0, ge=0),
    limit: int = Query(24, ge=1, le=100),
):
    suffix, args = figure_conditions(
        q,
        domain,
        sub_tags,
        tag_mode,
        venue,
        layout,
        span,
        archetype,
        color,
        view,
        honors,
        show_cases,
    )
    with connect() as db:
        total = db.execute(
            "SELECT COUNT(*) FROM figures f JOIN papers p ON p.id=f.paper_id " + suffix,
            args,
        ).fetchone()[0]
        ordering = "p.hf_upvotes DESC," if sort == "popular" else ""
        rows = db.execute(
            SELECT
            + suffix
            + " ORDER BY "
            + ordering
            + "f.created_at DESC,f.id DESC LIMIT ? OFFSET ?",
            args + [limit, offset],
        ).fetchall()
    return {
        "items": [deserialize(r) for r in rows],
        "total": total,
        "next_offset": offset + len(rows) if offset + len(rows) < total else None,
    }


def figure_number(figure):
    numbers = re.findall(r"\d+", figure["fig_label"])
    return (
        tuple(map(int, numbers)) if numbers else (10**9,),
        figure["page_number"],
        figure["id"],
    )


def feed_figure(row):
    figure = deserialize(row)
    figure["palette_top5"] = figure["palette"]["colors"][:5]
    figure["subfigure_count"] = len(figure["subitems"])
    return figure


@router.get("/figures/feed")
def figure_feed(
    group_by: Literal["paper", "none"] = "paper",
    q: str = "",
    domain: str = "",
    sub_tags: str = "",
    tag_mode: Literal["any", "all"] = "any",
    venue: str = "",
    layout: str = "",
    span: str = "",
    archetype: str = "",
    color: str = "",
    view: Literal["all", "method", "data"] = "all",
    honors: bool = False,
    show_cases: bool = False,
    sort: Literal["newest", "popular"] = "newest",
    offset: int = Query(0, ge=0),
    limit: int = Query(16, ge=1, le=100),
):
    suffix, args = figure_conditions(
        q,
        domain,
        sub_tags,
        tag_mode,
        venue,
        layout,
        span,
        archetype,
        color,
        view,
        honors,
        show_cases,
    )
    base = " FROM figures f JOIN papers p ON p.id=f.paper_id "
    with connect() as db:
        db.execute("BEGIN")
        counts = db.execute(
            "SELECT COUNT(*) AS figures,COUNT(DISTINCT f.paper_id) AS papers"
            + base
            + suffix,
            args,
        ).fetchone()
        if group_by == "none":
            order = "p.hf_upvotes DESC," if sort == "popular" else ""
            rows = db.execute(
                SELECT
                + suffix
                + " ORDER BY "
                + order
                + "f.created_at DESC,f.id DESC LIMIT ? OFFSET ?",
                args + [limit, offset],
            ).fetchall()
            items = [feed_figure(row) for row in rows]
            total = counts["figures"]
        else:
            order = "MAX(p.hf_upvotes) DESC," if sort == "popular" else ""
            ids = [
                r[0]
                for r in db.execute(
                    "SELECT f.paper_id"
                    + base
                    + suffix
                    + " GROUP BY f.paper_id ORDER BY "
                    + order
                    + "MAX(f.created_at) DESC,f.paper_id DESC LIMIT ? OFFSET ?",
                    args + [limit, offset],
                )
            ]
            rows = []
            if ids:
                restricted = (
                    suffix
                    + (" AND " if suffix else "WHERE ")
                    + "f.paper_id IN ("
                    + ",".join("?" for _ in ids)
                    + ")"
                )
                rows = db.execute(SELECT + restricted, args + ids).fetchall()
            groups = {pid: [] for pid in ids}
            for row in rows:
                groups[row["paper_id"]].append(feed_figure(row))
            rank = {
                "Framework": 0,
                "Pipeline": 0,
                "Teaser": 1,
                "Motivation": 1,
                "Micro-Mechanism": 2,
                "Curve": 3,
                "Bar": 3,
                "Scatter/Radar": 3,
                "Heatmap": 3,
            }
            items = []
            for pid, figures in groups.items():
                figures.sort(key=figure_number)
                hero = min(
                    figures,
                    key=lambda f: (rank.get(f["archetype"], 4), figure_number(f)),
                )
                paper = {
                    key: hero[key]
                    for key in (
                        "title",
                        "authors",
                        "abstract",
                        "venue",
                        "venue_year",
                        "venue_tier",
                        "hf_upvotes",
                        "layout_type",
                        "source_urls",
                        "domains",
                        "arxiv_id",
                    )
                }
                paper["id"] = pid
                items.append(
                    {
                        "paper": paper,
                        "hero_figure_id": hero["id"],
                        "matched_figures": figures,
                    }
                )
            total = counts["papers"]
    return {
        "group_by": group_by,
        "items": items,
        "total": total,
        "total_papers": counts["papers"],
        "total_figures": counts["figures"],
        "next_offset": offset + len(items) if offset + len(items) < total else None,
    }


@router.get("/papers/{pid}/figures")
def sibling_figures(
    pid: str,
    q: str = "",
    domain: str = "",
    sub_tags: str = "",
    tag_mode: Literal["any", "all"] = "any",
    venue: str = "",
    layout: str = "",
    span: str = "",
    archetype: str = "",
    color: str = "",
    view: Literal["all", "method", "data"] = "all",
    honors: bool = False,
    show_cases: bool = True,
):
    suffix, args = figure_conditions(
        q,
        domain,
        sub_tags,
        tag_mode,
        venue,
        layout,
        span,
        archetype,
        color,
        view,
        honors,
        show_cases,
    )
    suffix += (" AND " if suffix else "WHERE ") + "p.id=?"
    with connect() as db:
        db.execute("BEGIN")
        if not db.execute("SELECT id FROM papers WHERE id=?", (pid,)).fetchone():
            raise HTTPException(404, "论文不存在")
        total = db.execute(
            "SELECT COUNT(*) FROM figures WHERE paper_id=?", (pid,)
        ).fetchone()[0]
        figures = [
            feed_figure(row) for row in db.execute(SELECT + suffix, args + [pid])
        ]
    figures.sort(key=figure_number)
    return {
        "paper_id": pid,
        "items": figures,
        "matched_count": len(figures),
        "total": total,
    }


@router.get("/figures/{fid}")
def get_figure(fid: str):
    return figure(fid)


@router.post("/figures/{fid}/view")
def record_view(fid: str, user=Depends(require_user)):
    figure(fid)
    with connect() as db:
        db.execute(
            "INSERT INTO view_history VALUES(?,?,CURRENT_TIMESTAMP) ON CONFLICT(user_id,figure_id) DO UPDATE SET viewed_at=CURRENT_TIMESTAMP",
            (user["id"], fid),
        )
    return {"ok": True}


@router.get("/assets/{kind}/{filename}")
async def asset(kind: Literal["thumb", "hd", "raw"], filename: str, v: str = ""):
    fid = filename.rsplit(".", 1)[0]
    with connect() as db:
        r = db.execute(
            "SELECT asset_base,version_hash FROM figures WHERE id=?", (fid,)
        ).fetchone()
    if not r:
        raise HTTPException(404, "图片不存在")
    ext = ".pdf" if kind == "raw" else ".webp"
    # Never cache new bytes under an obsolete version URL.
    if v and v != r["version_hash"]:
        raise HTTPException(404, "图片版本已更新")
    try:
        data = await Storage().get(r["asset_base"] + "_" + kind + ext)
    except Exception:
        raise HTTPException(502, "远端图像暂时不可用，请稍后重试")
    headers = {
        "Cache-Control": "public, max-age=31536000, immutable"
        if v
        else "public, max-age=60",
        "ETag": '"' + r["version_hash"] + '"',
    }
    if kind == "raw":
        headers["Content-Disposition"] = f'attachment; filename="{fid}.pdf"'
    return Response(
        data,
        media_type="application/pdf" if kind == "raw" else "image/webp",
        headers=headers,
    )


@router.get("/figures/{fid}/subitems/{sid}/raw")
async def sub_raw(fid: str, sid: str):
    with connect() as db:
        r = db.execute("SELECT subitems FROM figures WHERE id=?", (fid,)).fetchone()
    if not r:
        raise HTTPException(404)
    sub = next((s for s in json.loads(r[0]) if s["id"] == sid), None)
    if not sub or not sub.get("raw_path"):
        raise HTTPException(404, "该子图没有独立原始资产")
    return Response(
        await Storage().get(sub["raw_path"]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="sub_{sid}.pdf"',
            "Cache-Control": "public, max-age=60",
        },
    )


@router.get("/papers/{pid}/pdf")
async def paper_pdf(pid: str):
    with connect() as db:
        r = db.execute(
            "SELECT webdav_pdf_path FROM papers WHERE id=?", (pid,)
        ).fetchone()
    if not r:
        raise HTTPException(404)
    return Response(
        await Storage().get(r[0]),
        media_type="application/pdf",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/figures/{fid}/page")
async def page_preview(fid: str, page: int | None = None, user=Depends(require_user)):
    with connect() as db:
        r = db.execute(
            "SELECT f.page_number,f.bbox,p.webdav_pdf_path FROM figures f JOIN papers p ON p.id=f.paper_id WHERE f.id=?",
            (fid,),
        ).fetchone()
    if not r:
        raise HTTPException(404)
    data = await Storage().get(r["webdav_pdf_path"])
    root = get_settings().data_dir / ".pipeline" / "work"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as work:
        path = Path(work) / "paper.pdf"
        path.write_bytes(data)
        n = page or r["page_number"]
        try:
            result = await cpu_call("preview", path, page=n, bbox=json.loads(r["bbox"]))
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    return Response(
        result["image"],
        media_type="image/png",
        headers={
            "Cache-Control": "private, no-store",
            "X-Page-Count": str(result["count"]),
            "X-Crop-Bbox": json.dumps(result["bbox"]),
            "X-Page-Number": str(n),
        },
    )


class Recrop(BaseModel):
    page: int = Field(ge=1, le=150)
    bbox: list[float] = Field(min_length=4, max_length=4)
    snap_vector: bool = True


@router.post("/figures/{fid}/recrop")
async def recrop_figure(fid: str, body: Recrop, user=Depends(require_user)):
    try:
        await recrop(fid, body.page, body.bbox, body.snap_vector)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return figure(fid)


@router.post("/figures/{fid}/repair")
def request_repair(fid: str, user=Depends(require_user)):
    figure(fid)
    with connect() as db:
        pending = db.execute(
            "SELECT id FROM repair_queue WHERE figure_id=? AND status='pending'", (fid,)
        ).fetchone()
        if pending:
            return {"id": pending[0], "status": "pending"}
        rid = uuid.uuid4().hex
        db.execute(
            "INSERT INTO repair_queue(id,figure_id,requested_by) VALUES(?,?,?)",
            (rid, fid, user["id"]),
        )
    return {"id": rid, "status": "pending"}


class Tags(BaseModel):
    archetype: Literal[
        "Teaser",
        "Pipeline",
        "Micro-Mechanism",
        "Curve",
        "Bar",
        "Scatter/Radar",
        "Heatmap",
        "Case Study",
    ]
    sub_tags: list[str] = Field(default_factory=list, max_length=20)


@router.patch("/figures/{fid}")
async def update_tags(fid: str, body: Tags, user=Depends(require_user)):
    f = figure(fid)
    with connect() as db:
        db.execute(
            "UPDATE figures SET archetype=?,sub_tags=? WHERE id=?",
            (body.archetype, json.dumps(body.sub_tags), fid),
        )
    from .ingest import backup

    await backup(f["paper_id"])
    return figure(fid)


class LinkIngest(BaseModel):
    input: str = Field(max_length=1000)
    domains: list[str] = Field(default_factory=list)
    venue: str = Field(default="Preprint", max_length=80)
    collection_id: str | None = None


@router.post("/ingest/link", status_code=202)
async def ingest_link(body: LinkIngest, user=Depends(require_user)):
    try:
        await resolve(body.input)
    except ValueError as e:
        raise HTTPException(400, str(e))
    check_job_limit(user["id"])
    metadata = {"venue": body.venue}
    if body.domains:
        metadata["domains"] = body.domains
    jid = new_job(user["id"], "ingest", {"input": body.input})
    launch(
        run_ingest(
            jid,
            user["id"],
            value=body.input,
            metadata=metadata,
            collection_id=body.collection_id,
        )
    )
    return {"job_id": jid}


@router.get("/ingest/preview")
async def preview(input: str, user=Depends(require_user)):
    try:
        _, meta = await resolve(input)
        return meta
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/ingest/check")
def check_hash(body: dict, user=Depends(require_user)):
    with connect() as db:
        r = db.execute(
            "SELECT id,title FROM papers WHERE file_sha256=?",
            (str(body.get("sha256", ""))[:64],),
        ).fetchone()
    return {"paper": dict(r) if r else None}


def check_job_limit(uid):
    with connect() as db:
        n = db.execute(
            "SELECT COUNT(*) FROM jobs WHERE user_id=? AND status IN ('queued','running') AND json_extract(payload,'$.batch_id') IS NULL",
            (uid,),
        ).fetchone()[0]
    if n >= 3:
        raise HTTPException(429, "最多同时排队 3 个任务")


@router.post("/ingest/pdf", status_code=202)
async def ingest_upload(
    file: UploadFile = File(),
    domains: str = Form(""),
    venue: str = Form("Preprint"),
    collection_id: str = Form(""),
    user=Depends(require_user),
):
    check_job_limit(user["id"])
    chunks = []
    size = 0
    while chunk := await file.read(1024 * 1024):
        size += len(chunk)
        if size > get_settings().max_pdf_bytes:
            raise HTTPException(413, "PDF 不能超过 50MB")
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data.lstrip().startswith(b"%PDF"):
        raise HTTPException(400, "请上传有效的 PDF 文件")
    meta = {"venue": venue[:80]}
    if domains:
        meta["domains"] = [
            d for d in domains.split(",") if d in {x["slug"] for x in all_domains()}
        ]
    jid = new_job(user["id"], "ingest", {"filename": (file.filename or "")[:200]})
    launch(
        run_ingest(
            jid,
            user["id"],
            data=data,
            metadata=meta,
            collection_id=collection_id or None,
        )
    )
    return {"job_id": jid}


@router.get("/jobs")
def jobs(user=Depends(require_user)):
    with connect() as db:
        rows = db.execute(
            "SELECT id,kind,status,progress,message,created_at,updated_at FROM jobs "
            + ("" if user["role"] == "admin" else "WHERE user_id=? ")
            + "ORDER BY created_at DESC LIMIT 30",
            () if user["role"] == "admin" else (user["id"],),
        ).fetchall()
    return [dict(r) for r in rows]


class Collection(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)


def owned_collection(db, cid, uid):
    if not db.execute(
        "SELECT id FROM collections WHERE id=? AND user_id=?", (cid, uid)
    ).fetchone():
        raise HTTPException(404, "看板不存在")


@router.get("/collections")
def collections(user=Depends(require_user)):
    with connect() as db:
        rows = db.execute(
            "SELECT c.*,(SELECT COUNT(*) FROM collection_items i WHERE i.collection_id=c.id) AS count FROM collections c WHERE c.user_id=? ORDER BY c.updated_at DESC",
            (user["id"],),
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/collections", status_code=201)
def create_collection(body: Collection, user=Depends(require_user)):
    cid = uuid.uuid4().hex
    with connect() as db:
        db.execute(
            "INSERT INTO collections(id,user_id,name,description) VALUES(?,?,?,?)",
            (cid, user["id"], body.name, body.description),
        )
    return {"id": cid, **body.model_dump()}


@router.patch("/collections/{cid}")
def edit_collection(cid: str, body: Collection, user=Depends(require_user)):
    with connect() as db:
        owned_collection(db, cid, user["id"])
        db.execute(
            "UPDATE collections SET name=?,description=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (body.name, body.description, cid),
        )
    return {"ok": True}


@router.delete("/collections/{cid}")
def delete_collection(cid: str, user=Depends(require_user)):
    with connect() as db:
        owned_collection(db, cid, user["id"])
        db.execute("DELETE FROM collections WHERE id=?", (cid,))
    return {"ok": True}


@router.get("/collections/{cid}")
def get_collection(cid: str, user=Depends(require_user)):
    with connect() as db:
        owned_collection(db, cid, user["id"])
        c = dict(db.execute("SELECT * FROM collections WHERE id=?", (cid,)).fetchone())
        items = db.execute(
            SELECT
            + "JOIN collection_items i ON i.figure_id=f.id WHERE i.collection_id=? ORDER BY i.created_at DESC",
            (cid,),
        ).fetchall()
        notes = {
            r["figure_id"]: dict(r)
            for r in db.execute(
                "SELECT * FROM collection_items WHERE collection_id=?", (cid,)
            )
        }
    c["items"] = [dict(deserialize(r), collection_item=notes[r["id"]]) for r in items]
    return c


class CollectionItem(BaseModel):
    figure_id: str
    focused_subitem_id: str | None = None
    user_note: str = Field(default="", max_length=4000)


@router.put("/collections/{cid}/items")
def save_item(cid: str, body: CollectionItem, user=Depends(require_user)):
    f = figure(body.figure_id)
    if body.focused_subitem_id and body.focused_subitem_id not in {
        s["id"] for s in f["subitems"]
    }:
        raise HTTPException(400, "子图不存在")
    with connect() as db:
        owned_collection(db, cid, user["id"])
        existing = db.execute(
            "SELECT user_note,focused_subitem_id FROM collection_items WHERE collection_id=? AND figure_id=?",
            (cid, body.figure_id),
        ).fetchone()
        if existing:
            if "user_note" not in body.model_fields_set:
                body.user_note = existing["user_note"]
            if "focused_subitem_id" not in body.model_fields_set:
                body.focused_subitem_id = existing["focused_subitem_id"]
        db.execute(
            "INSERT INTO collection_items(id,collection_id,figure_id,focused_subitem_id,user_note) VALUES(?,?,?,?,?) ON CONFLICT(collection_id,figure_id) DO UPDATE SET focused_subitem_id=excluded.focused_subitem_id,user_note=excluded.user_note",
            (
                uuid.uuid4().hex,
                cid,
                body.figure_id,
                body.focused_subitem_id,
                body.user_note,
            ),
        )
        db.execute(
            "UPDATE collections SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (cid,)
        )
    return {"ok": True}


class BulkCollectionItems(BaseModel):
    figure_ids: list[str] = Field(min_length=1, max_length=500)


@router.put("/collections/{cid}/items/bulk")
def save_items(cid: str, body: BulkCollectionItems, user=Depends(require_user)):
    ids = list(dict.fromkeys(body.figure_ids))
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        owned_collection(db, cid, user["id"])
        found = db.execute(
            "SELECT COUNT(*) FROM figures WHERE id IN ("
            + ",".join("?" for _ in ids)
            + ")",
            ids,
        ).fetchone()[0]
        if found != len(ids):
            raise HTTPException(404, "部分图表已不存在")
        for fid in ids:
            db.execute(
                "INSERT OR IGNORE INTO collection_items(id,collection_id,figure_id) VALUES(?,?,?)",
                (uuid.uuid4().hex, cid, fid),
            )
        db.execute(
            "UPDATE collections SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (cid,)
        )
    return {"ok": True, "count": len(ids)}


@router.delete("/collections/{cid}/items/{fid}")
def delete_item(cid: str, fid: str, user=Depends(require_user)):
    with connect() as db:
        owned_collection(db, cid, user["id"])
        db.execute(
            "DELETE FROM collection_items WHERE collection_id=? AND figure_id=?",
            (cid, fid),
        )
    return {"ok": True}


@router.get("/collections/{cid}/export")
async def export_collection(cid: str, user=Depends(require_user)):
    with connect() as db:
        owned_collection(db, cid, user["id"])
        rows = db.execute(
            "SELECT f.*,i.user_note FROM figures f JOIN collection_items i ON i.figure_id=f.id WHERE i.collection_id=?",
            (cid,),
        ).fetchall()
    if len(rows) > 100:
        raise HTTPException(400, "单次最多导出 100 张图，请拆分看板")
    out = io.BytesIO()
    tex = []
    py = ["# FigPrism scientific palettes"]
    notes = []
    size = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for i, r in enumerate(rows):
            for suffix, ext in [("raw", "pdf"), ("hd", "webp")]:
                data = await Storage().get(r["asset_base"] + "_" + suffix + "." + ext)
                size += len(data)
                if size > 200 * 1024**2:
                    raise HTTPException(413, "看板超过 200MB，请拆分后导出")
                z.writestr(f"{i + 1:03}_{r['id']}.{ext}", data)
            colors = [c["hex"] for c in json.loads(r["palette"])["colors"]]
            py.append(f"figure_{i + 1} = {colors!r}")
            tex.extend(
                "\\definecolor{fig"
                + str(i + 1)
                + "Color"
                + str(j + 1)
                + "}{HTML}{"
                + c[1:]
                + "}"
                for j, c in enumerate(colors)
            )
            notes.append(
                {"figure_id": r["id"], "note": r["user_note"], "caption": r["caption"]}
            )
        z.writestr("palettes.tex", "\n".join(tex))
        z.writestr("palettes.py", "\n".join(py))
        z.writestr("notes.json", json.dumps(notes, ensure_ascii=False, indent=2))
    return Response(
        out.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="figprism-moodboard.zip"'
        },
    )


class ColorCopy(BaseModel):
    figure_id: str
    hex_code: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    copied_format: str = Field(default="HEX", max_length=30)


@router.post("/me/palette-history")
def record_color(body: ColorCopy, user=Depends(require_user)):
    figure(body.figure_id)
    with connect() as db:
        db.execute(
            "INSERT INTO palette_history(user_id,figure_id,hex_code,copied_format) VALUES(?,?,?,?)",
            (user["id"], body.figure_id, body.hex_code.upper(), body.copied_format),
        )
    return {"ok": True}


@router.get("/me/history")
def history(
    kind: Literal["views", "colors"] = "views",
    offset: int = Query(0, ge=0),
    user=Depends(require_user),
):
    with connect() as db:
        if kind == "views":
            rows = db.execute(
                SELECT
                + "JOIN view_history h ON h.figure_id=f.id WHERE h.user_id=? ORDER BY h.viewed_at DESC LIMIT 60 OFFSET ?",
                (user["id"], offset),
            ).fetchall()
            times = {
                r["figure_id"]: r["viewed_at"]
                for r in db.execute(
                    "SELECT figure_id,viewed_at FROM view_history WHERE user_id=?",
                    (user["id"],),
                )
            }
            return [dict(deserialize(r), viewed_at=times[r["id"]]) for r in rows]
        rows = db.execute(
            "SELECT h.*,p.title,f.version_hash FROM palette_history h JOIN figures f ON f.id=h.figure_id JOIN papers p ON p.id=f.paper_id WHERE h.user_id=? ORDER BY h.created_at DESC,h.id DESC LIMIT 100 OFFSET ?",
            (user["id"], offset),
        ).fetchall()
        return [dict(r) for r in rows]


@router.get("/stream/events")
async def stream(request: Request):
    last = request.headers.get("last-event-id", "0")
    try:
        last = int(last)
    except ValueError:
        last = 0
    if not last:
        with connect() as db:
            last = db.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0]

    async def generate():
        nonlocal last
        yield "retry: 4000\n\n"
        ticks = 0
        while not await request.is_disconnected():
            with connect() as db:
                rows = db.execute(
                    "SELECT * FROM events WHERE id>? ORDER BY id LIMIT 100", (last,)
                ).fetchall()
            for r in rows:
                last = r["id"]
                yield f"id: {last}\nevent: {r['kind']}\ndata: {r['payload']}\n\n"
            ticks += 1
            if ticks % 10 == 0:
                yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/admin/overview")
def admin_overview(user=Depends(require_admin)):
    with connect() as db:
        users = [
            dict(r)
            for r in db.execute(
                "SELECT id,username,role,is_active,created_at FROM users"
            )
        ]
        pending = db.execute(
            "SELECT COUNT(*) FROM figures WHERE review_status='needs_review'"
        ).fetchone()[0]
        repairs = [
            dict(r)
            for r in db.execute(
                "SELECT id,figure_id,status,created_at FROM repair_queue ORDER BY created_at DESC LIMIT 50"
            )
        ]
    return {
        "users": users,
        "review_count": pending,
        "repairs": repairs,
        "domains": all_domains(False),
        "vision_driver": get_settings().vision.driver,
        "vision_model": get_settings().vision.model,
    }


@router.post("/admin/invites")
def invite(user=Depends(require_admin)):
    code = secrets.token_urlsafe(24)
    expires = (datetime.now(timezone.utc) + timedelta(days=7)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    with connect() as db:
        db.execute(
            "INSERT INTO invite_codes(code,created_by,expires_at) VALUES(?,?,?)",
            (code, user["id"], expires),
        )
    return {
        "code": code,
        "url": get_settings().public_origin + "/?invite=" + code,
        "expires_at": expires,
    }


class UserState(BaseModel):
    is_active: bool


@router.patch("/admin/users/{uid}")
def set_user(uid: int, body: UserState, user=Depends(require_admin)):
    if uid == user["id"]:
        raise HTTPException(400, "不能停用当前账号")
    with connect() as db:
        db.execute(
            "UPDATE users SET is_active=? WHERE id=?", (int(body.is_active), uid)
        )
        if not body.is_active:
            db.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
    return {"ok": True}


class DomainConfig(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9-]{1,64}$")
    name: str = Field(min_length=1, max_length=100)
    color_dot: str = Field(default="#8b85d6", pattern=r"^#[0-9A-Fa-f]{6}$")
    arxiv_cats: list[str] = Field(default_factory=list)
    phrases: list[str] = Field(default_factory=list, max_length=300)
    acronyms: list[str] = Field(default_factory=list, max_length=100)
    exclude_terms: list[str] = Field(default_factory=list, max_length=100)
    sub_tags: list[str] = Field(default_factory=list, max_length=100)
    vlm_criteria: str = Field(default="", max_length=5000)
    is_active: bool = True


@router.put("/admin/domains")
def update_domains(body: list[DomainConfig], user=Depends(require_admin)):
    if not 1 <= len(body) <= 50 or len({x.slug for x in body}) != len(body):
        raise HTTPException(400, "领域数量或 slug 不合法")
    save_domains([x.model_dump() for x in body])
    return {"ok": True}


class SyncRequest(BaseModel):
    kind: Literal["sync", "backfill", "rebuild"] = "sync"
    domain: str = "all"
    limit: int = Field(default=5, ge=1, le=50)


@router.post("/admin/sync", status_code=202)
async def admin_sync(body: SyncRequest, user=Depends(require_admin)):
    check_job_limit(user["id"])
    jid = new_job(user["id"], body.kind, body.model_dump())

    async def run():
        try:
            if body.kind == "rebuild":
                n = await rebuild()
                update_job(jid, 100, f"已重建 {n} 张图表", "completed")
            else:
                from .sources import sync

                await sync(
                    backfill=body.kind == "backfill",
                    domain=body.domain,
                    limit=body.limit,
                    job_id=jid,
                    user_id=user["id"],
                )
        except Exception as exc:
            update_job(jid, 0, error_message(exc), "failed")

    launch(run())
    return {"job_id": jid}
