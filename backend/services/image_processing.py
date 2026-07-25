"""Pure Pillow helpers for the BG-removal pipeline (SS-011). No I/O, no
external calls -- easy to unit-test with synthetic in-memory images.
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from typing import cast

from PIL import Image

_NEAR_WHITE_THRESHOLD = 245
_NEAR_TRANSPARENT_ALPHA_THRESHOLD = 10
_LOW_CONFIDENCE_FOREGROUND_RATIO = 0.03


def generate_thumbnail(image_bytes: bytes, width: int = 300) -> bytes:
    """Produces a JPEG thumbnail resized to ``width``, preserving aspect
    ratio. JPEG has no alpha channel, so any transparency in the source is
    flattened onto a white background first."""
    with Image.open(io.BytesIO(image_bytes)) as source:
        working: Image.Image = (
            source.convert("RGBA") if source.mode in ("RGBA", "LA", "P") else source.convert("RGB")
        )

        if working.mode == "RGBA":
            flattened = Image.new("RGB", working.size, (255, 255, 255))
            flattened.paste(working, mask=working.split()[3])
            working = flattened

        aspect_ratio = working.height / working.width
        target_height = max(1, round(width * aspect_ratio))
        resized = working.resize((width, target_height))

        out = io.BytesIO()
        resized.save(out, format="JPEG", quality=85)
        return out.getvalue()


def looks_already_transparent_or_white(original_bytes: bytes) -> bool:
    """Cost-saving pre-check: samples the 4 corner pixels. If every corner is
    either near-white (RGB all > 245) or near-transparent (alpha < 10, when
    an alpha channel is present), treats the image as already having a clean
    background and skips the Replicate call entirely.

    Approximate by design (a patterned background near the corners could
    false-negative into calling Replicate anyway) -- acceptable, since
    getting this wrong just costs one extra $0.0023 call, not a correctness
    or security issue.
    """
    with Image.open(io.BytesIO(original_bytes)) as image:
        has_alpha = image.mode in ("RGBA", "LA")
        width, height = image.size
        corners = [(0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)]

        rgba_image = image.convert("RGBA") if has_alpha else None
        rgb_image = image.convert("RGB")

        for x, y in corners:
            if has_alpha and rgba_image is not None:
                rgba_pixel = rgba_image.getpixel((x, y))
                assert isinstance(rgba_pixel, tuple)
                _, _, _, a = rgba_pixel
                if a < _NEAR_TRANSPARENT_ALPHA_THRESHOLD:
                    continue
            rgb_pixel = rgb_image.getpixel((x, y))
            assert isinstance(rgb_pixel, tuple)
            r, g, b = rgb_pixel
            if not (
                r > _NEAR_WHITE_THRESHOLD
                and g > _NEAR_WHITE_THRESHOLD
                and b > _NEAR_WHITE_THRESHOLD
            ):
                return False

        return True


def foreground_ratio(clean_png_bytes: bytes) -> float:
    """Fraction of pixels with alpha > 10 in a BG-removed PNG. BRIA-RMBG
    itself returns no classification/confidence score -- this is a proxy
    signal for "did BRIA-RMBG keep almost nothing as foreground," not a real
    content classifier (SS-012's Gemini-based confidence field is the real
    one, for a different pipeline stage)."""
    with Image.open(io.BytesIO(clean_png_bytes)) as image:
        rgba_image = image.convert("RGBA")
        width, height = rgba_image.size
        total_pixels = width * height
        if total_pixels == 0:
            return 0.0

        alpha_channel = rgba_image.split()[3]
        alpha_values = cast(Iterable[int], alpha_channel.getdata())
        foreground_pixels = sum(
            1 for value in alpha_values if value > _NEAR_TRANSPARENT_ALPHA_THRESHOLD
        )
        return foreground_pixels / total_pixels


def is_low_confidence(clean_png_bytes: bytes) -> bool:
    """Convenience wrapper around ``foreground_ratio`` using this module's
    pinned threshold (0.03), per the design doc's Concrete values."""
    return foreground_ratio(clean_png_bytes) < _LOW_CONFIDENCE_FOREGROUND_RATIO


def resize_for_bg_removal(original_bytes: bytes, max_width: int = 800) -> bytes:
    """Builds a smaller, in-memory-only JPEG proxy of ``original_bytes`` for
    the Replicate call itself (added post-QA, 2026-07-25 -- see the design
    doc's "Image sizing strategy" section). Never written to R2; SS-010's
    full-resolution original in R2 is untouched.

    Resizes down to ``max_width`` only if the source is wider than that --
    never upscales an already-narrower image. Always JPEG-encodes the result
    regardless (Replicate's input is a plain image, not something that needs
    to preserve an incoming alpha channel -- the pre-check
    ``looks_already_transparent_or_white`` already filtered out images where
    that would matter)."""
    with Image.open(io.BytesIO(original_bytes)) as source:
        working = source.convert("RGB")

        if source.width > max_width:
            aspect_ratio = source.height / source.width
            target_height = max(1, round(max_width * aspect_ratio))
            working = working.resize((max_width, target_height))

        out = io.BytesIO()
        working.save(out, format="JPEG", quality=90)
        return out.getvalue()


def apply_alpha_mask_to_original(original_bytes: bytes, low_res_rgba_bytes: bytes) -> bytes:
    """Composites Replicate's (lower-resolution proxy) alpha mask back onto
    the full-resolution original, so the final stored ``clean.png`` doesn't
    lose quality despite the Replicate call itself having processed a
    smaller image (see the design doc's "Image sizing strategy" section).

    Extracts the alpha channel from ``low_res_rgba_bytes``, upscales it to
    ``original_bytes``'s actual dimensions with
    ``Image.Resampling.LANCZOS``, and applies it to the full-resolution
    original's RGB. Returns encoded PNG bytes at the original's resolution.

    Tradeoff, stated plainly in the design doc: the upscaled alpha mask's
    edges are marginally softer than a native full-resolution mask would
    produce -- a small amount of edge precision traded for measured latency
    improvement."""
    with (
        Image.open(io.BytesIO(original_bytes)) as original,
        Image.open(io.BytesIO(low_res_rgba_bytes)) as low_res,
    ):
        original_rgb = original.convert("RGB")
        low_res_alpha = low_res.convert("RGBA").split()[3]
        upscaled_alpha = low_res_alpha.resize(original_rgb.size, Image.Resampling.LANCZOS)

        composited = original_rgb.copy()
        composited.putalpha(upscaled_alpha)

        out = io.BytesIO()
        composited.save(out, format="PNG")
        return out.getvalue()
