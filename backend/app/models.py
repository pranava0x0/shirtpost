"""ORM models. All datetimes stored as naive UTC (SQLite has no tz type).

Provenance is first-class: every Trend carries its ``source`` and ``source_url``,
and the original pre-cleaning title is preserved in ``term_raw`` so a bad
HTML-strip can always be debugged or re-derived.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    """Naive UTC. Single source of "now" for the whole backend."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DropStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PUBLISHED = "published"
    FAILED = "failed"


class Trend(Base):
    __tablename__ = "trends"
    __table_args__ = (UniqueConstraint("source", "term", name="uq_trend_source_term"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    term: Mapped[str] = mapped_column(String(280), index=True)  # cleaned, HTML-stripped
    term_raw: Mapped[str] = mapped_column(String(512))  # original title, pre-clean
    source: Mapped[str] = mapped_column(String(64), index=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # What `volume` measures for this source (e.g. "search_traffic", "presence",
    # "seed"). NOT comparable across sources — surfaced so the UI never implies it.
    measurement: Mapped[str] = mapped_column(String(32), default="unknown")

    volume: Mapped[int] = mapped_column(Integer, default=0)  # mentions, latest observation
    prev_volume: Mapped[int] = mapped_column(Integer, default=0)
    velocity: Mapped[float] = mapped_column(Float, default=0.0)  # mentions/hour gained
    hype_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    drops: Mapped[list["Drop"]] = relationship(
        back_populates="trend", cascade="all, delete-orphan"
    )
    observations: Mapped[list["TrendObservation"]] = relationship(
        back_populates="trend",
        cascade="all, delete-orphan",
        order_by="TrendObservation.observed_at",
    )


class TrendObservation(Base):
    """Append-only snapshot of a trend at one sweep. The Trend row keeps only the
    latest + previous volume; this table keeps every observation, so a true
    velocity curve can be reconstructed instead of a single latest delta.
    Never updated in place — one row per (trend, sweep).
    """

    __tablename__ = "trend_observations"
    __table_args__ = (
        Index("ix_trend_observation_trend_time", "trend_id", "observed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trend_id: Mapped[int] = mapped_column(
        ForeignKey("trends.id", ondelete="CASCADE"), index=True
    )
    trend: Mapped[Trend] = relationship(back_populates="observations")

    volume: Mapped[int] = mapped_column(Integer)
    velocity: Mapped[float] = mapped_column(Float)
    hype_score: Mapped[float] = mapped_column(Float)
    # Carried per row so a curve is self-describing even if a source later changes
    # what `volume` measures (search_traffic / presence / seed).
    measurement: Mapped[str] = mapped_column(String(32))
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Drop(Base):
    __tablename__ = "drops"
    __table_args__ = (
        # DB-level invariant: at most one in-flight (pending/processing) drop per
        # trend. Makes the 409 guard race-proof rather than check-then-insert.
        Index(
            "uq_drop_inflight_per_trend",
            "trend_id",
            unique=True,
            sqlite_where=text("status IN ('pending', 'processing')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trend_id: Mapped[int] = mapped_column(
        ForeignKey("trends.id", ondelete="CASCADE"), index=True
    )
    trend: Mapped[Trend] = relationship(back_populates="drops")

    design_copy: Mapped[str] = mapped_column(Text)  # operator-authored, from their own LLM

    # Store the enum *value* ("pending") not the name, so the partial-index
    # predicate above matches and the DB/API agree on the string.
    status: Mapped[DropStatus] = mapped_column(
        Enum(DropStatus, values_callable=lambda e: [m.value for m in e], name="dropstatus"),
        default=DropStatus.PENDING,
        index=True,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)  # surfaced, never swallowed

    printful_mockup_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    printful_sync_product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    x_tweet_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # set when auto-posted (api mode)
    # Prefilled x.com/intent/post URL for the operator to click (intent mode, $0).
    x_intent_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)  # simulated, not really published

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
