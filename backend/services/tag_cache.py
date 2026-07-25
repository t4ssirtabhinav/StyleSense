"""Thin Upstash REST wrapper for Gemini tagging result caching + a
short-TTL in-flight marker (SS-012, amended A1).

REST shape: uses Upstash's **"POST command in body"** mechanism (``POST
{url}`` with a JSON array body, e.g. ``["SET", "foo", "bar", "EX", 100]``)
rather than the path-style ``{url}/set/{key}/{value}/...`` this repo's
``RateLimiter``/``CircuitBreaker`` use for their own scalar (int) values --
because a tagging payload is an arbitrary JSON blob (braces/quotes/commas),
which the path-style form can't safely carry without extra escaping, while
the body-array form passes it as one JSON value untouched.

``[VERIFIED 2026-07-25, upstash.com/docs/redis/features/restapi.md]``
(fetched live during this ticket's Developer phase, same "verify, don't
recite" discipline as ``BL-035``/``BL-039``):
- ``SET foo bar EX 100`` -> path-style ``REST_URL/set/foo/bar/EX/100``
  (confirms this repo's existing ``RateLimiter``/``CircuitBreaker`` shape).
- ``GET foo`` -> ``REST_URL/get/foo``.
- The docs' own "POST Command in Body" section: ``curl -X POST -d
  '["SET", "foo", "bar", "EX", 100]' https://.../`` is an equally valid,
  documented alternate form -- used here specifically for its safety with
  an embedded JSON value.

Key scheme: results at ``tag:{md5_hex}`` (30-day TTL); in-flight marker at
``tag_inflight:{md5_hex}`` (~60s TTL, ``NX``-gated so only the first caller
for a given image within the window gets ``True``).

Fails **open**: ``get`` -> ``None`` (miss) on any error/unset env;
``set``/``clear_inflight`` -> silent no-op; ``mark_inflight`` -> ``True``
(i.e. "no marker seen, proceed") -- a cache/marker miss must never block
tagging. This is the opposite posture from ``DailyRateLimiter``'s money
gate, deliberately: the in-flight marker is a best-effort dedupe, not a
hard lock.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_RESULT_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days
_INFLIGHT_TTL_SECONDS = 60


def _result_key(image_hash: str) -> str:
    return f"tag:{image_hash}"


def _inflight_key(image_hash: str) -> str:
    return f"tag_inflight:{image_hash}"


class TagCache:
    async def get(self, image_hash: str) -> dict[str, Any] | None:
        result = await self._command(["GET", _result_key(image_hash)])
        if not isinstance(result, str):
            return None
        try:
            parsed = json.loads(result)
        except json.JSONDecodeError:
            logger.warning("tag_cache_corrupt_entry", extra={"image_hash": image_hash})
            return None
        return parsed if isinstance(parsed, dict) else None

    async def set(self, image_hash: str, payload: dict[str, Any]) -> None:
        await self._command(
            [
                "SET",
                _result_key(image_hash),
                json.dumps(payload),
                "EX",
                str(_RESULT_TTL_SECONDS),
            ]
        )

    async def mark_inflight(self, image_hash: str) -> bool:
        """Returns True if this call newly set the marker (no concurrent
        call in flight -- proceed), False if a marker already existed (a
        concurrent/retried call is mid-flight for the same image --
        short-circuit without calling Gemini again). Fails open (returns
        True, i.e. "proceed") on any infra error -- the marker degrades to
        "no dedupe", never to "blocked"."""
        result = await self._command(
            ["SET", _inflight_key(image_hash), "1", "EX", str(_INFLIGHT_TTL_SECONDS), "NX"],
            fail_open_value="OK",
        )
        return result is not None

    async def clear_inflight(self, image_hash: str) -> None:
        await self._command(["DEL", _inflight_key(image_hash)])

    async def _command(self, command: list[Any], *, fail_open_value: Any = None) -> Any:
        url = os.getenv("UPSTASH_REDIS_REST_URL")
        token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
        if not url or not token:
            logger.warning("tag_cache_env_unset", extra={"command": command[0]})
            return fail_open_value

        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(url, json=command, headers=headers)
                response.raise_for_status()
                body = response.json()
                if body.get("error"):
                    raise httpx.HTTPError(f"Upstash error: {body['error']}")
                return body.get("result")
        except httpx.HTTPError as exc:
            logger.warning(
                "tag_cache_command_failed", extra={"command": command[0], "error": str(exc)}
            )
            return fail_open_value
