"""Tests for backend/services/cost_budget_gate.py (SS-029 design §6.4) --
the boundary sweep: empty / at-limit / over-limit / stale-counter, plus tier
semantics. Concurrent-burst tests live in their own module
(test_cost_budget_gate_concurrency.py) per the design's own file split.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from adapters.interfaces import IAppConfigRepository, IRateLimiter, RateLimitDecision
from services.app_config import AppConfigService
from services.cost_budget_gate import CostBudgetGate


class _FakeAtomicLimiter(IRateLimiter):
    """In-memory stand-in that replicates UpstashRateLimiter's real
    contract: the allow/deny decision comes from a single atomic increment,
    and a deny self-refunds its own increment before returning -- mirrors
    the real adapter's behaviour exactly so gate-level tests exercise the
    same shape without a network."""

    def __init__(self, *, fail: bool = False) -> None:
        self.counters: dict[str, int] = {}
        self.check_calls: list[dict[str, Any]] = []
        self.adjust_calls: list[dict[str, Any]] = []
        self._fail = fail

    async def check_and_consume(
        self, *, key: str, amount: int, ceiling: int, ttl_seconds: int, fail_open: bool
    ) -> RateLimitDecision:
        self.check_calls.append({"key": key, "amount": amount, "ceiling": ceiling})
        if self._fail:
            return RateLimitDecision(allowed=fail_open, current=None, ceiling=ceiling, degraded=True)
        current = self.counters.get(key, 0) + amount
        self.counters[key] = current
        allowed = current <= ceiling
        if not allowed:
            self.counters[key] = current - amount  # self-refund on deny
        return RateLimitDecision(allowed=allowed, current=current, ceiling=ceiling, degraded=False)

    async def adjust(self, *, key: str, delta: int) -> None:
        self.adjust_calls.append({"key": key, "delta": delta})
        self.counters[key] = self.counters.get(key, 0) + delta


class _FakeConfigRepository(IAppConfigRepository):
    def __init__(self, values: dict[str, Any] | None = None, *, fail: bool = False) -> None:
        self._values = values or {}
        self._fail = fail

    async def fetch_all(self) -> dict[str, Any]:
        if self._fail:
            raise RuntimeError("config unreachable")
        return self._values


def _budgets_value(
    *,
    daily_paise: int = 500,
    monthly_paise: int = 2500,
    enforce: bool = True,
    fail_open: bool = False,
) -> dict[str, Any]:
    def _tier() -> dict[str, Any]:
        return {
            "daily_paise": daily_paise,
            "monthly_paise": monthly_paise,
            "enforce": enforce,
            "fail_open": fail_open,
        }

    # Independent dicts per tier -- NOT the same object reused three times,
    # otherwise mutating one tier's override in a test mutates all three.
    return {"free": _tier(), "premium": _tier(), "premium_annual": _tier()}


async def _config_service(values: dict[str, Any] | None = None, *, fail: bool = False) -> AppConfigService:
    service = AppConfigService(_FakeConfigRepository(values, fail=fail))
    return service


async def _snapshot(service: AppConfigService) -> Any:
    return await service.snapshot()


# --- empty -------------------------------------------------------------


async def test_first_call_of_the_day_allowed_from_zero_counter() -> None:
    limiter = _FakeAtomicLimiter()
    service = await _config_service({"ai_cost_budgets": _budgets_value(daily_paise=500)})
    snapshot = await _snapshot(service)
    gate = CostBudgetGate(limiter, service)

    decision = await gate.reserve(
        user_id="u1", tier="free", estimate_micropaise=1000, config_snapshot=snapshot
    )

    assert decision.allowed is True
    assert decision.reservation is not None
    assert decision.reservation.daily_current == 1000


async def test_zero_cost_call_is_allowed_without_touching_redis() -> None:
    limiter = _FakeAtomicLimiter()
    service = await _config_service({"ai_cost_budgets": _budgets_value()})
    snapshot = await _snapshot(service)
    gate = CostBudgetGate(limiter, service)

    decision = await gate.reserve(
        user_id="u1", tier="free", estimate_micropaise=0, config_snapshot=snapshot
    )

    assert decision.allowed is True
    assert limiter.check_calls == []


# --- at-limit / over-limit ------------------------------------------------


async def test_call_landing_exactly_on_the_ceiling_is_allowed() -> None:
    limiter = _FakeAtomicLimiter()
    daily_micropaise = 500 * 1_000_000
    service = await _config_service({"ai_cost_budgets": _budgets_value(daily_paise=500)})
    snapshot = await _snapshot(service)
    gate = CostBudgetGate(limiter, service)

    decision = await gate.reserve(
        user_id="u1", tier="free", estimate_micropaise=daily_micropaise, config_snapshot=snapshot
    )

    assert decision.allowed is True


async def test_call_one_micropaise_over_the_ceiling_is_denied() -> None:
    limiter = _FakeAtomicLimiter()
    daily_micropaise = 500 * 1_000_000
    service = await _config_service({"ai_cost_budgets": _budgets_value(daily_paise=500)})
    snapshot = await _snapshot(service)
    gate = CostBudgetGate(limiter, service)

    decision = await gate.reserve(
        user_id="u1",
        tier="free",
        estimate_micropaise=daily_micropaise + 1,
        config_snapshot=snapshot,
    )

    assert decision.allowed is False
    assert decision.scope == "daily"


async def test_denied_call_refunds_its_own_increment() -> None:
    limiter = _FakeAtomicLimiter()
    service = await _config_service({"ai_cost_budgets": _budgets_value(daily_paise=1)})
    snapshot = await _snapshot(service)
    gate = CostBudgetGate(limiter, service)

    huge = 999_000_000
    decision = await gate.reserve(
        user_id="u1", tier="free", estimate_micropaise=huge, config_snapshot=snapshot
    )

    assert decision.allowed is False
    key = f"stylesense:cost:daily:u1:{__import__('services.ist_window', fromlist=['ist_day_key']).ist_day_key()}"
    assert limiter.counters.get(key, 0) == 0


async def test_monthly_deny_rolls_back_the_daily_reservation() -> None:
    limiter = _FakeAtomicLimiter()
    # Daily ceiling huge, monthly ceiling tiny -- so daily allows, monthly denies.
    values = {
        "ai_cost_budgets": {
            "free": {
                "daily_paise": 10_000,
                "monthly_paise": 0,
                "enforce": True,
                "fail_open": False,
            },
            "premium": _budgets_value()["premium"],
            "premium_annual": _budgets_value()["premium_annual"],
        }
    }
    service = await _config_service(values)
    snapshot = await _snapshot(service)
    gate = CostBudgetGate(limiter, service)

    estimate = 500_000  # under daily ceiling, over monthly (1 paise = 1e6 micropaise)
    decision = await gate.reserve(
        user_id="u1", tier="free", estimate_micropaise=estimate, config_snapshot=snapshot
    )

    assert decision.allowed is False
    assert decision.scope == "monthly"
    from services.ist_window import ist_day_key

    daily_key = f"stylesense:cost:daily:u1:{ist_day_key()}"
    assert limiter.counters.get(daily_key, 0) == 0


# --- stale-counter ----------------------------------------------------------


async def test_counter_from_previous_ist_day_does_not_affect_today() -> None:
    limiter = _FakeAtomicLimiter()
    stale_key = "stylesense:cost:daily:u1:2026-07-29"
    limiter.counters[stale_key] = 999_000_000  # at/over ceiling for a past day

    service = await _config_service({"ai_cost_budgets": _budgets_value(daily_paise=500)})
    snapshot = await _snapshot(service)
    gate = CostBudgetGate(limiter, service)

    decision = await gate.reserve(
        user_id="u1", tier="free", estimate_micropaise=1000, config_snapshot=snapshot
    )

    assert decision.allowed is True  # today's key is distinct, untouched by the stale one


async def test_config_unreachable_falls_back_to_coded_default_budgets() -> None:
    limiter = _FakeAtomicLimiter()
    service = await _config_service(fail=True)
    snapshot = await _snapshot(service)
    gate = CostBudgetGate(limiter, service)

    # Coded default free ceiling is ₹5.00/day = 500_000_000 micropaise.
    decision = await gate.reserve(
        user_id="u1", tier="free", estimate_micropaise=500_000_000, config_snapshot=snapshot
    )
    assert decision.allowed is True

    over = await gate.reserve(
        user_id="u2", tier="free", estimate_micropaise=500_000_001, config_snapshot=snapshot
    )
    assert over.allowed is False


# --- tier semantics ----------------------------------------------------------


async def test_free_tier_denied_when_redis_unavailable(caplog: pytest.LogCaptureFixture) -> None:
    limiter = _FakeAtomicLimiter(fail=True)
    service = await _config_service({"ai_cost_budgets": _budgets_value(fail_open=False)})
    snapshot = await _snapshot(service)
    gate = CostBudgetGate(limiter, service)

    with caplog.at_level(logging.WARNING):
        decision = await gate.reserve(
            user_id="u1", tier="free", estimate_micropaise=1000, config_snapshot=snapshot
        )

    assert decision.allowed is False
    assert decision.degraded is True
    assert any(r.message == "budget_gate_fail_closed" for r in caplog.records)


async def test_premium_tier_allowed_when_redis_unavailable(caplog: pytest.LogCaptureFixture) -> None:
    limiter = _FakeAtomicLimiter(fail=True)
    values = _budgets_value(fail_open=False)
    values["premium"]["fail_open"] = True
    values["premium_annual"]["fail_open"] = True
    service = await _config_service({"ai_cost_budgets": values})
    snapshot = await _snapshot(service)
    gate = CostBudgetGate(limiter, service)

    with caplog.at_level(logging.ERROR):
        decision = await gate.reserve(
            user_id="u1", tier="premium", estimate_micropaise=1000, config_snapshot=snapshot
        )

    assert decision.allowed is True
    assert decision.degraded is True
    assert any(r.message == "budget_gate_fail_open" for r in caplog.records)


async def test_premium_annual_treated_as_paying() -> None:
    limiter = _FakeAtomicLimiter(fail=True)
    values = _budgets_value(fail_open=False)
    values["premium_annual"]["fail_open"] = True
    service = await _config_service({"ai_cost_budgets": values})
    snapshot = await _snapshot(service)
    gate = CostBudgetGate(limiter, service)

    decision = await gate.reserve(
        user_id="u1", tier="premium_annual", estimate_micropaise=1000, config_snapshot=snapshot
    )

    assert decision.allowed is True


async def test_null_plan_tier_normalises_to_free_and_fails_closed() -> None:
    limiter = _FakeAtomicLimiter(fail=True)
    values = _budgets_value(fail_open=False)
    values["premium"]["fail_open"] = True
    service = await _config_service({"ai_cost_budgets": values})
    snapshot = await _snapshot(service)
    gate = CostBudgetGate(limiter, service)

    decision = await gate.reserve(
        user_id="u1", tier=None, estimate_micropaise=1000, config_snapshot=snapshot
    )

    assert decision.allowed is False


async def test_unrecognised_plan_tier_normalises_to_free() -> None:
    limiter = _FakeAtomicLimiter(fail=True)
    values = _budgets_value(fail_open=False)
    values["premium"]["fail_open"] = True
    service = await _config_service({"ai_cost_budgets": values})
    snapshot = await _snapshot(service)
    gate = CostBudgetGate(limiter, service)

    decision = await gate.reserve(
        user_id="u1", tier="something_weird", estimate_micropaise=1000, config_snapshot=snapshot
    )

    assert decision.allowed is False


async def test_paying_tier_ceiling_is_still_enforced_when_redis_is_healthy() -> None:
    """Pins design §3.3's reading of the AC: fail_open governs infra
    failure only, NOT the ceiling itself."""
    limiter = _FakeAtomicLimiter()  # healthy
    values = _budgets_value(daily_paise=1, fail_open=True)
    service = await _config_service({"ai_cost_budgets": values})
    snapshot = await _snapshot(service)
    gate = CostBudgetGate(limiter, service)

    decision = await gate.reserve(
        user_id="u1", tier="premium", estimate_micropaise=999_000_000, config_snapshot=snapshot
    )

    assert decision.allowed is False
    assert decision.degraded is False


async def test_ceiling_exceeded_emits_production_assertion(caplog: pytest.LogCaptureFixture) -> None:
    limiter = _FakeAtomicLimiter()
    values = _budgets_value(daily_paise=1)  # ceiling = 1_000_000 micropaise
    service = await _config_service({"ai_cost_budgets": values})
    snapshot = await _snapshot(service)
    gate = CostBudgetGate(limiter, service)

    decision = await gate.reserve(
        user_id="u1", tier="free", estimate_micropaise=900_000, config_snapshot=snapshot
    )
    assert decision.allowed is True
    assert decision.reservation is not None

    with caplog.at_level(logging.ERROR):
        # Reconcile UP to more than the ceiling -- 900_000 reserved,
        # actual comes back at 2_000_000 (over the 1_000_000 ceiling).
        await gate.reconcile(reservation=decision.reservation, actual_micropaise=2_000_000)

    assert any(r.message == "budget_ceiling_exceeded" for r in caplog.records)


async def test_reconcile_adjusts_both_daily_and_monthly_by_the_delta() -> None:
    limiter = _FakeAtomicLimiter()
    service = await _config_service({"ai_cost_budgets": _budgets_value()})
    snapshot = await _snapshot(service)
    gate = CostBudgetGate(limiter, service)

    decision = await gate.reserve(
        user_id="u1", tier="free", estimate_micropaise=1000, config_snapshot=snapshot
    )
    assert decision.reservation is not None

    await gate.reconcile(reservation=decision.reservation, actual_micropaise=1500)

    deltas = [c["delta"] for c in limiter.adjust_calls]
    assert deltas == [500, 500]  # daily then monthly, same delta each


async def test_reconcile_to_zero_refunds_the_full_reservation() -> None:
    limiter = _FakeAtomicLimiter()
    service = await _config_service({"ai_cost_budgets": _budgets_value()})
    snapshot = await _snapshot(service)
    gate = CostBudgetGate(limiter, service)

    decision = await gate.reserve(
        user_id="u1", tier="free", estimate_micropaise=2000, config_snapshot=snapshot
    )
    assert decision.reservation is not None

    await gate.reconcile(reservation=decision.reservation, actual_micropaise=0)

    deltas = [c["delta"] for c in limiter.adjust_calls]
    assert deltas == [-2000, -2000]


async def test_reconcile_failure_is_logged_and_swallowed(caplog: pytest.LogCaptureFixture) -> None:
    class _RaisingLimiter(_FakeAtomicLimiter):
        async def adjust(self, *, key: str, delta: int) -> None:
            raise RuntimeError("upstash down")

    limiter = _RaisingLimiter()
    service = await _config_service({"ai_cost_budgets": _budgets_value()})
    snapshot = await _snapshot(service)
    gate = CostBudgetGate(limiter, service)

    decision = await gate.reserve(
        user_id="u1", tier="free", estimate_micropaise=1000, config_snapshot=snapshot
    )
    assert decision.reservation is not None

    with caplog.at_level(logging.WARNING):
        await gate.reconcile(reservation=decision.reservation, actual_micropaise=2000)  # must not raise

    assert any(r.message == "budget_reconcile_failed" for r in caplog.records)


async def test_enforcement_disabled_allows_without_touching_redis() -> None:
    limiter = _FakeAtomicLimiter()
    service = await _config_service({"ai_cost_budgets": _budgets_value(enforce=False)})
    snapshot = await _snapshot(service)
    gate = CostBudgetGate(limiter, service)

    decision = await gate.reserve(
        user_id="u1", tier="free", estimate_micropaise=999_000_000, config_snapshot=snapshot
    )

    assert decision.allowed is True
    assert limiter.check_calls == []
