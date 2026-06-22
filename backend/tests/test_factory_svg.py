"""SVG print file: text stays inside the canvas, and operator copy is escaped.

Guards two CLAUDE.md concerns: "escape all text payload variations before
outputting files" and not shipping art that renders off the printable area.
"""

import re
import xml.etree.ElementTree as ET

from app.factory.printful import PrintfulClient

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
