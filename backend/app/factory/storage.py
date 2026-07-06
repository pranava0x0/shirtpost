"""Print-file storage: publish the rasterized PNG somewhere Printful can fetch it
by public URL, and return that URL.

Backends (``PRINT_FILE_STORAGE``):
- **local** (default): this backend already serves the PNG at
  ``{PUBLIC_BASE_URL}/artifacts/<id>.png``, so it just returns that URL. Fails
  loud if ``PUBLIC_BASE_URL`` is a localhost address (Printful can't reach it) —
  deploy behind a public URL or use ``github_pages``.
- **github_pages**: push the PNG to a public artifacts repo via the GitHub API,
  then poll the Pages URL until it is live (deploys take ~1 min). $0, no card;
  needs the repo + a token. Idempotent — a retry updates the same file.

R2 (S3 API via boto3) is the documented upgrade path — deferred (adds a dependency
and needs a card on file). See docs/PLAN.md 2A #2.
"""

from __future__ import annotations

import base64
import logging
import time
from urllib.parse import urlsplit

import requests

from app.config import Settings

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


class StorageError(RuntimeError):
    pass


def publish(settings: Settings, drop_id: int, png_bytes: bytes) -> str:
    """Host the print file and return the public URL Printful will fetch."""
    backend = settings.print_file_storage
    if backend == "local":
        return _publish_local(settings, drop_id)
    if backend == "github_pages":
        return _publish_github_pages(settings, drop_id, png_bytes)
    raise StorageError(f"unknown PRINT_FILE_STORAGE={backend!r}")


def _publish_local(settings: Settings, drop_id: int) -> str:
    base = settings.public_base_url.rstrip("/")
    host = (urlsplit(base).hostname or "").lower()
    if host in _LOCAL_HOSTS:
        raise StorageError(
            f"PRINT_FILE_STORAGE=local but PUBLIC_BASE_URL={settings.public_base_url!r} "
            "is a localhost address Printful can't reach. Deploy behind a public URL, "
            "or set PRINT_FILE_STORAGE=github_pages."
        )
    return f"{base}/artifacts/{drop_id}.png"


def _gh_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _publish_github_pages(settings: Settings, drop_id: int, png_bytes: bytes) -> str:
    repo = settings.github_artifacts_repo
    token = settings.github_token
    pages_base = settings.github_pages_base_url
    if not (repo and token and pages_base):
        raise StorageError(
            "PRINT_FILE_STORAGE=github_pages needs GITHUB_ARTIFACTS_REPO (owner/repo), "
            "GITHUB_TOKEN, and GITHUB_PAGES_BASE_URL set."
        )
    path = f"drops/{drop_id}.png"
    api = f"{GITHUB_API}/repos/{repo}/contents/{path}"
    headers = _gh_headers(token)

    # An existing file needs its blob sha to update — makes a retry idempotent
    # rather than a 409.
    sha: str | None = None
    try:
        existing = requests.get(api, headers=headers, timeout=30)
        if existing.status_code == 200:
            sha = existing.json().get("sha")
    except requests.RequestException as exc:
        raise StorageError(f"github GET {path} failed: {exc}") from exc

    payload: dict[str, object] = {
        "message": f"ShirtPost drop {drop_id} print file",
        "content": base64.b64encode(png_bytes).decode("ascii"),
    }
    if sha:
        payload["sha"] = sha
    try:
        put = requests.put(api, headers=headers, json=payload, timeout=60)
    except requests.RequestException as exc:
        raise StorageError(f"github PUT {path} failed: {exc}") from exc
    if put.status_code >= 400:
        raise StorageError(f"github PUT {path} -> {put.status_code}: {put.text[:300]}")

    url = f"{pages_base.rstrip('/')}/{path}"
    _wait_until_live(settings, url)
    logger.info("drop %s print file live at %s", drop_id, url)
    return url


def _wait_until_live(
    settings: Settings, url: str, *, max_polls: int = 20, interval: float = 6.0
) -> None:
    """Poll the Pages URL until the file actually serves — a fresh deploy 404s for
    ~1 min, and handing Printful a not-yet-live URL fails the mockup. Each attempt
    is logged and the last status/error is surfaced in the raised error, so a
    permanently-broken deploy (Pages disabled, wrong base URL) is diagnosable
    rather than an opaque 2-minute timeout."""
    last = "no response"
    for attempt in range(max_polls):
        try:
            resp = requests.get(
                url, headers={"User-Agent": settings.user_agent}, timeout=15
            )
            if resp.status_code == 200 and resp.content:
                return
            last = f"HTTP {resp.status_code}"
            # 404 is the expected not-yet-live case worth polling through; a 401/403
            # (Pages disabled/private, bad host) will never heal — fail fast with body.
            if resp.status_code in (401, 403):
                raise StorageError(
                    f"github pages URL {url} returned {resp.status_code}: "
                    f"{resp.text[:200]} — Pages disabled/private or wrong "
                    "GITHUB_PAGES_BASE_URL?"
                )
            logger.info(
                "github pages not live yet url=%s attempt=%d status=%d",
                url, attempt, resp.status_code,
            )
        except requests.RequestException as exc:
            last = f"connection error: {exc}"
            logger.warning(
                "github pages poll error url=%s attempt=%d err=%s", url, attempt, exc
            )
        time.sleep(interval)
    raise StorageError(
        f"github pages file never went live after {max_polls} polls: {url} (last: {last})"
    )
