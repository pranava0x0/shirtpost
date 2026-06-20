"""Printful client: SVG text-mockup generation + store catalog sync.

The mockup generator is task-based and fetches the print file by *public URL*, so
the generated SVG has to be hosted somewhere Printful can reach it (see
``FactoryPipeline`` for where the URL is assembled). All design copy is XML-escaped
before it lands in the SVG to neutralize markup/script injection.
"""

from __future__ import annotations

import logging
import time
from xml.sax.saxutils import escape as xml_escape

import requests

from app.config import Settings

logger = logging.getLogger(__name__)

PRINTFUL_API_BASE = "https://api.printful.com"


class PrintfulError(RuntimeError):
    pass


class PrintfulClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.printful_api_key:
            raise PrintfulError("PRINTFUL_API_KEY is not configured")
        self._settings = settings
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {settings.printful_api_key}",
                "User-Agent": settings.user_agent,
            }
        )
        if settings.printful_store_id:
            self._session.headers["X-PF-Store-Id"] = str(settings.printful_store_id)

    # --- SVG print-file payload --------------------------------------------
    @staticmethod
    def build_text_svg(design_copy: str, width: int = 1800, height: int = 2400) -> str:
        """Center the design copy on a transparent print canvas.

        ``xml_escape`` handles ``< > &``; we escape ``"`` and ``'`` explicitly so
        the text can never break out of an attribute or inject markup.
        """
        safe = xml_escape(design_copy, {'"': "&quot;", "'": "&apos;"})

        # Naive word-wrap (~18 chars/line) so long copy doesn't overflow the shirt.
        lines: list[str] = []
        current = ""
        for word in safe.split():
            if current and len(current) + len(word) + 1 > 18:
                lines.append(current)
                current = word
            else:
                current = f"{current} {word}".strip()
        if current:
            lines.append(current)

        line_height = 180
        start_y = height // 2 - (len(lines) - 1) * line_height // 2
        texts = "".join(
            f'<text x="{width // 2}" y="{start_y + i * line_height}" '
            f'text-anchor="middle" font-family="Arial, sans-serif" '
            f'font-weight="700" font-size="160" fill="#FFFFFF">{line}</text>'
            for i, line in enumerate(lines)
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">{texts}</svg>'
        )

    # --- HTTP helpers -------------------------------------------------------
    def _post(self, path: str, payload: dict) -> dict:
        try:
            resp = self._session.post(
                f"{PRINTFUL_API_BASE}{path}", json=payload, timeout=60
            )
        except requests.RequestException as exc:
            raise PrintfulError(f"Printful POST {path} failed: {exc}") from exc
        if resp.status_code >= 400:
            raise PrintfulError(f"Printful {path} -> {resp.status_code}: {resp.text[:500]}")
        return resp.json()

    def _get(self, path: str) -> dict:
        try:
            resp = self._session.get(f"{PRINTFUL_API_BASE}{path}", timeout=60)
        except requests.RequestException as exc:
            raise PrintfulError(f"Printful GET {path} failed: {exc}") from exc
        if resp.status_code >= 400:
            raise PrintfulError(f"Printful {path} -> {resp.status_code}: {resp.text[:500]}")
        return resp.json()

    # --- Mockup generation --------------------------------------------------
    def create_mockup_task(self, print_file_url: str) -> str:
        product_id = self._settings.printful_default_product_id
        variant_id = self._settings.printful_default_variant_id
        payload = {
            "variant_ids": [variant_id],
            "format": "png",
            "files": [
                {
                    "placement": "front",
                    "image_url": print_file_url,
                    "position": {
                        "area_width": 1800,
                        "area_height": 2400,
                        "width": 1800,
                        "height": 2400,
                        "top": 0,
                        "left": 0,
                    },
                }
            ],
        }
        data = self._post(f"/mockup-generator/create-task/{product_id}", payload)
        return data["result"]["task_key"]

    def get_mockup_task(self, task_key: str) -> dict:
        return self._get(f"/mockup-generator/task?task_key={task_key}")["result"]

    def generate_mockup(
        self, print_file_url: str, *, max_polls: int = 10, interval: float = 3.0
    ) -> str:
        """Issue a mockup task and poll until it completes; return the mockup URL."""
        task_key = self.create_mockup_task(print_file_url)
        for _ in range(max_polls):
            result = self.get_mockup_task(task_key)
            status = result.get("status")
            if status == "completed":
                mockups = result.get("mockups") or []
                if not mockups:
                    raise PrintfulError("mockup task completed with no mockups")
                return mockups[0]["mockup_url"]
            if status == "failed":
                raise PrintfulError(f"mockup task failed: {result}")
            time.sleep(interval)
        raise PrintfulError("mockup task timed out")

    # --- Catalog sync -------------------------------------------------------
    def sync_product(
        self, *, name: str, print_file_url: str, thumbnail_url: str, retail_price: str = "24.00"
    ) -> str:
        payload = {
            "sync_product": {"name": name, "thumbnail": thumbnail_url},
            "sync_variants": [
                {
                    "variant_id": self._settings.printful_default_variant_id,
                    "retail_price": retail_price,
                    "files": [{"type": "front", "url": print_file_url}],
                }
            ],
        }
        data = self._post("/store/products", payload)
        return str(data["result"]["id"])
