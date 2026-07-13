"""Additive-column migration (`_add_missing_columns`). The autouse fresh-DB
fixture always builds the full schema via create_all, so the ALTER path only runs
here: we recreate an OLD-schema table lacking the v2 columns and assert the
migration backfills it, preserves existing rows, and is idempotent."""

from sqlalchemy import inspect, text

from app.database import _ADDITIVE_COLUMNS, Base, SessionLocal, _add_missing_columns, engine
from app.models import Trend, utcnow

_OLD_TRENDS = """
CREATE TABLE trends (
  id INTEGER PRIMARY KEY, term VARCHAR(280), term_raw VARCHAR(512),
  source VARCHAR(64), source_url VARCHAR(1024), measurement VARCHAR(32),
  volume INTEGER, prev_volume INTEGER, velocity FLOAT, hype_score FLOAT,
  first_seen_at DATETIME, last_seen_at DATETIME)
"""


def _recreate_old_trends() -> None:
    """Replace the fresh `trends` table with the pre-v2 schema + one row."""
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS trends"))
        conn.execute(text(_OLD_TRENDS))
        conn.execute(
            text(
                "INSERT INTO trends (id, term, term_raw, source, measurement, volume) "
                "VALUES (1, 'old row', 'old row', 'simulated', 'seed', 100)"
            )
        )
    # Drop pooled connections so later reflections/connections don't serve a stale
    # per-connection SQLite schema cache from before this DROP/CREATE.
    engine.dispose()


def _trend_columns() -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns("trends")}


def test_migration_adds_missing_columns_to_existing_table():
    _recreate_old_trends()
    assert not {"context", "angles", "ip_risk"} & _trend_columns()  # old schema
    _add_missing_columns()
    assert {"context", "angles", "ip_risk"} <= _trend_columns()


def test_migration_preserves_existing_rows_as_null():
    _recreate_old_trends()
    _add_missing_columns()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT term, context, angles, ip_risk FROM trends WHERE id = 1")
        ).fetchone()
    assert tuple(row) == ("old row", None, None, None)


def test_migration_is_idempotent():
    _recreate_old_trends()
    _add_missing_columns()
    _add_missing_columns()  # a second run must not raise "duplicate column"
    assert {"context", "angles", "ip_risk"} <= _trend_columns()


def test_json_column_roundtrips_after_alter_add_column():
    # The ALTER adds `angles JSON`; the ORM must still read/write a Python list
    # through it (SQLite stores it as a JSON-affinity TEXT column).
    _recreate_old_trends()
    _add_missing_columns()
    with SessionLocal() as s:
        t = Trend(
            term="new", term_raw="new", source="discovered", measurement="shirt_score",
            volume=78, hype_score=78, context="c", angles=["a", "b"], ip_risk=True,
            first_seen_at=utcnow(), last_seen_at=utcnow(),
        )
        s.add(t)
        s.commit()
        tid = t.id
    with SessionLocal() as s:
        t = s.get(Trend, tid)
        assert t.angles == ["a", "b"] and t.ip_risk is True and t.context == "c"


def test_additive_columns_reference_real_model_columns():
    # Parity guard: every migration entry must name a column the model actually
    # declares, so the two can't silently drift (CLAUDE.md: test the copies match).
    for table, column, _type in _ADDITIVE_COLUMNS:
        model_cols = {c.name for c in Base.metadata.tables[table].columns}
        assert column in model_cols, f"_ADDITIVE_COLUMNS[{table}.{column}] has no model column"
