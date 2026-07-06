"""Print-file storage backends: local (serve from this backend) and github_pages
(push to an artifacts repo + poll until live). No real network."""

import base64

import pytest

from app.config import Settings
from app.factory import storage
from app.factory.storage import StorageError


class FakeResp:
    def __init__(self, status_code, json_data=None, content=b"png", text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.content = content
        self.text = text

    def json(self):
        return self._json


# --- local -------------------------------------------------------------------


def test_local_returns_served_url():
    s = Settings(print_file_storage="local", public_base_url="https://cdn.example.com")
    assert storage.publish(s, 5, b"png") == "https://cdn.example.com/artifacts/5.png"


def test_local_fails_loud_on_localhost():
    # Default PUBLIC_BASE_URL is 127.0.0.1 — Printful can't reach it.
    with pytest.raises(StorageError) as exc:
        storage.publish(Settings(print_file_storage="local"), 5, b"png")
    assert "localhost" in str(exc.value).lower()


# --- github_pages ------------------------------------------------------------


def _gh_settings() -> Settings:
    return Settings(
        print_file_storage="github_pages",
        github_artifacts_repo="me/shirtpost-artifacts",
        github_token="tok",
        github_pages_base_url="https://me.github.io/shirtpost-artifacts",
    )


def test_github_pages_fails_loud_without_config():
    with pytest.raises(StorageError):
        storage.publish(Settings(print_file_storage="github_pages"), 5, b"png")


def test_github_pages_creates_new_file_then_returns_live_url(monkeypatch):
    monkeypatch.setattr(storage.time, "sleep", lambda *_: None)
    put_payloads = []

    def fake_get(url, **kw):
        if "api.github.com" in url:
            return FakeResp(404)  # no existing file
        return FakeResp(200, content=b"png")  # pages URL is live

    def fake_put(url, **kw):
        put_payloads.append(kw["json"])
        return FakeResp(201)

    monkeypatch.setattr(storage.requests, "get", fake_get)
    monkeypatch.setattr(storage.requests, "put", fake_put)

    url = storage.publish(_gh_settings(), 7, b"PNGBYTES")
    assert url == "https://me.github.io/shirtpost-artifacts/drops/7.png"
    assert "sha" not in put_payloads[0]  # a create, not an update
    assert base64.b64decode(put_payloads[0]["content"]) == b"PNGBYTES"


def test_github_pages_updates_existing_file_idempotently(monkeypatch):
    monkeypatch.setattr(storage.time, "sleep", lambda *_: None)
    put_payloads = []

    def fake_get(url, **kw):
        if "api.github.com" in url:
            return FakeResp(200, json_data={"sha": "existing-sha"})
        return FakeResp(200, content=b"png")

    def fake_put(url, **kw):
        put_payloads.append(kw["json"])
        return FakeResp(200)

    monkeypatch.setattr(storage.requests, "get", fake_get)
    monkeypatch.setattr(storage.requests, "put", fake_put)

    url = storage.publish(_gh_settings(), 7, b"PNGBYTES")
    assert url.endswith("/drops/7.png")
    assert put_payloads[0]["sha"] == "existing-sha"  # retry updates in place


def test_github_pages_raises_if_never_goes_live(monkeypatch):
    monkeypatch.setattr(storage.time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        storage.requests, "get",
        lambda url, **kw: FakeResp(404) if "api.github.com" in url else FakeResp(404),
    )
    monkeypatch.setattr(storage.requests, "put", lambda url, **kw: FakeResp(201))
    with pytest.raises(StorageError) as exc:
        storage.publish(_gh_settings(), 7, b"png")
    assert "never went live" in str(exc.value)
