"""SQLAlchemy engine/session wiring. FastAPI is the sole owner of this database."""

from __future__ import annotations

import logging
from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger(__name__)

# Additive columns create_all() can't add to an existing table (it only creates
# missing tables). Each entry is (table, column, SQL type). SQLite ADD COLUMN is
# cheap and the values default to NULL, matching each column's nullable model
# definition — so an existing dev DB gains them without a full migration tool.
_ADDITIVE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("trends", "context", "TEXT"),
    ("trends", "angles", "JSON"),
    ("trends", "ip_risk", "BOOLEAN"),
    ("drops", "layout", "VARCHAR(32)"),
)


class Base(DeclarativeBase):
    pass


_settings = get_settings()
_connect_args = (
    {"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {}
)
engine = create_engine(
    _settings.database_url, echo=False, future=True, connect_args=_connect_args
)
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, expire_on_commit=False, class_=Session
)


def init_db() -> None:
    """Create tables, then add any additive columns missing on existing tables.
    Idempotent — safe to call on every boot."""
    from app import models  # noqa: F401  (register models on Base.metadata)

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


def _add_missing_columns() -> None:
    """Lightweight forward-only migration: ADD COLUMN for any `_ADDITIVE_COLUMNS`
    entry absent from an existing table. A fresh DB already has them from
    create_all(), so this is a no-op there; on an upgraded DB it backfills NULLs.

    We attempt each ALTER and treat "duplicate column" as already-present rather
    than reflecting first: SQLite caches schema per pooled connection, so a
    reflection on one connection can disagree with the ALTER on another (it bites
    the test suite, which churns DROP/CREATE). Trusting the ALTER + swallowing the
    duplicate is fully idempotent and immune to that staleness. Each ALTER runs in
    its own transaction so a caught duplicate can't poison the others."""
    existing_tables = set(inspect(engine).get_table_names())
    for table, column, col_type in _ADDITIVE_COLUMNS:
        if table not in existing_tables:
            continue  # create_all handles a table it fully owns
        try:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
            logger.info("migrated: added %s.%s (%s)", table, column, col_type)
        except OperationalError as exc:
            if "duplicate column" in str(exc).lower():
                continue  # already present — idempotent
            raise


def get_session() -> Iterator[Session]:
    """FastAPI dependency. Commits on success, rolls back on error, always closes."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
