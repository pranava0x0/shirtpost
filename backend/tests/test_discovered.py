"""The `discovered` radar source: reads the cloud-routine's append-only judged
phrases from the local checkout, windows by day, dedupes by key keeping the max
shirt_score, and carries context/angles/ip_risk through. The worker passes a
judged shirt_score straight to Hype (no velocity boost)."""

import json
from datetime import date, timedelta

from app.database import SessionLocal
from app.models import Trend
from app.radar import scoring, sources

_TODAY = date(2026, 7, 13)


def _line(term: str, day: date, score: int, **extra) -> str:
    rec = {
        "term": term,
        "term_raw": term,
        "key": term,
        "day": day.isoformat(),
        "captured_at": f"{day.isoformat()}T13:00:00Z",
        "sources": [{"id": "x_aggregator", "url": f"https://ex/{term}", "seen_at": "x"}],
        "context": f"why {term} is trending",
        "scores": {"wearability": 4, "funny": 4, "durability": 3, "phraseness": 5},
        "shirt_score": score,
        "ip_risk": False,
        "angles": ["deadpan", "absurd"],
        "model": "test",
        "prompt_version": 1,
    }
    rec.update(extra)
    return json.dumps(rec)


def test_parse_happy_path_maps_score_context_angles():
    body = _line("crashing out", _TODAY, 78)
    rows = sources.parse_discovered(body, window_days=14, today=_TODAY)
    assert len(rows) == 1
    r = rows[0]
    assert r.source == "discovered"
    assert r.measurement == "shirt_score"
    assert r.volume == 78  # shirt_score carried as volume
    assert r.context == "why crashing out is trending"
    assert r.angles == ["deadpan", "absurd"]
    assert r.ip_risk is False
    assert r.source_url == "https://ex/crashing out"


def test_malformed_line_is_skipped_not_crashing():
    body = "\n".join(
        [
            _line("good one", _TODAY, 70),
            "{ this is not valid json",
            '{"term": "", "shirt_score": 90, "day": "2026-07-13"}',  # empty term
            '{"term": "no score", "day": "2026-07-13"}',  # missing shirt_score
            _line("another good", _TODAY, 60),
        ]
    )
    rows = sources.parse_discovered(body, window_days=14, today=_TODAY)
    terms = sorted(r.term for r in rows)
    assert terms == ["another good", "good one"]


def test_empty_file_returns_no_trends(tmp_path, monkeypatch):
    f = tmp_path / "discovered.jsonl"
    f.write_text("   \n\n")
    monkeypatch.setattr(sources, "get_settings", _settings_with(f))
    assert sources.fetch_discovered() == []


def test_missing_file_returns_no_trends(tmp_path, monkeypatch):
    f = tmp_path / "nope.jsonl"  # never created
    monkeypatch.setattr(sources, "get_settings", _settings_with(f))
    assert sources.fetch_discovered() == []


def test_line_older_than_window_is_excluded():
    old = _TODAY - timedelta(days=15)
    body = "\n".join([_line("fresh", _TODAY, 70), _line("stale", old, 95)])
    rows = sources.parse_discovered(body, window_days=14, today=_TODAY)
    terms = [r.term for r in rows]
    assert "fresh" in terms
    assert "stale" not in terms  # 15 days old, outside the 14-day window


def test_future_day_is_excluded():
    body = _line("time traveler", _TODAY + timedelta(days=1), 99)
    assert sources.parse_discovered(body, window_days=14, today=_TODAY) == []


def test_window_is_exactly_window_days_not_one_more():
    # window_days=14 keeps today and the prior 13 days (14 calendar days). The day
    # exactly window_days ago is the exclusive lower bound -> excluded.
    edge_out = _line("day-14", _TODAY - timedelta(days=14), 90)
    edge_in = _line("day-13", _TODAY - timedelta(days=13), 60)
    rows = sources.parse_discovered("\n".join([edge_out, edge_in]), window_days=14, today=_TODAY)
    terms = [r.term for r in rows]
    assert "day-13" in terms
    assert "day-14" not in terms  # true 14-day window, not 15


def test_bool_shirt_score_is_rejected():
    # bool is an int subclass; a JSON `true` must NOT slip in as score 1.
    body = '{"term": "boolish", "day": "%s", "shirt_score": true}' % _TODAY.isoformat()
    assert sources.parse_discovered(body, window_days=14, today=_TODAY) == []


def test_negative_shirt_score_is_rejected():
    body = _line("judged out", _TODAY, -5)
    assert sources.parse_discovered(body, window_days=14, today=_TODAY) == []


def test_out_of_range_shirt_score_is_rejected():
    # Judged scores bypass Hype (volume == shirt_score); a 500 would blow out the
    # discovered lane's within-source scale, so it's dropped, not clamped.
    body = _line("too big", _TODAY, 500)
    assert sources.parse_discovered(body, window_days=14, today=_TODAY) == []


def test_non_finite_shirt_score_is_rejected():
    # Python's json accepts NaN/Infinity — they must not pass the numeric check.
    for raw in ("NaN", "Infinity", "-Infinity"):
        body = '{"term": "wild", "day": "%s", "shirt_score": %s}' % (_TODAY.isoformat(), raw)
        assert sources.parse_discovered(body, window_days=14, today=_TODAY) == [], raw


def test_max_score_100_is_kept():
    rows = sources.parse_discovered(_line("perfect", _TODAY, 100), window_days=14, today=_TODAY)
    assert len(rows) == 1 and rows[0].volume == 100


def test_zero_shirt_score_is_kept_as_zero_volume():
    # 0 is a valid (if unexciting) score — kept, not confused with "invalid".
    rows = sources.parse_discovered(_line("meh", _TODAY, 0), window_days=14, today=_TODAY)
    assert len(rows) == 1 and rows[0].volume == 0


def test_dedupe_keeps_max_score_for_a_key():
    body = "\n".join(
        [
            _line("crashing out", _TODAY - timedelta(days=1), 60),
            _line("crashing out", _TODAY, 88),
            _line("crashing out", _TODAY - timedelta(days=2), 71),
        ]
    )
    rows = sources.parse_discovered(body, window_days=14, today=_TODAY)
    assert len(rows) == 1
    assert rows[0].volume == 88  # the max shirt_score across the window


def test_key_dedupe_is_case_insensitive():
    body = "\n".join(
        [_line("Crashing Out", _TODAY, 60, key="crashing out"),
         _line("crashing out", _TODAY, 80, key="crashing out")]
    )
    rows = sources.parse_discovered(body, window_days=14, today=_TODAY)
    assert len(rows) == 1
    assert rows[0].volume == 80


# --- worker: judged score bypasses the velocity boost -----------------------

def test_hype_for_judged_measurement_is_score_unboosted():
    # A first-sight shirt_score would get a ~2x boost under the volume model; the
    # judged bypass must return the score itself so lanes stay honest.
    assert scoring.hype_for("shirt_score", velocity=78.0, volume=78) == 78.0
    # An attention measurement still boosts.
    assert scoring.hype_for("search_traffic", velocity=25_000.0, volume=50_000) == 75_000.0


def test_resweep_leaves_discovered_hype_unchanged(monkeypatch):
    from app.radar import worker

    row = sources.RawTrend(
        term="crashing out", term_raw="crashing out", source="discovered",
        source_url=None, volume=78, measurement="shirt_score",
        context="ctx", angles=["a"], ip_risk=False,
    )
    monkeypatch.setattr(worker.sources, "collect", lambda ids: [row])
    worker.run_sweep_once()
    with SessionLocal() as s:
        t1 = s.query(Trend).filter_by(source="discovered").one()
        assert t1.hype_score == 78.0  # score straight through, no ~2x first-sight boost
        assert t1.context == "ctx" and t1.angles == ["a"] and t1.ip_risk is False
    worker.run_sweep_once()  # same score again
    with SessionLocal() as s:
        t2 = s.query(Trend).filter_by(source="discovered").one()
        assert t2.hype_score == 78.0  # unchanged on re-sweep


def test_non_discovery_resight_does_not_wipe_enrichment(monkeypatch):
    from app.radar import worker

    disc = sources.RawTrend(
        term="crashing out", term_raw="crashing out", source="discovered",
        source_url=None, volume=78, measurement="shirt_score",
        context="ctx", angles=["a"], ip_risk=False,
    )
    monkeypatch.setattr(worker.sources, "collect", lambda ids: [disc])
    worker.run_sweep_once()
    # A later sweep re-supplies the same term with no enrichment (None fields).
    bare = sources.RawTrend(
        term="crashing out", term_raw="crashing out", source="discovered",
        source_url=None, volume=80, measurement="shirt_score",
    )
    monkeypatch.setattr(worker.sources, "collect", lambda ids: [bare])
    worker.run_sweep_once()
    with SessionLocal() as s:
        t = s.query(Trend).filter_by(source="discovered").one()
        assert t.context == "ctx"  # not clobbered by the None re-sight
        assert t.volume == 80  # volume still updated


def _settings_with(path):
    """Return a get_settings replacement whose discovered_trends_path is `path`."""
    from app.config import get_settings

    base = get_settings()

    class _S:
        discovered_trends_path = str(path)
        discovered_window_days = base.discovered_window_days

    return lambda: _S()
