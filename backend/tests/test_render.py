"""PNG rasterization for Printful (which rejects SVG). Asserts the output is a
transparent, correctly-sized, print-ready PNG with contrasting ink."""

import io

from PIL import Image

import pytest

from app.factory.render import LAYOUTS, PRINT_HEIGHT, PRINT_WIDTH, render_text_png


def _open(png_bytes: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(png_bytes))
    img.load()
    return img


def test_output_is_transparent_rgba_png_at_print_size():
    img = _open(render_text_png("we are so back"))
    assert img.format == "PNG"
    assert img.mode == "RGBA"
    assert img.size == (PRINT_WIDTH, PRINT_HEIGHT)
    # Corners are the untouched transparent background.
    assert img.getpixel((0, 0))[3] == 0
    assert img.getpixel((PRINT_WIDTH - 1, PRINT_HEIGHT - 1))[3] == 0


def _has_ink(img: Image.Image) -> bool:
    # getextrema() on the alpha channel: max > 0 means some pixel is opaque.
    return img.getchannel("A").getextrema()[1] > 0


def test_ink_is_actually_drawn():
    assert _has_ink(_open(render_text_png("we are so back"))), "no ink drawn"


def _has_color(img: Image.Image, rgb: tuple[int, int, int]) -> bool:
    colors = img.getcolors(maxcolors=1 << 24) or []
    return any(a > 200 and (r, g, b) == rgb for _count, (r, g, b, a) in colors)


def test_dark_garment_gets_white_ink():
    img = _open(render_text_png("demure", garment_color="black"))
    assert _has_color(img, (255, 255, 255))


def test_light_garment_gets_dark_ink():
    img = _open(render_text_png("demure", garment_color="white"))
    assert _has_color(img, (17, 17, 17))  # #111111


def test_long_copy_still_fits_and_renders():
    copy = ("supercalifragilistic expialidocious " * 20)[:500]
    img = _open(render_text_png(copy))
    assert img.size == (PRINT_WIDTH, PRINT_HEIGHT)
    assert _has_ink(img)


def test_single_long_unbroken_word_hard_wraps_without_crashing():
    img = _open(render_text_png("x" * 400))
    assert img.size == (PRINT_WIDTH, PRINT_HEIGHT)
    assert _has_ink(img)


def test_injection_text_is_just_pixels_not_markup():
    # Rasterization renders text as pixels — markup can't escape a raster.
    img = _open(render_text_png("</text><script>alert(1)</script>"))
    assert img.mode == "RGBA"
    assert _has_ink(img)


def _corners_transparent(img: Image.Image) -> bool:
    return (
        img.getpixel((0, 0))[3] == 0
        and img.getpixel((PRINT_WIDTH - 1, 0))[3] == 0
        and img.getpixel((0, PRINT_HEIGHT - 1))[3] == 0
        and img.getpixel((PRINT_WIDTH - 1, PRINT_HEIGHT - 1))[3] == 0
    )


@pytest.mark.parametrize("layout", LAYOUTS)
def test_every_layout_stays_contained_and_draws_ink(layout):
    # Each template must render on-canvas (corners untouched = inside the print
    # area) with visible ink and the right size — the core containment invariant.
    img = _open(render_text_png("crashing out respectfully", layout=layout))
    assert img.size == (PRINT_WIDTH, PRINT_HEIGHT)
    assert img.mode == "RGBA"
    assert _has_ink(img), f"{layout} drew no ink"
    assert _corners_transparent(img), f"{layout} bled into a corner"


@pytest.mark.parametrize("layout", LAYOUTS)
def test_every_layout_handles_long_copy_without_bleeding(layout):
    copy = ("supercalifragilistic expialidocious " * 20)[:500]
    img = _open(render_text_png(copy, layout=layout))
    assert img.size == (PRINT_WIDTH, PRINT_HEIGHT)
    assert _has_ink(img)
    assert _corners_transparent(img), f"{layout} overflowed on long copy"


def test_unknown_layout_falls_back_to_centered_without_crashing():
    fallback = _open(render_text_png("demure", layout="not-a-layout"))
    centered = _open(render_text_png("demure", layout="centered"))
    assert fallback.tobytes() == centered.tobytes()  # identical to the default


def test_top_left_and_centered_differ():
    # Variety is the whole point: the same copy in two layouts must not be identical.
    a = _open(render_text_png("we are so back", layout="centered")).tobytes()
    b = _open(render_text_png("we are so back", layout="top_left")).tobytes()
    assert a != b
