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
    measurement: str
    volume: int
    velocity: float
    hype_score: float
    # Hype relative to *its own source* (0..1, min-max over all trends of that
    # source). Volumes are NOT comparable across sources, so this is the honest
    # within-lane scale for a bar; never a cross-source ranking. 1.0 when a
    # source has a single trend. Derived at read time.
    normalized_hype: float = 1.0
    # Recent hype trajectory (oldest -> newest) for an inline sparkline. Derived
    # from trend_observations at read time; capped, not the full history.
    spark: list[float] = Field(default_factory=list)
    first_seen_at: datetime
    last_seen_at: datetime


class TrendObservationOut(BaseModel):
    """One append-only snapshot of a trend at a single sweep."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    trend_id: int
    volume: int
    velocity: float
    hype_score: float
    measurement: str
    observed_at: datetime


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
    x_intent_url: str | None
    dry_run: bool
    created_at: datetime
    published_at: datetime | None


class DesignSubmission(BaseModel):
    """Operator-pasted design copy. ``extra="forbid"`` rejects unexpected fields."""

    model_config = ConfigDict(extra="forbid")

    design_copy: str = Field(min_length=1, max_length=500)
