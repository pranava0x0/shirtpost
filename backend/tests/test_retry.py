"""Factory idempotency + safe retry.

The pipeline commits each external result as it lands and skips any step whose
result is already present, so retrying a FAILED drop RESUMES rather than repeats.
The load-bearing guarantee: a drop whose tweet already posted is never tweeted
again on retry.
"""

from fastapi.testclient import TestClient

from app.config import Settings
from app.database import SessionLocal
from app.factory import pipeline as pipeline_mod
from app.factory.pipeline import FactoryPipeline
from app.factory.printful import PrintfulClient
from app.factory.xcom import XClient
from app.main import app
from app.models import Drop, DropStatus, Trend, utcnow


def _real_mode_settings() -> Settings:
    # api broadcast mode: these tests are about the auto-post path and its
    # never-double-post-on-retry guarantee (intent mode makes no external call).
    return Settings(
        printful_api_key="k",
        # local storage + a public base URL -> publish() returns a URL without
        # any network (the Printful/X clients are patched in these tests).
        print_file_storage="local",
        public_base_url="https://cdn.example.com",
        x_broadcast_mode="api",
        x_api_key="a",
        x_api_secret="b",
        x_access_token="c",
        x_access_token_secret="d",
        factory_dry_run=False,
    )


def _patch_clients(monkeypatch) -> list[str]:
    """Replace the external client methods with call recorders. Returns the list
    that accumulates step names in call order."""
    calls: list[str] = []
    monkeypatch.setattr(PrintfulClient, "__init__", lambda self, settings: None)
    monkeypatch.setattr(
        PrintfulClient, "generate_mockup",
        lambda self, url: (calls.append("mockup"), "https://mock/1.png")[1],
    )
    monkeypatch.setattr(
        PrintfulClient, "sync_product",
        lambda self, **kw: (calls.append("sync"), "sync-1")[1],
    )
    monkeypatch.setattr(XClient, "__init__", lambda self, settings: None)
    monkeypatch.setattr(
        XClient, "upload_media",
        lambda self, image_bytes, **kw: (calls.append("upload"), "media-1")[1],
    )
    monkeypatch.setattr(
        XClient, "post_tweet",
        lambda self, text, media_id=None: (calls.append("tweet"), "tweet-1")[1],
    )
    monkeypatch.setattr(FactoryPipeline, "_download", lambda self, url: b"img")
    return calls


def _seed_drop(session, **drop_kwargs) -> Drop:
    trend = Trend(
        term="we are so back", term_raw="we are so back", source="simulated",
        volume=1000, hype_score=1000.0, first_seen_at=utcnow(), last_seen_at=utcnow(),
    )
    session.add(trend)
    session.commit()
    drop = Drop(trend_id=trend.id, design_copy="we are so back", **drop_kwargs)
    session.add(drop)
    session.commit()
    return drop


def test_fresh_run_executes_every_step_once(monkeypatch):
    calls = _patch_clients(monkeypatch)
    with SessionLocal() as session:
        drop = _seed_drop(session, status=DropStatus.PENDING)
        FactoryPipeline(_real_mode_settings()).run(session, drop)
        session.refresh(drop)
    assert calls == ["mockup", "sync", "upload", "tweet"]
    assert drop.status == DropStatus.PUBLISHED
    assert drop.x_tweet_id == "tweet-1"


def test_retry_after_tweet_posted_never_double_posts(monkeypatch):
    # Simulate a partial run that already tweeted but failed before PUBLISHED.
    calls = _patch_clients(monkeypatch)
    with SessionLocal() as session:
        drop = _seed_drop(
            session,
            status=DropStatus.FAILED,
            printful_mockup_url="https://mock/existing.png",
            printful_sync_product_id="sync-existing",
            x_tweet_id="tweet-existing",
            error="died after posting",
        )
        FactoryPipeline(_real_mode_settings()).run(session, drop)
        session.refresh(drop)
    # No external step re-ran; the existing tweet id is preserved.
    assert "tweet" not in calls and "upload" not in calls
    assert calls == []
    assert drop.status == DropStatus.PUBLISHED
    assert drop.x_tweet_id == "tweet-existing"
    assert drop.error is None


def test_retry_resumes_from_last_committed_step(monkeypatch):
    # Mockup + sync already done, tweet not yet -> only the tweet steps run.
    calls = _patch_clients(monkeypatch)
    with SessionLocal() as session:
        drop = _seed_drop(
            session,
            status=DropStatus.FAILED,
            printful_mockup_url="https://mock/existing.png",
            printful_sync_product_id="sync-existing",
        )
        FactoryPipeline(_real_mode_settings()).run(session, drop)
        session.refresh(drop)
    assert calls == ["upload", "tweet"]  # mockup + sync skipped
    assert drop.status == DropStatus.PUBLISHED
    assert drop.x_tweet_id == "tweet-1"


# --- Retry endpoint guards ---------------------------------------------------


def _seed_via_client(status: DropStatus, **extra) -> tuple[int, int]:
    with SessionLocal() as session:
        drop = _seed_drop(session, status=status, **extra)
        return drop.id, drop.trend_id


def test_retry_endpoint_404_for_unknown_drop():
    with TestClient(app) as client:
        assert client.post("/api/drops/999999/retry").status_code == 404


def test_retry_endpoint_rejects_non_failed_drop():
    drop_id, _ = _seed_via_client(DropStatus.PUBLISHED)
    with TestClient(app) as client:
        resp = client.post(f"/api/drops/{drop_id}/retry")
    assert resp.status_code == 409
    assert "only failed" in resp.json()["detail"]


def test_retry_endpoint_blocks_when_another_drop_in_flight():
    # A FAILED drop plus a separate in-flight drop for the same trend: retrying
    # would create a second in-flight drop, which the unique index forbids.
    with SessionLocal() as session:
        failed = _seed_drop(session, status=DropStatus.FAILED)
        session.add(
            Drop(trend_id=failed.trend_id, design_copy="other", status=DropStatus.PROCESSING)
        )
        session.commit()
        failed_id = failed.id
    with TestClient(app) as client:
        resp = client.post(f"/api/drops/{failed_id}/retry")
    assert resp.status_code == 409


def test_retry_endpoint_accepts_failed_drop():
    drop_id, _ = _seed_via_client(DropStatus.FAILED)
    with TestClient(app) as client:
        resp = client.post(f"/api/drops/{drop_id}/retry")
    assert resp.status_code == 202
    # The response captures the drop as it was re-queued (processing), before the
    # background pipeline runs.
    assert resp.json()["status"] == "processing"
