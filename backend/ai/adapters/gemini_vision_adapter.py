"""Gemini vision-tagging adapter (SS-012, amended A1).

Wraps the current **``google-genai``** SDK -- NOT the deprecated
``google-generativeai`` (see ``requirements.txt`` and the design doc's
Amendment 1 banner: ``gemini-1.5-flash`` was retired 2025-09-29 and
``google-generativeai``'s support ended 2025-11-30, both live-verified dead
during this ticket, not merely unverified).

**Call shape live-verified 2026-07-25** during this ticket's Developer
phase, against the actually-installed ``google-genai==2.14.0`` package
source (``client.py``/``models.py``/``types.py``/``errors.py``) *and* a
real call against the real ``GEMINI_API_KEY`` using a synthetic
(non-photo, non-personal) test image -- per ``BL-065``'s paid-tier
precondition, no real user/wardrobe photo was ever sent:

- ``genai.Client(api_key=...)`` -- confirmed constructor kwarg.
- ``client.aio.models.generate_content(model=..., contents=[...],
  config=types.GenerateContentConfig(...))`` -- the async path (this
  adapter is ``async``, so ``.aio``, not the sync ``client.models...``).
- ``types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")`` for
  the image part; ``contents=[prompt_str, image_part]``.
- ``response_schema`` accepts a Pydantic model *class* directly (confirmed
  via ``types.SchemaUnion = Union[dict, type, Schema, ...]`` and a live
  call using a small Pydantic schema) -- passed as ``GarmentTags`` itself,
  no separate JSON-schema translation needed.
- ``response.text`` returns the concatenated JSON string, or ``None`` if
  there were no candidates (safety-blocked/empty) -- handled explicitly
  below, never left to raise on ``.text`` access.
- ``google.genai.errors.ClientError`` (4xx, has ``.code``) vs
  ``errors.ServerError`` (5xx, has ``.code``) -- confirmed live (an
  invalid model id raised ``ClientError`` with ``code=404``). Only
  ``ServerError`` (503/transient) is retried, per the design's
  Timeout/retry section; ``ClientError`` and any parse/validation failure
  are never retried (a guaranteed repeat failure isn't worth another spend
  against the 15 RPM / 500 RPD budget).

**Explicit enforced timeout, not just ``HttpOptions.timeout``:** the SDK's
own ``HttpOptions.timeout`` is documented (``googleapis/python-genai``
#911, #1330) as unreliable -- a call can hang past 60s before the server
drops it, and a partially-processed call still bills input tokens with no
output returned. This adapter instead wraps every call in
``asyncio.wait_for`` at the call site, which the standard library
enforces regardless of what the SDK itself does internally.

**Never raises** -- any SDK/network/safety-block/parse/timeout failure is
caught and returned as ``VisionTaggingResult(success=False, error=...)`` so
``WardrobeTaggingService`` owns fallback policy uniformly (mirrors
``IBackgroundRemovalProvider``'s contract).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from typing import Any

from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from ai.ports.interfaces import GarmentTags, IVisionProvider, VisionTaggingResult

logger = logging.getLogger(__name__)

# [VERIFIED 2026-07-25] via a live call against the real GEMINI_API_KEY and
# the installed google-genai==2.14.0 SDK -- see module docstring. Replaces
# the shut-down `gemini-1.5-flash`.
MODEL = "gemini-3.5-flash-lite"

_TAXONOMY_PROMPT = """You are a fashion-cataloguing AI for an India-first wardrobe app.
Look at the single garment photo provided and return ONLY a JSON object (no
markdown, no prose) matching this shape:

{
  "category": one of [western_top, western_bottom, western_dress, western_outerwear,
    ethnic_kurta, ethnic_saree, ethnic_lehenga, ethnic_anarkali,
    ethnic_salwar_kameez, ethnic_dupatta, ethnic_sherwani, indo_western,
    footwear_formal, footwear_casual, footwear_ethnic, footwear_sports,
    accessory_bag, accessory_jewellery, accessory_watch, accessory_belt,
    accessory_scarf] or null if the photo is not clothing (e.g. food, a pet,
    a person with no garment focus),
  "subcategory": a short free-text label (e.g. "straight-fit kurta"), or null,
  "color_primary": the dominant colour as a hex string, e.g. "#1E3A8A",
  "color_secondary": a secondary colour as hex, or null if the garment is a
    single solid colour,
  "pattern": one of [solid, stripes, checks, floral, block_print, bandhani,
    ikat, paisley, polka_dots, embroidered, printed] or another short
    free-text label if none fit,
  "fabric": one of [cotton, silk, linen, denim, wool, rayon, polyester,
    georgette, chiffon, khadi, chikankari] or another short free-text label
    if none fit,
  "occasion_tags": a list of zero or more of [office, casual, date_night,
    wedding_guest, festival, puja, party, travel, workout, beach,
    formal_event, college],
  "season_tags": a list of zero or more of [summer, winter, monsoon, all],
  "confidence": your confidence in this classification, 0.0 to 1.0,
  "content_flag": "ok" (normal clothing photo), "nsfw" (explicit content),
    "not_clothing" (no garment visible), or "other" (unclear/inappropriate),
  "contains_person": true if any identifiable person (including a mirror
    selfie) is visible in the photo, false otherwise -- this is independent
    of content_flag; a mirror selfie of an outfit is normal and is NOT nsfw,
  "alternatives": a list of up to 2 alternative category values if the
    garment is ambiguous (e.g. Indo-Western fusion pieces), or null
}

Rules:
- If multiple garments/accessories appear in one photo, tag only the single
  dominant/largest garment.
- A saree is the primary 5-6 yard draped garment; a dupatta is a narrower
  accompanying scarf-like drape usually worn over a kurta/salwar kameez --
  use photo context (size, how it's worn) to disambiguate the two.
- If the photo is not clothing at all, set category to null and confidence
  to 0.0, and set content_flag to "not_clothing".
- Output strict JSON only, matching the shape above exactly."""


class GeminiVisionAdapter(IVisionProvider):
    """Calls Gemini's ``gemini-3.5-flash-lite`` via the ``google-genai``
    SDK. ``client`` is constructor-injectable (a duck-typed object exposing
    ``.aio.models.generate_content``) so tests can pass a fake without
    touching real network/credentials -- mirrors this repo's existing
    dependency-injection conventions for adapters."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        timeout_seconds: float = 30.0,
        max_attempts: int = 3,
        retry_backoff_base_seconds: float = 0.5,
    ) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._retry_backoff_base_seconds = retry_backoff_base_seconds

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        api_key = os.environ["GEMINI_API_KEY"]
        return genai.Client(api_key=api_key)

    async def tag_garment(self, image_bytes: bytes) -> VisionTaggingResult:
        start = time.perf_counter()
        attempt = 0

        while True:
            attempt += 1
            try:
                client = self._get_client()
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=MODEL,
                        contents=[
                            _TAXONOMY_PROMPT,
                            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                        ],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=GarmentTags,
                        ),
                    ),
                    timeout=self._timeout_seconds,
                )
            except TimeoutError:
                # asyncio.wait_for's cutoff -- the enforced timeout this
                # adapter owns explicitly, not relying on the SDK's own
                # (unreliable) HttpOptions.timeout. Never retried: a call
                # that already hung this long is not worth a second attempt
                # against the same 30s+ budget.
                latency_ms = _elapsed_ms(start)
                logger.warning("gemini_tag_timeout", extra={"latency_ms": latency_ms})
                return VisionTaggingResult(
                    success=False, latency_ms=latency_ms, error="timeout", model=MODEL
                )
            except errors.ServerError as exc:
                # 503/transient -- documented as not billed (server rejects
                # before processing), so retrying is cost-safe. Bounded,
                # small retry count with backoff + jitter.
                if attempt < self._max_attempts:
                    await asyncio.sleep(self._backoff_seconds(attempt))
                    continue
                latency_ms = _elapsed_ms(start)
                logger.warning(
                    "gemini_tag_server_error_exhausted_retries",
                    extra={"latency_ms": latency_ms, "code": exc.code, "attempts": attempt},
                )
                return VisionTaggingResult(
                    success=False,
                    latency_ms=latency_ms,
                    error=f"server_error:{exc.code}",
                    model=MODEL,
                )
            except errors.ClientError as exc:
                # 4xx (bad request/malformed) -- never retried, a
                # guaranteed repeat failure not worth another RPM spend.
                latency_ms = _elapsed_ms(start)
                logger.warning(
                    "gemini_tag_client_error",
                    extra={"latency_ms": latency_ms, "code": exc.code},
                )
                return VisionTaggingResult(
                    success=False,
                    latency_ms=latency_ms,
                    error=f"client_error:{exc.code}",
                    model=MODEL,
                )
            except Exception as exc:  # noqa: BLE001 - caller owns fallback policy
                # Safety-block / unexpected SDK / network failure -- caught
                # broadly and deliberately, never retried (deterministic
                # classes like a safety block would just fail again).
                latency_ms = _elapsed_ms(start)
                logger.warning(
                    "gemini_tag_failed", extra={"latency_ms": latency_ms, "error": str(exc)}
                )
                return VisionTaggingResult(
                    success=False, latency_ms=latency_ms, error=str(exc), model=MODEL
                )

            latency_ms = _elapsed_ms(start)
            text = getattr(response, "text", None)
            if not text:
                # Empty/blocked-candidates response -- google-genai never
                # raises for this case, `.text` just returns None.
                logger.warning("gemini_tag_empty_response", extra={"latency_ms": latency_ms})
                return VisionTaggingResult(
                    success=False,
                    latency_ms=latency_ms,
                    error="empty_or_blocked_response",
                    model=MODEL,
                )

            try:
                payload = json.loads(text)
                tags = GarmentTags.model_validate(payload)
            except (json.JSONDecodeError, ValidationError) as exc:
                logger.warning(
                    "gemini_tag_parse_failed",
                    extra={"latency_ms": latency_ms, "error": str(exc)},
                )
                return VisionTaggingResult(
                    success=False, latency_ms=latency_ms, error="parse_error", model=MODEL
                )

            return VisionTaggingResult(
                success=True, tags=tags, latency_ms=latency_ms, model=MODEL, source="gemini"
            )

    def _backoff_seconds(self, attempt: int) -> float:
        base = self._retry_backoff_base_seconds * (2 ** (attempt - 1))
        return base + random.uniform(0, base * 0.5)


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)
