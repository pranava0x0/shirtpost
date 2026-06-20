"""Background poller. Sweeps configured sources on an interval and upserts trends,
recomputing velocity + Hype Score per observation. Per-item try/except keeps one
bad record from sinking the sweep.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import Trend, utcnow
from app.radar import scoring, sources

logger = logging.getLogger(__name__)


def run_sweep_once() -> int:
    """Fetch all configured sources and upsert trends. Returns rows touched."""
    settings = get_settings()
    raw = sources.collect(settings.radar_sources)
    now = utcnow()
    touched = 0
    with SessionLocal() as session:
        for item in raw:
            try:
                trend = session.scalar(
                    select(Trend).where(
                        Trend.source == item.source, Trend.term == item.term
                    )
                )
                if trend is None:
                    velocity = scoring.compute_velocity(0, item.volume, now, now)
                    session.add(
                        Trend(
                            term=item.term,
                            term_raw=item.term_raw,
                            source=item.source,
                            source_url=item.source_url,
                            volume=item.volume,
                            prev_volume=0,
                            velocity=velocity,
                            hype_score=scoring.hype_score(velocity, item.volume),
                            first_seen_at=now,
                            last_seen_at=now,
                        )
                    )
                else:
                    velocity = scoring.compute_velocity(
                        trend.volume, item.volume, trend.last_seen_at, now
                    )
                    trend.prev_volume = trend.volume
                    trend.volume = item.volume
                    trend.velocity = velocity
                    trend.hype_score = scoring.hype_score(velocity, item.volume)
                    trend.last_seen_at = now
                    if item.source_url:
                        trend.source_url = item.source_url
                touched += 1
            except Exception as exc:  # per-record resilience
                logger.exception("radar upsert failed term=%r: %s", item.term, exc)
        session.commit()
    logger.info("radar sweep complete touched=%d", touched)
    return touched


async def radar_loop(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    logger.info(
        "radar loop start interval=%ss sources=%s",
        settings.radar_poll_interval_seconds,
        settings.radar_sources,
    )
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(run_sweep_once)
        except Exception as exc:
            logger.exception("radar sweep crashed: %s", exc)
        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=settings.radar_poll_interval_seconds
            )
        except asyncio.TimeoutError:
            pass  # interval elapsed -> next sweep
