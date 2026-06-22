"""Test config. Sets env BEFORE any app import so the cached Settings and the
SQLAlchemy engine bind to throwaway paths with the Radar disabled and live-fetch
rate limiting turned off (so tests never sleep or hit the network).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

_HERE = Path(__file__).parent
_TEST_DB = _HERE / ".pytest_shirtpost.db"
_CACHE_DIR = _HERE / ".pytest_radar_cache"
_ARTIFACTS_DIR = _HERE / ".pytest_artifacts"

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["RADAR_ENABLED"] = "false"
os.environ["ALLOWED_HOSTS"] = '["testserver","localhost","127.0.0.1"]'
os.environ["RADAR_MIN_REQUEST_INTERVAL_SECONDS"] = "0"
os.environ["RADAR_CACHE_DIR"] = str(_CACHE_DIR)
os.environ["ARTIFACTS_DIR"] = str(_ARTIFACTS_DIR)

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
    for d in (_CACHE_DIR, _ARTIFACTS_DIR):
        shutil.rmtree(d, ignore_errors=True)
