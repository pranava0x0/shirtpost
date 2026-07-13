"""Source feed adapters. Text-only: every title is stripped of HTML markup with
BeautifulSoup before it is stored or scored, keeping the data (and tokens) clean.

A "simulated" source lets the whole pipeline run end-to-end with zero external
credentials or network access. "wikipedia" is the ToS-clean real source (open
pageviews API, no key). Reddit was dropped — its free API forbids commercial use.
"""

from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Judged shirt_score is defined on a 0..100 scale (A3 rubric). Enforced at ingest.
SHIRT_SCORE_MIN = 0
SHIRT_SCORE_MAX = 100

import feedparser
from bs4 import BeautifulSoup

from app.config import get_settings
from app.radar import fetch

logger = logging.getLogger(__name__)

_WS = re.compile(r"\s+")

# Wikipedia namespaces / meta pages that aren't real trends.
_WIKI_SKIP_PREFIXES = (
    "Special:", "Wikipedia:", "Portal:", "Category:", "Help:",
    "Template:", "File:", "Talk:", "Draft:",
)


@dataclass(slots=True)
class RawTrend:
    term: str  # cleaned, HTML-stripped
    term_raw: str  # original title, pre-clean
    source: str
    source_url: str | None
    volume: int
    measurement: str  # what `volume` measures; NOT comparable across sources
    # Discovery enrichment — populated only by the "discovered" source; None for
    # every attention-based source (they have no shirt-worthiness judgment).
    context: str | None = None
    angles: list[str] | None = None
    ip_risk: bool | None = None


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
        # A real traffic estimate we couldn't parse (unexpected format) — surface
        # it instead of silently flattening to the "no signal" placeholder.
        logger.warning(
            "google_trends approx_traffic %r had no digits — using presence placeholder",
            approx,
        )
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


# Family-friendly, lighthearted seeds so the queue is never empty in dev. These
# double as the funny-phrase source *and* the house-voice anchors the quip
# generator riffs on (the best of them are mirrored in the Next.js dashboard at
# `frontend/lib/quips.ts` `STYLE_ANCHORS` — the generator lives there, not here).
# Kept a couple of originals ("we are so back", "delulu is the solulu") and
# freshened the rest toward current, wearable, meme-literate bangers.
_SIMULATED: list[tuple[str, int]] = [
    ("we are so back", 92_000),  # original, still undefeated
    ("delulu is the solulu", 73_000),  # original
    ("it's giving unemployed", 61_000),
    ("in my villain era", 79_000),
    ("gaslight gatekeep girlboss", 84_000),
    ("touch grass immediately", 58_000),
    ("crashing out respectfully", 66_000),
    ("nobody is ready for this conversation", 47_000),
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


def parse_wikipedia_top(body: str, top_n: int) -> list[RawTrend]:
    """Parse the Wikimedia most-viewed payload into trends. Split out so it can be
    tested on a fixture without any network. `volume` is real daily pageviews."""
    try:
        articles = json.loads(body)["items"][0]["articles"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        logger.warning("wikipedia parse failed: %s", exc)
        return []
    out: list[RawTrend] = []
    for art in articles:
        title = art.get("article", "") or ""
        if not title or title == "Main_Page" or title.startswith(_WIKI_SKIP_PREFIXES):
            continue
        term = clean_text(title.replace("_", " "))
        if not term:
            continue
        out.append(
            RawTrend(
                term=term,
                term_raw=title,
                source="wikipedia",
                source_url=f"https://en.wikipedia.org/wiki/{title}",
                volume=int(art.get("views", 0)),
                measurement="pageviews",
            )
        )
        if len(out) >= top_n:
            break
    return out


def fetch_wikipedia() -> list[RawTrend]:
    """Most-viewed English Wikipedia articles yesterday — free, open, ToS-clean."""
    settings = get_settings()
    # Pageviews data lags ~1 day, so read yesterday (UTC).
    day = datetime.now(timezone.utc).date() - timedelta(days=1)
    url = f"{settings.wikipedia_top_api}/{day.year}/{day.month:02d}/{day.day:02d}"
    body = fetch.get(url)
    if body is None:
        # Fetch itself failed (network / 4xx) — a coverage gap, NOT "no trends".
        # Distinguished from an empty parse below so a broken source is visible.
        logger.warning("radar source=wikipedia fetch failed url=%s — no trends this sweep", url)
        return []
    out = parse_wikipedia_top(body, settings.wikipedia_top_n)
    if not out:
        logger.warning(
            "radar source=wikipedia fetched a body but parsed 0 trends url=%s "
            "— possible API format change", url
        )
    else:
        logger.info("radar source=wikipedia parsed=%d", len(out))
    return out


def _parse_discovered_line(raw: str) -> dict | None:
    """Parse one JSONL line into the fields the adapter needs, or None if it's
    unusable (malformed JSON, missing term/shirt_score). Never raises — a bad line
    is logged and skipped so it can't sink the sweep."""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("discovered: skipping malformed JSONL line: %s", exc)
        return None
    if not isinstance(obj, dict):
        logger.warning("discovered: skipping non-object JSONL line")
        return None
    term = clean_text(str(obj.get("term", "")))
    if not term:
        logger.warning("discovered: skipping line with empty term")
        return None
    score = obj.get("shirt_score")
    # bool is a subclass of int — reject it explicitly so `true`/`false` can't
    # sneak in as a score of 1/0. Reject non-finite (Python's json accepts
    # NaN/Infinity) and anything outside the judged 0..100 range: since judged
    # scores bypass Hype (volume == shirt_score), an out-of-range value would
    # corrupt the whole discovered lane's within-source scale.
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        logger.warning("discovered: skipping term=%r with non-numeric shirt_score %r", term, score)
        return None
    if not math.isfinite(score):
        logger.warning("discovered: skipping term=%r with non-finite shirt_score %r", term, score)
        return None
    if not SHIRT_SCORE_MIN <= score <= SHIRT_SCORE_MAX:
        logger.warning(
            "discovered: skipping term=%r with out-of-range shirt_score %r (want %d..%d)",
            term, score, SHIRT_SCORE_MIN, SHIRT_SCORE_MAX,
        )
        return None
    return {
        "term": term,
        "term_raw": str(obj.get("term_raw") or obj.get("term") or term),
        "key": clean_text(str(obj.get("key") or term)).lower(),
        "day": str(obj.get("day", "")),
        "shirt_score": int(score),
        "context": obj.get("context") or None,
        "angles": obj.get("angles") if isinstance(obj.get("angles"), list) else None,
        "ip_risk": bool(obj["ip_risk"]) if isinstance(obj.get("ip_risk"), bool) else None,
        "source_url": _first_source_url(obj.get("sources")),
    }


def _first_source_url(sources: object) -> str | None:
    """First non-empty `url` from the record's `sources` array, if any."""
    if not isinstance(sources, list):
        return None
    for src in sources:
        if isinstance(src, dict) and src.get("url"):
            return str(src["url"])
    return None


def parse_discovered(body: str, *, window_days: int, today: date) -> list[RawTrend]:
    """Parse the discovered JSONL into RawTrends. Keeps only lines whose `day` is
    within the last `window_days` (bound by content, not count — the file itself is
    never trimmed). Dedupes by `key`, keeping the row with the max `shirt_score`.

    `volume` carries `shirt_score` under measurement ``shirt_score`` — an honest
    volume for its own lane, since lanes never compare across sources. The worker
    bypasses the velocity boost for this measurement (a judged score is already a
    ranking; see worker.run_sweep_once)."""
    # Exclusive lower bound: keep `today` and the prior window_days-1 days =
    # exactly window_days calendar days (e.g. window_days=14 keeps a 14-day span,
    # not 15). Future days are guarded too.
    cutoff = today - timedelta(days=window_days)
    best: dict[str, dict] = {}
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        rec = _parse_discovered_line(line)
        if rec is None:
            continue
        try:
            day = date.fromisoformat(rec["day"])
        except ValueError:
            logger.warning("discovered: term=%r has unparseable day=%r — skipping", rec["term"], rec["day"])
            continue
        if day <= cutoff or day > today:
            continue  # outside the window (future days guarded too)
        prev = best.get(rec["key"])
        if prev is None or rec["shirt_score"] > prev["shirt_score"]:
            best[rec["key"]] = rec
    out = [
        RawTrend(
            term=rec["term"],
            term_raw=rec["term_raw"],
            source="discovered",
            source_url=rec["source_url"],
            volume=rec["shirt_score"],
            measurement="shirt_score",
            context=rec["context"],
            angles=rec["angles"],
            ip_risk=rec["ip_risk"],
        )
        for rec in best.values()
    ]
    return out


def fetch_discovered() -> list[RawTrend]:
    """Read the cloud-routine's append-only discovery file from the local checkout
    and emit judged, shirt-worthy candidates. Missing/empty file logs a distinct
    "no discovery data" warning (empty ≠ broken — the routine may simply not have
    run yet), never a crash."""
    settings = get_settings()
    path = Path(settings.discovered_trends_path)
    if not path.exists():
        logger.warning(
            "radar source=discovered no file at %s — no discovery data (routine not run yet?)",
            path,
        )
        return []
    try:
        body = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("radar source=discovered could not read %s: %s", path, exc)
        return []
    if not body.strip():
        logger.warning("radar source=discovered file %s is empty — no discovery data", path)
        return []
    today = datetime.now(timezone.utc).date()
    out = parse_discovered(body, window_days=settings.discovered_window_days, today=today)
    logger.info("radar source=discovered parsed=%d (window=%dd)", len(out), settings.discovered_window_days)
    return out


def is_family_safe(term: str, blocklist: list[str]) -> bool:
    """Cheap keyword gate: drop a trend if its term contains a blocklisted word.

    Intentionally a *substring* match, not word-boundary: a safety filter must
    err toward over-blocking, and word boundaries would miss compounds like
    "Pornhub"/"pornstar" (`\\bporn\\b` doesn't match them) — a worse error than
    dropping the occasional innocent "grape". The blocklist is tuned to avoid the
    worst false positives (e.g. "execution" removed). A first-pass heuristic; an
    LLM classifier (deferred) is the real fix. Drops are counted in `collect`."""
    low = term.lower()
    return not any(bad in low for bad in blocklist)


def collect(source_ids: list[str]) -> list[RawTrend]:
    """Run every configured source. One source crashing never sinks the rest.
    Family-unsafe trends are filtered out before they reach the queue."""
    settings = get_settings()
    results: list[RawTrend] = []
    for sid in source_ids:
        try:
            if sid == "simulated":
                results.extend(fetch_simulated())
            elif sid == "wikipedia":
                results.extend(fetch_wikipedia())
            elif sid == "google_trends":
                results.extend(fetch_rss("google_trends", settings.google_trends_rss_url))
            elif sid == "discovered":
                results.extend(fetch_discovered())
            else:
                logger.warning("unknown radar source id=%s (skipping)", sid)
        except Exception as exc:
            logger.exception("radar source=%s crashed: %s", sid, exc)

    if not settings.family_safe_filter_enabled:
        return results
    kept: list[RawTrend] = []
    for row in results:
        if is_family_safe(row.term, settings.family_blocklist):
            kept.append(row)
        else:
            logger.info(
                "radar family filter dropped term=%r source=%s", row.term, row.source
            )
    dropped = len(results) - len(kept)
    if dropped:
        # A count, not just per-item info lines — so an over-broad blocklist that
        # is silently eating real trends is visible in the sweep summary.
        logger.info("radar family filter dropped %d of %d trends", dropped, len(results))
    return kept
