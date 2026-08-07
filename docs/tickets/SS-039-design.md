# SS-039 — Engine v2 Effort Dial (E0–E2, `app_config`-driven) — Design

## Scope restatement

This ticket wires the E0 (degraded) / E1 (economy) / E2 (standard) rows of the proposal's §6 tuning-dial table into one new `app_config` `ConfigSpec` (`engine_v2_effort_tiers`), plus a pure, independently-testable tier-resolution function that picks E0 vs E1 vs E2 per request from two existing signals — SS-028's in-process provider-outage tracking (`RoutingMixMonitor`) and SS-029's budget ledger (`CostBudgetGate`) — never SS-039's own new logic for "is a provider down" or "is the caller over budget." The resolved tier's parameters (search pool size, MMR `λ`, exploration-slot count, LLM candidate count) are the literal arguments SS-038's `engine_v2_candidate_search.search_candidates()` / `engine_v2_portfolio.select_portfolio()` already accept as keyword parameters — this ticket supplies values for those parameters per-tier, it does not add or change any scoring formula, stage, or file inside `engine_v2_*.py`'s scoring/search/portfolio logic itself. E3/E4 are out of scope by construction (not merely "unimplemented"): the tier type this ticket introduces only has three members, so nothing in the codebase can ever produce or request a fourth/fifth value, and the config schema is designed so a future ticket can add `e3`/`e4` as new optional fields without touching this ticket's `e0`/`e1`/`e2` shape. This ticket ships no HTTP route and no migration DDL — one data-only seed row (migration `018`) is the only live-project change.

## Files to create/modify

**New files (exactly as the raw ticket's Technical Notes name them):**
- `backend/services/engine_v2_effort_dial.py` — the tier-resolution function(s) and the `EffortTierKey` type. See "Concrete values" below for the exact functions/signatures the Developer must implement.
- `supabase/migrations/018_seed_engine_v2_effort_dial_config.sql` — data-only seed of the `engine_v2_effort_tiers` row, same shape as `017_seed_engine_v2_near_white_config.sql`. **Before pushing, re-confirm `018` is still free via `supabase migration list --linked`** (per `BL-110`'s standing discipline — SS-039 depends on SS-038 so the slots are naturally sequenced, but re-confirm rather than assume).
- `backend/tests/test_engine_v2_effort_dial.py` — new, covers the `ConfigSpec` defaults/malformed-row fallback and every branch of tier resolution (see Test plan).

**Modified — in the ticket's stated scope:**
- `backend/services/app_config_specs.py` — add `EffortTierParams`, `EngineV2EffortTierConfig`, `ENGINE_V2_EFFORT_TIER_SPEC` (module docstring gets one more paragraph, same pattern as the existing `NEAR_WHITE_THRESHOLD_SPEC` paragraph).

**Modified — beyond the ticket's stated file list, found necessary during this design pass (see "Open questions" #1/#2 for why); every change below is additive (a new method/field on an existing class), nothing existing is removed or behaviourally changed for any caller that doesn't invoke the new method:**
- `backend/adapters/interfaces.py` — add one new abstract method `IRateLimiter.peek(*, key: str) -> int | None` (non-mutating GET; advisory-only, never used for an allow/deny decision).
- `backend/adapters/upstash_rate_limiter.py` — implement `UpstashRateLimiter.peek()` via Upstash's `GET {url}/get/{key}` REST call.
- `backend/services/cost_budget_gate.py` — add `BudgetStatus` (frozen dataclass) and `CostBudgetGate.budget_status(...)` (read-only; calls `peek()` twice, never `check_and_consume`/`reserve`).
- `backend/services/routing_mix_monitor.py` — add `RoutingMixMonitor.provider_is_down(provider: str) -> bool` (reads the same `_first_failure_at` state that already drives the existing Sentry outage alert — no new tracking state, just a public read of what's already tracked).
- `backend/tests/test_cost_budget_gate.py` — `_FakeAtomicLimiter` gains a trivial in-memory `peek()` (required once `IRateLimiter` grows the new abstract method, or the fake stops satisfying the ABC).
- `backend/tests/test_cost_budget_gate_concurrency.py` — `_ForcedInterleavingLimiter` gains the same trivial `peek()`.
- `backend/tests/test_routing_mix_monitor.py` — new test(s) for `provider_is_down()`.

No `routers/`, no other `services/engine_v2*.py` file, no mobile file. This ticket ships no consumer of `EffortTierKey`/`resolve_effort_tier*` — per SS-038's own precedent (`build_default_engine_v2()`'s "guidance for SS-020's Architect pass" comment), wiring a real caller is SS-020's job, not this ticket's.

## Concrete values to use, not invent

### 1. `app_config_specs.py` — `ENGINE_V2_EFFORT_TIER_SPEC`

Transcribed **verbatim** from the raw ticket's own E0–E2 table (do not alter without product sign-off, per the ticket's own instruction) and mapped onto the exact keyword parameters `engine_v2_candidate_search.search_candidates()` / `engine_v2_portfolio.select_portfolio()` already accept:

```python
class EffortTierParams(BaseModel):
    search_pool_size: int          # -> search_candidates(top_k_bases=...)
    colour_mode: str                # documentation-only today -- see Open Q #3, NOT wired to any stage call
    mmr_lambda: float               # -> select_portfolio(lambda_=...)
    max_exploration: int            # -> select_portfolio(max_exploration=...)
    llm_candidate_count: int | None # -> max_suggestions on IStylingProvider.suggest_outfits; None = no LLM call (E0)


class EngineV2EffortTierConfig(BaseModel):
    e0: EffortTierParams = EffortTierParams(
        search_pool_size=500, colour_mode="star", mmr_lambda=0.9,
        max_exploration=0, llm_candidate_count=None,
    )
    e1: EffortTierParams = EffortTierParams(
        search_pool_size=1500, colour_mode="pairwise", mmr_lambda=0.85,
        max_exploration=0, llm_candidate_count=5,
    )
    e2: EffortTierParams = EffortTierParams(
        search_pool_size=5000, colour_mode="pairwise_plus_volume", mmr_lambda=0.75,
        max_exploration=1, llm_candidate_count=6,
    )
    # Additive-only forward compat for a future E3/E4 ticket (AC #5's "design
    # note showing the planned shape"): that ticket adds
    #   e3: EffortTierParams | None = None
    #   e4: EffortTierParams | None = None
    # here -- Pydantic optional-field-with-default means every row already
    # seeded (this ticket's `018` included) still validates unchanged; no
    # migration, no `AppConfigService.read()` change, no existing consumer
    # breaks. `EffortTierKey` (below) only widens to include "E3"/"E4" once
    # that future ticket also adds the code path that can return them.


ENGINE_V2_EFFORT_TIER_SPEC: ConfigSpec[EngineV2EffortTierConfig] = ConfigSpec(
    key="engine_v2_effort_tiers",
    model=EngineV2EffortTierConfig,
    default=EngineV2EffortTierConfig(),
)
```

`max_exploration` values (0/0/1) are a literal transcription of the ticket table's "Diversity" column: only E2's cell states "+ 1 explore"; E0/E1's cells state only a `λ` value with no explore suffix, read here as `max_exploration=0` for both (not SS-038's coded default of `2` — the dial narrows exploration at low tiers, only E2 reopens one exploration slot). `mmr_lambda`/`max_exploration` are the two dial fields SS-038's own `styling_rules_defaults.py` comment explicitly flagged as "named exactly this way so SS-039's Architect pass can find them by name" (`DEFAULT_MMR_LAMBDA`, `DEFAULT_MAX_EXPLORATION`) — this spec supersedes those two coded defaults per-tier; it does not touch the constants themselves (a missing/malformed config row still falls back to `EngineV2EffortTierConfig()`'s Pydantic defaults above, which are separately hardcoded to match the ticket table, not to `styling_rules_defaults.py`'s pre-dial constants — see Edge Cases for why that's the correct posture here, unlike `NEAR_WHITE_THRESHOLD_SPEC`'s "identical to today" posture).

`score_floor` (`DEFAULT_SCORE_FLOOR=0.5`) and `portfolio_size_range` (`DEFAULT_PORTFOLIO_SIZE_RANGE=(5,8)`) are **not** part of this ticket's dial — the raw ticket's table has no column for either, and Technical Notes lists only "search pool size, colour mode, MMR λ/exploration-slot count, LLM candidate count" as in scope. Both stay at SS-038's coded defaults for all three tiers, unchanged by this ticket.

### 2. `engine_v2_effort_dial.py` — the resolution function(s)

Three independently-testable units (satisfies AC #3's "each branch independently tested" literally) plus one thin async orchestrator for a real future caller:

```python
EffortTierKey = Literal["E0", "E1", "E2"]  # only 3 members -- E3/E4 structurally unreachable, AC #4

_KNOWN_PROVIDERS: tuple[str, ...] = ("gemini", "claude")  # SS-028's DEFAULT_ROUTING_TABLE.failover keys
BUDGET_NEAR_CEILING_RATIO = 0.9  # Architect-assigned, unvalidated -- same flag class as RULE_WEIGHTS


def both_providers_down(
    monitor: RoutingMixMonitor, providers: tuple[str, ...] = _KNOWN_PROVIDERS,
) -> bool:
    """Pure (no I/O) -- reads RoutingMixMonitor's already-tracked in-process
    failure-streak state via the new provider_is_down() method."""
    return all(monitor.provider_is_down(p) for p in providers)


async def is_budget_near_ceiling(
    gate: CostBudgetGate, *, user_id: str, tier: str | None,
    config_snapshot: AppConfigSnapshot, near_ceiling_ratio: float = BUDGET_NEAR_CEILING_RATIO,
) -> bool:
    """The only I/O boundary in this module -- calls the new read-only
    CostBudgetGate.budget_status() (never reserve())."""
    status = await gate.budget_status(
        user_id=user_id, tier=tier, config_snapshot=config_snapshot,
    )
    return status.near_ceiling  # near_ceiling_ratio threaded through budget_status(), not recomputed here


def resolve_effort_tier(*, providers_down: bool, budget_near_ceiling: bool) -> EffortTierKey:
    """Pure, 3-branch, no I/O -- the literal AC #3 decision table. Order
    matters: providers_down is checked FIRST and unconditionally wins
    (edge case: both signals bad -> E0, not E1)."""
    if providers_down:
        return "E0"
    if budget_near_ceiling:
        return "E1"
    return "E2"


async def resolve_effort_tier_for_request(
    *, monitor: RoutingMixMonitor, gate: CostBudgetGate, user_id: str, tier: str | None,
    config_snapshot: AppConfigSnapshot, app_config: AppConfigService,
) -> tuple[EffortTierKey, EffortTierParams]:
    """Glue for a real future caller (SS-020) -- composes the three pure/
    I/O units above, then looks up that tier's EffortTierParams from
    ENGINE_V2_EFFORT_TIER_SPEC. Not itself unit-tested in isolation beyond
    a thin integration smoke test -- the branches it composes are already
    independently proven."""
    providers_down = both_providers_down(monitor)
    budget_near_ceiling = await is_budget_near_ceiling(
        gate, user_id=user_id, tier=tier, config_snapshot=config_snapshot,
    )
    tier_key = resolve_effort_tier(providers_down=providers_down, budget_near_ceiling=budget_near_ceiling)
    tier_config = app_config.read(config_snapshot, ENGINE_V2_EFFORT_TIER_SPEC)
    params = {"E0": tier_config.e0, "E1": tier_config.e1, "E2": tier_config.e2}[tier_key]
    return tier_key, params
```

### 3. `RoutingMixMonitor.provider_is_down()` (new method on the existing SS-028 class)

```python
def provider_is_down(self, provider: str, *, now: float | None = None) -> bool:
    """True iff `provider`'s current failure streak (tracked by record(),
    cleared on any success) has lasted >= self._provider_outage_alert_seconds
    -- reuses the EXACT same state/threshold that already drives the
    existing Sentry 'ai_routing_provider_outage' alert (design SS-028 §7),
    so "down" here is literally what an operator is already paged for, not
    a new definition invented for this ticket."""
    first_failure_at = self._first_failure_at.get(provider)
    if first_failure_at is None:
        return False
    current_time = now if now is not None else self._clock()
    return (current_time - first_failure_at) >= self._provider_outage_alert_seconds
```

A freshly-constructed `RoutingMixMonitor()` (no calls to `record()` yet, e.g. right after a process restart) has an empty `_first_failure_at`, so `provider_is_down()` returns `False` for every provider — a cold-started process never spuriously resolves to E0. This is deliberate and matches `outfit_suggestions.py`'s own stated precedent: "unknown context routes cheap, never 'to be safe' expensive."

### 4. `CostBudgetGate.budget_status()` / `IRateLimiter.peek()` (new, read-only)

```python
# adapters/interfaces.py, added to IRateLimiter (ABC)
@abstractmethod
async def peek(self, *, key: str) -> int | None:
    """Advisory-only, NON-mutating read of a counter's current value (None
    on a missing key or any infra failure -- never raises). NEVER used for
    an allow/deny decision: check_and_consume's atomic INCRBY remains the
    ONLY enforcement path in this codebase. This method exists solely so a
    caller can ask "roughly how close is this user to their ceiling right
    now" without perturbing the ceiling itself."""
    raise NotImplementedError
```

```python
# adapters/upstash_rate_limiter.py, added to UpstashRateLimiter
async def peek(self, *, key: str) -> int | None:
    """GET {url}/get/{key} -- the one GET this class makes, deliberately
    kept out of check_and_consume's atomic-INCRBY path (that method's own
    docstring's "no GET anywhere in this class" invariant is about the
    enforcement path specifically; this is a separate, clearly-labelled
    advisory method). Missing env vars, HTTP error, non-integer body, or a
    key that doesn't exist yet (Upstash returns {"result": null}) all
    degrade to None -- caller treats None as "unknown," never as 0."""
```

```python
# services/cost_budget_gate.py
@dataclass(frozen=True)
class BudgetStatus:
    near_ceiling: bool
    daily_ratio: float | None    # None if unenforced for this tier, or peek() failed
    monthly_ratio: float | None

class CostBudgetGate:
    ...
    async def budget_status(
        self, *, user_id: str, tier: str | None, config_snapshot: AppConfigSnapshot,
        near_ceiling_ratio: float = 0.9,
    ) -> BudgetStatus:
        """Read-only -- two peek() calls, never check_and_consume/reserve.
        A tier with enforce=False (today: none; the schema allows it)
        always reports near_ceiling=False, matching reserve()'s own
        unenforced-tier short-circuit. A peek() failure (None) is excluded
        from the near-ceiling computation, not treated as 0 or as
        over-ceiling -- an advisory signal degrading safely toward the
        richer tier (E2), since the REAL enforcement decision still happens
        later, atomically, at the actual reserve() call this ticket never
        makes."""
```

`near_ceiling_ratio=0.9` is an Architect-assigned constant (unvalidated product input, same class as `RULE_WEIGHTS`/`_hue_distance_score`'s thresholds) — tunable later without a schema change since it's a Python default parameter, not (yet) itself an `app_config` field; not promoted to config in this ticket since the raw ticket's Technical Notes don't ask for it and one more knob was not requested.

## Edge cases

Carried forward from the raw ticket, plus new ones found during this design pass:

1. **Config row present but only partially valid (e.g. `e1` malformed, `e0`/`e2` fine)** — falls back to the coded default for the **whole** `EngineV2EffortTierConfig`, not a per-tier partial merge, matching `AppConfigService.read()`'s existing all-or-nothing behaviour (same posture as `GEMINI_QUOTA_CEILING_SPEC`/`NEAR_WHITE_THRESHOLD_SPEC`) — no new code needed, this is inherent to how `ConfigSpec`/`AppConfigService.read()` already validates.
2. **Provider-health and budget signals disagree (providers healthy, budget exhausted)** — `resolve_effort_tier()` checks `providers_down` first and unconditionally; budget only matters when providers are healthy. Healthy-but-unaffordable → **E1**, not E0, per the ticket's own framing. Both bad → **E0** (providers_down wins outright), also per the ticket's framing ("nothing works").
3. **E2 resolves but the wardrobe is too small to fill a 5,000-item search pool** — `top_k_bases=5000` passed straight to `search_candidates()`; that function already handles a `bases` list shorter than `top_k_bases` honestly (`ranked_bases[:top_k_bases]` is simply the whole list when it's shorter — no padding, no error). No new handling needed.
4. **Rapid tier flapping** (provider health oscillating near the 900s outage-alert boundary within one session) — out of scope for this ticket per the raw ticket's own instruction; `provider_is_down()`'s threshold is a hard boundary with no hysteresis, and `resolve_effort_tier_for_request()` recomputes fresh on every call rather than caching a tier across a session. Noted, not built.
5. **A future E3/E4 ticket reads this config row shape** — see "Concrete values" #1's `e3`/`e4: EffortTierParams | None = None` forward-compat note; additive, no breaking change.
6. **`search_pool_size` (`top_k_bases`) is a no-op at every one of this ticket's three values, given SS-038's shipped code** — see Open Questions #4. Flagged here because it means edge case 3 above ("pool ceiling, not requirement") is true for a reason unrelated to this ticket's tuning: `top_k_bases` never actually constrains anything once it's ≥ 50, at any of E0/E1/E2's magnitudes (500/1500/5000 are all ≥ 50).
7. **`budget_status()`'s `peek()` calls both fail (Upstash unreachable)** — both ratios come back `None`, `near_ceiling=False`, so the effort dial degrades toward **E2** (the richer tier), not E1 or E0. This is deliberately asymmetric with `CostBudgetGate.reserve()`'s own per-tier `fail_open` semantics (SS-029): the REAL spend decision still happens later at the actual `reserve()` call, which has its own tier-appropriate fail-open/closed behaviour untouched by this ticket. A stale/failed advisory peek here can at worst cause the pipeline to generate E2-richness candidates that `reserve()` then still correctly gates at the real spend point — never a double-spend, never a bypassed budget.
8. **A user with `tier="premium"`/`"premium_annual"` and `enforce=True`, `fail_open=True` (today's live `AI_COST_BUDGETS_SPEC` seed)** — `budget_status()` still computes real ratios for these tiers (advisory `peek()` doesn't consult `fail_open` at all, only `enforce`), so a paying user genuinely near their own ceiling still resolves to E1, not always E2 — "paying tier" in the raw ticket's Description ("E2 ... paying tier, and free tier when budget allows") is read as "paying tier's *default*, absent budget pressure," not "paying tier always gets E2 unconditionally regardless of spend."
9. **`RoutingMixMonitor` is in-process only (SS-028's own documented limitation, compounds `BL-037`)** — with no deployed backend yet, this is expected and not a new gap; once a multi-instance deploy exists, each worker's `provider_is_down()` view is partial, same caveat SS-028/SS-029 already carry for their own in-process state. Not re-logged as a new backlog row (already covered by `BL-037`'s reaffirmed note trail).

## Test plan

**`backend/tests/test_engine_v2_effort_dial.py` (new):**
- `test_config_spec_defaults_match_ticket_table` — `EngineV2EffortTierConfig()`'s `e0`/`e1`/`e2` fields equal the raw ticket's literal table values (500/1500/5000 pool, 0.9/0.85/0.75 λ, 0/0/1 exploration, None/5/6 LLM candidates).
- `test_malformed_row_falls_back_to_full_default_not_partial_merge` — an `app_config` fake repo returning `{"engine_v2_effort_tiers": {"e0": {...valid...}, "e1": "not-an-object"}}` still yields `AppConfigService.read()`'s *entire* coded default (all three tiers), not a partial merge (edge case 1).
- `test_resolve_effort_tier_providers_down_wins_over_budget` — `resolve_effort_tier(providers_down=True, budget_near_ceiling=True)` → `"E0"` (edge case 2, both-bad branch).
- `test_resolve_effort_tier_providers_down_alone` — `resolve_effort_tier(providers_down=True, budget_near_ceiling=False)` → `"E0"`.
- `test_resolve_effort_tier_budget_near_ceiling_alone` — `resolve_effort_tier(providers_down=False, budget_near_ceiling=True)` → `"E1"`.
- `test_resolve_effort_tier_healthy_and_affordable` — `resolve_effort_tier(providers_down=False, budget_near_ceiling=False)` → `"E2"`.
- `test_both_providers_down_true_only_when_both_streaks_exceed_threshold` — a fake/real `RoutingMixMonitor` with only `gemini` past the outage threshold → `both_providers_down()` is `False`; both past → `True`.
- `test_both_providers_down_false_on_fresh_monitor` — a freshly-constructed `RoutingMixMonitor()` (no `record()` calls yet) → `both_providers_down()` is `False` (edge case: cold start never spuriously degrades).
- `test_is_budget_near_ceiling_true_at_or_above_ratio` — a fake `CostBudgetGate.budget_status()` returning `near_ceiling=True` → `is_budget_near_ceiling()` returns `True` (thin pass-through, still exercised).
- `test_resolve_effort_tier_for_request_e0_short_circuits_before_budget_read` — with a fake `CostBudgetGate` that raises/asserts-not-called if `budget_status()` is invoked, and `providers_down=True`, confirm the orchestrator still returns `("E0", ...)` **without** calling `budget_status()` at all (proves the short-circuit is real, not just a lucky branch order).
- `test_e3_e4_are_structurally_unreachable` — `typing.get_args(EffortTierKey) == ("E0", "E1", "E2")`; `resolve_effort_tier`'s only two `bool` inputs cannot produce anything else — a `mypy`-level proof, asserted at runtime via `get_args` so CI catches an accidental future widening without also updating this test (AC #4).

**`backend/tests/test_engine_v2_integration.py` (extend existing suite) or a new dedicated section in `test_engine_v2_effort_dial.py`:**
- `test_portfolio_diversity_and_size_differ_between_e0_and_e2` — run the SAME wardrobe fixture (reuse this file's existing fixture repos) through `EngineV2.generate_portfolio()` twice, once with `lambda_=0.9, max_exploration=0` (E0's values) and once with `lambda_=0.75, max_exploration=1` (E2's values), passed through to `select_portfolio()`. Assert: (a) the E2 run's portfolio has exactly one more member than the E0 run's (the exploration slot — `max_exploration` 0 vs 1 is a real, observable count difference), and (b) mean pairwise Jaccard similarity among the E0 portfolio's `item_ids` is ≥ the E2 portfolio's (E0's higher λ favours raw score over diversity, so its portfolio is measurably less diverse) — this is the AC #3 integration proof, and it is satisfied via `mmr_lambda`/`max_exploration`, **not** `search_pool_size` (see Open Questions #4 for why `top_k_bases` alone cannot produce an observable difference at these magnitudes — do not write a test asserting `top_k_bases` changes candidate count or composition, it will not, and is not a bug to "fix" under this ticket's scope).

**`backend/tests/test_routing_mix_monitor.py` (extend existing suite):**
- `test_provider_is_down_false_before_threshold` — one failure recorded, clock advanced less than `provider_outage_alert_seconds` → `False`.
- `test_provider_is_down_true_at_threshold` — clock advanced to exactly/past `provider_outage_alert_seconds` since first failure → `True`.
- `test_provider_is_down_clears_on_success` — a failure streak past threshold, then one `record(..., outcome="success")` → `provider_is_down()` immediately `False` again (mirrors `_check_outage`'s existing clear-on-success behaviour).

**`backend/tests/test_cost_budget_gate.py` (extend existing suite):**
- `test_budget_status_near_ceiling_true_above_ratio` — `_FakeAtomicLimiter` seeded so `peek()` returns a daily counter ≥ 90% of the tier's `daily_micropaise` ceiling → `near_ceiling=True`.
- `test_budget_status_near_ceiling_false_below_ratio` — counter well under ceiling → `near_ceiling=False`.
- `test_budget_status_unenforced_tier_never_near_ceiling` — a tier config with `enforce=False` → `near_ceiling=False` regardless of counter value, no `peek()` call made (mirrors `reserve()`'s own short-circuit).
- `test_budget_status_peek_failure_degrades_to_none_not_zero` — `_FakeAtomicLimiter.peek()` returns `None` (simulated infra failure) → `daily_ratio`/`monthly_ratio` are `None`, `near_ceiling=False` (edge case 7 — never treated as 0 or as over-ceiling).
- `test_budget_status_never_calls_check_and_consume_or_adjust` — assert `_FakeAtomicLimiter.check_calls`/`adjust_calls` are empty after a `budget_status()` call (proves this is genuinely read-only, the ticket's own explicit "not reserve()" instruction).

**Migration test:**
- Manual verification step (no automated test, matching `017`'s own precedent): after `supabase db push`, `SELECT value FROM app_config WHERE key = 'engine_v2_effort_tiers'` returns the exact seeded JSON; `supabase db diff --linked` is empty (AC #7).

## Open questions / blockers

None of the below block the Developer from building against this design as written — each has a concrete, buildable resolution already chosen above. Flagged here per CLAUDE.md's "say so explicitly, don't silently pick" instruction, since each is a real gap between what the raw ticket's prose assumes exists and what SS-028/SS-029/SS-038's shipped code actually expose.

1. **SS-029's `CostBudgetGate` has no pre-existing read-only status method.** The raw ticket's Technical Notes say "calling into ... SS-029's `CostBudgetGate` read-only status (not `reserve()`)" as if such a method already existed — it doesn't; `CostBudgetGate` only has `reserve()` (mutating) and `reconcile()`. This design adds a genuinely new, clearly-scoped `budget_status()` read path (via a new non-mutating `IRateLimiter.peek()`), rather than either (a) misusing `reserve()` for a probe (would double-count spend against the real call this ticket never makes) or (b) inventing a parallel budget-tracking mechanism inside `engine_v2_effort_dial.py` (would duplicate SS-029's logic, which the ticket explicitly forbids). This is why the file list above extends beyond the ticket's stated two new files. `UpstashRateLimiter`'s own docstring states "there is no GET anywhere in this class" as a structural property of its **enforcement** path (`check_and_consume`) — `peek()` is a deliberately separate, advisory-only method that does not touch that invariant; flagged prominently in both files' docstrings so a future reader never repurposes `peek()` for an allow/deny decision.
2. **SS-028 has no pre-existing standalone "is this provider down right now" query.** `StylingRouter` only discovers a provider is unhealthy mid-request (a live call fails), and `RoutingMixMonitor` already tracks the needed state (`_first_failure_at`) for its own Sentry outage alert but exposed no public read of it. This design adds `provider_is_down()` as a thin public accessor over that *already-tracked* state — not a new detection mechanism, not a new alert, not new I/O.
3. **`colour_mode` has no real toggle in SS-038's shipped code.** `engine_v2_colour.py`'s star-topology function was deleted and replaced entirely by `pairwise_colour_harmony` (SS-038, resolving `BL-128`'s star-topology half) — there is no live "star" mode left to select, and `engine_v2_attribute_scoring.score_assembled_candidate()` always computes `volume_balance`/`register_coherence` for every candidate regardless of tier (they're two of ten always-active `ENGINE_V2_RULE_WEIGHTS` terms, not a toggle). This design keeps `colour_mode` as a **documented, inert metadata field** — transcribed per the ticket's table so the config shape matches the proposal's intent and a future ticket can wire it for real — but the tier-resolution function's output is never passed into any stage-③ call to select a colour algorithm, because no such parameter exists to receive it. Building that toggle would mean writing new scoring logic inside `engine_v2_colour.py`/`engine_v2_attribute_scoring.py`, which the raw ticket's own Source note explicitly rules out ("does not itself build any scoring logic"). **Logged as `BL-135`** (see Backlog deltas) for a future ticket to decide whether real per-tier colour-mode differentiation is worth building, once SS-038's own "100% LIVE-INERT" `volume_balance`/`register_coherence` gap (its module docstring's own admission, pending the taxonomy migration) is resolved anyway — building a colour-mode toggle before that lands would be tuning a signal that currently never fires on real data.
4. **`search_pool_size` (`top_k_bases`) is a no-op at every value this ticket's table specifies.** Traced through `engine_v2_candidate_search.search_candidates()`: `ranked_bases` is sorted over the **full**, uncapped `bases` list before `top_k_bases` ever truncates it, and `bases_to_expand = kept_bases[:_TOP_BASES_TO_EXPAND]` where `_TOP_BASES_TO_EXPAND=50` is a private module constant SS-038 explicitly did not expose as a function parameter ("not independently tunable via `styling_rules_defaults`"). Since `kept_bases[:50] == ranked_bases[:50]` whenever `top_k_bases >= 50` — true for all three of this ticket's values (500/1500/5000) — passing a different `search_pool_size` into `top_k_bases` produces **byte-identical** output at every tier, today. This design still wires `search_pool_size` straight into `top_k_bases` (satisfies AC #3's literal "the exact parameters SS-038's stage② ... functions accept," and is forward-compatible if a future SS-038 change ever makes `_TOP_BASES_TO_EXPAND` itself tunable or lowers below 50), but the Test plan above deliberately does **not** claim an observable difference from this parameter alone — the AC #3 integration proof is satisfied via `mmr_lambda`/`max_exploration` instead, which do produce a real, measurable difference. Not something for the Developer to "fix" — SS-038's `_TOP_BASES_TO_EXPAND` is out of this ticket's scope to change (that's scoring/search logic, again ruled out by the Source note). **Logged as `BL-136`** for whoever next revisits SS-038's search-breadth tuning.
5. **`RoutingMixMonitor` remains in-process-only** (SS-028's own documented limitation) — this ticket's E0 signal inherits that limitation exactly as-is. Not a new gap; already covered by `BL-037`'s reaffirmed note trail across SS-011/012/026/028/029/035. No new backlog row for this.

## Backlog deltas (for the orchestrator to apply — Architect cannot edit `docs/BACKLOG.md` directly)

Scanned `docs/BACKLOG.md`'s Active table for `ai`/`infra`/`test` rows before writing this design, per the once-per-ticket resurfacing scan. Confirmed clean scope for the effort dial specifically (no existing row named it) but two rows are directly relevant context, reaffirmed rather than duplicated:
- **`BL-037`** (infra, "no backend deployment exists") — does not block this ticket (ships no HTTP route); reaffirms its existing note trail re: in-process signals (`RoutingMixMonitor`, now also this ticket's `provider_is_down()` reader) needing a distributed rework at first multi-instance deploy. Not modified, not re-logged as new.
- **`BL-082`** (infra, "Upstash → Durable Objects for rate limiting") — this ticket adds one new `IRateLimiter` method (`peek()`). Since `BL-082`'s own note calls out that "`IRateLimiter` port is what keeps this a two-week adapter swap," the future Durable Objects adapter will need to implement `peek()` too, alongside `check_and_consume`/`adjust`. Not modified (still Active, unresolved, unaffected in substance — just one more method the eventual swap must cover); no new row needed for this, noting it here is sufficient.

New rows to append (next IDs per the file's own reservation notice: **starts at `BL-135`**):

| ID | Title | Tag | Source (ticket / phase) | Description | Logged |
|----|-------|-----|--------------------------|--------------|--------|
| BL-135 | `colour_mode` effort-tier field is documented metadata only — no real per-tier colour-scoring toggle exists in SS-038's shipped code | ai | SS-039 / Architect | SS-038 replaced the old star-topology colour scoring entirely with `pairwise_colour_harmony` (no toggle), and always computes `volume_balance`/`register_coherence` for every candidate as fixed `ENGINE_V2_RULE_WEIGHTS` terms, not a switchable mode. SS-039's `EngineV2EffortTierConfig.colour_mode` field transcribes the raw ticket's table values ("star"/"pairwise"/"pairwise_plus_volume") for forward-compat and documentation, but nothing reads it to select a scoring path. A future ticket should decide whether real per-tier colour-mode differentiation is worth building — probably after SS-038's own "100% LIVE-INERT" `volume_balance`/`register_coherence` gap (blocked on the taxonomy migration, `BL-132`) is resolved, since building a toggle for a signal that doesn't fire on real data yet is premature. | 2026-08-07 |
| BL-136 | `search_pool_size`/`top_k_bases` is a no-op in `engine_v2_candidate_search.search_candidates()` at every value ≥ 50 (all three of SS-039's E0/E1/E2 values) | ai | SS-039 / Architect | `ranked_bases` is sorted over the full, uncapped base-pair list before `top_k_bases` truncates it, and only the true top 50 (`_TOP_BASES_TO_EXPAND`, a private SS-038 constant not exposed as a function parameter) are ever expanded into real candidates — so `kept_bases[:50] == ranked_bases[:50]` regardless of where `top_k_bases` sits above 50. SS-039 still wires its `search_pool_size` field straight into `top_k_bases` (correct/harmless, forward-compatible, and literally satisfies AC #3's "the exact parameter the function accepts"), but it produces no observable difference between tiers today. Whoever next revisits SS-038's search-breadth tuning (or decides `_TOP_BASES_TO_EXPAND` itself should become tunable/config-driven) should read this row first rather than re-discovering the same trace. | 2026-08-07 |

## Risk: low

Fast lane. This ticket touches no auth, no payments, no RLS, no secrets, and ships no HTTP route or external-facing surface — its only live-project change is one data-only `INSERT` (migration `018`, same shape as `017`, no DDL). The additive `IRateLimiter.peek()`/`CostBudgetGate.budget_status()`/`RoutingMixMonitor.provider_is_down()` extensions found necessary during this design pass are all new, opt-in methods on already-shipped classes — no existing method's behaviour, signature, or call site changes, so nothing already relying on `check_and_consume`/`reserve`/`adjust`/the existing outage-alert path is affected. The one genuinely irreversible-feeling piece — a new `app_config` row read by a not-yet-wired consumer — is itself inert until a future ticket (SS-020) actually calls `resolve_effort_tier_for_request()`, so a mistake here has no live blast radius today. Confirmed not revised from the raw ticket's own `Risk: low` header.
