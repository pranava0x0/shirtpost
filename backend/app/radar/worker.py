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
from app.models import Trend, TrendObservation, utcnow
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
                    hype = scoring.hype_for(item.measurement, velocity, item.volume)
                    trend = Trend(
                        term=item.term,
                        term_raw=item.term_raw,
                        source=item.source,
                        source_url=item.source_url,
                        measurement=item.measurement,
                        volume=item.volume,
                        prev_volume=0,
                        velocity=velocity,
                        hype_score=hype,
                        context=item.context,
                        angles=item.angles,
                        ip_risk=item.ip_risk,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                    session.add(trend)
                    session.flush()  # assign trend.id for the observation FK below
                else:
                    velocity = scoring.compute_velocity(
                        trend.volume, item.volume, trend.last_seen_at, now
                    )
                    hype = scoring.hype_for(item.measurement, velocity, item.volume)
                    trend.prev_volume = trend.volume
                    trend.volume = item.volume
                    trend.velocity = velocity
                    trend.hype_score = hype
                    trend.measurement = item.measurement
                    trend.last_seen_at = now
                    if item.source_url:
                        trend.source_url = item.source_url
                    # Refresh discovery enrichment when the source re-supplies it;
                    # never clobber existing values with None (a non-discovery
                    # re-sight of the same term must not wipe context/angles).
                    if item.context is not None:
                        trend.context = item.context
                    if item.angles is not None:
                        trend.angles = item.angles
                    if item.ip_risk is not None:
                        trend.ip_risk = item.ip_risk
                # Append-only snapshot for the velocity curve. Add by trend_id
                # rather than trend.observations.append() so we never load the
                # (unbounded, ever-growing) prior history on each sweep.
                session.add(
                    TrendObservation(
                        trend_id=trend.id,
                        volume=item.volume,
                        velocity=velocity,
                        hype_score=hype,
                        measurement=item.measurement,
                        observed_at=now,
                    )
                )
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
