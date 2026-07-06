"""SVG print file: text stays inside the canvas, and operator copy is escaped.

Guards two CLAUDE.md concerns: "escape all text payload variations before
outputting files" and not shipping art that renders off the printable area.
"""

import re
import xml.etree.ElementTree as ET

import pytest

from app.factory.printful import PrintfulClient, print_color_for_garment

CANVAS_H = 2400


def _baselines_and_fontsize(svg: str) -> tuple[list[float], float]:
    ys = [float(y) for y in re.findall(r'y="([\d.]+)"', svg)]
    fs = float(re.search(r'font-size="([\d.]+)"', svg).group(1))
    return ys, fs


def test_long_copy_stays_within_canvas():
    # Max-length (500-char) submission used to spill from y=-1500 to y=3900.
    copy = ("supercalifragilistic expialidocious " * 20)[:500]
    svg = PrintfulClient.build_text_svg(copy)
    ys, fs = _baselines_and_fontsize(svg)
    assert ys, "no text rendered"
    assert all(0 <= y <= CANVAS_H for y in ys), f"baseline off-canvas: {ys}"
    assert all((y - fs) >= 0 for y in ys), "text top above the canvas"


def test_single_long_unbroken_word_is_hard_wrapped_and_contained():
    svg = PrintfulClient.build_text_svg("x" * 400)
    ys, fs = _baselines_and_fontsize(svg)
    assert len(ys) > 1  # had to wrap
    assert all(0 <= y <= CANVAS_H for y in ys)


def test_svg_escapes_injection_payload():
    svg = PrintfulClient.build_text_svg('</text><script>alert(1)</script>"x')
    assert "<script>" not in svg
    assert "</text><script>" not in svg
    assert "&lt;" in svg and "&gt;" in svg  # angle brackets escaped
    ET.fromstring(svg)  # well-formed despite wrapping


def test_svg_escapes_ampersand_and_quotes():
    svg = PrintfulClient.build_text_svg("Tom & Jerry's \"big\" day")
    assert "&amp;" in svg
    assert "&apos;" in svg
    assert "&quot;" in svg


def test_svg_is_well_formed_xml():
    ET.fromstring(PrintfulClient.build_text_svg("we are so back & <b>delulu</b>"))


# --- Garment-color safety: ink must contrast with the shirt ------------------


@pytest.mark.parametrize(
    "garment,expected",
    [
        ("black", "#FFFFFF"),  # dark garment -> white ink
        ("navy", "#FFFFFF"),
        ("forest green", "#FFFFFF"),
        ("white", "#111111"),  # light garment -> dark ink
        ("sport grey", "#111111"),
        ("yellow", "#111111"),
        ("#FFFFFF", "#111111"),  # hex passthrough
        ("#000000", "#FFFFFF"),
    ],
)
def test_print_color_contrasts_with_garment(garment, expected):
    assert print_color_for_garment(garment) == expected


def test_unknown_garment_color_falls_back_to_white_ink():
    # Safe default for the black default variant; logged, never a crash.
    assert print_color_for_garment("chartreuse-ish") == "#FFFFFF"
    assert print_color_for_garment("") == "#FFFFFF"


def test_light_garment_svg_is_not_white_on_white():
    # Regression: build_text_svg used to hardcode white ink, so a light garment
    # printed invisible art. Now the ink is derived from the garment color.
    svg = PrintfulClient.build_text_svg("we are so back", garment_color="white")
    assert 'fill="#111111"' in svg
    assert 'fill="#FFFFFF"' not in svg


def test_dark_garment_svg_keeps_white_ink():
    svg = PrintfulClient.build_text_svg("we are so back", garment_color="black")
    assert 'fill="#FFFFFF"' in svg
