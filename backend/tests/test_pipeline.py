"""Factory pipeline: dry-run completes the loop without external services."""

from app.config import Settings
from app.database import SessionLocal
from app.factory.pipeline import FactoryPipeline
from app.models import Drop, DropStatus, Trend, utcnow


def _seed_drop(session) -> Drop:
    trend = Trend(
        term="we are so back",
        term_raw="we are so back",
        source="simulated",
        volume=1000,
        hype_score=1000.0,
        first_seen_at=utcnow(),
        last_seen_at=utcnow(),
    )
    session.add(trend)
    session.commit()
    drop = Drop(trend_id=trend.id, design_copy="we are so back", status=DropStatus.PENDING)
    session.add(drop)
    session.commit()
    return drop


def test_dry_run_publishes_without_external_calls():
    with SessionLocal() as session:
        drop = _seed_drop(session)
        FactoryPipeline(Settings(factory_dry_run=True)).run(session, drop)
        session.refresh(drop)
        assert drop.status == DropStatus.PUBLISHED
        assert drop.dry_run is True
        assert drop.x_tweet_id.startswith("dryrun-")
        assert drop.printful_sync_product_id.startswith("dryrun-")
        assert drop.printful_mockup_url.endswith(f"/artifacts/{drop.id}.svg")
        assert drop.error is None


def test_real_mode_fails_loud_without_config():
    # Default (dry-run off) with no Printful host/creds must still fail loud.
    with SessionLocal() as session:
        drop = _seed_drop(session)
        try:
            FactoryPipeline(Settings()).run(session, drop)
        except Exception:
            pass
        session.refresh(drop)
        assert drop.status == DropStatus.FAILED
        assert drop.dry_run is False
        assert "PRINTFUL_PRINT_FILE_BASE_URL" in (drop.error or "")
