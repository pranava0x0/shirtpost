"""Shared layout geometry for the two renderers (the Pillow PNG in ``render.py``
and the hand-built SVG source in ``printful.py``). Single source of truth so the
debuggable SVG and the printed PNG always agree on placement, scale, and case —
they only differ in *how* they draw (pixel metrics vs. char heuristic), never in
*what* layout they draw. See TRENDS-DISCOVERY-SPEC Part C.
"""

from __future__ import annotations

from dataclasses import dataclass

LAYOUTS = ("centered", "top_left", "oversized", "boxed")
DEFAULT_LAYOUT = "centered"

# Max font each layout may grow to (px). Centered keeps the historical cap.
_CENTERED_MAX_FONT = 220


@dataclass(frozen=True, slots=True)
class LayoutSpec:
    """The box the text must stay within, plus how it's placed/styled."""

    x0: float
    y0: float
    x1: float
    y1: float
    max_font: int
    align: str  # "center" | "left"
    lowercase: bool
    box: bool  # draw an outline framing the text block

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


def layout_spec(layout: str, width: int, height: int, margin: int) -> LayoutSpec:
    """Geometry for ``layout`` within a ``width``x``height`` print area. Every
    region is a sub-box of the printable area, so text never leaves it. An unknown
    layout falls back to ``centered`` (callers also normalize, this is belt)."""
    if layout == "top_left":
        # Small left-chest hit in the upper-left, roughly a fifth of the front.
        return LayoutSpec(margin, margin, width * 0.6, height * 0.42, 130, "left", False, False)
    if layout == "oversized":
        # Fill the width aggressively (half the margin) for a big, loud print.
        m = margin // 2
        return LayoutSpec(m, m, width - m, height - m, 300, "center", True, False)
    if layout == "boxed":
        # Inset a little so the outline box has room inside the print area.
        inset = margin + 40
        return LayoutSpec(inset, inset, width - inset, height - inset, 190, "center", False, True)
    # centered (default) — the historical full-box centered stack.
    return LayoutSpec(margin, margin, width - margin, height - margin, _CENTERED_MAX_FONT, "center", False, False)
