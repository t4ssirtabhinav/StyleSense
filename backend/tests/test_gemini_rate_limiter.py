"""Tests for backend/services/gemini_rate_limiter.py (SS-012)."""

from __future__ import annotations

import asyncio

import pytest

from services.gemini_rate_limiter import GeminiRateLimiter


async def test_up_to_max_requests_acquire_without_blocking() -> None:
    limiter = GeminiRateLimiter(max_requests=15, window_seconds=60.0)

    for _ in range(15):
        await asyncio.wait_for(limiter.acquire(), timeout=0.5)


async def test_the_16th_acquire_queues_until_a_token_frees_instead_of_rejecting() -> None:
    clock_value = [0.0]

    def clock() -> float:
        return clock_value[0]

    limiter = GeminiRateLimiter(max_requests=15, window_seconds=0.2, clock=clock)

    for _ in range(15):
        await limiter.acquire()

    # The 16th call must queue (await), not raise/reject -- simulate time
    # passing past the window in the background while it's waiting (the
    # limiter's internal sleep is real-wall-clock, but the injected clock
    # decides whether the window has actually elapsed on the next check).
    async def _advance_clock_soon() -> None:
        await asyncio.sleep(0.05)
        clock_value[0] = 2.0  # past the 0.2s window -- frees all 15 slots

    advance_task = asyncio.create_task(_advance_clock_soon())
    await asyncio.wait_for(limiter.acquire(), timeout=2.0)
    await advance_task


async def test_tokens_refill_over_elapsed_time_via_injected_clock() -> None:
    clock_value = [100.0]

    def clock() -> float:
        return clock_value[0]

    limiter = GeminiRateLimiter(max_requests=2, window_seconds=10.0, clock=clock)

    await limiter.acquire()
    await limiter.acquire()
    assert len(limiter._timestamps) == 2  # noqa: SLF001 - white-box assertion

    # Not enough time has passed -- the window hasn't freed anything yet.
    clock_value[0] = 105.0
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(limiter.acquire(), timeout=0.05)

    # Advance past the window -- both old timestamps should now evict.
    clock_value[0] = 111.0
    await asyncio.wait_for(limiter.acquire(), timeout=0.5)
