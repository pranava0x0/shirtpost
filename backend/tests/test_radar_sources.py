import json

from app.radar import sources

# Trimmed Wikimedia most-viewed payload: a meta page, an adult page, real ones.
_WIKI_FIXTURE = json.dumps(
    {
        "items": [
            {
                "articles": [
                    {"article": "Main_Page", "views": 5_000_000, "rank": 1},
                    {"article": "Special:Search", "views": 900_000, "rank": 2},
                    {"article": "Barbie_(film)", "views": 300_000, "rank": 3},
                    {"article": "Pornhub", "views": 250_000, "rank": 4},
                    {"article": "Taylor_Swift", "views": 200_000, "rank": 5},
                ]
            }
        ]
    }
)


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


def test_reddit_is_no_longer_a_source():
    # Dropped for commercial ToS — it must now be an unknown id, not fetched.
    assert sources.collect(["reddit"]) == []


def test_parse_wikipedia_maps_views_and_filters_meta_pages():
    rows = sources.parse_wikipedia_top(_WIKI_FIXTURE, top_n=25)
    terms = [r.term for r in rows]
    assert "Main Page" not in terms  # meta page dropped
    assert "Special:Search" not in " ".join(terms)  # namespace dropped
    assert "Barbie (film)" in terms  # underscores -> spaces
    barbie = next(r for r in rows if r.term == "Barbie (film)")
    assert barbie.source == "wikipedia"
    assert barbie.measurement == "pageviews"
    assert barbie.volume == 300_000
    assert barbie.source_url == "https://en.wikipedia.org/wiki/Barbie_(film)"


def test_parse_wikipedia_respects_top_n():
    assert len(sources.parse_wikipedia_top(_WIKI_FIXTURE, top_n=1)) == 1


def test_parse_wikipedia_bad_payload_returns_empty():
    assert sources.parse_wikipedia_top("not json", top_n=5) == []
    assert sources.parse_wikipedia_top("{}", top_n=5) == []


def test_family_filter_blocks_and_allows():
    block = ["porn", "nsfw"]
    assert sources.is_family_safe("Barbie (film)", block) is True
    # Substring (not word-boundary) so compound adult terms are caught — a safety
    # filter over-blocks on purpose (missing "Pornhub" would be the worse error).
    assert sources.is_family_safe("Pornhub", block) is False


def test_execution_removed_from_default_blocklist():
    from app.config import get_settings

    # "execution" caused false positives ("code execution") and was removed.
    assert sources.is_family_safe("Code execution", get_settings().family_blocklist) is True


def test_collect_wikipedia_drops_family_unsafe(monkeypatch):
    # fetch.get returns the fixture; collect parses, then the family filter drops
    # the adult page before it can reach the queue.
    monkeypatch.setattr(sources.fetch, "get", lambda url: _WIKI_FIXTURE)
    rows = sources.collect(["wikipedia"])
    terms = [r.term for r in rows]
    assert "Barbie (film)" in terms
    assert "Taylor Swift" in terms
    assert "Pornhub" not in terms  # family filter dropped it
