"""Trend observation history: an append-only snapshot per sweep, so a true
velocity curve survives instead of only the latest delta on the Trend row."""

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Trend, TrendObservation
from app.radar.worker import run_sweep_once


def _count_observations() -> int:
    with SessionLocal() as s:
        return s.query(TrendObservation).count()


def _trend_count() -> int:
    with SessionLocal() as s:
        return s.query(Trend).count()


def test_sweep_records_one_observation_per_trend():
    touched = run_sweep_once()  # simulated source -> 5 seeds
    assert touched >= 5
    # One observation per trend touched this sweep.
    assert _count_observations() == touched == _trend_count()


def test_observations_are_append_only_across_sweeps():
    run_sweep_once()
    first = _count_observations()
    trends = _trend_count()
    run_sweep_once()  # same terms upsert the Trend rows but ADD observations
    assert _trend_count() == trends  # no new trends
    assert _count_observations() == first + trends  # history grew, nothing overwritten


def test_observation_carries_measurement_and_scores():
    run_sweep_once()
    with SessionLocal() as s:
        obs = s.query(TrendObservation).first()
        assert obs.measurement == "seed"  # simulated source
        assert obs.volume > 0
        assert obs.hype_score > 0


def test_observations_endpoint_returns_history_newest_first():
    run_sweep_once()
    run_sweep_once()
    with SessionLocal() as s:
        trend_id = s.query(Trend).first().id
    with TestClient(app) as client:
        resp = client.get(f"/api/trends/{trend_id}/observations")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2  # two sweeps
    times = [o["observed_at"] for o in body]
    assert times == sorted(times, reverse=True)  # newest first


def test_observations_endpoint_404_for_unknown_trend():
    with TestClient(app) as client:
        assert client.get("/api/trends/999999/observations").status_code == 404


def test_trend_list_includes_chronological_spark_series():
    run_sweep_once()
    run_sweep_once()
    run_sweep_once()
    with TestClient(app) as client:
        trends = client.get("/api/trends").json()
    assert trends
    for t in trends:
        # Three sweeps -> three sparkline points, oldest -> newest.
        assert len(t["spark"]) == 3
        assert all(isinstance(v, (int, float)) for v in t["spark"])


def test_normalized_hype_is_per_source_and_bounded():
    # Two sources with very different volume scales must each normalize to [0,1]
    # on their OWN scale — a low-volume source is not crushed to ~0 globally.
    with SessionLocal() as s:
        from app.models import utcnow

        s.add_all(
            [
                Trend(term="big-a", term_raw="big-a", source="google_trends",
                      measurement="search_traffic", volume=200_000, hype_score=200_000.0,
                      first_seen_at=utcnow(), last_seen_at=utcnow()),
                Trend(term="big-b", term_raw="big-b", source="google_trends",
                      measurement="search_traffic", volume=50_000, hype_score=50_000.0,
                      first_seen_at=utcnow(), last_seen_at=utcnow()),
                Trend(term="small-a", term_raw="small-a", source="reddit",
                      measurement="presence", volume=1, hype_score=1.0,
                      first_seen_at=utcnow(), last_seen_at=utcnow()),
            ]
        )
        s.commit()
    with TestClient(app) as client:
        by_term = {t["term"]: t for t in client.get("/api/trends?limit=200").json()}
    assert by_term["big-a"]["normalized_hype"] == 1.0  # top of its source
    assert by_term["big-b"]["normalized_hype"] == 0.0  # bottom of its source
    # The lone reddit trend normalizes to 1.0 on its own lane, not ~0 globally.
    assert by_term["small-a"]["normalized_hype"] == 1.0
    for t in by_term.values():
        assert 0.0 <= t["normalized_hype"] <= 1.0


def test_trends_can_be_filtered_by_source():
    run_sweep_once()  # simulated
    with SessionLocal() as s:
        from app.models import utcnow

        s.add(Trend(term="only-reddit", term_raw="only-reddit", source="reddit",
                    measurement="presence", volume=1, hype_score=1.0,
                    first_seen_at=utcnow(), last_seen_at=utcnow()))
        s.commit()
    with TestClient(app) as client:
        reddit = client.get("/api/trends?source=reddit").json()
    assert reddit
    assert all(t["source"] == "reddit" for t in reddit)
