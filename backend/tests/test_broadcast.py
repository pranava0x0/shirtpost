"""X broadcast modes. Default "intent" is $0: the Factory generates a prefilled
x.com/intent/post URL the operator clicks — no API key, no metered post."""

from urllib.parse import parse_qs, urlparse

from app.config import Settings
from app.database import SessionLocal
from app.factory.pipeline import FactoryPipeline
from app.factory.xcom import build_x_intent_url
from app.models import Drop, DropStatus, Trend, utcnow


def test_intent_url_encodes_text():
    url = build_x_intent_url('trend "x" & y')
    assert url.startswith("https://x.com/intent/post?text=")
    text = parse_qs(urlparse(url).query)["text"][0]
    assert text == 'trend "x" & y'  # round-trips through URL encoding


def _seed_drop(session, store_base=None) -> Drop:
    trend = Trend(
        term="very demure", term_raw="very demure", source="simulated",
        volume=1000, hype_score=1000.0, first_seen_at=utcnow(), last_seen_at=utcnow(),
    )
    session.add(trend)
    session.commit()
    drop = Drop(trend_id=trend.id, design_copy="very demure", status=DropStatus.PENDING)
    session.add(drop)
    session.commit()
    return drop


def test_intent_mode_needs_no_x_credentials():
    # The whole point of intent mode: complete the loop with NO X keys. Dry-run
    # keeps Printful out of it too, so this runs fully keyless.
    with SessionLocal() as session:
        drop = _seed_drop(session)
        FactoryPipeline(Settings(factory_dry_run=True)).run(session, drop)  # intent default
        session.refresh(drop)
        assert drop.status == DropStatus.PUBLISHED
        assert drop.x_tweet_id is None
        assert drop.x_intent_url.startswith("https://x.com/intent/post?text=")


def test_intent_text_is_a_teaser_without_a_storefront():
    with SessionLocal() as session:
        drop = _seed_drop(session)
        FactoryPipeline(Settings(factory_dry_run=True)).run(session, drop)
        session.refresh(drop)
        text = parse_qs(urlparse(drop.x_intent_url).query)["text"][0]
        assert "very demure" in text
        assert "live" not in text.lower()  # honest: not a buyable claim yet


def test_intent_url_is_idempotent_across_retries():
    # Regenerating on retry is harmless but the URL should not change/duplicate.
    with SessionLocal() as session:
        drop = _seed_drop(session)
        pipe = FactoryPipeline(Settings(factory_dry_run=True))
        pipe.run(session, drop)
        session.refresh(drop)
        first = drop.x_intent_url
        drop.status = DropStatus.FAILED  # pretend it failed, then retry
        session.commit()
        pipe.run(session, drop)
        session.refresh(drop)
        assert drop.x_intent_url == first
