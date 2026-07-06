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
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.factory.printful import PrintfulClient
from app.factory.render import render_text_png
from app.factory.xcom import XClient
from app.models import Drop, DropStatus, Trend, utcnow

logger = logging.getLogger(__name__)


class FactoryError(RuntimeError):
    pass


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
            png_path = self._write_artifact(
                drop.id, "png", render_text_png(drop.design_copy, garment_color=garment)
            )

            # Dry-run: complete the loop without any external service. Mark every
            # output as simulated so it can never be mistaken for a real publish.
            if self._settings.factory_dry_run:
                base = self._settings.public_base_url.rstrip("/")
                drop.printful_mockup_url = f"{base}/artifacts/{drop.id}.png"
                drop.printful_sync_product_id = f"dryrun-{drop.id}"
                drop.x_tweet_id = f"dryrun-{drop.id}"
                drop.dry_run = True
                drop.status = DropStatus.PUBLISHED
                drop.published_at = utcnow()
                session.commit()
                logger.info("drop %s DRY RUN published (no external calls)", drop.id)
                return drop

            base = self._settings.printful_print_file_base_url
            if not base:
                raise FactoryError(
                    "PRINTFUL_PRINT_FILE_BASE_URL is not set. Printful must fetch the "
                    f"print file by public URL. PNG saved to {png_path}; host it and "
                    "set the base URL to continue."
                )
            print_file_url = f"{base.rstrip('/')}/{drop.id}.png"

            printful = PrintfulClient(self._settings)
            x = XClient(self._settings)

            # Each external step commits its result as it lands and is skipped if
            # already present, so retrying a failed drop RESUMES rather than
            # repeats — critically, it never posts a second tweet (see step 4).

            # 2. Printful mockup.
            if not drop.printful_mockup_url:
                drop.printful_mockup_url = printful.generate_mockup(print_file_url)
                session.commit()
            mockup_url = drop.printful_mockup_url

            # 3. Printful catalog sync.
            if not drop.printful_sync_product_id:
                drop.printful_sync_product_id = printful.sync_product(
                    name=f"ShirtPost — {trend.term}",
                    print_file_url=print_file_url,
                    thumbnail_url=mockup_url,
                )
                session.commit()

            # 4. X.com: upload mockup then tweet (v2) with the media_id. Gated on
            # x_tweet_id and committed on its own BEFORE the published transition,
            # so a failure after posting can't make a retry double-post.
            if not drop.x_tweet_id:
                store_base = self._settings.store_base_url
                product_url = (
                    f"{store_base.rstrip('/')}/{drop.printful_sync_product_id}"
                    if store_base
                    else None
                )
                media_id = x.upload_media(self._download(mockup_url))
                drop.x_tweet_id = x.post_tweet(
                    self._broadcast_copy(trend.term, product_url), media_id=media_id
                )
                session.commit()

            drop.status = DropStatus.PUBLISHED
            drop.published_at = utcnow()
            session.commit()
            logger.info("drop %s published tweet=%s", drop.id, drop.x_tweet_id)
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
