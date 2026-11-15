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


def test_sibling_filters_preserve_feed_scope_without_page_truncation(library):
    method = library.get(
        "/api/papers/paper-a/figures?view=method&show_cases=false&limit=1&offset=99"
    ).json()
    assert [f["id"] for f in method["items"]] == ["a1", "a2"]
    assert method["total"] == 3 and method["matched_count"] == 2
    data = library.get("/api/papers/paper-a/figures?view=data").json()
    assert [f["id"] for f in data["items"]] == ["a10"]
    assert data["total"] == 3 and data["matched_count"] == 1
    empty = library.get("/api/papers/paper-a/figures?view=method&color=8").json()
    assert empty["items"] == [] and empty["total"] == 3
    searched = library.get(
        "/api/papers/paper-a/figures?q=font:Helvetica%20ratio:%3E1.5&archetype=Pipeline"
    ).json()
    assert [f["id"] for f in searched["items"]] == ["a2"]
    assert library.get("/api/papers/paper-b/figures").json()["matched_count"] == 2
    assert (
        library.get("/api/papers/paper-b/figures?show_cases=false").json()[
            "matched_count"
        ]
        == 1
    )
    assert library.get("/api/papers/paper-a/figures?view=invalid").status_code == 422


def test_isolated_taxonomy_tab_counts_and_cross_category_guard(library):
    with connect() as db:
        db.execute(
            """UPDATE figures
               SET primary_style='clean_iconic',
                   secondary_style='refined_gradient',
                   layout_topology='ab_comparison',
                   craft_badges_json='["dedicated_legend_box"]'
               WHERE id='a1'"""
        )
        db.execute(
            """UPDATE figures
               SET primary_style='plain_wireframe',
                   layout_topology='linear_pipeline',
                   craft_badges_json='["frozen_trainable_marks","hybrid_mini_chart"]'
               WHERE id='a2'"""
        )
        db.execute(
            """UPDATE figures
               SET sub_type='line_scaling', chart_layout='multi_panel_grid'
               WHERE id='a10'"""
        )
        db.execute(
            """UPDATE figures
               SET sub_type='bar_ablation', chart_layout='single_plot'
               WHERE id='b1'"""
        )

    # Unfiltered common scope: 5 non-case figures (2 method in paper-a, 3 data_chart across paper-a/b/c)
    all_feed = library.get("/api/figures/feed?macro_category=all").json()
    assert all_feed["tab_counts"] == {
        "all": {"papers": 3, "figures": 5},
        "method": {"papers": 1, "figures": 2},
        "data_chart": {"papers": 3, "figures": 3},
    }

    # Selecting method + subtype/style narrows items, while tab_counts remain fixed for the common filters!
    method_styled = library.get(
        "/api/figures/feed?macro_category=method&visual_style=refined_gradient&chart_type=bar_ablation&chart_layout=single_plot"
    ).json()
    assert method_styled["total_figures"] == 1
    assert method_styled["items"][0]["matched_figures"][0]["id"] == "a1"
    assert method_styled["items"][0]["matched_figures"][0]["craft_badges"] == [
        "dedicated_legend_box"
    ]
    assert method_styled["tab_counts"] == all_feed["tab_counts"]

    # Craft filter & topology filter on method
    method_craft = library.get(
        "/api/figures/feed?macro_category=method&topology=linear_pipeline&craft=frozen_trainable_marks"
    ).json()
    assert method_craft["total_figures"] == 1
    assert method_craft["items"][0]["matched_figures"][0]["id"] == "a2"

    # Selecting data_chart ignores stale method params completely
    data_filtered = library.get(
        "/api/figures/feed?macro_category=data_chart&chart_layout=multi_panel_grid&method_type=concept_teaser&visual_style=clean_iconic"
    ).json()
    assert data_filtered["total_figures"] == 1
    assert data_filtered["items"][0]["matched_figures"][0]["id"] == "a10"
    assert data_filtered["tab_counts"] == all_feed["tab_counts"]

    # Common domain filter updates all three tab_counts buckets independently
    memory_feed = library.get(
        "/api/figures/feed?domain=memory&macro_category=data_chart"
    ).json()
    assert memory_feed["tab_counts"] == {
        "all": {"papers": 2, "figures": 4},
        "method": {"papers": 1, "figures": 2},
        "data_chart": {"papers": 2, "figures": 2},
    }


@pytest.mark.anyio
async def test_manual_patch_locks_taxonomy_and_retag_skips_locked(library, monkeypatch):
    from PIL import Image
    import io
    from figprism import ingest
    from figprism.vision import Verdict

    async def noop_backup(pid):
        return None

    monkeypatch.setattr(ingest, "backup", noop_backup)

    create_user("editor", "long-enough-password")
    library.post(
        "/api/auth/login",
        json={"username": "editor", "password": "long-enough-password"},
    )
    # Manually change a1 (method) to data_chart -> clears method styles & sets taxonomy_locked = 1
    patched = library.patch(
        "/api/figures/a1",
        json={
            "macro_category": "data_chart",
            "sub_type": "radar_polar",
            "primary_style": "clean_iconic",
            "chart_layout": "single_plot",
        },
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["macro_category"] == "data_chart"
    assert body["sub_type"] == "radar_polar"
    assert body["archetype"] == "Scatter/Radar"
    assert body["primary_style"] is None
    assert body["craft_badges"] == []
    assert body["chart_layout"] == "single_plot"
    assert body["taxonomy_locked"] == 1

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (240, 240, 240)).save(buf, "WEBP")
    thumb_bytes = buf.getvalue()

    async def fake_get(self, remote):
        return thumb_bytes

    async def fake_judge(
        image, caption, domains=None, driver=None, use_stage=True, **kwargs
    ):
        return Verdict(
            macro_category="method",
            sub_type="micro_mechanism",
            primary_style="tensor_schematic",
            layout_topology="macro_zoom_in",
            craft_badges=["frozen_trainable_marks"],
            style_confidence=0.93,
            style_reason="Matrix schematic operator",
        )

    monkeypatch.setattr(ingest.Storage, "get", fake_get)
    monkeypatch.setattr(ingest, "judge", fake_judge)

    stats = await ingest.retag_taxonomy(
        scope="all", concurrency=2, vision_driver="openai_mini"
    )
    assert stats["updated"] == 5 and stats["failed"] == 0

    # Locked figure a1 remains untouched; unlocked figure a2 got the new VLM taxonomy
    after_a1 = library.get("/api/figures/a1").json()
    assert after_a1["macro_category"] == "data_chart"
    assert after_a1["sub_type"] == "radar_polar"
    assert after_a1["taxonomy_locked"] == 1

    after_a2 = library.get("/api/figures/a2").json()
    assert after_a2["macro_category"] == "method"
    assert after_a2["sub_type"] == "micro_mechanism"
    assert after_a2["primary_style"] == "tensor_schematic"
    assert after_a2["layout_topology"] == "macro_zoom_in"
    assert after_a2["craft_badges"] == ["frozen_trainable_marks"]
    assert after_a2["taxonomy_locked"] == 0
