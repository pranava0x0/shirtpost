"""Security regression: design copy must be XML-escaped in the SVG print file so
operator-pasted text can never inject markup/script. Guards CLAUDE.md's
"escape all text payload variations before outputting files".
"""

from app.factory.printful import PrintfulClient


def test_svg_escapes_injection_payload():
    svg = PrintfulClient.build_text_svg('</text><script>alert(1)</script>"x')
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg
    assert "&quot;" in svg
    # The raw closing-tag breakout must not survive verbatim.
    assert "</text><script>" not in svg


def test_svg_escapes_ampersand_and_quotes():
    svg = PrintfulClient.build_text_svg("Tom & Jerry's \"big\" day")
    assert "&amp;" in svg
    assert "&apos;" in svg
    assert "&quot;" in svg


def test_svg_is_well_formed_xml():
    import xml.etree.ElementTree as ET

    svg = PrintfulClient.build_text_svg("we are so back & <b>delulu</b>")
    ET.fromstring(svg)  # raises if malformed
