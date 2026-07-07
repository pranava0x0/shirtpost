"""Admin API: list trends by Hype Score, submit design copy, list drops.

Submission triggers the Factory pipeline as a background task so the operator
gets an immediate 201; the Drop's status/error reflect the outcome and are
polled by the dashboard.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.copy.generate import QuipConfigError, QuipError, generate_quips
from app.database import SessionLocal, get_session
from app.factory.pipeline import FactoryPipeline
from app.models import Drop, DropStatus, Trend, TrendObservation
from app.schemas import (
    DesignSubmission,
    DropOut,
    QuipsOut,
    TrendObservationOut,
    TrendOut,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# How many recent observations feed each trend's inline sparkline.
SPARK_POINTS = 24


def _spark_map(session: Session, trend_ids: list[int]) -> dict[int, list[float]]:
    """Last SPARK_POINTS hype scores per trend, oldest->newest. One windowed
    query for the whole page, so the sparkline never costs a query-per-trend."""
    if not trend_ids:
        return {}
    rn = (
        func.row_number()
        .over(
            partition_by=TrendObservation.trend_id,
            order_by=TrendObservation.observed_at.desc(),
        )
        .label("rn")
    )
    recent = (
        select(
            TrendObservation.trend_id.label("trend_id"),
            TrendObservation.hype_score.label("hype_score"),
            TrendObservation.observed_at.label("observed_at"),
            rn,
        )
        .where(TrendObservation.trend_id.in_(trend_ids))
        .subquery()
    )
    rows = session.execute(
        select(recent.c.trend_id, recent.c.hype_score)
        .where(recent.c.rn <= SPARK_POINTS)
        .order_by(recent.c.trend_id, recent.c.observed_at)  # oldest -> newest
    ).all()
    out: dict[int, list[float]] = {}
    for trend_id, hype in rows:
        out.setdefault(trend_id, []).append(round(hype, 2))
    return out


def _source_bounds(session: Session) -> dict[str, tuple[float, float]]:
    """Per-source (min, max) hype over the full population, so normalized_hype is
    a stable within-source scale rather than a per-page artifact."""
    rows = session.execute(
        select(
            Trend.source,
            func.min(Trend.hype_score),
            func.max(Trend.hype_score),
        ).group_by(Trend.source)
    ).all()
    return {source: (lo, hi) for source, lo, hi in rows}


@router.get("/trends", response_model=list[TrendOut])
def list_trends(
    limit: int = 50,
    source: str | None = None,
    session: Session = Depends(get_session),
) -> list[Trend]:
    limit = max(1, min(limit, 200))
    stmt = select(Trend).order_by(Trend.hype_score.desc()).limit(limit)
    if source:
        stmt = stmt.where(Trend.source == source)
    trends = list(session.scalars(stmt).all())

    # Enrich with the within-source normalized hype and the sparkline series.
    bounds = _source_bounds(session)
    sparks = _spark_map(session, [t.id for t in trends])
    for t in trends:
        lo, hi = bounds.get(t.source, (t.hype_score, t.hype_score))
        t.normalized_hype = (t.hype_score - lo) / (hi - lo) if hi > lo else 1.0
        t.spark = sparks.get(t.id, [])
    return trends


@router.get(
    "/trends/{trend_id}/observations", response_model=list[TrendObservationOut]
)
def list_trend_observations(
    trend_id: int,
    limit: int = 200,
    session: Session = Depends(get_session),
) -> list[TrendObservation]:
    """Append-only observation history for one trend, newest first. `limit` is a
    display cap on the response, not on what is stored (the table keeps every
    sweep)."""
    if session.get(Trend, trend_id) is None:
        raise HTTPException(status_code=404, detail="trend not found")
    limit = max(1, min(limit, 1000))
    return list(
        session.scalars(
            select(TrendObservation)
            .where(TrendObservation.trend_id == trend_id)
            .order_by(TrendObservation.observed_at.desc())
            .limit(limit)
        ).all()
    )


@router.get("/drops", response_model=list[DropOut])
def list_drops(session: Session = Depends(get_session)) -> list[Drop]:
    return list(session.scalars(select(Drop).order_by(Drop.created_at.desc())).all())


@router.get("/drops/{drop_id}", response_model=DropOut)
def get_drop(drop_id: int, session: Session = Depends(get_session)) -> Drop:
    drop = session.get(Drop, drop_id)
    if drop is None:
        raise HTTPException(status_code=404, detail="drop not found")
    return drop


@router.post("/trends/{trend_id}/quips", response_model=QuipsOut)
def generate_trend_quips(
    trend_id: int,
    count: int | None = None,
    session: Session = Depends(get_session),
) -> QuipsOut:
    """Propose funny one-liner shirt slogans for a trend via Claude. The operator
    picks one and submits it as design copy — this never auto-fires the Factory."""
    trend = session.get(Trend, trend_id)
    if trend is None:
        raise HTTPException(status_code=404, detail="trend not found")
    try:
        quips = generate_quips(
            trend.term,
            source=trend.source,
            measurement=trend.measurement,
            count=count,
        )
    except QuipConfigError as exc:
        # Not configured (no key) — fail loud so the operator knows to paste copy.
        raise HTTPException(status_code=503, detail=str(exc))
    except QuipError as exc:
        # The model ran but returned nothing usable — a real upstream failure.
        raise HTTPException(status_code=502, detail=str(exc))
    return QuipsOut(quips=quips)


@router.post("/radar/sweep")
def trigger_sweep() -> dict[str, int]:
    """Force an immediate radar sweep instead of waiting for the interval."""
    from app.radar.worker import run_sweep_once

    return {"touched": run_sweep_once()}


def _run_pipeline(drop_id: int) -> None:
    """Background runner. The pipeline records status/error on the Drop itself;
    we log here so a background failure is never silent."""
    with SessionLocal() as session:
        drop = session.get(Drop, drop_id)
        if drop is None:
            logger.error("pipeline: drop %s vanished before execution", drop_id)
            return
        try:
            FactoryPipeline().run(session, drop)
        except Exception:
            logger.exception("pipeline: drop %s failed (recorded on drop)", drop_id)


@router.post("/trends/{trend_id}/submit", response_model=DropOut, status_code=201)
def submit_design(
    trend_id: int,
    body: DesignSubmission,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> Drop:
    trend = session.get(Trend, trend_id)
    if trend is None:
        raise HTTPException(status_code=404, detail="trend not found")
    # Fast path: friendly 409 without hitting the constraint in the common case.
    in_flight = session.scalar(
        select(Drop).where(
            Drop.trend_id == trend.id,
            Drop.status.in_([DropStatus.PENDING, DropStatus.PROCESSING]),
        )
    )
    if in_flight is not None:
        raise HTTPException(
            status_code=409, detail="a drop for this trend is already in flight"
        )
    drop = Drop(trend_id=trend.id, design_copy=body.design_copy, status=DropStatus.PENDING)
    session.add(drop)
    try:
        # Authoritative guard: the partial unique index rejects a concurrent
        # second in-flight drop even if two requests passed the check above.
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="a drop for this trend is already in flight"
        )
    session.commit()
    session.refresh(drop)
    background.add_task(_run_pipeline, drop.id)
    return drop


@router.post("/drops/{drop_id}/retry", response_model=DropOut, status_code=202)
def retry_drop(
    drop_id: int,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> Drop:
    """Re-run a FAILED drop. The pipeline resumes from the last committed step
    (mockup / sync / tweet), so an already-posted tweet is never sent twice."""
    drop = session.get(Drop, drop_id)
    if drop is None:
        raise HTTPException(status_code=404, detail="drop not found")
    if drop.status != DropStatus.FAILED:
        raise HTTPException(
            status_code=409, detail=f"only failed drops can be retried (is {drop.status.value})"
        )
    # Reserve the in-flight slot synchronously so a concurrent submit can't race
    # in between here and the background run. The partial unique index rejects a
    # retry when another drop for the same trend is already in flight.
    drop.status = DropStatus.PROCESSING
    drop.error = None
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="another drop for this trend is already in flight"
        )
    session.commit()
    session.refresh(drop)
    background.add_task(_run_pipeline, drop.id)
    return drop
