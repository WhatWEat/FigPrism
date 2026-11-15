import asyncio

import pytest
from figprism import sources
from figprism.cvf import parse_index, parse_paper

URL = "https://openaccess.thecvf.com/content/CVPR2026/html/A_Visual_Memory_CVPR_2026_paper.html"
PDF = URL.replace("/html/", "/papers/").replace(".html", ".pdf")
HTML = f'''<meta name="citation_title" content="Agent memory and visual hallucination">
<meta name="citation_author" content="A, Researcher">
<meta name="citation_publication_date" content="2026">
<meta name="citation_conference_title" content="Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition">
<meta name="citation_pdf_url" content="{PDF}">
<div id="abstract">Long-term memory for a <b>vision-language model</b>.</div>
<a href="https://arxiv.org/abs/2511.12345">arXiv</a>'''


def test_cvf_index_excludes_workshops_findings_and_foreign_hosts():
    data = f'<a href="{URL}">Visual Memory</a><a href="{URL.replace("CVPR2026/", "CVPR2026W/")}">Workshop</a><a href="https://evil.test/content/CVPR2026/html/A_CVPR_2026_paper.html">Evil</a>'
    assert parse_index(data, 2026) == [{"title": "Visual Memory", "url": URL}]


def test_cvf_authoritative_year_can_differ_from_arxiv_submission():
    p = parse_paper(HTML, URL, 2026)
    assert p["venue"] == "CVPR" and p["venue_year"] == 2026
    assert p["arxiv_id"] == "2511.12345"
    assert p["source_urls"]["pdf"] == PDF
    assert "vision-language model" in p["abstract"]
    assert p["authors"] == ["A, Researcher"]


def test_cvf_without_arxiv_has_stable_identity():
    p = parse_paper(HTML.split("<a href=")[0], URL, 2026)
    assert p["doc_uid"].startswith("cvf:")
    assert "arxiv_id" not in p


@pytest.mark.parametrize(
    "data,url",
    [
        (HTML.replace("Pattern Recognition", "Pattern Recognition Workshops"), URL),
        (HTML.replace(PDF, "https://evil.test/paper.pdf"), URL),
        (HTML, URL.replace("CVPR2026/", "CVPR2026F/")),
    ],
)
def test_cvf_rejects_invalid_proceedings(data, url):
    with pytest.raises(ValueError):
        parse_paper(data, url, 2026)


@pytest.mark.asyncio
async def test_known_accepted_paper_is_ingested_before_slow_verification(
    client, monkeypatch
):
    config = {"slug": "memory", "phrases": ["agent memory"]}
    papers = [
        {
            "arxiv_id": "2601.00001",
            "doc_uid": "2601.00001",
            "title": "Known agent memory",
            "venue": "CVPR",
            "venue_year": 2026,
            "source_urls": {"pdf": "https://arxiv.org/pdf/2601.00001"},
        },
        {
            "arxiv_id": "2601.00002",
            "doc_uid": "2601.00002",
            "title": "Unknown agent memory",
            "source_urls": {"pdf": "https://arxiv.org/pdf/2601.00002"},
        },
    ]
    known, verifying, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    order = []
    monkeypatch.setattr(sources, "all_domains", lambda: [config])

    async def discover(*args):
        return papers

    async def fetch(*args):
        return b"%PDF"

    async def ingest(data, p, *args, **kwargs):
        order.append(p["title"])
        if p["title"].startswith("Known"):
            known.set()

    async def verify(p):
        verifying.set()
        await release.wait()
        return dict(p, venue="CVPR", venue_year=2026)

    monkeypatch.setattr(sources, "arxiv_search", discover)
    monkeypatch.setattr(sources, "fetch", fetch)
    monkeypatch.setattr(sources, "ingest_pdf", ingest)
    monkeypatch.setattr(sources, "verified", verify)
    task = asyncio.create_task(
        sources._sync(source="arxiv", backfill=True, years=(2026,), limit=2)
    )
    try:
        await asyncio.wait_for(known.wait(), 1)
        await asyncio.wait_for(verifying.wait(), 1)
        assert order == ["Known agent memory"]
    finally:
        release.set()
        result = await task
    assert result["completed"] == 2


@pytest.mark.asyncio
async def test_verification_has_deadline_and_success_is_cached(client, monkeypatch):
    paper = {"title": "Cache agent memory", "source_urls": {}}
    calls = []

    async def verify(p):
        calls.append(1)
        return dict(p, venue="CVPR", venue_year=2026)

    monkeypatch.setattr(sources, "verified", verify)
    await sources.cached_verification(paper)
    assert (await sources.cached_verification(paper))["venue"] == "CVPR"
    assert len(calls) == 1

    async def block(p):
        await asyncio.Event().wait()

    monkeypatch.setattr(sources, "verified", block)
    monkeypatch.setattr(sources, "VERIFICATION_TIMEOUT", 0.01)
    with pytest.raises(TimeoutError):
        await sources.cached_verification({"title": "Never responds"})
