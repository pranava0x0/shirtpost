"""API smoke tests against the real app via TestClient (Radar disabled)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.main import app
from app.models import Drop, DropStatus, Trend, utcnow


def _seed_trend(term: str, hype: float) -> int:
    with SessionLocal() as session:
        trend = Trend(
            term=term,
            term_raw=term,
            source="simulated",
            volume=100,
            velocity=1.0,
            hype_score=hype,
            first_seen_at=utcnow(),
            last_seen_at=utcnow(),
        )
        session.add(trend)
        session.commit()
        return trend.id


def test_health():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_trends_sorted_by_hype_desc():
    _seed_trend("low hype", 10.0)
    _seed_trend("high hype", 999.0)
    with TestClient(app) as client:
        terms = [t["term"] for t in client.get("/api/trends").json()]
    assert terms[0] == "high hype"


def test_submit_unknown_trend_404():
    with TestClient(app) as client:
        resp = client.post("/api/trends/999999/submit", json={"design_copy": "hi"})
    assert resp.status_code == 404


def test_quips_unknown_trend_404():
    with TestClient(app) as client:
        resp = client.post("/api/trends/999999/quips")
    assert resp.status_code == 404


def test_quips_without_api_key_fails_loud_503():
    # No ANTHROPIC_API_KEY in the test env -> the generator can't run, and the
    # endpoint says so (503) rather than silently returning nothing.
    trend_id = _seed_trend("layoffs", 500.0)
    with TestClient(app) as client:
        resp = client.post(f"/api/trends/{trend_id}/quips")
    assert resp.status_code == 503
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]


def test_quips_happy_path_returns_candidates(monkeypatch):
    from app.api import routes

    trend_id = _seed_trend("in my villain era", 500.0)
    monkeypatch.setattr(
        routes, "generate_quips", lambda *a, **k: ["we are so back", "touch grass"]
    )
    with TestClient(app) as client:
        resp = client.post(f"/api/trends/{trend_id}/quips")
    assert resp.status_code == 200
    assert resp.json() == {"quips": ["we are so back", "touch grass"]}


def test_submit_creates_pending_drop():
    trend_id = _seed_trend("we are so back", 500.0)
    with TestClient(app) as client:
        resp = client.post(
            f"/api/trends/{trend_id}/submit", json={"design_copy": "we are so back"}
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["trend_id"] == trend_id
    # No Printful/X creds in tests -> the background pipeline records FAILED, but
    # the immediate response is the freshly-created PENDING drop.
    assert body["status"] == "pending"


def test_submit_rejects_empty_copy():
    trend_id = _seed_trend("make no mistakes", 300.0)
    with TestClient(app) as client:
        resp = client.post(f"/api/trends/{trend_id}/submit", json={"design_copy": ""})
    assert resp.status_code == 422


def test_get_drop_by_id_and_404():
    trend_id = _seed_trend("delulu is the solulu", 200.0)
    with SessionLocal() as s:
        drop = Drop(trend_id=trend_id, design_copy="copy", status=DropStatus.PENDING)
        s.add(drop)
        s.commit()
        drop_id = drop.id
    with TestClient(app) as client:
        assert client.get(f"/api/drops/{drop_id}").json()["id"] == drop_id
        assert client.get("/api/drops/424242").status_code == 404


def test_duplicate_inflight_submission_409():
    trend_id = _seed_trend("very mindful very demure", 400.0)
    # Seed an in-flight drop directly so the guard is exercised deterministically
    # (avoids racing the background pipeline that would otherwise mark it failed).
    with SessionLocal() as s:
        s.add(Drop(trend_id=trend_id, design_copy="x", status=DropStatus.PROCESSING))
        s.commit()
    with TestClient(app) as client:
        resp = client.post(f"/api/trends/{trend_id}/submit", json={"design_copy": "again"})
    assert resp.status_code == 409


def test_manual_sweep_populates_trends():
    with TestClient(app) as client:
        resp = client.post("/api/radar/sweep")
        assert resp.status_code == 200
        assert resp.json()["touched"] >= 5
        assert len(client.get("/api/trends").json()) >= 5


def test_inflight_unique_index_blocks_second_pending():
    # DB-level invariant (race-proof): a second in-flight drop for the same trend
    # must be rejected by the constraint, not just the application pre-check.
    trend_id = _seed_trend("we are so back", 100.0)
    with SessionLocal() as s:
        s.add(Drop(trend_id=trend_id, design_copy="a", status=DropStatus.PENDING))
        s.commit()
    with SessionLocal() as s:
        s.add(Drop(trend_id=trend_id, design_copy="b", status=DropStatus.PENDING))
        with pytest.raises(IntegrityError):
            s.commit()


def test_inflight_index_allows_multiple_terminal_drops():
    # Terminal drops (failed/published) are not covered by the partial index, so a
    # trend can accumulate history and be retried after a failure.
    trend_id = _seed_trend("delulu is the solulu", 100.0)
    with SessionLocal() as s:
        s.add(Drop(trend_id=trend_id, design_copy="a", status=DropStatus.FAILED))
        s.add(Drop(trend_id=trend_id, design_copy="b", status=DropStatus.PUBLISHED))
        s.commit()  # no IntegrityError
        assert len(s.query(Drop).filter(Drop.trend_id == trend_id).all()) == 2
