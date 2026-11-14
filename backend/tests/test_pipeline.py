import io
import json
import tarfile
import fitz
import pytest
from PIL import Image, ImageDraw
from figprism.palette import extract_palette
from figprism.tex import unpack, figures
from figprism.extraction import detect, render
from figprism.ingest import ingest_pdf
from figprism.auth import create_user
from figprism.db import connect
from figprism.storage import Storage


@pytest.fixture
def paper():
    d = fitz.open()
    p = d.new_page(width=600, height=800)
    p.insert_text((50, 50), "A Test of Scientific Figure Extraction", fontsize=20)
    p.draw_rect(
        fitz.Rect(70, 100, 240, 190),
        color=(0.14, 0.35, 0.66),
        fill=(0.88, 0.93, 0.99),
        width=2,
    )
    p.draw_rect(
        fitz.Rect(330, 100, 500, 190),
        color=(0.2, 0.6, 0.4),
        fill=(0.9, 0.98, 0.91),
        width=2,
    )
    p.draw_line((240, 145), (330, 145), color=(0.2, 0.2, 0.2), width=2)
    p.insert_text((100, 145), "Encoder", fontsize=16)
    p.insert_text((360, 145), "Decoder", fontsize=16)
    p.insert_text(
        (70, 220), "Figure 1: Overview of the model architecture.", fontsize=11
    )
    raw = d.tobytes()
    d.close()
    return raw


def test_palette_background_and_pairing():
    im = Image.new("RGB", (300, 200), "white")
    draw = ImageDraw.Draw(im)
    draw.rectangle((10, 10, 200, 180), fill="#E1EDFA", outline="#24589F", width=18)
    palette = extract_palette(im)
    assert all(c["hex"] != "#FFFFFF" for c in palette["colors"])
    assert any(
        p["fill"] == "#E1EDFA" and p["stroke"] == "#24589F" for p in palette["pairs"]
    )


def test_vector_crop_keeps_text(paper, client):
    with fitz.open(stream=paper, filetype="pdf") as d:
        crops = detect(d[0])
        assert len(crops) == 1
        result = render(d, crops[0])
        assert result["width"] > 2000
        assert result["blurhash"]
        with fitz.open(stream=result["raw"], filetype="pdf") as out:
            assert out[0].rect.width < 500
            assert "Encoder" in out[0].get_text()
            assert out[0].get_drawings()


def test_tex_archive_does_not_extract_traversal():
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as t:
        for name, body in [
            ("../outside.tex", b"bad"),
            (
                "main.tex",
                b"\\documentclass{article}\\begin{figure}\\caption{A {nested} caption}\\end{figure}",
            ),
        ]:
            info = tarfile.TarInfo(name)
            info.size = len(body)
            t.addfile(info, io.BytesIO(body))
    files = unpack(out.getvalue())
    assert "../outside.tex" not in files
    assert figures(files)[0]["caption"] == "A nested caption"


@pytest.fixture
def fake_storage(monkeypatch):
    blobs = {}

    async def put(self, key, data, content_type="application/octet-stream"):
        blobs[key] = data

    async def get(self, key):
        return blobs[key]

    monkeypatch.setattr(Storage, "put", put)
    monkeypatch.setattr(Storage, "get", get)
    return blobs


@pytest.mark.asyncio
async def test_ingest_assets_search_and_ownership(client, paper, fake_storage):
    pid = await ingest_pdf(paper, vision_driver="codex_subagent")
    assert len(fake_storage) >= 5
    same = await ingest_pdf(paper, vision_driver="codex_subagent")
    assert same == pid
    res = client.get("/api/figures?q=Encoder")
    assert res.status_code == 200
    res = client.get("/api/figures?q=architecture")
    assert res.json()["total"] == 1
    f = res.json()["items"][0]
    assert f["review_status"] == "needs_review"
    assert "asset_base" not in f
    assert client.get(f["raw_url"]).content.startswith(b"%PDF")
    assert (
        client.get("/api/assets/hd/" + f["id"] + ".webp?v=obsolete").status_code == 404
    )
    assert (
        client.post("/api/ingest/link", json={"input": "2501.00001"}).status_code == 401
    )
    assert client.post("/api/collections", json={"name": "test"}).status_code == 401
    for name in ("alice", "bob"):
        create_user(name, "long-enough-password")
    client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "long-enough-password"},
    )
    cid = client.post("/api/collections", json={"name": "My board"}).json()["id"]
    assert (
        client.put(
            "/api/collections/" + cid + "/items",
            json={"figure_id": f["id"], "user_note": "Use these colors"},
        ).status_code
        == 200
    )
    client.put("/api/collections/" + cid + "/items", json={"figure_id": f["id"]})
    assert (
        client.get("/api/collections/" + cid).json()["items"][0]["collection_item"][
            "user_note"
        ]
        == "Use these colors"
    )
    assert client.get("/api/collections/" + cid + "/export").status_code == 200
    assert client.post("/api/figures/" + f["id"] + "/view").status_code == 200
    assert len(client.get("/api/me/history").json()) == 1
    assert client.get("/api/admin/overview").status_code == 403
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/login", json={"username": "bob", "password": "long-enough-password"}
    )
    assert client.get("/api/collections/" + cid).status_code == 404
    assert client.get("/api/collections/" + cid + "/export").status_code == 404
    assert client.delete("/api/collections/" + cid).status_code == 404
    assert client.get("/api/me/history").json() == []


@pytest.mark.asyncio
async def test_network_allowlist():
    from figprism.network import fetch
    from figprism.ingest import resolve

    for url in (
        "http://127.0.0.1/internal",
        "https://arxiv.org.evil.invalid/pdf/test",
        "https://user@arxiv.org/pdf/1",
    ):
        with pytest.raises(ValueError):
            await fetch(url)
    with pytest.raises(ValueError):
        await resolve("https://evil.invalid/2501.12345")


def test_composite_caption_does_not_clip_left_panel(client):
    from figprism.extraction import geometry_crops

    d = fitz.open()
    p = d.new_page(width=600, height=800)
    for x in (70, 330):
        p.draw_rect(
            fitz.Rect(x, 70, x + 190, 160),
            color=(0.3, 0.4, 0.5),
            fill=(0.85, 0.9, 0.95),
        )
    p.insert_textbox(
        fitz.Rect(70, 165, 270, 220),
        "(a) Memory as Context. "
        + ("Explanation of the panel and its components. " * 5),
        fontsize=7,
    )
    p.insert_textbox(
        fitz.Rect(330, 165, 530, 220),
        "(b) Memory as Gate. " + ("Explanation of the panel and its components. " * 5),
        fontsize=7,
    )
    p.insert_text((170, 240), "Figure 3: Attention masks for Titans.", fontsize=11)
    crops = geometry_crops(p)
    assert len(crops) == 1
    assert crops[0].bbox[0] < 70 and crops[0].bbox[2] > 520
    result = render(d, crops[0])
    assert {s["id"] for s in result["subitems"]} == {"a", "b"}
    d.close()


@pytest.mark.asyncio
async def test_retry_partial_ingest_preserves_existing_figures(
    client, paper, fake_storage
):
    pid = await ingest_pdf(paper, vision_driver="codex_subagent")
    with connect() as db:
        fid = db.execute("SELECT id FROM figures WHERE paper_id=?", (pid,)).fetchone()[
            0
        ]
        db.execute("UPDATE papers SET ingest_status='processing' WHERE id=?", (pid,))
    again = await ingest_pdf(paper, vision_driver="codex_subagent")
    assert again == pid
    with connect() as db:
        assert (
            db.execute("SELECT id FROM figures WHERE paper_id=?", (pid,)).fetchall()[0][
                0
            ]
            == fid
        )
        assert db.execute("SELECT COUNT(*) FROM figures").fetchone()[0] == 1
        assert (
            db.execute(
                "SELECT ingest_status FROM papers WHERE id=?", (pid,)
            ).fetchone()[0]
            == "completed"
        )


@pytest.mark.asyncio
async def test_recrop_versions_assets_and_keeps_collection(client, paper, fake_storage):
    await ingest_pdf(paper, vision_driver="codex_subagent")
    f = client.get("/api/figures").json()["items"][0]
    old_url = f["hd_url"]
    assert "immutable" in client.get(old_url).headers["cache-control"]
    assert client.get("/api/figures/" + f["id"] + "/page").status_code == 401
    create_user("cropper", "long-enough-password")
    client.post(
        "/api/auth/login",
        json={"username": "cropper", "password": "long-enough-password"},
    )
    cid = client.post("/api/collections", json={"name": "Keep this figure"}).json()[
        "id"
    ]
    client.put("/api/collections/" + cid + "/items", json={"figure_id": f["id"]})
    preview = client.get("/api/figures/" + f["id"] + "/page")
    assert (
        preview.status_code == 200
        and preview.headers["cache-control"] == "private, no-store"
    )
    assert (
        client.post(
            "/api/figures/" + f["id"] + "/recrop",
            json={"page": 1, "bbox": [0.5, 0.5, 0.2, 0.2]},
        ).status_code
        == 400
    )
    r = client.post(
        "/api/figures/" + f["id"] + "/recrop",
        json={"page": 1, "bbox": [0.1, 0.1, 0.9, 0.25], "snap_vector": False},
    )
    assert r.status_code == 200
    assert r.json()["id"] == f["id"] and r.json()["hd_url"] != old_url
    assert client.get(old_url).status_code == 404
    assert client.get(r.json()["hd_url"]).status_code == 200
    assert client.get("/api/collections/" + cid).json()["items"][0]["id"] == f["id"]
