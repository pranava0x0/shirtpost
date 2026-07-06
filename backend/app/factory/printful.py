"""Printful client: SVG text-mockup generation + store catalog sync.

The mockup generator is task-based and fetches the print file by *public URL*, so
the generated SVG has to be hosted somewhere Printful can reach it (see
``FactoryPipeline`` for where the URL is assembled). All design copy is XML-escaped
before it lands in the SVG to neutralize markup/script injection.
"""

from __future__ import annotations

import logging
import re
import time
from xml.sax.saxutils import escape as xml_escape

import requests

from app.config import Settings

logger = logging.getLogger(__name__)

PRINTFUL_API_BASE = "https://api.printful.com"

# Common Printful garment colors -> approx #RRGGBB. Not exhaustive; an unknown
# name falls back to the dark-garment assumption (white ink) and logs a warning.
_GARMENT_HEX: dict[str, str] = {
    "black": "#000000",
    "white": "#FFFFFF",
    "navy": "#1F2A44",
    "red": "#B02020",
    "maroon": "#5C1A1B",
    "royal": "#1D4ED8",
    "royal blue": "#1D4ED8",
    "forest": "#14532D",
    "forest green": "#14532D",
    "charcoal": "#36454F",
    "dark heather": "#3F4448",
    "asphalt": "#3B3B3B",
    "sport grey": "#B4B4B4",
    "athletic heather": "#CFD2D4",
    "ash": "#E7E7E4",
    "heather grey": "#B4B4B4",
    "light blue": "#ADD8E6",
    "yellow": "#F5D547",
    "daisy": "#F5D547",
    "pink": "#F4A6C0",
}


class PrintfulError(RuntimeError):
    pass


def _relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance (0=black, 1=white) of a #RRGGBB string."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))

    def _lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def print_color_for_garment(garment_color: str) -> str:
    """Pick a print (ink) color that contrasts with the garment.

    Light garment -> near-black ink; dark garment -> white ink. Accepts a known
    color name or a ``#RRGGBB`` hex. An unrecognized value falls back to white
    ink (the safe default for the black default variant) and logs a warning so a
    bad color surfaces instead of silently printing invisible white-on-white.
    """
    raw = (garment_color or "").strip().lower()
    hex_color = _GARMENT_HEX.get(raw)
    if hex_color is None and re.fullmatch(r"#?[0-9a-f]{6}", raw):
        hex_color = f"#{raw.lstrip('#')}"
    if hex_color is None:
        logger.warning(
            "unknown garment color %r; defaulting print to white ink", garment_color
        )
        return "#FFFFFF"
    # Threshold ~0.4: garments lighter than mid-grey get dark ink.
    return "#111111" if _relative_luminance(hex_color) > 0.4 else "#FFFFFF"


def _wrap_words(words: list[str], max_chars: int) -> list[str]:
    """Greedy word wrap; hard-breaks any single token longer than max_chars."""
    lines: list[str] = []
    current = ""
    for word in words:
        while len(word) > max_chars:  # break a token too long for one line
            if current:
                lines.append(current)
                current = ""
            lines.append(word[:max_chars])
            word = word[max_chars:]
        if current and len(current) + 1 + len(word) > max_chars:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines or [""]


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
    def build_text_svg(
        design_copy: str,
        width: int = 1800,
        height: int = 2400,
        *,
        margin: int = 150,
        garment_color: str = "black",  # default variant 4012 is black -> white ink
    ) -> str:
        """Render design copy centered *inside* the printable area.

        Picks the largest font size at which the wrapped copy fits the canvas on
        both axes, so even a max-length (500-char) submission stays on the shirt
        instead of spilling above/below it. Wrapping is done on the raw text and
        each line is XML-escaped afterward, so an escaped entity (``&lt;`` …) can
        never be split into invalid markup, and no raw markup can break out.

        The ink color is derived from ``garment_color`` for contrast, so the art
        never prints white-on-white when the variant is a light garment.
        """
        fill = print_color_for_garment(garment_color)
        words = design_copy.split() or [design_copy]
        avail_w = width - 2 * margin
        avail_h = height - 2 * margin

        # Largest font (descending) whose wrapped lines fit the box vertically.
        lines, font_size, line_height = _wrap_words(words, 1), 24, 30.0
        for fs in range(220, 23, -4):
            chars_per_line = max(1, int(avail_w / (0.6 * fs)))  # ~0.6em/char, Arial bold
            wrapped = _wrap_words(words, chars_per_line)
            lh = fs * 1.25
            if len(wrapped) * lh <= avail_h:
                lines, font_size, line_height = wrapped, fs, lh
                break
        else:
            # Still overflows at the min size: keep only the lines that fit.
            font_size, line_height = 24, 24 * 1.25
            chars_per_line = max(1, int(avail_w / (0.6 * font_size)))
            max_lines = max(1, int(avail_h / line_height))
            lines = _wrap_words(words, chars_per_line)[:max_lines]

        total_h = len(lines) * line_height
        start_y = (height - total_h) / 2 + font_size  # first baseline, vertically centered
        parts = []
        for i, line in enumerate(lines):
            safe = xml_escape(line, {'"': "&quot;", "'": "&apos;"})
            y = start_y + i * line_height
            parts.append(
                f'<text x="{width // 2}" y="{y:.0f}" text-anchor="middle" '
                f'font-family="Arial, sans-serif" font-weight="700" '
                f'font-size="{font_size}" fill="{fill}">{safe}</text>'
            )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">{"".join(parts)}</svg>'
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
