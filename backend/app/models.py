"""ORM models. All datetimes stored as naive UTC (SQLite has no tz type).

Provenance is first-class: every Trend carries its ``source`` and ``source_url``,
and the original pre-cleaning title is preserved in ``term_raw`` so a bad
HTML-strip can always be debugged or re-derived.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
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

    volume: Mapped[int] = mapped_column(Integer, default=0)  # mentions, latest observation
    prev_volume: Mapped[int] = mapped_column(Integer, default=0)
    velocity: Mapped[float] = mapped_column(Float, default=0.0)  # mentions/hour gained
    hype_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    drops: Mapped[list["Drop"]] = relationship(
        back_populates="trend", cascade="all, delete-orphan"
    )


class Drop(Base):
    __tablename__ = "drops"

    id: Mapped[int] = mapped_column(primary_key=True)
    trend_id: Mapped[int] = mapped_column(
        ForeignKey("trends.id", ondelete="CASCADE"), index=True
    )
    trend: Mapped[Trend] = relationship(back_populates="drops")

    design_copy: Mapped[str] = mapped_column(Text)  # operator-authored, from their own LLM

    status: Mapped[DropStatus] = mapped_column(
        Enum(DropStatus), default=DropStatus.PENDING, index=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)  # surfaced, never swallowed

    printful_mockup_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    printful_sync_product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    x_tweet_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
