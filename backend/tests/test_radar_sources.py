from app.radar import sources


def test_clean_text_strips_html_and_collapses_whitespace():
    raw = "<b>we are</b>   so\n\tback <script>alert(1)</script>"
    cleaned = sources.clean_text(raw)
    assert "<" not in cleaned and ">" not in cleaned
    assert "  " not in cleaned
    assert "we are so back" in cleaned


def test_clean_text_handles_empty():
    assert sources.clean_text("") == ""


def test_simulated_source_returns_seeds_with_provenance():
    rows = sources.fetch_simulated()
    assert len(rows) >= 5
    for row in rows:
        assert row.source == "simulated"
        assert row.term and row.volume > 0
        assert row.measurement == "seed"  # not comparable to real-source volumes


def test_collect_skips_unknown_source_without_crashing():
    assert sources.collect(["does-not-exist"]) == []
