"""SS-039 -- Engine v2 effort dial: tier-resolution function(s) that pick
E0 (degraded) / E1 (economy) / E2 (standard) per request from two existing
signals -- SS-028's ``RoutingMixMonitor`` (in-process provider-outage
tracking) and SS-029's ``CostBudgetGate`` (budget ledger) -- never this
module's own new logic for "is a provider down" or "is the caller over
budget". Each branch is independently, pure-function testable (see
``docs/tickets/SS-039-design.md``'s "Concrete values" #2 and Test plan).

E3/E4 are structurally unreachable: ``EffortTierKey`` below only has three
members, and ``resolve_effort_tier``'s only two ``bool`` inputs cannot
produce a fourth/fifth value (AC #4).

No live consumer wires ``resolve_effort_tier_for_request`` into
``engine_v2.py``/``engine_v2_candidate_search.py``/``engine_v2_portfolio.py``
yet -- per SS-038's own precedent, wiring a real caller is SS-020's job.
"""

from __future__ import annotations

from typing import Literal

from services.app_config import AppConfigService, AppConfigSnapshot
from services.app_config_specs import ENGINE_V2_EFFORT_TIER_SPEC, EffortTierParams
from services.cost_budget_gate import CostBudgetGate
from services.routing_mix_monitor import RoutingMixMonitor

EffortTierKey = Literal["E0", "E1", "E2"]  # only 3 members -- E3/E4 structurally unreachable, AC #4

# SS-028's DEFAULT_ROUTING_TABLE.failover keys -- the two providers this
# ticket's "both providers down" signal considers.
_KNOWN_PROVIDERS: tuple[str, ...] = ("gemini", "claude")

# Architect-assigned, unvalidated -- same flag class as RULE_WEIGHTS
# (folds into BL-077). Tunable later without a schema change since it's a
# Python default parameter, not (yet) itself an app_config field.
BUDGET_NEAR_CEILING_RATIO = 0.9


def both_providers_down(
    monitor: RoutingMixMonitor, providers: tuple[str, ...] = _KNOWN_PROVIDERS
) -> bool:
    """Pure (no I/O) -- reads ``RoutingMixMonitor``'s already-tracked
    in-process failure-streak state via ``provider_is_down()``."""
    return all(monitor.provider_is_down(p) for p in providers)


async def is_budget_near_ceiling(
    gate: CostBudgetGate,
    *,
    user_id: str,
    tier: str | None,
    config_snapshot: AppConfigSnapshot,
    near_ceiling_ratio: float = BUDGET_NEAR_CEILING_RATIO,
) -> bool:
    """The only I/O boundary in this module -- calls the new read-only
    ``CostBudgetGate.budget_status()`` (never ``reserve()``)."""
    status = await gate.budget_status(
        user_id=user_id,
        tier=tier,
        config_snapshot=config_snapshot,
        near_ceiling_ratio=near_ceiling_ratio,
    )
    return status.near_ceiling


def resolve_effort_tier(*, providers_down: bool, budget_near_ceiling: bool) -> EffortTierKey:
    """Pure, 3-branch, no I/O -- the literal AC #3 decision table. Order
    matters: ``providers_down`` is checked FIRST and unconditionally wins
    (edge case: both signals bad -> E0, not E1)."""
    if providers_down:
        return "E0"
    if budget_near_ceiling:
        return "E1"
    return "E2"


async def resolve_effort_tier_for_request(
    *,
    monitor: RoutingMixMonitor,
    gate: CostBudgetGate,
    user_id: str,
    tier: str | None,
    config_snapshot: AppConfigSnapshot,
    app_config: AppConfigService,
) -> tuple[EffortTierKey, EffortTierParams]:
    """Glue for a real future caller (SS-020) -- composes the three pure/
    I/O units above, then looks up that tier's ``EffortTierParams`` from
    ``ENGINE_V2_EFFORT_TIER_SPEC``. Not itself unit-tested in isolation
    beyond a thin integration smoke test -- the branches it composes are
    already independently proven.

    ``providers_down`` short-circuits BEFORE any budget read -- when both
    providers are down, ``gate.budget_status()`` (and its two ``peek()``
    calls) is never invoked."""
    providers_down = both_providers_down(monitor)
    if providers_down:
        tier_key: EffortTierKey = "E0"
    else:
        budget_near_ceiling = await is_budget_near_ceiling(
            gate, user_id=user_id, tier=tier, config_snapshot=config_snapshot
        )
        tier_key = resolve_effort_tier(
            providers_down=providers_down, budget_near_ceiling=budget_near_ceiling
        )

    tier_config = app_config.read(config_snapshot, ENGINE_V2_EFFORT_TIER_SPEC)
    params = {"E0": tier_config.e0, "E1": tier_config.e1, "E2": tier_config.e2}[tier_key]
    return tier_key, params
