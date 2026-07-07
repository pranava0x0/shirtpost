"""Runtime configuration. Every secret loads from the environment only.

Validated with pydantic-settings (strict schema, ``extra="forbid"``) so a typo'd
or unexpected env var fails loud at boot rather than silently doing nothing.

Integration credentials (Printful, X.com) are optional at startup so the Radar
and Admin queue run without them; the Factory pipeline fails loud at submission
time if the credentials it needs are absent.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        case_sensitive=False,
    )

    # --- Database -----------------------------------------------------------
    database_url: str = Field(
        default="sqlite:///./shirtpost.db",
        description="SQLAlchemy database URL. SQLite by default (single source of truth).",
    )

    # --- Security / network -------------------------------------------------
    # allowed_hosts is the interim mitigation for CVE-2026-48710 (Starlette
    # "BadHost" host-header auth bypass). See security.md.
    allowed_hosts: list[str] = Field(default=["localhost", "127.0.0.1", "testserver"])
    admin_cors_origins: list[str] = Field(default=["http://localhost:3000"])

    # --- Radar --------------------------------------------------------------
    radar_enabled: bool = True
    radar_poll_interval_seconds: int = Field(default=900, ge=30)
    radar_sources: list[str] = Field(
        default=["simulated"],
        # "wikipedia" is the ToS-clean real source (open pageviews API, no key).
        # Reddit was dropped (its free API forbids commercial use). Google Trends
        # has no sanctioned feed until the alpha API is granted — apply for it.
        description='Enabled source ids: "simulated", "wikipedia", "google_trends".',
    )
    google_trends_rss_url: str = "https://trends.google.com/trending/rss?geo=US"
    # Wikipedia most-viewed articles — free, open, ToS-clean. Date is appended as
    # /YYYY/MM/DD at fetch time (data lags ~1 day, so the radar reads yesterday).
    wikipedia_top_api: str = (
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access"
    )
    wikipedia_top_n: int = Field(default=25, ge=1, le=100)
    # Family-friendly gate (Phase 3 #5). A cheap keyword blocklist that drops a
    # trend before it reaches the queue; a stronger LLM classifier is deferred.
    family_safe_filter_enabled: bool = True
    # Substring-matched (see is_family_safe — a safety filter over-blocks on
    # purpose). Tuned to avoid the worst false positives: "execution" was dropped
    # (too common in innocent "code execution"); "beheading" covers the violent case.
    family_blocklist: list[str] = Field(
        default=[
            "porn", "pornographic", "nsfw", "xxx", "nude", "onlyfans",
            "rape", "massacre", "genocide", "terrorist attack", "mass shooting",
            "suicide", "beheading",
        ]
    )
    # Fetch hygiene for live sources (no effect on the simulated source).
    radar_min_request_interval_seconds: float = Field(default=1.5, ge=0.0)
    radar_feed_cache_seconds: int = Field(default=300, ge=0)
    radar_cache_dir: str = ".cache/radar"
    radar_max_retries: int = Field(default=2, ge=0)

    # --- Printful -----------------------------------------------------------
    printful_api_key: str | None = None
    printful_store_id: str | None = None
    # Baseline blank: a standard unisex t-shirt. Override per the Printful catalog.
    printful_default_product_id: int = 71
    printful_default_variant_id: int = 4012
    # Garment color the print sits on. Drives the print *text* color for contrast:
    # a light garment gets dark ink, a dark garment gets white. Default variant
    # 4012 is black, so the print defaults to white. Change this whenever you
    # change the variant, or the art can vanish into the shirt (white-on-white).
    # Accepts a common color name ("black", "navy", "sport grey") or a #RRGGBB hex.
    printful_garment_color: str = "black"
    artifacts_dir: str = "artifacts"

    # --- Print-file storage (host the PNG for Printful to fetch by URL) ------
    # "local" (default): serve from this backend at PUBLIC_BASE_URL/artifacts/<id>.png
    # (fails loud if PUBLIC_BASE_URL is localhost — Printful can't reach it).
    # "github_pages": push to a public artifacts repo + poll until live ($0, no card).
    print_file_storage: Literal["local", "github_pages"] = "local"
    github_artifacts_repo: str | None = None  # "owner/repo"
    github_token: str | None = None
    github_pages_base_url: str | None = None  # e.g. https://<user>.github.io/<repo>
    # Dry-run: complete the Factory pipeline without Printful/X (dev/demo). Outputs
    # are clearly marked simulated. Default off so a real misconfig still fails loud.
    factory_dry_run: bool = False
    # Public base URL of this backend (used to build reachable artifact/mockup URLs).
    public_base_url: str = "http://127.0.0.1:8000"

    # Public storefront base URL. When set, the X broadcast includes a real shop
    # link ("{store_base}/{sync_product_id}"). Unset (Phase 1, no storefront) =>
    # the post is a teaser, never a "live"/buyable claim.
    store_base_url: str | None = None

    # --- X.com broadcast ----------------------------------------------------
    # X has no free API tier since 2026-02 (~$0.20/post with a URL). Default to
    # "intent": the Factory generates a prefilled x.com/intent/post URL and the
    # operator clicks Post ($0, no keys). "api" auto-posts via the credentials
    # below (metered — logs an estimated per-post cost).
    x_broadcast_mode: Literal["intent", "api"] = "intent"
    # Fail-loud spend cap for api mode: refuse to auto-post if this month's posts
    # (counted conservatively at the URL rate) would exceed this. Unset = no cap.
    x_monthly_budget_usd: float | None = Field(default=None, ge=0)
    # OAuth 1.0a user context — only needed when x_broadcast_mode="api".
    x_api_key: str | None = None
    x_api_secret: str | None = None
    x_access_token: str | None = None
    x_access_token_secret: str | None = None

    # --- Copy generation (LLM quips) ----------------------------------------
    # Optional: turns a trend into candidate funny one-liner shirt copy. Absent
    # key => the /quips endpoint fails loud (503); the operator can still paste
    # their own copy. Read from the env only; never logged.
    anthropic_api_key: str | None = None
    # Cheapest model that clears the humor bar (CLAUDE.md: Haiku before Opus). We
    # generate a *batch* and let the operator pick, so a flat line or two is fine.
    # Set to a Sonnet id (e.g. "claude-sonnet-5") for wittier, pricier output.
    quip_model: str = "claude-haiku-4-5"
    quip_count: int = Field(default=6, ge=1, le=12)
    # Drop candidates longer than this — a shirt one-liner, not a paragraph.
    quip_max_chars: int = Field(default=80, ge=10, le=200)

    # --- App ----------------------------------------------------------------
    user_agent: str = "ShirtPostRadar/0.1 (+https://github.com/pranava0x0/shirtpost)"


@lru_cache
def get_settings() -> Settings:
    return Settings()
