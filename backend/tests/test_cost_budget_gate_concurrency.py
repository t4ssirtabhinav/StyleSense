"""The case most likely to be wrong (SS-029 design §6.5): real ``asyncio``
concurrency, not sequential calls, proving ``CostBudgetGate`` derives its
decision solely from one atomic server-side ``INCRBY`` and never a
``GET``-then-``INCR`` read-then-write.

**Honesty constraint (carried from the design doc into this module, and
into the worklog):** these tests prove CLIENT-SIDE atomicity -- that this
code's own logic never does a read-then-write, and that a real atomic
Redis ``INCRBY`` (faithfully modelled here as a single uninterruptible
dict mutation with a forced ``await asyncio.sleep(0)`` around it to force
task interleaving) closes the burst race. They do **not** prove distributed
correctness across multiple backend instances -- per ``BL-037`` no
multi-instance backend is deployed anywhere. What is verified here is
verifiable locally; the gap is stated, not glossed over.
"""

from __future__ import annotations

import asyncio
from typing import Any

from adapters.interfaces import IRateLimiter, RateLimitDecision
from services.app_config import AppConfigService, IAppConfigRepository
from services.cost_budget_gate import CostBudgetGate


class _FakeConfigRepository(IAppConfigRepository):
    def __init__(self, values: dict[str, Any]) -> None:
        self._values = values

    async def fetch_all(self) -> dict[str, Any]:
        return self._values


class _ForcedInterleavingLimiter(IRateLimiter):
    """Models a real atomic Upstash ``INCRBY``: the mutation of the shared
    counter dict is a single uninterruptible Python statement (correct,
    since there's no ``await`` inside the critical section) -- but every
    call still does an ``await asyncio.sleep(0)`` BEFORE the mutation to
    force the event loop to interleave many concurrent tasks' calls, the
    same way real concurrent HTTP requests to Upstash would interleave at
    the network layer. Records every command issued, in order, so tests can
    assert there is never a ``GET`` before a decision."""

    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self.command_log: list[tuple[str, str]] = []  # (command, key)

    async def check_and_consume(
        self, *, key: str, amount: int, ceiling: int, ttl_seconds: int, fail_open: bool
    ) -> RateLimitDecision:
        await asyncio.sleep(0)  # force interleaving with other concurrent callers
        self.command_log.append(("INCRBY", key))
        current = self.counters.get(key, 0) + amount
        self.counters[key] = current
        allowed = current <= ceiling
        if not allowed:
            await asyncio.sleep(0)
            self.command_log.append(("DECRBY", key))
            # Relative decrement (mirrors real Redis DECRBY's atomic
            # semantics) -- NOT `self.counters[key] = current - amount`,
            # which would silently clobber any other concurrent task's
            # increment that landed on this key between this task's own
            # INCRBY and its refund. That subtle bug is exactly the kind of
            # thing this module exists to catch.
            self.counters[key] -= amount
        return RateLimitDecision(allowed=allowed, current=current, ceiling=ceiling, degraded=False)

    async def adjust(self, *, key: str, delta: int) -> None:
        await asyncio.sleep(0)
        self.command_log.append(("DECRBY" if delta < 0 else "INCRBY", key))
        self.counters[key] = self.counters.get(key, 0) + delta

    async def peek(self, *, key: str) -> int | None:
        """(SS-039) Trivial in-memory read, no mutation, not part of this
        module's own atomicity proof (that's ``check_and_consume``/
        ``adjust``'s job)."""
        await asyncio.sleep(0)
        self.command_log.append(("GET", key))
        return self.counters.get(key)


def _budgets(daily_paise: int, monthly_paise: int = 100_000) -> dict[str, Any]:
    tier = {
        "daily_paise": daily_paise,
        "monthly_paise": monthly_paise,
        "enforce": True,
        "fail_open": False,
    }
    return {"ai_cost_budgets": {"free": dict(tier), "premium": dict(tier), "premium_annual": dict(tier)}}


async def _gate_with_ceiling(
    daily_paise: int,
) -> tuple[CostBudgetGate, _ForcedInterleavingLimiter, AppConfigService]:
    limiter = _ForcedInterleavingLimiter()
    config_service = AppConfigService(_FakeConfigRepository(_budgets(daily_paise)))
    gate = CostBudgetGate(limiter, config_service)
    return gate, limiter, config_service


async def test_parallel_requests_cannot_burst_past_the_ceiling() -> None:
    # ceiling 10 units (paise), cost 1 unit (paise) per call -- 20 calls
    # fired concurrently via asyncio.gather.
    gate, limiter, config_service = await _gate_with_ceiling(daily_paise=10)
    snapshot = await config_service.snapshot()

    unit_micropaise = 1_000_000  # 1 paise

    async def call(i: int) -> bool:
        decision = await gate.reserve(
            user_id="burst-user",
            tier="free",
            estimate_micropaise=unit_micropaise,
            config_snapshot=snapshot,
        )
        return decision.allowed

    results = await asyncio.gather(*(call(i) for i in range(20)))

    allowed_count = sum(1 for r in results if r)
    denied_count = sum(1 for r in results if not r)
    assert allowed_count == 10
    assert denied_count == 10


async def test_gate_makes_no_read_before_write_under_concurrency() -> None:
    gate, limiter, config_service = await _gate_with_ceiling(daily_paise=10)
    snapshot = await config_service.snapshot()
    unit_micropaise = 1_000_000

    async def call() -> None:
        await gate.reserve(
            user_id="burst-user-2",
            tier="free",
            estimate_micropaise=unit_micropaise,
            config_snapshot=snapshot,
        )

    await asyncio.gather(*(call() for _ in range(20)))

    assert all(cmd != "GET" for cmd, _ in limiter.command_log)


async def test_concurrent_denies_do_not_over_refund() -> None:
    gate, limiter, config_service = await _gate_with_ceiling(daily_paise=10)
    snapshot = await config_service.snapshot()
    unit_micropaise = 1_000_000

    async def call() -> None:
        await gate.reserve(
            user_id="refund-user",
            tier="free",
            estimate_micropaise=unit_micropaise,
            config_snapshot=snapshot,
        )

    await asyncio.gather(*(call() for _ in range(20)))

    from services.ist_window import ist_day_key

    key = f"stylesense:cost:daily:refund-user:{ist_day_key()}"
    # Exactly 10 units survive -- each of the 10 denies refunded exactly
    # once, never twice (which would under-count) and never zero times
    # (which would over-count / lock the user out below their real ceiling).
    assert limiter.counters[key] == 10_000_000  # 10 paise in micropaise


async def test_concurrent_calls_from_different_users_do_not_share_a_counter() -> None:
    gate, limiter, config_service = await _gate_with_ceiling(daily_paise=10)
    snapshot = await config_service.snapshot()
    unit_micropaise = 1_000_000

    async def call(user_id: str) -> bool:
        decision = await gate.reserve(
            user_id=user_id,
            tier="free",
            estimate_micropaise=unit_micropaise,
            config_snapshot=snapshot,
        )
        return decision.allowed

    # 5 calls each for 2 different users, all interleaved -- both users
    # should get all 5 allowed (well under either one's ceiling of 10).
    results = await asyncio.gather(
        *([call("user-a") for _ in range(5)] + [call("user-b") for _ in range(5)])
    )

    assert all(results)


async def test_concurrent_daily_and_monthly_rollback_is_consistent() -> None:
    # Daily ceiling generous, monthly ceiling tight -- most calls should be
    # denied at the monthly leg, and each such deny must roll back its own
    # daily reservation, leaving daily's final counter exactly equal to the
    # sum of what was actually ALLOWED.
    limiter = _ForcedInterleavingLimiter()
    values = {
        "ai_cost_budgets": {
            "free": {
                "daily_paise": 10_000,
                "monthly_paise": 3,
                "enforce": True,
                "fail_open": False,
            },
            "premium": {
                "daily_paise": 10_000,
                "monthly_paise": 3,
                "enforce": True,
                "fail_open": False,
            },
            "premium_annual": {
                "daily_paise": 10_000,
                "monthly_paise": 3,
                "enforce": True,
                "fail_open": False,
            },
        }
    }
    config_service = AppConfigService(_FakeConfigRepository(values))
    gate = CostBudgetGate(limiter, config_service)
    snapshot = await config_service.snapshot()
    unit_micropaise = 1_000_000  # 1 paise

    async def call() -> bool:
        decision = await gate.reserve(
            user_id="rollback-user",
            tier="free",
            estimate_micropaise=unit_micropaise,
            config_snapshot=snapshot,
        )
        return decision.allowed

    results = await asyncio.gather(*(call() for _ in range(10)))
    allowed_count = sum(1 for r in results if r)

    from services.ist_window import ist_day_key

    daily_key = f"stylesense:cost:daily:rollback-user:{ist_day_key()}"
    assert allowed_count == 3
    assert limiter.counters[daily_key] == allowed_count * unit_micropaise
