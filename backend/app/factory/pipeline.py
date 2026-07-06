"""The Factory pipeline: invoked on admin submission.

Sequence: build the SVG source + rasterize a print-ready PNG (Printful rejects
SVG) -> Printful mockup -> Printful catalog sync -> download mockup -> X.com media
upload -> X.com tweet. Each external step commits its result as it lands, so a
later failure leaves a partial, debuggable trail rather than losing everything.
Failures are recorded on the Drop (status + error) and re-raised — never swallowed.
"""

from __future__ import annotations

import logging
from pathlib import Path

import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.factory import storage
from app.factory.printful import PrintfulClient
from app.factory.render import render_text_png
from app.factory.xcom import XClient, build_x_intent_url
from app.models import Drop, DropStatus, Trend, utcnow

# Rough X API cost per post (2026 pay-per-use): ~$0.20 with a URL, else ~$0.015.
# Only relevant when x_broadcast_mode="api"; logged so a metered bill is visible.
_X_POST_COST_URL = 0.20
_X_POST_COST_PLAIN = 0.015

logger = logging.getLogger(__name__)


class FactoryPipeline:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def run(self, session: Session, drop: Drop) -> Drop:
        trend: Trend = drop.trend
        drop.status = DropStatus.PROCESSING
        drop.error = None
        session.commit()

        try:
            # 1. Build the SVG source (debuggable) and rasterize the PNG Printful
            # will actually fetch — Printful's DTG pipeline rejects SVG.
            garment = self._settings.printful_garment_color
            svg = PrintfulClient.build_text_svg(drop.design_copy, garment_color=garment)
            self._write_artifact(drop.id, "svg", svg.encode("utf-8"))
            png = render_text_png(drop.design_copy, garment_color=garment)
            self._write_artifact(drop.id, "png", png)

            # Dry-run: complete the loop without any external service. Mark every
            # output as simulated so it can never be mistaken for a real publish.
            if self._settings.factory_dry_run:
                base = self._settings.public_base_url.rstrip("/")
                drop.printful_mockup_url = f"{base}/artifacts/{drop.id}.png"
                drop.printful_sync_product_id = f"dryrun-{drop.id}"
                drop.dry_run = True
                self._broadcast(session, drop, trend, mockup_url=None, simulate=True)
                drop.status = DropStatus.PUBLISHED
                drop.published_at = utcnow()
                session.commit()
                logger.info("drop %s DRY RUN published (no external calls)", drop.id)
                return drop

            # 2. Host the PNG somewhere Printful can fetch it by URL (local /
            # github_pages). Fails loud if hosting isn't reachable.
            print_file_url = storage.publish(self._settings, drop.id, png)

            printful = PrintfulClient(self._settings)

            # Each external step commits its result as it lands and is skipped if
            # already present, so retrying a failed drop RESUMES rather than
            # repeats — critically, it never posts a second tweet (see _broadcast).

            # 3. Printful mockup.
            if not drop.printful_mockup_url:
                drop.printful_mockup_url = printful.generate_mockup(print_file_url)
                session.commit()
            mockup_url = drop.printful_mockup_url

            # 4. Printful catalog sync.
            if not drop.printful_sync_product_id:
                drop.printful_sync_product_id = printful.sync_product(
                    name=f"ShirtPost — {trend.term}",
                    print_file_url=print_file_url,
                    thumbnail_url=mockup_url,
                )
                session.commit()

            # 5. Broadcast (intent = free, or api = auto-post).
            self._broadcast(session, drop, trend, mockup_url=mockup_url, simulate=False)

            drop.status = DropStatus.PUBLISHED
            drop.published_at = utcnow()
            session.commit()
            logger.info(
                "drop %s published (tweet=%s intent=%s)",
                drop.id, drop.x_tweet_id, bool(drop.x_intent_url),
            )
            return drop
        except Exception as exc:
            session.rollback()
            drop.status = DropStatus.FAILED
            drop.error = str(exc)[:1000]
            session.commit()
            logger.exception("drop %s failed: %s", drop.id, exc)
            raise

    # --- helpers ------------------------------------------------------------
    def _write_artifact(self, drop_id: int, ext: str, data: bytes) -> Path:
        out_dir = Path(self._settings.artifacts_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{drop_id}.{ext}"
        path.write_bytes(data)
        return path

    def _download(self, url: str) -> bytes:
        resp = requests.get(
            url, timeout=60, headers={"User-Agent": self._settings.user_agent}
        )
        resp.raise_for_status()
        return resp.content

    def _product_url(self, drop: Drop) -> str | None:
        """The buyable product URL, if a storefront is wired. Only then does the
        broadcast claim a purchasable drop (see _broadcast_copy)."""
        store_base = self._settings.store_base_url
        if store_base and drop.printful_sync_product_id:
            return f"{store_base.rstrip('/')}/{drop.printful_sync_product_id}"
        return None

    def _broadcast(
        self, session: Session, drop: Drop, trend: Trend, *, mockup_url: str | None, simulate: bool
    ) -> None:
        """Broadcast the drop. Default "intent" mode is $0: generate a prefilled
        x.com/intent/post URL the operator clicks — no API key, no metered bill.
        "api" mode auto-posts (and logs an estimated per-post cost). Both are
        idempotent so a retry never re-broadcasts."""
        text = self._broadcast_copy(trend.term, self._product_url(drop))
        if self._settings.x_broadcast_mode == "intent":
            if not drop.x_intent_url:
                drop.x_intent_url = build_x_intent_url(text)
                session.commit()
            return
        # api mode — auto-post. Gated on x_tweet_id so a retry never double-posts.
        if drop.x_tweet_id:
            return
        if simulate:  # dry-run + api mode
            drop.x_tweet_id = f"dryrun-{drop.id}"
        else:
            self._enforce_x_budget(session)
            x = XClient(self._settings)
            media_id = x.upload_media(self._download(mockup_url))
            drop.x_tweet_id = x.post_tweet(text, media_id=media_id)
            cost = _X_POST_COST_URL if self._product_url(drop) else _X_POST_COST_PLAIN
            logger.info("drop %s auto-posted to X (est cost ~$%.3f)", drop.id, cost)
        session.commit()

    def _enforce_x_budget(self, session: Session) -> None:
        """Fail loud before an api post if this month's spend would exceed the
        cap. Counts this month's real (non-dry-run) tweets at the URL rate — a
        conservative estimate that errs toward not overspending."""
        budget = self._settings.x_monthly_budget_usd
        if budget is None:
            return
        month_start = utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        posted = session.scalar(
            select(func.count())
            .select_from(Drop)
            .where(
                Drop.x_tweet_id.is_not(None),
                Drop.dry_run.is_(False),
                Drop.published_at >= month_start,
            )
        )
        projected = (posted + 1) * _X_POST_COST_URL
        if projected > budget:
            raise RuntimeError(
                f"X monthly budget ${budget:.2f} would be exceeded: {posted} post(s) "
                f"already this month, next would reach ~${projected:.2f}. Not posting."
            )

    @staticmethod
    def _broadcast_copy(term: str, product_url: str | None = None) -> str:
        """Honest broadcast copy. Only claims a buyable drop when a real shop URL
        exists; reserves room for that URL instead of blindly slicing at 280."""
        limit = 280
        if product_url:
            suffix = f"\nShop: {product_url}"
            head = f'New ShirtPost drop inspired by "{term}" \U0001f455'
            return head[: limit - len(suffix)] + suffix
        # Phase 1: no storefront/checkout — a teaser, not a purchasable "live" drop.
        return f'Trend spotted: "{term}" — a ShirtPost drop in the works \U0001f440'[:limit]
