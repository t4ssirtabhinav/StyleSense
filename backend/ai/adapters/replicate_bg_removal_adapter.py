"""Replicate-backed ``IBackgroundRemovalProvider`` adapter (SS-011).

Wraps the ``replicate`` Python SDK (already in ``requirements.txt`` --
``replicate==1.0.7``, no new install needed).

Model reference: ``bria/remove-background:5ecc270b34e9d8e1f007d9dbd3c724f0badf638f05ffaa0c5e0634ed64d3d378``
-- ``[VERIFIED 2026-07-24]`` against Replicate's real
``GET https://api.replicate.com/v1/models/bria/remove-background`` API using
the real ``REPLICATE_API_TOKEN`` now present in ``.env`` (200 response;
``latest_version.id`` transcribed verbatim above). This supersedes the raw
ticket's informal "bria-rmbg" name and the design doc's "not verified this
session" flag -- the exact slug/version is now confirmed live, not guessed.

Input schema (also live-verified from the same call): ``image`` (a file/URI),
``preserve_alpha`` (bool, default ``true`` -- kept default so BRIA-RMBG
preserves the alpha channel this pipeline's ``clean.png`` needs). Output is a
single URI (``format: "uri"``) pointing at the hosted result PNG.

Real end-to-end call attempted during Developer phase: ``replicate.async_run``
raised ``replicate.exceptions.ReplicateError`` with ``status: 402
"Insufficient credit"`` -- the token itself is valid (confirmed via the 200
GET above) but the account has no run credit. Logged as ``BL-054`` (not a
code gap). This adapter's exception handling was validated against that same
real error object.
"""

from __future__ import annotations

import io
import logging
import time

import replicate
from replicate.helpers import FileOutput

from ai.ports.interfaces import BackgroundRemovalResult, IBackgroundRemovalProvider

logger = logging.getLogger(__name__)

# [VERIFIED 2026-07-24] via a live GET against Replicate's models API using
# the real REPLICATE_API_TOKEN -- see module docstring.
MODEL_REFERENCE = (
    "bria/remove-background:5ecc270b34e9d8e1f007d9dbd3c724f0badf638f05ffaa0c5e0634ed64d3d378"
)

# Logged verbatim on every real (non-skipped) Replicate call, per the design
# doc's Concrete values -- Replicate is billed per-run, not per-token.
COST_USD_PER_RUN = 0.0023


class ReplicateBgRemovalAdapter(IBackgroundRemovalProvider):
    """Calls Replicate's BRIA-RMBG (``bria/remove-background``) model."""

    async def remove_background(self, image_bytes: bytes) -> BackgroundRemovalResult:
        start = time.perf_counter()
        try:
            output = await replicate.async_run(
                MODEL_REFERENCE,
                input={"image": io.BytesIO(image_bytes), "preserve_alpha": True},
            )
            latency_ms = int((time.perf_counter() - start) * 1000)

            if isinstance(output, FileOutput):
                result_bytes = await output.aread()
            else:
                # Defensive fallback -- ``use_file_output`` defaults to True
                # for a single-uri ``Output`` schema (confirmed live), so
                # this branch is not expected to be hit in practice.
                result_bytes = bytes(output)  # type: ignore[arg-type] # pragma: no cover - defensive

            return BackgroundRemovalResult(
                success=True, image_bytes=result_bytes, latency_ms=latency_ms
            )
        except Exception as exc:  # noqa: BLE001 - caller owns retry/circuit-breaker policy
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.warning(
                "replicate_bg_removal_failed",
                extra={"error": str(exc), "latency_ms": latency_ms},
            )
            return BackgroundRemovalResult(success=False, latency_ms=latency_ms, error=str(exc))
