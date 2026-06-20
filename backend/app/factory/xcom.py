"""X.com (Twitter) client.

Flow mandated by the spec: upload the mockup image via the v1.1 media endpoint
first (OAuth 1.0a user context), then attach the returned ``media_id`` to a v2
``POST /2/tweets`` call. OAuth 1.0a signing is delegated to ``requests-oauthlib``.
"""

from __future__ import annotations

import logging

import requests
from requests_oauthlib import OAuth1

from app.config import Settings

logger = logging.getLogger(__name__)

X_MEDIA_UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"
X_TWEETS_URL = "https://api.twitter.com/2/tweets"

_REQUIRED = ("x_api_key", "x_api_secret", "x_access_token", "x_access_token_secret")


class XError(RuntimeError):
    pass


class XClient:
    def __init__(self, settings: Settings) -> None:
        missing = [name for name in _REQUIRED if not getattr(settings, name)]
        if missing:
            raise XError(f"X.com credentials missing: {', '.join(missing)}")
        self._auth = OAuth1(
            settings.x_api_key,
            settings.x_api_secret,
            settings.x_access_token,
            settings.x_access_token_secret,
        )
        self._ua = settings.user_agent

    def upload_media(self, image_bytes: bytes) -> str:
        """v1.1 media upload -> media_id_string."""
        resp = requests.post(
            X_MEDIA_UPLOAD_URL,
            auth=self._auth,
            files={"media": image_bytes},
            headers={"User-Agent": self._ua},
            timeout=60,
        )
        if resp.status_code >= 400:
            raise XError(f"media upload -> {resp.status_code}: {resp.text[:500]}")
        return str(resp.json()["media_id_string"])

    def post_tweet(self, text: str, media_id: str | None = None) -> str:
        """v2 POST /2/tweets -> tweet id."""
        payload: dict = {"text": text}
        if media_id:
            payload["media"] = {"media_ids": [media_id]}
        resp = requests.post(
            X_TWEETS_URL,
            auth=self._auth,
            json=payload,
            headers={"User-Agent": self._ua},
            timeout=60,
        )
        if resp.status_code >= 400:
            raise XError(f"tweet -> {resp.status_code}: {resp.text[:500]}")
        return str(resp.json()["data"]["id"])
