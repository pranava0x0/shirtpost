"""Radar fetch hygiene: disk cache, cache-served-without-network, 429 backoff."""

from app.radar import fetch


class FakeResp:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


def test_cache_roundtrip_and_freshness():
    url = "https://example.com/feed.rss"
    fetch._write_cache(url, "<rss>hi</rss>")
    assert fetch._read_cache(url, max_age=300) == "<rss>hi</rss>"
    assert fetch._read_cache(url, max_age=0) is None  # max_age 0 => never fresh


def test_get_serves_cache_without_network(monkeypatch):
    url = "https://example.com/cached.rss"
    fetch._write_cache(url, "CACHED")

    def boom(*a, **k):
        raise AssertionError("network must not be hit on a cache hit")

    monkeypatch.setattr(fetch.requests, "get", boom)
    assert fetch.get(url) == "CACHED"


def test_get_happy_path_writes_cache(monkeypatch):
    url = "https://example.com/fresh.rss"
    p = fetch._cache_path(url)
    if p.exists():
        p.unlink()
    monkeypatch.setattr(fetch.requests, "get", lambda *a, **k: FakeResp(200, "BODY"))
    assert fetch.get(url) == "BODY"
    assert fetch._read_cache(url, 300) == "BODY"  # cached for next run


def test_get_retries_on_429_then_succeeds(monkeypatch):
    url = "https://example.com/ratelimited.rss"
    p = fetch._cache_path(url)
    if p.exists():
        p.unlink()
    monkeypatch.setattr(fetch.time, "sleep", lambda *_: None)  # no real backoff wait
    calls = {"n": 0}

    def fake_get(*a, **k):
        calls["n"] += 1
        return FakeResp(429) if calls["n"] == 1 else FakeResp(200, "OK")

    monkeypatch.setattr(fetch.requests, "get", fake_get)
    assert fetch.get(url) == "OK"
    assert calls["n"] == 2


def test_get_backs_off_on_connection_error_then_succeeds(monkeypatch):
    # A connection error retries (with backoff) instead of burning retries in a
    # burst — same treatment as a 429, so a transient blip is ridden through.
    url = "https://example.com/conn.rss"
    p = fetch._cache_path(url)
    if p.exists():
        p.unlink()
    monkeypatch.setattr(fetch.time, "sleep", lambda *_: None)  # no real backoff wait
    calls = {"n": 0}

    def fake_get(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise fetch.requests.RequestException("connection reset")
        return FakeResp(200, "OK")

    monkeypatch.setattr(fetch.requests, "get", fake_get)
    assert fetch.get(url) == "OK"
    assert calls["n"] == 2


def test_get_returns_none_on_4xx(monkeypatch):
    url = "https://example.com/gone.rss"
    p = fetch._cache_path(url)
    if p.exists():
        p.unlink()
    monkeypatch.setattr(fetch.requests, "get", lambda *a, **k: FakeResp(404))
    assert fetch.get(url) is None
