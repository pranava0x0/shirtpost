"""X.com (Twitter) client.

Flow: upload the mockup image to the media endpoint first (OAuth 1.0a user
context), then attach the returned ``media_id`` to a v2 ``POST /2/tweets`` call.
OAuth 1.0a signing is delegated to ``requests-oauthlib``.

NOTE: the spec named the v1.1 media endpoint, but X **deprecated v1.1 media
upload on 2025-06-09**; the live replacement is v2 ``POST /2/media/upload``. We
target v2 and parse the id defensively (the response shape shifted across
releases: ``data.id`` on the new endpoint, ``media_id_string`` on older ones).
"""

from __future__ import annotations

import logging
from urllib.parse import quote

import requests
from requests_oauthlib import OAuth1

from app.config import Settings

logger = logging.getLogger(__name__)

X_MEDIA_UPLOAD_URL = "https://api.twitter.com/2/media/upload"
X_TWEETS_URL = "https://api.twitter.com/2/tweets"
X_INTENT_URL = "https://x.com/intent/post"

_REQUIRED = ("x_api_key", "x_api_secret", "x_access_token", "x_access_token_secret")


def build_x_intent_url(text: str) -> str:
    """Prefilled Web Intent URL — the free ($0, no API key) broadcast path. The
    operator opens it and clicks Post. Intents can't attach media, but a linked
    product page unfurls its mockup as a card, which covers the image."""
    return f"{X_INTENT_URL}?text={quote(text)}"


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

    def upload_media(self, image_bytes: bytes, media_category: str = "tweet_image") -> str:
        """v2 POST /2/media/upload -> media id (parsed defensively)."""
        resp = requests.post(
            X_MEDIA_UPLOAD_URL,
            auth=self._auth,
            files={"media": image_bytes},
            data={"media_category": media_category},
            headers={"User-Agent": self._ua},
            timeout=60,
        )
        if resp.status_code >= 400:
            raise XError(f"media upload -> {resp.status_code}: {resp.text[:500]}")
        body = resp.json()
        media_id = (
            (body.get("data") or {}).get("id")
            or body.get("media_id_string")
            or body.get("id")
        )
        if not media_id:
            raise XError(f"media upload: no media id in response {body}")
        return str(media_id)

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
