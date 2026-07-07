"""Unit tests for the LLM quip generator. The model call is faked — these cover
the parse/filter logic and the fail-loud contract, no network or API key needed.
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.copy import generate
from app.copy.generate import (
    QuipConfigError,
    QuipError,
    _clean_and_filter,
    _parse_batch,
    generate_quips,
)


# --- parsing --------------------------------------------------------------

def test_parse_batch_reads_plain_json():
    assert _parse_batch('{"quips": ["we are so back", "delulu"]}') == [
        "we are so back",
        "delulu",
    ]


def test_parse_batch_tolerates_prose_and_code_fences():
    text = 'Sure!\n```json\n{"quips": ["in my villain era"]}\n```'
    assert _parse_batch(text) == ["in my villain era"]


def test_parse_batch_raises_on_no_json():
    # A broken parse is a real failure to surface — never a silent empty list.
    with pytest.raises(QuipError):
        _parse_batch("sorry, I can't do that")


def test_parse_batch_raises_on_malformed_json():
    with pytest.raises(QuipError):
        _parse_batch('{"quips": [unquoted, broken}')


# --- cleaning / filtering -------------------------------------------------

def test_clean_and_filter_normalizes_dedupes_and_caps():
    quips = [
        '  "we are so back"  ',  # surrounding quotes + whitespace stripped
        "We Are So Back",  # case-insensitive duplicate -> dropped
        "touch grass",
        "",  # empty -> dropped
        "in my villain era",
    ]
    out = _clean_and_filter(quips, blocklist=["nsfw"], max_chars=80, count=2)
    assert out == ["we are so back", "touch grass"]  # capped to count


def test_clean_and_filter_drops_unsafe_and_overlong():
    quips = [
        "safe and funny",
        "totally nsfw joke",  # family filter drops it
        "x" * 200,  # too long for a shirt -> dropped
    ]
    out = _clean_and_filter(quips, blocklist=["nsfw"], max_chars=80, count=6)
    assert out == ["safe and funny"]


def test_clean_and_filter_empty_after_filter_is_valid():
    # Everything filtered is a legitimate [] (empty != broken); no exception.
    out = _clean_and_filter(["nsfw only"], blocklist=["nsfw"], max_chars=80, count=6)
    assert out == []


# --- generate_quips end to end (faked client) -----------------------------

class _FakeBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeUsage:
    output_tokens = 42


class _FakeMessage:
    def __init__(self, text: str) -> None:
        self.content = [_FakeBlock(text)]
        self.usage = _FakeUsage()


class _FakeMessages:
    def __init__(self, text: str) -> None:
        self._text = text
        self.last_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return _FakeMessage(self._text)


class _FakeClient:
    def __init__(self, text: str) -> None:
        self.messages = _FakeMessages(text)


def _settings_with_key(**overrides) -> Settings:
    return Settings(anthropic_api_key="test-key", **overrides)


def test_generate_quips_requires_api_key():
    settings = Settings(anthropic_api_key=None)
    with pytest.raises(QuipConfigError):
        generate_quips("we are so back", source="simulated", measurement="seed", settings=settings)


def test_generate_quips_returns_filtered_batch(monkeypatch):
    canned = (
        '{"quips": ["we are so back", "in my villain era", '
        '"nsfw bad one", "we are so back"]}'  # unsafe + duplicate present
    )
    fake = _FakeClient(canned)
    monkeypatch.setattr(generate.anthropic, "Anthropic", lambda api_key: fake)

    out = generate_quips(
        "layoffs",
        source="wikipedia",
        measurement="pageviews",
        settings=_settings_with_key(),
    )
    assert out == ["we are so back", "in my villain era"]  # unsafe + dup removed
    # The trend term reached the model prompt.
    assert "layoffs" in fake.messages.last_kwargs["messages"][0]["content"]
    assert fake.messages.last_kwargs["model"] == "claude-haiku-4-5"


def test_generate_quips_respects_count(monkeypatch):
    canned = '{"quips": ["one", "two", "three", "four"]}'
    monkeypatch.setattr(
        generate.anthropic, "Anthropic", lambda api_key: _FakeClient(canned)
    )
    out = generate_quips(
        "topic",
        source="simulated",
        measurement="seed",
        count=2,
        settings=_settings_with_key(),
    )
    assert out == ["one", "two"]
