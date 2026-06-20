"""API smoke tests against the real app via TestClient (Radar disabled)."""

from fastapi.testclient import TestClient

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
