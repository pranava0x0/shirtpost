"""Pydantic request/response schemas. Validated before anything touches the DB."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import DropStatus


class TrendOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    term: str
    source: str
    source_url: str | None
    volume: int
    velocity: float
    hype_score: float
    first_seen_at: datetime
    last_seen_at: datetime


class DropOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trend_id: int
    design_copy: str
    status: DropStatus
    error: str | None
    printful_mockup_url: str | None
    printful_sync_product_id: str | None
    x_tweet_id: str | None
    created_at: datetime
    published_at: datetime | None


class DesignSubmission(BaseModel):
    """Operator-pasted design copy. ``extra="forbid"`` rejects unexpected fields."""

    model_config = ConfigDict(extra="forbid")

    design_copy: str = Field(min_length=1, max_length=500)
