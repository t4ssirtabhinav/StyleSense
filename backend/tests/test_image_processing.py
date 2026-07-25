"""Tests for backend/services/image_processing.py (SS-011)."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from services.image_processing import (
    apply_alpha_mask_to_original,
    foreground_ratio,
    generate_thumbnail,
    is_low_confidence,
    looks_already_transparent_or_white,
    resize_for_bg_removal,
)


def _jpeg_bytes(size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", size, color)
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    return buf.getvalue()


def _rgba_bytes(size: tuple[int, int], color: tuple[int, int, int, int]) -> bytes:
    image = Image.new("RGBA", size, color)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.parametrize("size", [(400, 300), (300, 400), (500, 500), (1200, 200)])
def test_generate_thumbnail_produces_300px_wide_jpeg_for_various_aspect_ratios(
    size: tuple[int, int],
) -> None:
    original = _jpeg_bytes(size, (100, 150, 200))

    thumbnail_bytes = generate_thumbnail(original, width=300)

    with Image.open(io.BytesIO(thumbnail_bytes)) as thumb:
        assert thumb.format == "JPEG"
        assert thumb.width == 300


def test_looks_already_transparent_or_white_true_for_all_white_image() -> None:
    white = _jpeg_bytes((200, 200), (255, 255, 255))

    assert looks_already_transparent_or_white(white) is True


def test_looks_already_transparent_or_white_false_for_non_white_image() -> None:
    colored = _jpeg_bytes((200, 200), (30, 60, 90))

    assert looks_already_transparent_or_white(colored) is False


def test_looks_already_transparent_or_white_true_for_transparent_corners() -> None:
    transparent = _rgba_bytes((200, 200), (10, 20, 30, 0))

    assert looks_already_transparent_or_white(transparent) is True


def test_foreground_ratio_below_threshold_for_near_fully_transparent_png() -> None:
    mostly_transparent = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    # A tiny 2x2 opaque patch -- well under 3% of 100x100=10000 pixels.
    for x in range(2):
        for y in range(2):
            mostly_transparent.putpixel((x, y), (255, 0, 0, 255))
    buf = io.BytesIO()
    mostly_transparent.save(buf, format="PNG")

    ratio = foreground_ratio(buf.getvalue())

    assert ratio < 0.03
    assert is_low_confidence(buf.getvalue()) is True


def test_foreground_ratio_above_threshold_for_large_opaque_region() -> None:
    mostly_opaque = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
    buf = io.BytesIO()
    mostly_opaque.save(buf, format="PNG")

    ratio = foreground_ratio(buf.getvalue())

    assert ratio > 0.03
    assert is_low_confidence(buf.getvalue()) is False


def test_resize_for_bg_removal_downscales_wider_input_to_max_width() -> None:
    wide_original = _jpeg_bytes((1200, 600), (100, 150, 200))

    proxy_bytes = resize_for_bg_removal(wide_original, max_width=800)

    with Image.open(io.BytesIO(proxy_bytes)) as proxy:
        assert proxy.format == "JPEG"
        assert proxy.width == 800
        assert proxy.height == 400  # aspect ratio preserved (1200:600 -> 800:400)


def test_resize_for_bg_removal_never_upscales_already_narrower_input() -> None:
    narrow_original = _jpeg_bytes((500, 300), (100, 150, 200))

    proxy_bytes = resize_for_bg_removal(narrow_original, max_width=800)

    with Image.open(io.BytesIO(proxy_bytes)) as proxy:
        assert proxy.width == 500
        assert proxy.height == 300


def test_apply_alpha_mask_to_original_matches_original_dimensions_and_scales_alpha() -> None:
    original = _jpeg_bytes((400, 400), (10, 20, 30))

    # Low-res (100x100) RGBA mask: fully opaque center 40x40 square,
    # fully transparent elsewhere.
    low_res_mask = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    for x in range(30, 70):
        for y in range(30, 70):
            low_res_mask.putpixel((x, y), (255, 255, 255, 255))
    buf = io.BytesIO()
    low_res_mask.save(buf, format="PNG")

    composited_bytes = apply_alpha_mask_to_original(original, buf.getvalue())

    with Image.open(io.BytesIO(composited_bytes)) as composited:
        assert composited.mode == "RGBA"
        assert composited.size == (400, 400)  # matches the *original's* dimensions

        # Center (scaled proportionally from the low-res opaque square)
        # should be fully opaque; a far corner should be fully transparent.
        center_pixel = composited.getpixel((200, 200))
        assert isinstance(center_pixel, tuple)
        assert center_pixel[3] > 250

        corner_pixel = composited.getpixel((5, 5))
        assert isinstance(corner_pixel, tuple)
        assert corner_pixel[3] < 5
