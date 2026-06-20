"""Test config. Sets env BEFORE any app import so the cached Settings and the
SQLAlchemy engine bind to a throwaway SQLite file with the Radar disabled.
"""

from __future__ import annotations

import os
from pathlib import Path

_TEST_DB = Path(__file__).parent / ".pytest_shirtpost.db"

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["RADAR_ENABLED"] = "false"
os.environ["ALLOWED_HOSTS"] = '["testserver","localhost","127.0.0.1"]'

import pytest  # noqa: E402

from app.database import Base, engine  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def pytest_sessionfinish(session, exitstatus):
    if _TEST_DB.exists():
        _TEST_DB.unlink()
