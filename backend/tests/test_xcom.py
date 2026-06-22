"""X client: v2 media endpoint + defensive id parsing + fail-loud on bad creds."""

import pytest

from app.config import Settings
from app.factory import xcom
from app.factory.xcom import XClient, XError


def _creds() -> Settings:
    return Settings(
        x_api_key="k", x_api_secret="s", x_access_token="t", x_access_token_secret="ts"
    )


class FakeResp:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


def test_media_endpoint_is_v2():
    assert xcom.X_MEDIA_UPLOAD_URL == "https://api.twitter.com/2/media/upload"


def test_missing_credentials_raise():
    with pytest.raises(XError):
        XClient(Settings())


def test_upload_media_parses_v2_data_id(monkeypatch):
    client = XClient(_creds())
    monkeypatch.setattr(
        xcom.requests, "post", lambda *a, **k: FakeResp(200, {"data": {"id": "98765"}})
    )
    assert client.upload_media(b"img") == "98765"


def test_upload_media_parses_legacy_media_id_string(monkeypatch):
    client = XClient(_creds())
    monkeypatch.setattr(
        xcom.requests, "post", lambda *a, **k: FakeResp(200, {"media_id_string": "111"})
    )
    assert client.upload_media(b"img") == "111"


def test_upload_media_raises_on_error(monkeypatch):
    client = XClient(_creds())
    monkeypatch.setattr(
        xcom.requests, "post", lambda *a, **k: FakeResp(403, {"detail": "nope"})
    )
    with pytest.raises(XError):
        client.upload_media(b"img")


def test_post_tweet_returns_id(monkeypatch):
    client = XClient(_creds())
    monkeypatch.setattr(
        xcom.requests, "post", lambda *a, **k: FakeResp(201, {"data": {"id": "555"}})
    )
    assert client.post_tweet("hello", media_id="98765") == "555"
