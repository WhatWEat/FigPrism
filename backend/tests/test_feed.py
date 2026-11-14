import json
import pytest
from figprism.db import connect
from figprism.auth import create_user


@pytest.fixture
def library(client):
    with connect() as db:
        for pid in ["paper-a", "paper-b", "paper-c"]:
            db.execute(
                "INSERT INTO papers(id,doc_uid,file_sha256,title,domains) VALUES(?,?,?,?,?)",
                (
                    pid,
                    pid,
                    pid,
                    pid,
                    json.dumps(["memory"] if pid != "paper-c" else ["reasoning"]),
                ),
            )
        for fid, pid, label, kind, bucket in [
            ("a10", "paper-a", "Fig. 10", "Curve", "8"),
            ("a2", "paper-a", "Fig. 2", "Pipeline", "1"),
            ("a1", "paper-a", "Fig. 1", "Teaser", "1"),
            ("b1", "paper-b", "Fig. 1", "Bar", "8"),
            ("b2", "paper-b", "Fig. 2", "Case Study", "1"),
            ("c1", "paper-c", "Fig. 1", "Heatmap", "8"),
        ]:
            db.execute(
                "INSERT INTO figures(id,paper_id,fig_label,page_number,bbox,archetype,width,height,aspect_ratio,palette,color_buckets,asset_base,version_hash) VALUES(?,?,?,1,?,?,?,?,?,?,?,?,?)",
                (
                    fid,
                    pid,
                    label,
                    "[0,0,400,200]",
                    kind,
                    400,
                    200,
                    2,
                    json.dumps({"colors": [], "pairs": [], "neutrals": []}),
                    json.dumps([bucket]),
                    fid,
                    "v1",
                ),
            )
            db.execute(
                "INSERT INTO figures_fts VALUES(?,?,?,?)", (fid, pid, kind, "Helvetica")
            )
        db.execute("UPDATE figures SET fonts='[\"Helvetica\"]'")
    return client


def test_group_pagination_natural_order_and_representative(library):
    first = library.get("/api/figures/feed?limit=2").json()
    assert first["group_by"] == "paper" and len(first["items"]) == 2
    assert (
        first["total"] == 3
        and first["total_figures"] == 5
        and first["next_offset"] == 2
    )
    second = library.get("/api/figures/feed?limit=2&offset=2").json()
    assert len(second["items"]) == 1 and second["next_offset"] is None
    groups = first["items"] + second["items"]
    assert len({g["paper"]["id"] for g in groups}) == 3
    a = next(g for g in groups if g["paper"]["id"] == "paper-a")
    assert [f["id"] for f in a["matched_figures"]] == ["a1", "a2", "a10"]
    assert a["hero_figure_id"] == "a2"
    assert all(
        "thumb_url" in f and "palette_top5" in f and "subfigure_count" in f
        for f in a["matched_figures"]
    )


def test_filters_apply_before_grouping_and_flat_remains_available(library):
    data = library.get("/api/figures/feed?domain=memory&color=8").json()
    assert data["total"] == 2 and data["total_figures"] == 2
    assert {f["id"] for g in data["items"] for f in g["matched_figures"]} == {
        "a10",
        "b1",
    }
    data = library.get("/api/figures/feed?archetype=Curve").json()
    assert data["items"][0]["hero_figure_id"] == "a10"
    data = library.get(
        "/api/figures/feed?q=font:Helvetica%20ratio:%3E1.5&view=method"
    ).json()
    assert data["total"] == 1 and data["total_figures"] == 2
    flat = library.get("/api/figures/feed?group_by=none&limit=2").json()
    assert (
        flat["total"] == 5
        and flat["next_offset"] == 2
        and "paper_id" in flat["items"][0]
    )
    assert library.get("/api/figures/feed?group_by=invalid").status_code == 422


def test_siblings_are_complete_and_naturally_sorted(library):
    data = library.get("/api/papers/paper-a/figures").json()
    assert [f["id"] for f in data["items"]] == ["a1", "a2", "a10"]
    assert len(library.get("/api/papers/paper-b/figures").json()["items"]) == 2
    assert library.get("/api/papers/missing/figures").status_code == 404


def test_bulk_collection_requires_owner_and_preserves_notes(library):
    create_user("alice", "long-enough-password")
    create_user("bob", "long-enough-password")
    assert (
        library.put(
            "/api/collections/x/items/bulk", json={"figure_ids": ["a1"]}
        ).status_code
        == 401
    )
    library.post(
        "/api/auth/login",
        json={"username": "alice", "password": "long-enough-password"},
    )
    cid = library.post("/api/collections", json={"name": "Whole paper"}).json()["id"]
    library.put(
        f"/api/collections/{cid}/items",
        json={"figure_id": "a1", "user_note": "Keep my note"},
    )
    assert (
        library.put(
            f"/api/collections/{cid}/items/bulk",
            json={"figure_ids": ["a1", "a2", "a10", "a1"]},
        ).json()["count"]
        == 3
    )
    data = library.get("/api/collections/" + cid).json()["items"]
    assert (
        len(data) == 3
        and next(f for f in data if f["id"] == "a1")["collection_item"]["user_note"]
        == "Keep my note"
    )
    assert (
        library.put(
            f"/api/collections/{cid}/items/bulk", json={"figure_ids": ["b1", "missing"]}
        ).status_code
        == 404
    )
    assert len(library.get("/api/collections/" + cid).json()["items"]) == 3
    library.post("/api/auth/logout")
    library.post(
        "/api/auth/login", json={"username": "bob", "password": "long-enough-password"}
    )
    assert (
        library.put(
            f"/api/collections/{cid}/items/bulk", json={"figure_ids": ["b1"]}
        ).status_code
        == 404
    )
