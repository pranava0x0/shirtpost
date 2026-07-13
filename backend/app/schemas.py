"""Pydantic request/response schemas. Validated before anything touches the DB."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.factory.render import DEFAULT_LAYOUT, LAYOUTS
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
    # Discovery enrichment, null for attention-based sources. `context` grounds the
    # quip generator ("why this is trending"); `angles` are comedic-direction hints;
    # `ip_risk` flags a term built on a real person/brand/franchise/lyric so the
    # dashboard warns and the generator riffs around it. See TRENDS-DISCOVERY-SPEC.
    context: str | None = None
    angles: list[str] | None = None
    ip_risk: bool | None = None
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
    layout: str | None
    garment_color: str | None
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
    # Merch variety (Part C). Both optional: layout defaults to "centered", and a
    # null garment_color falls back to the config default at render time.
    layout: str | None = None
    garment_color: str | None = Field(default=None, max_length=64)

    @field_validator("layout")
    @classmethod
    def _known_layout(cls, v: str | None) -> str | None:
        if v is not None and v not in LAYOUTS:
            raise ValueError(f"layout must be one of {LAYOUTS} (or omitted for {DEFAULT_LAYOUT})")
        return v
