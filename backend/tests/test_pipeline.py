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
    # Default broadcast mode is "intent": the drop gets a prefilled Post-to-X URL
    # for the operator to click, not an auto-posted (fake) tweet id.
    with SessionLocal() as session:
        drop = _seed_drop(session)
        FactoryPipeline(Settings(factory_dry_run=True)).run(session, drop)
        session.refresh(drop)
        assert drop.status == DropStatus.PUBLISHED
        assert drop.dry_run is True
        assert drop.x_tweet_id is None
        assert drop.x_intent_url and drop.x_intent_url.startswith("https://x.com/intent/post")
        assert drop.printful_sync_product_id.startswith("dryrun-")
        # Printful rejects SVG -> the served/mockup artifact is the rasterized PNG.
        assert drop.printful_mockup_url.endswith(f"/artifacts/{drop.id}.png")
        assert drop.error is None


def test_dry_run_api_mode_simulates_a_tweet():
    with SessionLocal() as session:
        drop = _seed_drop(session)
        FactoryPipeline(Settings(factory_dry_run=True, x_broadcast_mode="api")).run(
            session, drop
        )
        session.refresh(drop)
        assert drop.status == DropStatus.PUBLISHED
        assert drop.x_tweet_id.startswith("dryrun-")
        assert drop.x_intent_url is None  # api mode auto-posts, no manual intent URL


def test_broadcast_copy_no_storefront_is_not_a_live_claim():
    txt = FactoryPipeline._broadcast_copy("we are so back")
    assert "live" not in txt.lower()  # no false "buy it now" implication
    assert "we are so back" in txt
    assert len(txt) <= 280


def test_broadcast_copy_reserves_room_for_shop_url():
    url = "https://shop.example.com/" + "p" * 80
    txt = FactoryPipeline._broadcast_copy("x" * 400, url)
    assert url in txt  # URL is never truncated away
    assert len(txt) <= 280


def test_real_mode_fails_loud_without_config():
    # Default (dry-run off) with local storage but a localhost PUBLIC_BASE_URL
    # must fail loud — Printful can't fetch a print file from localhost.
    with SessionLocal() as session:
        drop = _seed_drop(session)
        try:
            FactoryPipeline(Settings()).run(session, drop)
        except Exception:
            pass
        session.refresh(drop)
        assert drop.status == DropStatus.FAILED
        assert drop.dry_run is False
        assert "localhost" in (drop.error or "").lower()
