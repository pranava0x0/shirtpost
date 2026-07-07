"""Turn a trending topic into funny, print-ready one-liner shirt slogans.

The Radar surfaces *what* is trending; this turns a trend into candidate merch
copy. It asks Claude for a batch of banger one-liners, then runs each through the
same family-safe gate the Radar uses so nothing unsafe reaches a shirt. The model
proposes; a human still picks the winner — humor is taste, and taste isn't
automatable (see CLAUDE.md "AI has no taste").

Cost-optimized per CLAUDE.md: defaults to Haiku (cheapest that clears the bar) and
generates a *batch* so the operator can pick the funniest even if a few land flat.
Set ``QUIP_MODEL`` to a Sonnet id for wittier (pricier) output.

Keyless/$0 path: without ``ANTHROPIC_API_KEY`` this fails loud — the operator can
still paste their own copy into the drop. No network happens at import time.
"""

from __future__ import annotations

import json
import logging
import re

import anthropic
from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings
from app.radar.sources import is_family_safe

logger = logging.getLogger(__name__)


class QuipConfigError(RuntimeError):
    """The generator can't run because it isn't configured (e.g. no API key)."""


class QuipError(RuntimeError):
    """The model call ran but produced nothing usable (bad JSON, empty batch)."""


class _QuipBatch(BaseModel):
    """The exact shape we ask the model to return. Validated before use."""

    quips: list[str]


# The original simulated seeds, reused as *style anchors* in the prompt so the
# model matches the house voice (short, current, meme-literate) — see
# radar/sources.py. Keep this in sync with the funniest seeds there.
_STYLE_ANCHORS = (
    "we are so back",
    "delulu is the solulu",
    "it's giving unemployed",
    "in my villain era",
)

_SYSTEM = (
    "You write merch copy: short, funny one-liners for t-shirts and stickers. "
    "You are handed a phrase or topic that is trending right now and must riff on "
    "it into banger one-liners someone would actually wear.\n\n"
    "Rules:\n"
    "- Punchy. Most lines are 2-6 words; never more than ~8. A shirt is not a "
    "paragraph.\n"
    "- Actually funny: play on the trend, subvert it, or deadpan it. No corny "
    "puns, no hashtags, no emoji, no quotation marks around the line.\n"
    "- Wearable: self-deprecating, absurd, or relatable beats mean-spirited. "
    "Keep it family-safe — nothing sexual, hateful, or violent.\n"
    "- Vary the angle across the batch so the human has a real choice; don't "
    "give eight rewrites of the same joke.\n"
    "- Match this house voice (meme-literate, lowercase-casual): "
    + "; ".join(_STYLE_ANCHORS)
    + ".\n\n"
    'Return ONLY a JSON object of the form {"quips": ["line one", "line two"]} '
    "with no prose, preamble, or code fences."
)

# Pull the first {...} object out of the model's reply, tolerating stray prose or
# ```json fences even though the prompt asks for none (belt and suspenders).
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def _build_user_prompt(term: str, source: str, measurement: str, count: int) -> str:
    return (
        f"Trending topic: {term!r}\n"
        f"(surfaced from {source}, measured as {measurement})\n\n"
        f"Write {count} distinct funny one-liner shirt slogans riffing on it."
    )


def _extract_text(message: object) -> str:
    """Join the text blocks of a Messages API response. Defensive: skips any
    non-text block (thinking, tool_use) so a shape change can't crash us."""
    parts: list[str] = []
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
    return "".join(parts).strip()


def _parse_batch(text: str) -> list[str]:
    """Extract + validate the model's JSON into a raw list of quip strings.

    Raises QuipError on unparseable output — a broken parse is a real failure to
    surface, never a silent empty list (CLAUDE.md: empty != broken)."""
    match = _JSON_OBJECT.search(text)
    if not match:
        raise QuipError(f"model returned no JSON object (got {text[:120]!r})")
    try:
        batch = _QuipBatch.model_validate_json(match.group(0))
    except (ValidationError, json.JSONDecodeError) as exc:
        raise QuipError(f"model returned malformed quip JSON: {exc}") from exc
    return batch.quips


def _clean_and_filter(
    quips: list[str], *, blocklist: list[str], max_chars: int, count: int
) -> list[str]:
    """Normalize, drop the unwearable, family-safe filter, dedupe, cap to `count`.

    A legitimately-empty result (everything filtered) is valid and returned as [];
    the caller distinguishes it from a parse failure, which raises above."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in quips:
        line = (raw or "").strip().strip('"').strip("'").strip()
        if not line or len(line) > max_chars:
            continue
        if not is_family_safe(line, blocklist):
            logger.info("quip filter dropped unsafe candidate=%r", line)
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
        if len(out) >= count:
            break
    return out


def generate_quips(
    term: str,
    *,
    source: str,
    measurement: str,
    count: int | None = None,
    settings: Settings | None = None,
) -> list[str]:
    """Generate up to `count` family-safe one-liner shirt slogans for `term`.

    Raises QuipConfigError if no API key is configured, QuipError if the model
    call produces unusable output."""
    settings = settings or get_settings()
    if not settings.anthropic_api_key:
        raise QuipConfigError(
            "ANTHROPIC_API_KEY is not set — cannot auto-generate copy. "
            "Set the key, or paste design copy manually."
        )
    n = count or settings.quip_count
    n = max(1, min(n, 12))

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model=settings.quip_model,
        max_tokens=1024,
        system=_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": _build_user_prompt(term, source, measurement, n),
            }
        ],
    )
    logger.info(
        "quips generated term=%r model=%s tokens_out=%s",
        term,
        settings.quip_model,
        getattr(getattr(message, "usage", None), "output_tokens", "?"),
    )
    raw = _parse_batch(_extract_text(message))
    return _clean_and_filter(
        raw,
        blocklist=settings.family_blocklist,
        max_chars=settings.quip_max_chars,
        count=n,
    )
