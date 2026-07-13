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
import logging
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from app.factory.printful import print_color_for_garment

logger = logging.getLogger(__name__)

# Print area in px. 1800x2400 over a ~12x16in DTG area ≈ 150 DPI, and matches the
# position payload the mockup request sends. Kept in sync with build_text_svg.
PRINT_WIDTH = 1800
PRINT_HEIGHT = 2400
PRINT_MARGIN = 150

_MAX_FONT = 220
_MIN_FONT = 24
_LINE_SPACING = 1.25

# Layout templates so two drops never look identical (TRENDS-DISCOVERY-SPEC Part
# C). Each keeps the print inside the area with a transparent background — only
# the placement, case, scale, and decoration change. "centered" is the historical
# default; the operator picks per drop (the dashboard rotates by default).
LAYOUTS = ("centered", "top_left", "oversized", "boxed")
DEFAULT_LAYOUT = "centered"


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


def _fit_lines(
    words: list[str], avail_w: float, avail_h: float, max_font: int
) -> tuple[list[str], ImageFont.FreeTypeFont, float]:
    """Largest font (down from ``max_font``) whose wrapped lines fit the region on
    both axes; falls back to the min size, keeping only the lines that fit."""
    for fs in range(max_font, _MIN_FONT - 1, -4):
        candidate_font = _font(fs)
        wrapped = _wrap_to_width(words, candidate_font, avail_w)
        lh = fs * _LINE_SPACING
        if len(wrapped) * lh <= avail_h:
            return wrapped, candidate_font, lh
    font = _font(_MIN_FONT)
    line_height = _MIN_FONT * _LINE_SPACING
    wrapped = _wrap_to_width(words, font, avail_w)
    max_lines = max(1, int(avail_h / line_height))
    return wrapped[:max_lines], font, line_height


def _region(layout: str, width: int, height: int, margin: int) -> tuple[float, float, float, float, int]:
    """The (x0, y0, x1, y1, max_font) the text must stay within for a layout.
    Every region is a sub-box of the printable area, so text never leaves it."""
    if layout == "top_left":
        # Small left-chest hit in the upper-left, roughly a fifth of the front.
        return (margin, margin, width * 0.6, height * 0.42, 130)
    if layout == "oversized":
        # Fill the width aggressively (half the margin) for a big, loud print.
        m = margin // 2
        return (m, m, width - m, height - m, 300)
    if layout == "boxed":
        # Inset a little so the outline box has room inside the print area.
        inset = margin + 40
        return (inset, inset, width - inset, height - inset, 190)
    # centered (default) — the historical full-box centered stack.
    return (margin, margin, width - margin, height - margin, _MAX_FONT)


def render_text_png(
    design_copy: str,
    *,
    width: int = PRINT_WIDTH,
    height: int = PRINT_HEIGHT,
    margin: int = PRINT_MARGIN,
    garment_color: str = "black",
    layout: str = DEFAULT_LAYOUT,
) -> bytes:
    """Render ``design_copy`` to transparent-background PNG bytes, print-ready.

    ``layout`` selects a placement template (see ``LAYOUTS``). An unknown layout
    falls back to ``centered`` so a bad value never crashes a drop."""
    if layout not in LAYOUTS:
        logger.warning("unknown layout %r; falling back to %s", layout, DEFAULT_LAYOUT)
        layout = DEFAULT_LAYOUT

    fill = _hex_to_rgba(print_color_for_garment(garment_color))
    text = design_copy.lower() if layout == "oversized" else design_copy
    words = text.split() or [text]

    x0, y0, x1, y1, max_font = _region(layout, width, height, margin)
    region_w, region_h = x1 - x0, y1 - y0
    lines, font, line_height = _fit_lines(words, region_w, region_h, max_font)

    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    block_h = len(lines) * line_height

    left_aligned = layout == "top_left"
    # top_left starts at the region top; the rest vertically-center in the region.
    start_y = y0 if left_aligned else y0 + (region_h - block_h) / 2
    anchor = "lm" if left_aligned else "mm"
    text_x = x0 if left_aligned else (x0 + x1) / 2

    for i, line in enumerate(lines):
        y = start_y + i * line_height + line_height / 2
        draw.text((text_x, y), line, font=font, fill=fill, anchor=anchor)

    if layout == "boxed":
        # Outline framing the text block, in the same ink so it stays on-garment.
        widest = max((font.getlength(ln) for ln in lines), default=0.0)
        cx = (x0 + x1) / 2
        pad = max(line_height * 0.45, 24)
        box = (
            cx - widest / 2 - pad,
            start_y - pad,
            cx + widest / 2 + pad,
            start_y + block_h + pad,
        )
        draw.rectangle(box, outline=fill, width=max(6, int(font.size / 12)))

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")  # untagged RGBA PNG is interpreted as sRGB
    return buffer.getvalue()
