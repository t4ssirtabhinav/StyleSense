"""``CostBudgetGate`` -- reserve/deny/reconcile orchestration over
``IRateLimiter``. Owns tier semantics (fail-open governs the infra-failure
path only; a paying tier's ceiling is still enforced when Redis is healthy
-- design §3.3's "precise reading of the tier AC") and the production
assertions (design §4.4).

**Reserve-before, reconcile-after** (design §4.1/§4.2) is the entire answer
to the concurrent-burst boundary case: the allow/deny decision comes SOLELY
from the single atomic value ``IRateLimiter.check_and_consume`` returns --
never a ``GET`` followed by a conditional increment. N concurrent requests
against the same key get N distinct, strictly-increasing post-increment
totals from Upstash itself; only the ones landing at-or-under the ceiling
are allowed. This module adds no read-then-write of its own.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from adapters.interfaces import IRateLimiter
from services.app_config import AppConfigService, AppConfigSnapshot
from services.cost_config_specs import AI_COST_BUDGETS_SPEC
from services.ist_window import (
    ist_day_key,
    ist_month_key,
    seconds_until_next_ist_midnight,
    seconds_until_next_ist_month_start,
)

logger = logging.getLogger(__name__)

_KEY_PREFIX_DAILY = "stylesense:cost:daily"
_KEY_PREFIX_MONTHLY = "stylesense:cost:monthly"

_KNOWN_TIERS = ("free", "premium", "premium_annual")


def normalize_tier(tier: str | None) -> str:
    """A ``NULL``, missing, or unrecognised ``plan_tier`` normalises to
    ``free`` (fail-closed direction) -- design §3.3/edge case 8. Never
    treat an unknown tier as paying."""
    return tier if tier in _KNOWN_TIERS else "free"


@dataclass(frozen=True)
class Reservation:
    """Opaque token returned by a successful ``reserve()``, threaded through
    the router -> ``BackgroundTasks`` -> service -> ``reconcile()``. Carries
    everything ``reconcile()`` needs without a second Redis round-trip or a
    second config read."""

    user_id: str
    tier: str
    reserved_micropaise: int
    daily_key: str
    monthly_key: str
    daily_current: int | None
    monthly_current: int | None
    daily_ceiling: int
    monthly_ceiling: int
    touched_redis: bool  # False on the zero-cost / enforcement-disabled no-op path


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    scope: str | None  # 'daily' | 'monthly' on deny; None otherwise
    degraded: bool
    reservation: Reservation | None  # present iff allowed


@dataclass(frozen=True)
class BudgetStatus:
    """(SS-039) Read-only snapshot of how close a caller is to their
    budget ceiling -- distinct from ``GateDecision``, which is only ever
    produced by the mutating ``reserve()``. Never itself an allow/deny
    decision; the real enforcement still happens at ``reserve()``."""

    near_ceiling: bool
    daily_ratio: float | None  # None if unenforced for this tier, or peek() failed
    monthly_ratio: float | None


class CostBudgetGate:
    def __init__(self, limiter: IRateLimiter, config_service: AppConfigService) -> None:
        self._limiter = limiter
        self._config_service = config_service

    async def reserve(
        self,
        *,
        user_id: str,
        tier: str | None,
        estimate_micropaise: int,
        config_snapshot: AppConfigSnapshot,
    ) -> GateDecision:
        tier_norm = normalize_tier(tier)
        daily_key = f"{_KEY_PREFIX_DAILY}:{user_id}:{ist_day_key()}"
        monthly_key = f"{_KEY_PREFIX_MONTHLY}:{user_id}:{ist_month_key()}"

        if estimate_micropaise <= 0:
            # test_zero_cost_call_is_allowed_without_touching_redis
            return GateDecision(
                allowed=True,
                scope=None,
                degraded=False,
                reservation=Reservation(
                    user_id=user_id,
                    tier=tier_norm,
                    reserved_micropaise=0,
                    daily_key=daily_key,
                    monthly_key=monthly_key,
                    daily_current=None,
                    monthly_current=None,
                    daily_ceiling=0,
                    monthly_ceiling=0,
                    touched_redis=False,
                ),
            )

        budgets_config = self._config_service.read(config_snapshot, AI_COST_BUDGETS_SPEC)
        tier_budget = budgets_config.for_tier(tier_norm)

        if not tier_budget.enforce:
            return GateDecision(
                allowed=True,
                scope=None,
                degraded=False,
                reservation=Reservation(
                    user_id=user_id,
                    tier=tier_norm,
                    reserved_micropaise=0,
                    daily_key=daily_key,
                    monthly_key=monthly_key,
                    daily_current=None,
                    monthly_current=None,
                    daily_ceiling=tier_budget.daily_micropaise,
                    monthly_ceiling=tier_budget.monthly_micropaise,
                    touched_redis=False,
                ),
            )

        day_decision = await self._limiter.check_and_consume(
            key=daily_key,
            amount=estimate_micropaise,
            ceiling=tier_budget.daily_micropaise,
            ttl_seconds=seconds_until_next_ist_midnight(),
            fail_open=tier_budget.fail_open,
        )
        self._log_degraded(day_decision.degraded, day_decision.allowed, scope="daily", user_id=user_id)
        if not day_decision.allowed:
            return GateDecision(
                allowed=False, scope="daily", degraded=day_decision.degraded, reservation=None
            )

        month_decision = await self._limiter.check_and_consume(
            key=monthly_key,
            amount=estimate_micropaise,
            ceiling=tier_budget.monthly_micropaise,
            ttl_seconds=seconds_until_next_ist_month_start(),
            fail_open=tier_budget.fail_open,
        )
        self._log_degraded(
            month_decision.degraded, month_decision.allowed, scope="monthly", user_id=user_id
        )
        if not month_decision.allowed:
            # Step 5's rollback: a call denied by the monthly ceiling must
            # not silently consume daily budget.
            await self._limiter.adjust(key=daily_key, delta=-estimate_micropaise)
            return GateDecision(
                allowed=False, scope="monthly", degraded=month_decision.degraded, reservation=None
            )

        return GateDecision(
            allowed=True,
            scope=None,
            degraded=day_decision.degraded or month_decision.degraded,
            reservation=Reservation(
                user_id=user_id,
                tier=tier_norm,
                reserved_micropaise=estimate_micropaise,
                daily_key=daily_key,
                monthly_key=monthly_key,
                daily_current=day_decision.current,
                monthly_current=month_decision.current,
                daily_ceiling=tier_budget.daily_micropaise,
                monthly_ceiling=tier_budget.monthly_micropaise,
                touched_redis=True,
            ),
        )

    async def budget_status(
        self,
        *,
        user_id: str,
        tier: str | None,
        config_snapshot: AppConfigSnapshot,
        near_ceiling_ratio: float = 0.9,
    ) -> BudgetStatus:
        """(SS-039) Read-only -- two ``peek()`` calls, never
        ``check_and_consume``/``reserve``. A tier with ``enforce=False``
        always reports ``near_ceiling=False``, matching ``reserve()``'s own
        unenforced-tier short-circuit (no ``peek()`` call made). A
        ``peek()`` failure (``None``) is excluded from the near-ceiling
        computation, not treated as 0 or as over-ceiling -- an advisory
        signal degrading safely toward the richer tier (E2), since the REAL
        enforcement decision still happens later, atomically, at the actual
        ``reserve()`` call this method never makes."""
        tier_norm = normalize_tier(tier)
        daily_key = f"{_KEY_PREFIX_DAILY}:{user_id}:{ist_day_key()}"
        monthly_key = f"{_KEY_PREFIX_MONTHLY}:{user_id}:{ist_month_key()}"

        budgets_config = self._config_service.read(config_snapshot, AI_COST_BUDGETS_SPEC)
        tier_budget = budgets_config.for_tier(tier_norm)

        if not tier_budget.enforce:
            return BudgetStatus(near_ceiling=False, daily_ratio=None, monthly_ratio=None)

        daily_current = await self._limiter.peek(key=daily_key)
        monthly_current = await self._limiter.peek(key=monthly_key)

        daily_ratio = (
            daily_current / tier_budget.daily_micropaise
            if daily_current is not None and tier_budget.daily_micropaise > 0
            else None
        )
        monthly_ratio = (
            monthly_current / tier_budget.monthly_micropaise
            if monthly_current is not None and tier_budget.monthly_micropaise > 0
            else None
        )

        near_ceiling = (daily_ratio is not None and daily_ratio >= near_ceiling_ratio) or (
            monthly_ratio is not None and monthly_ratio >= near_ceiling_ratio
        )

        return BudgetStatus(
            near_ceiling=near_ceiling, daily_ratio=daily_ratio, monthly_ratio=monthly_ratio
        )

    async def reconcile(self, *, reservation: Reservation, actual_micropaise: int) -> None:
        """Best-effort. Adjusts both counters by the delta between what was
        reserved and what the call actually cost -- e.g. a cache hit
        reconciles to 0, refunding the full reservation (design edge case
        4); an under-estimated call adjusts upward."""
        if not reservation.touched_redis:
            return

        delta = actual_micropaise - reservation.reserved_micropaise
        new_daily = reservation.daily_current
        new_monthly = reservation.monthly_current

        if delta != 0:
            try:
                await self._limiter.adjust(key=reservation.daily_key, delta=delta)
                await self._limiter.adjust(key=reservation.monthly_key, delta=delta)
            except Exception as exc:  # noqa: BLE001 -- IRateLimiter.adjust must never raise,
                # this is a defensive backstop in case an adapter breaks that contract.
                logger.warning(
                    "budget_reconcile_failed",
                    extra={"user_id": reservation.user_id, "delta": delta, "error": str(exc)},
                )
                return
            new_daily = (
                reservation.daily_current + delta if reservation.daily_current is not None else None
            )
            new_monthly = (
                reservation.monthly_current + delta
                if reservation.monthly_current is not None
                else None
            )

        self._assert_ceiling(reservation, new_daily, new_monthly)

    def _assert_ceiling(
        self, reservation: Reservation, daily_value: int | None, monthly_value: int | None
    ) -> None:
        """The literal "logs every time a ceiling is exceeded by even one"
        production assertion (design §4.4). Best-effort/diagnostic --
        derived from the reservation's own known counter values, not a
        fresh atomic read, so it is not immune to a concurrent adjustment
        racing it; that is an accepted, documented limitation of a logging
        instrument, not of the enforcement path itself (enforcement already
        happened atomically at reserve() time)."""
        if daily_value is not None and daily_value > reservation.daily_ceiling:
            logger.error(
                "budget_ceiling_exceeded",
                extra={
                    "user_id": reservation.user_id,
                    "scope": "daily",
                    "current": daily_value,
                    "ceiling": reservation.daily_ceiling,
                },
            )
        if monthly_value is not None and monthly_value > reservation.monthly_ceiling:
            logger.error(
                "budget_ceiling_exceeded",
                extra={
                    "user_id": reservation.user_id,
                    "scope": "monthly",
                    "current": monthly_value,
                    "ceiling": reservation.monthly_ceiling,
                },
            )

    def _log_degraded(
        self, degraded: bool, allowed: bool, *, scope: str, user_id: str
    ) -> None:
        if not degraded:
            return
        if allowed:
            logger.error(
                "budget_gate_fail_open", extra={"user_id": user_id, "scope": scope}
            )
        else:
            logger.warning(
                "budget_gate_fail_closed", extra={"user_id": user_id, "scope": scope}
            )
