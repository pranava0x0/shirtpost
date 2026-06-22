"""Source feed adapters. Text-only: every title is stripped of HTML markup with
BeautifulSoup before it is stored or scored, keeping the data (and tokens) clean.

A "simulated" source lets the whole pipeline run end-to-end with zero external
credentials or network access.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import feedparser
from bs4 import BeautifulSoup

from app.config import get_settings
from app.radar import fetch

logger = logging.getLogger(__name__)

_WS = re.compile(r"\s+")


@dataclass(slots=True)
class RawTrend:
    term: str  # cleaned, HTML-stripped
    term_raw: str  # original title, pre-clean
    source: str
    source_url: str | None
    volume: int
    measurement: str  # what `volume` measures; NOT comparable across sources


def clean_text(value: str) -> str:
    """Strip all HTML markup and collapse whitespace. Text-only and token-cheap."""
    text = BeautifulSoup(value or "", "html.parser").get_text(separator=" ")
    return _WS.sub(" ", text).strip()


def _parse_volume(entry: object) -> tuple[int, str]:
    """Return (volume, measurement). Google Trends RSS exposes ht:approx_traffic
    (e.g. "200,000+") = a search-traffic estimate; otherwise the feed merely
    listed the item, so volume is a placeholder 1 with measurement "presence"."""
    approx = entry.get("ht_approx_traffic") if hasattr(entry, "get") else None
    if approx:
        digits = re.sub(r"[^\d]", "", str(approx))
        if digits:
            return int(digits), "search_traffic"
    return 1, "presence"


def fetch_rss(source_id: str, url: str) -> list[RawTrend]:
    body = fetch.get(url)
    if body is None:
        return []
    feed = feedparser.parse(body)
    out: list[RawTrend] = []
    for entry in feed.entries:
        raw_title = getattr(entry, "title", "") or ""
        term = clean_text(raw_title)
        if not term:
            continue
        volume, measurement = _parse_volume(entry)
        out.append(
            RawTrend(
                term=term,
                term_raw=raw_title,
                source=source_id,
                source_url=getattr(entry, "link", None),
                volume=volume,
                measurement=measurement,
            )
        )
    logger.info("radar source=%s parsed=%d", source_id, len(out))
    return out


# Family-friendly, lighthearted seeds so the queue is never empty in dev.
_SIMULATED: list[tuple[str, int]] = [
    ("we are so back", 92_000),
    ("make no mistakes", 41_000),
    ("very mindful very demure", 158_000),
    ("delulu is the solulu", 73_000),
    ("it's giving main character", 55_000),
]


def fetch_simulated(source_id: str = "simulated") -> list[RawTrend]:
    return [
        RawTrend(
            term=clean_text(t),
            term_raw=t,
            source=source_id,
            source_url=None,
            volume=v,
            measurement="seed",
        )
        for t, v in _SIMULATED
    ]


def collect(source_ids: list[str]) -> list[RawTrend]:
    """Run every configured source. One source crashing never sinks the rest."""
    settings = get_settings()
    results: list[RawTrend] = []
    for sid in source_ids:
        try:
            if sid == "simulated":
                results.extend(fetch_simulated())
            elif sid == "google_trends":
                results.extend(fetch_rss("google_trends", settings.google_trends_rss_url))
            elif sid == "reddit":
                results.extend(fetch_rss("reddit", settings.reddit_rss_url))
            else:
                logger.warning("unknown radar source id=%s (skipping)", sid)
        except Exception as exc:
            logger.exception("radar source=%s crashed: %s", sid, exc)
    return results
