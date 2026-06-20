"""Admin API: list trends by Hype Score, submit design copy, list drops.

Submission triggers the Factory pipeline as a background task so the operator
gets an immediate 201; the Drop's status/error reflect the outcome and are
polled by the dashboard.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_session
from app.factory.pipeline import FactoryPipeline
from app.models import Drop, DropStatus, Trend
from app.schemas import DesignSubmission, DropOut, TrendOut

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/trends", response_model=list[TrendOut])
def list_trends(limit: int = 50, session: Session = Depends(get_session)) -> list[Trend]:
    limit = max(1, min(limit, 200))
    return list(
        session.scalars(
            select(Trend).order_by(Trend.hype_score.desc()).limit(limit)
        ).all()
    )


@router.get("/drops", response_model=list[DropOut])
def list_drops(session: Session = Depends(get_session)) -> list[Drop]:
    return list(session.scalars(select(Drop).order_by(Drop.created_at.desc())).all())


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
    drop = Drop(trend_id=trend.id, design_copy=body.design_copy, status=DropStatus.PENDING)
    session.add(drop)
    session.commit()
    session.refresh(drop)
    background.add_task(_run_pipeline, drop.id)
    return drop
