"""Rasterize the design copy to a print-ready PNG.

Printful's DTG pipeline rejects SVG — it needs a transparent-background PNG in
sRGB at the print-area pixel size (150–300 DPI). The SVG (``printful.build_text_svg``)
stays as the human-readable *source* artifact; this module produces the PNG the
Factory actually uploads.

Rendering uses Pillow's bundled scalable font (``ImageFont.load_default(size=...)``),
so there is no system ``cairo``/``pango`` dependency and no vendored font binary in
the repo — just one pinned pip package. Text is measured with real font metrics,
wrapped, sized to the largest font that fits the print area on both axes, and
centered. Ink color contrasts with the garment (shared with the SVG path).
"""

from __future__ import annotations

import io
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from app.factory.printful import print_color_for_garment

# Print area in px. 1800x2400 over a ~12x16in DTG area ≈ 150 DPI, and matches the
# position payload the mockup request sends. Kept in sync with build_text_svg.
PRINT_WIDTH = 1800
PRINT_HEIGHT = 2400
PRINT_MARGIN = 150

_MAX_FONT = 220
_MIN_FONT = 24
_LINE_SPACING = 1.25


@lru_cache(maxsize=128)
def _font(size: int) -> ImageFont.FreeTypeFont:
    """Cache the bundled scalable font by size — the fit search loads each size
    repeatedly across renders, and reparsing the font each time is the hot cost."""
    return ImageFont.load_default(size=size)


def _hex_to_rgba(hex_color: str) -> tuple[int, int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)


def _wrap_to_width(words: list[str], font: ImageFont.FreeTypeFont, max_px: float) -> list[str]:
    """Greedy word wrap by measured pixel width; hard-breaks a token wider than
    the line by characters so nothing ever exceeds the print area horizontally."""
    lines: list[str] = []
    current = ""
    for word in words:
        while font.getlength(word) > max_px and len(word) > 1:
            # Peel off the largest prefix that fits (binary search — a linear
            # per-char scan is O(n^2) and dominates runtime on a long token).
            lo, hi = 1, len(word)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if font.getlength(word[:mid]) <= max_px:
                    lo = mid
                else:
                    hi = mid - 1
            if current:
                lines.append(current)
                current = ""
            lines.append(word[:lo])
            word = word[lo:]
        candidate = f"{current} {word}".strip()
        if current and font.getlength(candidate) > max_px:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def render_text_png(
    design_copy: str,
    *,
    width: int = PRINT_WIDTH,
    height: int = PRINT_HEIGHT,
    margin: int = PRINT_MARGIN,
    garment_color: str = "black",
) -> bytes:
    """Render ``design_copy`` to transparent-background PNG bytes, print-ready."""
    fill = _hex_to_rgba(print_color_for_garment(garment_color))
    words = design_copy.split() or [design_copy]
    avail_w = width - 2 * margin
    avail_h = height - 2 * margin

    # Largest font whose wrapped lines fit the box on both axes.
    lines: list[str] = [design_copy]
    font = _font(_MIN_FONT)
    line_height = _MIN_FONT * _LINE_SPACING
    for fs in range(_MAX_FONT, _MIN_FONT - 1, -4):
        candidate_font = _font(fs)
        wrapped = _wrap_to_width(words, candidate_font, avail_w)
        lh = fs * _LINE_SPACING
        if len(wrapped) * lh <= avail_h:
            lines, font, line_height = wrapped, candidate_font, lh
            break
    else:
        # Still overflows at the min size: keep only the lines that fit vertically.
        font = _font(_MIN_FONT)
        line_height = _MIN_FONT * _LINE_SPACING
        wrapped = _wrap_to_width(words, font, avail_w)
        max_lines = max(1, int(avail_h / line_height))
        lines = wrapped[:max_lines]

    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    block_h = len(lines) * line_height
    start_y = (height - block_h) / 2
    for i, line in enumerate(lines):
        y = start_y + i * line_height + line_height / 2
        # anchor="mm": center each line horizontally and within its line slot.
        draw.text((width / 2, y), line, font=font, fill=fill, anchor="mm")

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")  # untagged RGBA PNG is interpreted as sRGB
    return buffer.getvalue()
