"""Runtime configuration. Every secret loads from the environment only.

Validated with pydantic-settings (strict schema, ``extra="forbid"``) so a typo'd
or unexpected env var fails loud at boot rather than silently doing nothing.

Integration credentials (Printful, X.com) are optional at startup so the Radar
and Admin queue run without them; the Factory pipeline fails loud at submission
time if the credentials it needs are absent.
"""

from __future__ import annotations

from functools import lru_cache

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
        description='Enabled source ids: "simulated", "google_trends", "reddit".',
    )
    google_trends_rss_url: str = "https://trends.google.com/trending/rss?geo=US"
    reddit_rss_url: str = "https://www.reddit.com/r/popular/.rss"
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
    # Printful's mockup generator fetches the print file by public URL, so the
    # generated SVG must be hosted somewhere Printful can reach. Base URL of that
    # host; the pipeline appends "/<drop_id>.svg". Unset => Factory fails loud.
    printful_print_file_base_url: str | None = None
    artifacts_dir: str = "artifacts"

    # --- X.com (OAuth 1.0a user context: required for v1.1 media + v2 tweets) -
    x_api_key: str | None = None
    x_api_secret: str | None = None
    x_access_token: str | None = None
    x_access_token_secret: str | None = None

    # --- App ----------------------------------------------------------------
    user_agent: str = "ShirtPostRadar/0.1 (+https://github.com/pranava0x0/shirtpost)"


@lru_cache
def get_settings() -> Settings:
    return Settings()
