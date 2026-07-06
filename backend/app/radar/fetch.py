"""HTTP fetch for live radar sources, with the manners CLAUDE.md asks for:

- **Disk cache** so re-runs within the cache window never re-download.
- **Per-host rate limiting** (>= configured interval between requests to a host).
- **429 backoff** — exponential from 10s.

Failures are logged and return ``None`` — a bad source never crashes the sweep.
The simulated source does not go through here, so tests stay offline.
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests

from app.config import get_settings

logger = logging.getLogger(__name__)

# host -> monotonic-ish timestamp of last request (process-local).
_last_request_at: dict[str, float] = {}


def _host(url: str) -> str:
    return urlsplit(url).netloc or "unknown"


def _cache_path(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return Path(get_settings().radar_cache_dir) / f"{digest}.cache"


def _read_cache(url: str, max_age: float) -> str | None:
    if max_age <= 0:
        return None
    path = _cache_path(url)
    if not path.exists():
        return None
    age = time.time() - path.stat().st_mtime
    if age > max_age:
        return None
    logger.info("radar cache hit url=%s age=%.0fs", url, age)
    return path.read_text(encoding="utf-8")


def _write_cache(url: str, body: str) -> None:
    path = _cache_path(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _respect_rate_limit(host: str, min_interval: float) -> None:
    last = _last_request_at.get(host)
    if last is not None:
        wait = min_interval - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
    _last_request_at[host] = time.time()


def get(url: str) -> str | None:
    """Fetch ``url`` as text, honoring cache + rate limit + backoff. None on failure."""
    settings = get_settings()
    cached = _read_cache(url, settings.radar_feed_cache_seconds)
    if cached is not None:
        return cached

    host = _host(url)
    backoff = 10.0
    for attempt in range(settings.radar_max_retries + 1):
        _respect_rate_limit(host, settings.radar_min_request_interval_seconds)
        try:
            resp = requests.get(
                url, headers={"User-Agent": settings.user_agent}, timeout=15
            )
        except requests.RequestException as exc:
            # A down/refusing host: back off like a 429 instead of burning every
            # retry in a tight burst, so a transient blip is ridden through.
            logger.warning(
                "radar fetch error url=%s attempt=%d err=%s; backing off %.0fs",
                url, attempt, exc, backoff,
            )
            time.sleep(backoff)
            backoff *= 2
            continue
        if resp.status_code == 429:
            logger.warning("radar 429 url=%s; backing off %.0fs", url, backoff)
            time.sleep(backoff)
            backoff *= 2
            continue
        if resp.status_code >= 400:
            logger.warning("radar fetch url=%s -> %d", url, resp.status_code)
            return None
        _write_cache(url, resp.text)
        return resp.text
    logger.warning("radar fetch giving up url=%s after retries", url)
    return None
