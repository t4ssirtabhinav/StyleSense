"""Tests for backend/services/provider_quota.py (SS-028 design §11)."""

from __future__ import annotations

import asyncio

from services.provider_quota import ProviderQuotaTracker, estimate_tokens


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


async def test_allows_exactly_rpm_reservations_then_refuses() -> None:
    tracker = ProviderQuotaTracker({"gemini": (3, 100_000)}, window_seconds=60.0)

    for _ in range(3):
        assert await tracker.try_reserve("gemini", estimated_tokens=10) is True

    assert await tracker.try_reserve("gemini", estimated_tokens=10) is False


async def test_allows_again_after_the_window_slides() -> None:
    clock = _FakeClock()
    tracker = ProviderQuotaTracker({"gemini": (2, 100_000)}, window_seconds=10.0, clock=clock)

    assert await tracker.try_reserve("gemini", estimated_tokens=10) is True
    assert await tracker.try_reserve("gemini", estimated_tokens=10) is True
    assert await tracker.try_reserve("gemini", estimated_tokens=10) is False

    clock.advance(11.0)
    assert await tracker.try_reserve("gemini", estimated_tokens=10) is True


async def test_tpm_ceiling_refuses_independently_of_rpm() -> None:
    tracker = ProviderQuotaTracker({"gemini": (100, 1000)}, window_seconds=60.0)

    assert await tracker.try_reserve("gemini", estimated_tokens=900) is True
    # Plenty of RPM headroom left, but TPM budget is exhausted.
    assert await tracker.try_reserve("gemini", estimated_tokens=200) is False


async def test_record_usage_reconciles_an_under_estimate_so_next_reservation_reflects_real_spend() -> (
    None
):
    tracker = ProviderQuotaTracker({"gemini": (100, 1000)}, window_seconds=60.0)

    assert await tracker.try_reserve("gemini", estimated_tokens=100) is True
    # The real call turned out to use far more tokens than estimated.
    await tracker.record_usage("gemini", tokens_in=700, tokens_out=200)

    # 900 real tokens now on the books (out of 1000) -- only 100 left.
    assert await tracker.try_reserve("gemini", estimated_tokens=150) is False
    assert await tracker.try_reserve("gemini", estimated_tokens=90) is True


async def test_provider_absent_from_config_is_unlimited() -> None:
    tracker = ProviderQuotaTracker({"gemini": (1, 100)})

    for _ in range(50):
        assert await tracker.try_reserve("claude", estimated_tokens=10_000) is True


async def test_set_ceilings_live_applies_a_new_ceiling_onto_the_same_instance() -> None:
    tracker = ProviderQuotaTracker({"gemini": (1, 100_000)})

    assert await tracker.try_reserve("gemini", estimated_tokens=10) is True
    assert await tracker.try_reserve("gemini", estimated_tokens=10) is False

    tracker.set_ceilings({"gemini": (5, 100_000)})
    # Still within the same 60s window, but the ceiling just moved from 1
    # to 5 -- an already-reserved slot plus 3 more should now succeed.
    assert await tracker.try_reserve("gemini", estimated_tokens=10) is True


def test_ceiling_of_zero_is_clamped_to_at_least_one() -> None:
    tracker = ProviderQuotaTracker({"gemini": (0, 0)})
    assert tracker._ceilings["gemini"] == (1, 1)  # noqa: SLF001 - white-box assertion


async def test_concurrent_reservations_grant_exactly_the_ceiling_not_more() -> None:
    tracker = ProviderQuotaTracker({"gemini": (5, 1_000_000)})

    results = await asyncio.gather(
        *(tracker.try_reserve("gemini", estimated_tokens=10) for _ in range(20))
    )

    assert sum(1 for r in results if r) == 5
    assert sum(1 for r in results if not r) == 15


def test_estimate_tokens_floors_at_min_tokens_plus_output_allowance() -> None:
    assert estimate_tokens(0) == 32 + 512


def test_estimate_tokens_scales_with_prompt_length() -> None:
    assert estimate_tokens(4000, output_allowance=100, min_tokens=1) == 1000 + 100
