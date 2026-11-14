from figprism.sources import venue_from_text, normalized, parse_arxiv


def test_venue_excludes_unaccepted_and_workshops():
    for value in (
        "Submitted to ICLR 2026",
        "ICML 2025 Workshop",
        "Under review at ACL 2026",
        "Findings of EMNLP 2025",
        "Rejected by CVPR 2026",
    ):
        assert venue_from_text(value) is None
    assert venue_from_text("Accepted at ICLR 2025 (Oral)") == {
        "venue": "ICLR",
        "venue_year": 2025,
        "venue_tier": "oral",
    }
    assert venue_from_text("NeurIPS 2026 Spotlight")["venue_tier"] == "spotlight"


def test_title_matching_ignores_punctuation_not_words():
    assert normalized("A Model: for Memory.") == normalized("A Model for Memory")
    assert normalized("A Model for Memory") != normalized("A Model for Vision")


def test_parse_arxiv():
    xml = b"""<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom"><entry><id>http://arxiv.org/abs/2501.12345v2</id><title>A memory model</title><summary>neural memory</summary><author><name>A Researcher</name></author><arxiv:comment>Accepted at ICLR 2025</arxiv:comment></entry></feed>"""
    p = parse_arxiv(xml)[0]
    assert p["venue"] == "ICLR"
    assert p["authors"] == ["A Researcher"]
