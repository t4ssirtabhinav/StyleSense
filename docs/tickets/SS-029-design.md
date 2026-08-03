# SS-029 — Cost & Capacity Ledger (Budget-Based Rate Limiting) — Design

Ticket: [`docs/tickets/raw/SS-029.md`](raw/SS-029.md) · `[Infra]` `[P0]` `[Sprint 5]` `[4 pts]` · Depends on SS-018, SS-026
Architect pass: 2026-07-29 (Opus, per the full-lane model-triage policy — the raw ticket already carries `Risk: high`)

---

## 1. Scope restatement

Today this backend limits AI spend by *counting calls* — `DailyRateLimiter` (20 bg-removals/day/user), `RateLimiter` (5/60s), `GeminiRateLimiter` (15 RPM globally) — and records cost nowhere durable: `WardrobeBgRemovalService` logs a hardcoded `COST_USD_PER_RUN = 0.0023` to stdout, and `WardrobeTaggingService` logs `latency_ms` with no cost at all. A call count is the wrong unit: a 200-item wardrobe costs ~4× a 50-item one for the same three suggestions, so counting calls systematically under-charges the heaviest users, and nothing today stops one user from consuming the whole Gemini budget (`BL-062`).

SS-029 replaces the *unit* with money and adds the durable record. Concretely: a new `ai_cost_ledger` Postgres table (one row per provider call, in exact integer sub-paise, attributed to a `request_id` so retries/failovers stay truthful), per-user daily + monthly spend counters in Upstash Redis keyed on the **IST** calendar day/month, and a `CostBudgetGate` that atomically reserves the estimated cost of a call *before* the call is made and reconciles the actual cost after. Cost is derived from a **dated** price table living in SS-026's `app_config`, so a vendor price change (Claude Sonnet 5's introductory rate expires **2026-08-31**) is a config `UPDATE`, and the ledger stores the exact rate it used so history is never retroactively rewritten. Enforcement is **fail-closed for free tier, fail-open-with-logging for paying tiers**, reusing SS-018's already-verified Upstash REST mechanism — this ticket writes no second rate limiter, it changes what is counted and how failure is handled.

Per the ticket's Technical Notes, the mechanism is extracted behind two new hexagonal ports — `IRateLimiter` and `ICostLedger` — so `BL-082`'s eventual Upstash → Cloudflare Durable Objects migration is an adapter swap. Enforcement + ledger writes are wired into the two **real, costed** AI call sites that exist today (`POST /wardrobe/tag` → Gemini, `POST /wardrobe/remove-bg` → Replicate). This is what actually resolves `BL-062`.

---

## 2. Files to create / modify

### 2.1 Create

| Path | Purpose |
|---|---|
| `supabase/migrations/011_ai_cost_ledger.sql` | `ai_cost_ledger` table + indexes + RLS + `ai_cost_breakdown` view. Forward-only, purely additive (never edit `001_initial.sql` — `BL-060`). |
| `backend/services/ist_window.py` | Single home for IST day/month key derivation + seconds-to-next-boundary. Removes the third copy of this logic. |
| `backend/services/price_table.py` | `PriceTable` — resolves a dated price row for `(provider, model, date)`, computes `cost_micropaise`, exposes the estimate used for pre-call reservation. Pure, no I/O. |
| `backend/services/cost_config_specs.py` | SS-026 `ConfigSpec`s + Pydantic models for the two new config keys (`ai_price_table`, `ai_cost_budgets`), each with a hardcoded safe default. |
| `backend/services/cost_budget_gate.py` | `CostBudgetGate` — reserve / deny / reconcile orchestration over `IRateLimiter`. Owns tier semantics and the production assertions. |
| `backend/adapters/upstash_rate_limiter.py` | `UpstashRateLimiter(IRateLimiter)` — SS-018's verified REST shape, generalised from `INCR`-by-1 to `INCRBY`/`DECRBY`-by-amount. |
| `backend/adapters/supabase_cost_ledger.py` | `SupabaseCostLedger(ICostLedger)` — `service_role` writes to `ai_cost_ledger`; never raises. |
| `backend/tests/test_ist_window.py` | IST boundary correctness (incl. the 05:30-vs-00:00 bug). |
| `backend/tests/test_price_table.py` | Dated resolution, the 2026-08-31 Sonnet cliff, unpriced/expired handling. |
| `backend/tests/test_upstash_rate_limiter.py` | REST shape, fail-open/fail-closed, TTL `NX`, refund path. |
| `backend/tests/test_cost_budget_gate.py` | The full boundary sweep: empty / at-limit / over-limit / stale-counter / tier semantics. |
| `backend/tests/test_cost_budget_gate_concurrency.py` | The racing-parallel-requests case, run with real `asyncio` concurrency. |
| `backend/tests/test_supabase_cost_ledger.py` | Row shape, never-raises contract, cache-hit rows. |

### 2.2 Modify

| Path | Change |
|---|---|
| `backend/adapters/interfaces.py` | Add `IRateLimiter`, `ICostLedger` ports + `RateLimitDecision`, `CostLedgerEntry` dataclasses. Existing ports untouched. |
| `backend/ai/ports/interfaces.py` | Add `TokenUsage` model and an **optional, defaulted** `usage: TokenUsage \| None = None` field on `VisionTaggingResult`. `IVisionProvider.tag_garment`'s signature is **not** changed (Open/Closed). |
| `backend/ai/adapters/gemini_vision_adapter.py` | Populate `usage` from the SDK response's usage metadata (see §7 Q1 — Developer must verify the field name against the installed SDK, not assume it). |
| `backend/services/wardrobe_tagging_service.py` | Accept `ICostLedger` + `CostBudgetGate`; reconcile the router's reservation; write a ledger row on every outcome (gemini success, cache hit, provider failure). |
| `backend/services/wardrobe_bg_removal_service.py` | Same, for the Replicate path. Delete the now-redundant `COST_USD_PER_RUN` stdout log (the ledger supersedes it); keep the constant only if the adapter still needs it. |
| `backend/routers/wardrobe.py` | DI providers for the new ports/gate; mint a `request_id` per request; run the budget gate **before** dispatching the background task on `/tag` and `/remove-bg`; return `429` on deny. |
| `backend/services/rate_limiter.py` | `_seconds_until_next_ist_midnight` delegates to `services/ist_window.py`. Behaviour-preserving one-liner; **no other change** to this shipped SS-018 file. |
| `backend/tests/test_db_schema.py` | Add `ai_cost_ledger` assertions alongside the existing table checks. |
| `backend/tests/test_wardrobe_tagging_service.py`, `test_wardrobe_bg_removal_service.py`, `test_wardrobe_router.py`, `test_gemini_vision_adapter.py`, `test_rate_limiter.py` | Update for the new constructor args / DI; existing assertions must keep passing unchanged. |

### 2.3 Explicitly **not** touched

- `backend/services/outfit_suggestion_service.py` — the only other AI call site, but it drives a zero-cost `MockStylingAdapter` and contains a known live landmine (`BL-096`: it raises `HTTPException` inside a `BackgroundTasks` callback, which always crashes on a real rate-limit rejection). Wiring the ledger into it means touching that broken path; `BL-096` already recommends fixing it alongside SS-020. Deliberately deferred — logged as `BL-102`.
- `backend/services/gemini_rate_limiter.py` — `BL-076`'s stale `15` constant is SS-028's job (SS-026's Status note is explicit: "move the mechanism, not the constant"). Not moved here either.
- Mobile (`mobile/**`) — nothing in this ticket's AC is user-facing beyond the `429` body copy on an existing endpoint.

### 2.4 Port placement rationale

`IRateLimiter` and `ICostLedger` go in **`backend/adapters/interfaces.py`**, not `backend/ai/ports/interfaces.py`. CLAUDE.md scopes `ai/ports/` to AI provider capabilities (`IVisionProvider`, `IStylingProvider`, …); these two are infrastructure ports one layer below AI, exactly as the ticket words it. `adapters/interfaces.py` already hosts non-AI external-system ports by documented precedent — `IWardrobeRepository` (Postgres), `IOccasionRepository` (Postgres), `IAppConfigRepository` (Postgres/`service_role`), and its own module docstring records that R2 object storage lives in the same folder because it is "the same *kind* of thing — an adapter to an external system". No new folder is invented.

---

## 3. Concrete values to use, not invent

### 3.1 Money unit — integer micropaise, exposed as `cost_paise`

**`cost_paise` cannot be a plain `INTEGER`.** From `docs/proposals/EXECUTION-PLAN.md` §2.2, a pre-filtered Gemini 2.5 Flash-Lite suggestion call costs **₹0.024 = 2.4 paise**. Rounding that to an integer paise is a 17% error on the cheapest call and rounds sub-paise calls to zero — silently under-reporting exactly the way the ticket forbids. Floats are also out: a money counter accumulated with `INCRBYFLOAT` drifts.

Therefore the canonical internal unit everywhere (Python, Redis, the ledger's source-of-truth column) is **micropaise**, an integer:

```
1 rupee = 100 paise = 100_000_000 micropaise
1 paise  = 1_000_000 micropaise
```

The ledger column `cost_paise` is kept — the AC names it literally — but as a **generated** column derived from the integer, so the money value is never stored twice independently:

```sql
cost_micropaise BIGINT      NOT NULL DEFAULT 0 CHECK (cost_micropaise >= 0),
cost_paise      NUMERIC(18,6) GENERATED ALWAYS AS (cost_micropaise::numeric / 1000000) STORED
```

`BIGINT` headroom check: the highest ceiling proposed below is ₹500/month = 5×10¹⁰ micropaise, against an `int64` max of ~9.2×10¹⁸. Note this adds a third `GENERATED ALWAYS` column to the schema — see `BL-004`'s write-safety gap. It is safe here because RLS grants no client write path to this table at all (§3.5), but the Developer must not "fix" a generated-column write error by removing the constraint.

### 3.2 Price table — dated, config-driven (`app_config` key `ai_price_table`)

Transcribed from `docs/proposals/EXECUTION-PLAN.md` §2.2 `[VERIFIED 2026-07-28 — ai.google.dev/gemini-api/docs/pricing]` and `BL-080` `[VERIFIED 2026-07-28]`. **Do not restyle these numbers.**

| Provider | Model | Mode | USD/MTok in | USD/MTok out | `effective_from` | `effective_until` |
|---|---|---|---|---|---|---|
| gemini | `gemini-2.5-flash-lite` | per_token | 0.10 | 0.40 | 2026-01-01 | — |
| gemini | `gemini-3.1-flash-lite` | per_token | 0.25 | 1.50 | 2026-01-01 | — |
| gemini | `gemini-2.5-flash` | per_token | 0.30 | 2.50 | 2026-01-01 | — |
| gemini | `gemini-3.5-flash-lite` | per_token | 0.10 | 0.40 | 2026-01-01 | — |
| anthropic | `claude-haiku-4.5` | per_token | 1.00 | 5.00 | 2026-01-01 | — |
| anthropic | `claude-sonnet-5` | per_token | **2.00** | **10.00** | 2026-01-01 | **2026-08-31** |
| anthropic | `claude-sonnet-5` | per_token | **3.00** | **15.00** | **2026-09-01** | — |
| replicate | `bria-rmbg` | per_call | — | — | 2026-01-01 | — |

- The two `claude-sonnet-5` rows are the entire point of the dated table: the introductory $2/$10 rate expires 2026-08-31 and reverts to $3/$15 (a ~50% step-up). A ledger hardcoding today's rate under-reports from 2026-09-01 onward.
- `gemini-3.5-flash-lite` is the model this repo actually calls today (`gemini_vision_adapter.py`'s `MODEL` constant). Its price is **not** in the execution plan's table — it is seeded at 2.5-Flash-Lite's rate as a **placeholder**, marked `"verified": false` in the config row, so a call against it lands as `pricing_status = 'estimated'` and logs loudly rather than silently claiming an exact figure. See §7 Q2.
- `replicate/bria-rmbg` is `per_call` at `usd_per_call = 0.0023`, transcribed from `wardrobe_bg_removal_service.py`'s existing `COST_USD_PER_RUN`. **This number is `BL-086`'s explicitly-unverified figure** — seed it with `"verified": false` for the same reason.
- **FX rate.** Vendor prices are USD; the ledger is paise. The execution plan's ₹/call column implies **₹84.0 = $1** (back-solved: ₹0.832 ÷ $0.0099 for Sonnet, ₹0.125 ÷ $0.00149 for 2.5-Flash — consistent to ~84 across all five rows) `[inference from EXECUTION-PLAN §2.2's own figures, 2026-07-28 — the rate itself is stated nowhere and is not independently verified]`. It is therefore a **dated `fx_usd_to_inr` list in the same config key**, never a bare constant, and the resolved rate is snapshotted into every ledger row. Logged as `BL-103`.

Config shape (`app_config.value`, validated by a Pydantic model in `cost_config_specs.py`):

```jsonc
{
  "fx_usd_to_inr": [ { "effective_from": "2026-01-01", "rate": 84.0, "verified": false } ],
  "prices": [
    { "provider": "gemini", "model": "gemini-3.5-flash-lite", "mode": "per_token",
      "effective_from": "2026-01-01", "usd_per_mtok_in": 0.10, "usd_per_mtok_out": 0.40,
      "default_tokens_in": 1800, "default_tokens_out": 300, "verified": false },
    { "provider": "anthropic", "model": "claude-sonnet-5", "mode": "per_token",
      "effective_from": "2026-01-01", "effective_until": "2026-08-31",
      "usd_per_mtok_in": 2.00, "usd_per_mtok_out": 10.00,
      "default_tokens_in": 800, "default_tokens_out": 500, "verified": true },
    { "provider": "anthropic", "model": "claude-sonnet-5", "mode": "per_token",
      "effective_from": "2026-09-01",
      "usd_per_mtok_in": 3.00, "usd_per_mtok_out": 15.00,
      "default_tokens_in": 800, "default_tokens_out": 500, "verified": true },
    { "provider": "replicate", "model": "bria-rmbg", "mode": "per_call",
      "effective_from": "2026-01-01", "usd_per_call": 0.0023, "verified": false }
  ]
}
```

**Resolution rule (exact, no ambiguity):** for a call at IST date `D`, select rows matching `(provider, model)` where `effective_from <= D`, and take the one with the greatest `effective_from`. Then:

- selected row has no `effective_until`, or `D <= effective_until` → `pricing_status = 'priced'`.
- selected row has `effective_until < D` **and no successor row exists** → `pricing_status = 'estimated'`, log `ledger_price_row_expired` at **ERROR**. (This is the mechanical guard that makes the Sonnet cliff impossible to miss even if nobody adds the successor row.)
- row has `verified: false` → `pricing_status = 'estimated'`.
- **no row matches at all** → `cost_micropaise = 0`, `pricing_status = 'unpriced'`, log `ledger_unpriced_call` at **ERROR**. Never silently treat an unknown model as free — `unpriced` rows are excluded from cost totals in the breakdown view so the gap is visibly loud, not silently zero.

`default_tokens_in/out` exist only to size the **pre-call reservation** (you cannot know real token counts before the call). `per_call` rows need no estimate — estimate equals actual, so reconciliation is a no-op.

### 3.3 Budgets (`app_config` key `ai_cost_budgets`) — **derived defaults, needs product sign-off**

Every SS-026 config key must carry a hardcoded safe default. These ceilings are **derived from what free users can already spend today**, not invented from nothing — but they are still a product decision, not an Architect one. See §7 Q3; logged as `BL-104`.

Derivation: `routers/wardrobe.py` already ships `_FREE_DAILY_LIMIT = 20` bg-removals/day at $0.0023 ≈ ₹0.193/run = **₹3.86/day** of Replicate spend a free user can already incur, plus unbounded tagging (`BL-062`). So a free daily ceiling of ₹5.00 is approximately *status quo made explicit*, not a new restriction.

| Tier | `daily_paise` | `monthly_paise` | `enforce` | `fail_open` |
|---|---|---|---|---|
| `free` | 500 (₹5.00) | 2500 (₹25.00) | `true` | **`false`** |
| `premium` | 5000 (₹50.00) | 50000 (₹500.00) | `true` | **`true`** |
| `premium_annual` | 5000 (₹50.00) | 50000 (₹500.00) | `true` | **`true`** |

Tier values come from `001_initial.sql`'s real enum: `plan_tier AS ENUM ('free', 'premium', 'premium_annual')`, and the column is `plan_tier DEFAULT 'free'` — **nullable**. A `NULL`, absent, or unrecognised tier normalises to **`free`** (fail-closed direction). Never treat an unknown tier as paying.

**Precise reading of the tier AC**, because the ticket's wording admits two readings and picking silently would be wrong: `enforce` and `fail_open` are *independent*. A paying user's ceiling **is** enforced when the counter is readable (the ticket's own Description calls this "the backstop against a single heavy or abusive user breaking the unit economics" — a tier with no ceiling is not a backstop). What "fail-open for paying tiers" governs is the **infra-failure** path only: Redis unreachable / env unset / REST error → paying tiers are allowed through with a logged `budget_gate_fail_open`, free tier is denied. Both paths are explicitly tested (§6).

### 3.4 Redis keys, units and IST boundaries

Mirrors `DailyRateLimiter`'s established `bg_remove:{user_id}:{ist_date}` convention — **the IST date/month is in the key, so the key rotation *is* the reset**; TTL is only garbage collection. This is what makes "resets at IST midnight, not UTC" literally true rather than approximate, and it is also why a stale counter cannot leak across a boundary (§5).

```
stylesense:cost:daily:{user_id}:{YYYY-MM-DD}      # IST calendar date
stylesense:cost:monthly:{user_id}:{YYYY-MM}       # IST calendar month
```

- Value unit: **micropaise** (integer), so `INCRBY`/`DECRBY` stay exact.
- Daily TTL: `seconds_until_next_ist_midnight()` — the existing exact-seconds helper in `rate_limiter.py`, moved to `ist_window.py`. Not a fixed 86400.
- Monthly TTL: `seconds_until_next_ist_month_start()` — new sibling. Must handle 28/29/30/31-day months and December→January rollover.
- TTL is applied with SS-018's verified idempotent pattern: `POST {url}/expire/{key}/{seconds}/NX`, called unconditionally after every `INCRBY`, never gated on "is this the first request". A failure here is logged and does **not** flip the already-computed allow/deny decision.

### 3.5 `ai_cost_ledger` schema (`supabase/migrations/011_ai_cost_ledger.sql`)

```sql
CREATE TABLE ai_cost_ledger (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  request_id      UUID NOT NULL,
  provider        TEXT NOT NULL CHECK (provider ~ '^[a-z][a-z0-9_]*$'),
  model           TEXT NOT NULL,
  feature         TEXT NOT NULL CHECK (feature ~ '^[a-z][a-z0-9_]*$'),
  tokens_in       INTEGER CHECK (tokens_in  >= 0),   -- NULL for per_call providers
  tokens_out      INTEGER CHECK (tokens_out >= 0),
  cost_micropaise BIGINT NOT NULL DEFAULT 0 CHECK (cost_micropaise >= 0),
  cost_paise      NUMERIC(18,6) GENERATED ALWAYS AS (cost_micropaise::numeric / 1000000) STORED,
  latency_ms      INTEGER CHECK (latency_ms >= 0),
  cache_hit       BOOLEAN NOT NULL DEFAULT false,
  pricing_status  TEXT NOT NULL DEFAULT 'priced'
                    CHECK (pricing_status IN ('priced','estimated','unpriced')),
  price_effective_from DATE,                          -- NULL only when unpriced
  unit_price_snapshot  JSONB NOT NULL DEFAULT '{}',   -- exact rates + fx used, frozen
  attempt         SMALLINT NOT NULL DEFAULT 1 CHECK (attempt >= 1),
  outcome         TEXT NOT NULL DEFAULT 'success'
                    CHECK (outcome IN ('success','failed','timeout','denied')),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Columns beyond the AC's verbatim list, each justified by an AC or an edge case — nothing speculative:

- `request_id` — required by the ticket's retries/failovers edge case ("bill all of them, but attribute them to one `request_id`"). This is also the hook SS-028's router writes through.
- `attempt` / `outcome` — a retried or failed-but-billed provider call must be distinguishable from a clean success; without these, "bill all of them" produces N indistinguishable rows.
- `pricing_status` / `price_effective_from` / `unit_price_snapshot` — the ticket's "the ledger records the rate it used". `unit_price_snapshot` freezes the resolved USD rates **and** the FX rate, so a later config `UPDATE` never retroactively rewrites history.

Indexes (each tied to a named query, no speculative indexing):

```sql
CREATE INDEX idx_ai_cost_ledger_user_created ON ai_cost_ledger (user_id, created_at DESC);  -- per-user breakdown
CREATE INDEX idx_ai_cost_ledger_request      ON ai_cost_ledger (request_id);                -- per-request attribution
CREATE INDEX idx_ai_cost_ledger_feature      ON ai_cost_ledger (feature, created_at DESC);  -- per-feature breakdown
```

**RLS — default-deny, `service_role` only.** Follows `010_app_config.sql`'s established shape: RLS enabled, and the *absence* of any policy is the protection.

```sql
ALTER TABLE ai_cost_ledger ENABLE ROW LEVEL SECURITY;
-- DELIBERATELY no SELECT/INSERT/UPDATE/DELETE policy for anon or authenticated.
-- service_role bypasses RLS; every other role gets a hard deny.
```

This is the second deliberate deviation from CLAUDE.md's "all user data queries MUST use authenticated Supabase client", after `SupabaseAppConfigRepository`, and it is called out rather than slipped in. Two reasons it is not merely convenient but *required*:

1. **Integrity.** This is accounting data *about* a user, not authored *by* them. Under a conventional `FOR ALL USING (auth.uid() = user_id)` policy, a user could `DELETE` their own spend rows straight from the client and erase the record the revenue gate depends on.
2. **Availability of a JWT.** The write happens in a `BackgroundTasks` callback after the response was sent, and can outlive the caller's short-lived JWT; a denied-at-the-gate call may have no usable session at all. Accounting must still be recorded.

`ON DELETE CASCADE` matches every other `users`-referencing table in `001_initial.sql`; it does mean a user deletion erases their cost history, which is the right privacy default pre-launch and is noted here rather than assumed.

**Breakdown view** (satisfies "a per-user and per-feature cost breakdown is queryable"):

```sql
CREATE VIEW ai_cost_breakdown AS
SELECT user_id,
       feature,
       provider,
       model,
       (created_at AT TIME ZONE 'Asia/Kolkata')::date AS ist_date,
       count(*)                                        AS call_count,
       count(*) FILTER (WHERE cache_hit)               AS cache_hits,
       count(*) FILTER (WHERE pricing_status = 'unpriced') AS unpriced_calls,
       sum(cost_micropaise) FILTER (WHERE pricing_status <> 'unpriced') AS cost_micropaise,
       sum(cost_paise)      FILTER (WHERE pricing_status <> 'unpriced') AS cost_paise
FROM ai_cost_ledger
GROUP BY user_id, feature, provider, model, ist_date;
```

Grouping day is **IST**, matching the counters. `unpriced_calls` is surfaced as its own column so a costing gap can never hide inside a total that looks plausible.

### 3.6 Port signatures

```python
# backend/adapters/interfaces.py  (additions only — existing ports untouched)

@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    current: int | None      # post-INCRBY counter value; None when degraded
    ceiling: int
    degraded: bool           # True = decision came from the fail-open/closed fallback, not a real counter

class IRateLimiter(ABC):
    """Amounts and ceilings are opaque non-negative integers -- micropaise for
    the budget gate, 1-per-call for a count limiter. Never widen this to fit a
    new backend; add an adapter (Open/Closed). The Durable Objects adapter
    (BL-082) implements exactly this."""

    @abstractmethod
    async def check_and_consume(
        self, *, key: str, amount: int, ceiling: int, ttl_seconds: int, fail_open: bool
    ) -> RateLimitDecision:
        """Atomically add `amount` and decide from the returned total in ONE
        round-trip. MUST NOT read-then-write. On infra failure returns
        RateLimitDecision(allowed=fail_open, current=None, degraded=True)."""

    @abstractmethod
    async def adjust(self, *, key: str, delta: int) -> None:
        """Best-effort counter correction (refund or reconcile). Never raises;
        a failure is logged and never flips an already-made decision."""


@dataclass(frozen=True)
class CostLedgerEntry:
    user_id: str
    request_id: str
    provider: str
    model: str
    feature: str
    cost_micropaise: int
    pricing_status: str            # 'priced' | 'estimated' | 'unpriced'
    unit_price_snapshot: dict[str, Any]
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int | None = None
    cache_hit: bool = False
    price_effective_from: str | None = None
    attempt: int = 1
    outcome: str = "success"       # 'success' | 'failed' | 'timeout' | 'denied'

class ICostLedger(ABC):
    @abstractmethod
    async def record(self, entry: CostLedgerEntry) -> None:
        """MUST NEVER RAISE. An accounting failure must never fail a user's
        request whose AI call already succeeded -- log and drop (see §4.3)."""

    @abstractmethod
    async def breakdown(
        self, *, user_id: str, since: date, until: date
    ) -> list[dict[str, Any]]:
        """Reads `ai_cost_breakdown`. May raise -- this is an operator/BI read
        path, not on any user request path."""
```

### 3.7 Upstash REST command shapes

SS-018 live-verified `POST {url}/incr/{key}` and `POST {url}/expire/{key}/{seconds}/NX` `[VERIFIED 2026-07-23, upstash.com/docs/redis/features/restapi]`. This ticket needs *by-amount* variants:

```
POST {url}/incrby/{key}/{amount}     # amount > 0
POST {url}/decrby/{key}/{amount}     # refund / negative reconcile — amount > 0
POST {url}/expire/{key}/{seconds}/NX # unchanged, verified
```

**`DECRBY` is used for negative deltas deliberately** — never `INCRBY` with a negative number, which would put a leading `-` in a URL path segment. `[trained-knowledge, inferred from SS-018's VERIFIED path-argument convention — NOT itself verified]`. Per CLAUDE.md's "verify, don't recite", the Developer **must** confirm `/incrby/` and `/decrby/` against Upstash's current REST docs before treating them as load-bearing, and update the module docstring with a dated `[VERIFIED …]` marker exactly as `rate_limiter.py` does. `BL-001`/`BL-039` are the precedent for what happens when this step is skipped. Error handling copies SS-018 verbatim: `raise_for_status()`, plus the defensive JSON-body `"error"` key check.

---

## 4. Control flow

### 4.1 Reserve-before, reconcile-after

This is the core of the design and the answer to the concurrency edge case.

```
ROUTER (foreground, before dispatching the BackgroundTask)
  request_id = uuid4()
  tier       = normalize(await repository.get_plan_tier(...))     # NULL/unknown -> 'free'
  estimate   = price_table.estimate(provider, model, feature)     # micropaise
  decision   = await gate.reserve(user_id, tier, feature, estimate)
  if not decision.allowed:  -> HTTP 429 (never dispatch the task)
  background_tasks.add_task(service.<op>, ..., request_id=request_id,
                            reservation_micropaise=decision.reserved)

SERVICE (background, after the provider call returns)
  actual = price_table.cost(provider, model, tokens_in, tokens_out, at=ist_today)
  await gate.reconcile(user_id, tier, reservation, actual)        # best-effort
  await ledger.record(CostLedgerEntry(...))                       # never raises
```

`gate.reserve` is the only thing that can deny, and it runs strictly before any spend — satisfying CLAUDE.md's "Rate limit checks via Upstash Redis BEFORE expensive AI calls".

### 4.2 `CostBudgetGate.reserve` — exact algorithm

```
1. if estimate <= 0:              return ALLOW(reserved=0, reason='zero_cost')
2. budgets = config.read(snapshot, COST_BUDGETS_SPEC).for_tier(tier)
3. if not budgets.enforce:        return ALLOW(reserved=0, reason='enforcement_disabled')
4. day = limiter.check_and_consume(key=daily_key,  amount=estimate,
                                   ceiling=budgets.daily_micropaise,
                                   ttl_seconds=seconds_until_next_ist_midnight(),
                                   fail_open=budgets.fail_open)
   if not day.allowed:            return DENY(scope='daily', degraded=day.degraded)
5. mon = limiter.check_and_consume(key=monthly_key, amount=estimate,
                                   ceiling=budgets.monthly_micropaise,
                                   ttl_seconds=seconds_until_next_ist_month_start(),
                                   fail_open=budgets.fail_open)
   if not mon.allowed:
       await limiter.adjust(key=daily_key, delta=-estimate)   # roll back step 4
       return DENY(scope='monthly', degraded=mon.degraded)
6. return ALLOW(reserved=estimate)
```

**Why this closes the parallel-burst race.** The decision is derived *solely* from the value `INCRBY` returns, in one atomic server-side operation. There is no `GET` followed by a conditional `INCR` anywhere — that read-then-write is exactly the shape that lets two concurrent requests both observe "99/100" and both proceed. With `INCRBY`, N concurrent requests get N distinct, strictly-increasing post-increment totals, and only those landing at or under the ceiling are allowed. (`RateLimiter`/`DailyRateLimiter`'s existing `INCR`-then-compare is already this shape; SS-029 generalises the amount, not the mechanism.)

On **deny**, `check_and_consume` refunds its own increment before returning, so a rejected call does not permanently inflate the counter and lock the user out below their real ceiling. Residual, documented rather than hidden: a process crash between the increment and its refund leaves the counter inflated — the error always lands in the *over*-counting direction (user temporarily under-served), never under-counting, and self-clears at the next IST boundary when the key rotates.

Step 5's rollback matters: a call denied by the monthly ceiling must not silently consume daily budget.

### 4.3 Ledger writes never fail a user request

Three independent guarantees, in order of strength:

1. **Structural.** Both wired call sites already run inside `BackgroundTasks`, dispatched after the HTTP response was sent. There is no user request left to fail.
2. **Defensive.** `ICostLedger.record` is contractually never-raising; `SupabaseCostLedger` wraps its write in `try/except Exception`, logs `ledger_write_failed` at ERROR (captured by Sentry, per SS-009/SS-026), and returns. An unbilled call is better than a broken feature.
3. **Decoupled.** Enforcement lives in Redis, accounting in Postgres. The counter was already incremented at reserve time, so a Postgres outage degrades *reporting* without weakening the *gate* — and a Redis outage degrades the gate (per tier) without losing the ledger row. Neither failure cascades.

No durable queue is built here. `BL-056` (in-flight `BackgroundTasks` are in-memory, no retry, no sweeper) and `BL-074` already own that gap, and `BL-074` explicitly directs: "pick up together with that row's durable-queue/sweeper work rather than building a second one-off mechanism." Followed. Noted on `BL-056`.

### 4.4 Production assertions (required by the ticket, not optional)

The ticket's Status note is explicit that this ships with production assertions, not just tests, because a limiter that lets 4 calls through instead of 3 throws no error. Structured log events (Sentry-visible), each at ERROR unless noted:

| Event | Fires when | Why it matters |
|---|---|---|
| `budget_ceiling_exceeded` | post-reconcile counter > ceiling by **any** amount | The literal "logs every time a ceiling is exceeded by even one" assertion. |
| `budget_gate_fail_open` | paying tier allowed through on a degraded decision | Otherwise an infra outage silently becomes unlimited spend. |
| `budget_gate_fail_closed` (WARNING) | free tier denied on a degraded decision | Distinguishes "over budget" from "Redis is down" in incident triage. |
| `ledger_unpriced_call` | no price row matched provider/model | The silent-under-report failure mode, made loud. |
| `ledger_price_row_expired` | selected row's `effective_until` has passed with no successor | The 2026-08-31 Sonnet cliff, mechanically. |
| `ledger_write_failed` | ledger row could not be persisted | An accounting hole that would otherwise be invisible. |
| `budget_reconcile_failed` (WARNING) | `adjust()` failed after a call | Counter now drifts from the ledger until IST rollover. |

---

## 5. Edge cases

Every edge case from the ticket, carried forward with its resolution, plus ones found in the current codebase.

### From the ticket

1. **Redis unavailable → free fails closed, paid fails open.** `UpstashRateLimiter` returns `RateLimitDecision(allowed=fail_open, current=None, degraded=True)` on unset env vars *or* a REST error — the same two triggers SS-018 established. `fail_open` comes from the tier's config row, never from a constructor default that could drift. Free-tier denial surfaces as HTTP `429` with a clear message, not a generic `500`. Both paths tested explicitly (§6), never inferred.
2. **Ledger write fails but the AI call succeeded.** §4.3 — never raises, logged, request unaffected.
3. **Concurrent requests racing the budget check.** §4.2 — single atomic `INCRBY`, decision from its return value, no read-then-write anywhere. Tested with real `asyncio` concurrency (§6.5), not sequential calls.
4. **Cache hits cost ~nothing but must still be recorded.** `WardrobeTaggingService`'s cache-hit branch (`tag_cache` hit, before any Gemini call) writes a ledger row with `cache_hit=true`, `cost_micropaise=0`, `tokens_in/out=NULL`, `outcome='success'`, and reconciles the router's reservation to **0** — refunding the full reserved amount so a cache hit consumes no budget. Without this the ledger cannot tell an efficient user from an inactive one.
5. **User crosses budget mid-multi-call request.** The gate runs **once per user request**, at the router, not once per provider call. A retry/failover inside the same `request_id` is *billed* (its own ledger row, incremented `attempt`) but **not re-gated** — so an in-flight request always completes and the next request is the one denied. Never a half-generated result.
6. **Clock/timezone on daily reset.** IST date/month is in the key itself; TTL is exact seconds to the next `Asia/Kolkata` boundary via `ist_window.py`. A UTC-based implementation would reset at 05:30 IST — asserted against directly in §6.1.
7. **Retries and failovers generate multiple provider calls for one user request.** All share the router-minted `request_id`; each gets its own row with its own `attempt` and `outcome`. Per-request cost = `SUM(cost_micropaise) GROUP BY request_id`.

### Found in the current codebase

8. **`plan_tier` is nullable.** `001_initial.sql` line 35: `plan_tier plan_tier DEFAULT 'free'` — no `NOT NULL`. A `NULL`, missing-row, or unrecognised value normalises to `free` (fail-closed). Never default an unknown tier to paying.
9. **`get_plan_tier` can itself fail.** It is an RLS-scoped Supabase read that may raise or time out. On failure → treat as `free` and log; a tier lookup failure must not become an accidental unlimited-spend path.
10. **`gemini-3.5-flash-lite` is priced nowhere.** The model this repo actually calls is absent from every source document's price table. Seeded `verified: false` → `pricing_status='estimated'` + loud log, never a confidently-wrong number. §7 Q2.
11. **`VisionTaggingResult` carries no token counts.** The adapter discards the SDK's usage metadata, so `tokens_in`/`tokens_out` are unobtainable without the additive port field in §2.2. If the field turns out not to exist on the installed SDK, the fallback is the price row's `default_tokens_*` with `pricing_status='estimated'` — never a silent zero. §7 Q1.
12. **The tagging in-flight dedupe short-circuits before any ledger write.** `WardrobeTaggingService` returns early when `mark_inflight` reports a concurrent call for the same image hash. That path must reconcile the reservation to 0 (refund) and record **no** ledger row — no provider call happened, so billing one would double-count against the request that is actually in flight.
13. **The bg-removal "already transparent" and "circuit open" short-circuits** likewise never reach Replicate. Same treatment: refund the reservation, no ledger row (`skipped_already_transparent`, `circuit_open`).
14. **Gemini `ServerError` retries happen *inside* the adapter** (`max_attempts=3`), invisible to the service. Those retries are documented in the adapter as not billed (server rejects before processing), so they produce **one** ledger row, not three. Do not attempt to bill adapter-internal retries — `attempt` tracks *service/router*-level retries, which is what SS-028 will introduce.
15. **A failed-but-billed provider call.** A Gemini call that returns `success=False` after the model already consumed input tokens (`parse_error`, `empty_or_blocked_response`) still costs money. Record a row with `outcome='failed'` and the estimated cost — do **not** refund the reservation for these, only for the never-called paths in 12/13.
16. **Two `app_config` snapshots within one request.** SS-026's own edge case ("a single request must see one consistent snapshot, not a value that changes between the router and the ledger" — its design doc names this scenario literally). The router takes **one** `AppConfigSnapshot` per request and passes it into every `price_table` / gate read for that request, including the background task. Never call `.snapshot()` twice in one request.
17. **`app_config` unreachable at first read.** `AppConfigService` degrades to coded defaults and never raises (SS-026 AC #4), so the gate falls back to §3.3's defaults rather than failing open by accident.

---

## 6. Test plan

Backend Pytest (+ `pytest-asyncio`, `httpx`), per CLAUDE.md. The five boundary-sweep dimensions the ticket makes mandatory — **empty / at-limit / over-limit / concurrent / stale-counter** — are called out by name below so QA can check them off individually.

### 6.1 `backend/tests/test_ist_window.py`

- `test_ist_day_key_uses_asia_kolkata_not_utc` — at `2026-08-31T19:00:00Z` (= 2026-09-01 00:30 IST) the day key is `2026-09-01`, not `2026-08-31`.
- `test_seconds_until_next_ist_midnight_is_exact_not_86400` — from 23:30 IST returns 1800, not 86400.
- `test_ist_midnight_boundary_is_1830_utc_not_0000_utc` — asserts the reset lands at 18:30 UTC of the prior day; the literal "resets at 05:30 IST" bug the ticket names would fail this.
- `test_seconds_until_next_ist_month_start_handles_31_30_and_february` — Jan→Feb, Feb(28)→Mar, Apr(30)→May.
- `test_ist_month_rollover_across_year_boundary` — 2026-12-31 23:59 IST → next key `2027-01`.
- `test_rate_limiter_helper_delegates_unchanged` — `rate_limiter._seconds_until_next_ist_midnight` still returns what SS-018's own tests expect (regression guard on the delegation).

### 6.2 `backend/tests/test_price_table.py`

- `test_resolves_row_with_greatest_effective_from_not_after_date` — two dated rows, date between them → earlier row wins.
- **`test_sonnet_5_price_steps_up_on_2026_09_01`** — the ticket's named case: at `2026-08-31` resolves $2/$10; at `2026-09-01` resolves $3/$15. A single-rate table would fail this.
- `test_expired_row_with_no_successor_marks_estimated_and_logs_error` — `effective_until` passed, no successor → `pricing_status='estimated'` and `ledger_price_row_expired` logged.
- `test_unknown_model_returns_unpriced_zero_and_logs_error` — asserts `cost_micropaise == 0`, `pricing_status == 'unpriced'`, `ledger_unpriced_call` at ERROR. **Explicitly asserts it is not silently treated as free-and-priced.**
- `test_per_token_cost_matches_execution_plan_figure` — 800 in / 500 out on `gemini-2.5-flash-lite` @ fx 84.0 → ₹0.024 (within rounding), i.e. reproduces the source document's own published number.
- `test_per_call_pricing_ignores_tokens` — `bria-rmbg` returns the same cost with tokens `None`.
- `test_cost_is_exact_integer_micropaise_no_float_drift` — summing 10,000 identical cheap calls equals `10_000 × unit` exactly.
- `test_fx_rate_is_dated_and_snapshotted` — resolved fx appears in `unit_price_snapshot`.
- `test_verified_false_row_marks_estimated` — the `gemini-3.5-flash-lite` / `bria-rmbg` placeholder path.

### 6.3 `backend/tests/test_upstash_rate_limiter.py`

Fake `httpx` transport, no network.

- `test_incrby_decides_from_returned_total_in_one_round_trip` — asserts exactly one `INCRBY` request and **zero `GET` requests** before the decision. This is the structural guard against reintroducing read-then-write.
- `test_expire_nx_called_unconditionally_after_every_incrby` — SS-018's idempotent-TTL contract, not gated on `count == 1`.
- `test_expire_failure_does_not_flip_the_decision` — allow/deny already computed stands.
- `test_fails_closed_when_env_unset` / `test_fails_closed_on_rest_error` — `fail_open=False` → `allowed=False`, `degraded=True`.
- `test_fails_open_when_opted_in` — `fail_open=True` → `allowed=True`, `degraded=True`.
- `test_error_key_in_json_body_is_treated_as_failure` — SS-018's defensive body check.
- `test_adjust_uses_decrby_for_negative_delta` — asserts the URL contains `/decrby/` and no `-` path segment.
- `test_adjust_never_raises_on_rest_error`.

### 6.4 `backend/tests/test_cost_budget_gate.py` — boundary sweep

| Sweep dimension | Test |
|---|---|
| **empty** | `test_first_call_of_the_day_allowed_from_zero_counter` — no key exists yet; allowed, counter equals the reservation. |
| **empty** | `test_zero_cost_call_is_allowed_without_touching_redis` — cache-hit/zero estimate makes no Redis round-trip at all. |
| **at-limit** | `test_call_landing_exactly_on_the_ceiling_is_allowed` — counter reaches exactly `daily_micropaise` → allowed (`<=`, not `<`). |
| **over-limit** | `test_call_one_micropaise_over_the_ceiling_is_denied` — the off-by-one that a call-count limiter would round away. |
| **over-limit** | `test_denied_call_refunds_its_own_increment` — after a deny, the counter is back to its pre-call value. |
| **over-limit** | `test_monthly_deny_rolls_back_the_daily_reservation` — step-5 rollback; daily counter unchanged after a monthly denial. |
| **stale-counter** | `test_counter_from_previous_ist_day_does_not_affect_today` — a key at the ceiling for `2026-08-31` does not deny a call on `2026-09-01` (different key). |
| **stale-counter** | `test_key_without_ttl_self_heals_via_expire_nx` — simulates a crash-before-EXPIRE; the next call sets the TTL. |
| **stale-counter** | `test_monthly_counter_rolls_over_at_ist_month_boundary`. |
| **concurrent** | see §6.5 (separate module). |

Tier semantics (both paths explicitly tested, never inferred — the ticket requires this):

- `test_free_tier_denied_when_redis_unavailable` — `degraded=True`, `allowed=False`, `budget_gate_fail_closed` logged.
- `test_premium_tier_allowed_when_redis_unavailable` — `allowed=True`, `degraded=True`, `budget_gate_fail_open` logged at ERROR.
- `test_premium_annual_treated_as_paying`.
- `test_null_plan_tier_normalises_to_free_and_fails_closed`.
- `test_unrecognised_plan_tier_normalises_to_free`.
- `test_plan_tier_lookup_failure_normalises_to_free`.
- `test_paying_tier_ceiling_is_still_enforced_when_redis_is_healthy` — pins §3.3's reading of the AC: fail-open governs infra failure only, not the ceiling.
- `test_ceiling_exceeded_emits_production_assertion` — `budget_ceiling_exceeded` fires when reconciliation pushes the counter past the ceiling by even 1 micropaise.
- `test_reconcile_adjusts_both_daily_and_monthly_by_the_delta`.
- `test_reconcile_to_zero_refunds_the_full_reservation` — the cache-hit path.
- `test_reconcile_failure_is_logged_and_swallowed`.
- `test_config_unreachable_falls_back_to_coded_default_budgets`.

### 6.5 `backend/tests/test_cost_budget_gate_concurrency.py` — the case most likely to be wrong

The ticket names this explicitly: *"test it explicitly with real concurrency, not sequential calls."*

- **`test_parallel_requests_cannot_burst_past_the_ceiling`** — ceiling 10 units, cost 1/call, **20 calls fired via `asyncio.gather`** against a fake Upstash whose `INCRBY` is atomic but which `await asyncio.sleep(0)`s mid-handler to force task interleaving. Asserts **exactly 10** allowed and 10 denied — not "about 10".
- **`test_gate_makes_no_read_before_write_under_concurrency`** — the fake records every command; asserts no `GET` for a counter key ever precedes a decision. This is the test that would fail if someone later "optimises" the gate into a read-then-write.
- `test_concurrent_denies_do_not_over_refund` — after 20 concurrent calls against a ceiling of 10, the final counter equals exactly 10 units, not less (each deny refunded exactly once).
- `test_concurrent_calls_from_different_users_do_not_share_a_counter` — key isolation under load.
- `test_concurrent_daily_and_monthly_rollback_is_consistent` — monthly-denied concurrent calls leave the daily counter exactly at the value implied by the allowed set.

**Honesty constraint the Developer and QA must carry into the worklog:** these prove *client-side* atomicity — that this code derives its decision from one atomic server-side operation. They do **not** prove distributed correctness across multiple backend instances, because per `BL-037` no multi-instance backend is deployed anywhere. Verify what can be verified locally; state the gap plainly rather than claiming coverage we do not have (the ticket's own Status note requires exactly this).

### 6.6 `backend/tests/test_supabase_cost_ledger.py`

- `test_record_writes_every_ac_named_column` — `user_id`, `provider`, `model`, `feature`, `tokens_in`, `tokens_out`, `cost_paise`, `latency_ms`, `cache_hit`, `created_at` all present (the AC's list, literally).
- `test_record_never_raises_on_db_error` — the never-raises contract; asserts `ledger_write_failed` logged.
- `test_cache_hit_row_has_zero_cost_and_cache_hit_true`.
- `test_unit_price_snapshot_is_frozen_on_the_row` — a later price change does not alter an existing row.
- `test_uses_service_role_client_not_caller_jwt` — pins the §3.5 deviation so it cannot be "fixed" back to an anon+JWT client by a later pass.
- `test_retries_share_one_request_id_with_incrementing_attempt`.
- `test_breakdown_groups_by_user_and_feature_on_ist_dates`.

### 6.7 Call-site integration

`backend/tests/test_wardrobe_router.py`:
- `test_tag_returns_429_when_budget_exceeded` — and asserts the background task was **never** dispatched.
- `test_tag_429_body_is_a_clear_message_not_a_generic_500`.
- `test_remove_bg_budget_gate_runs_before_dispatch`.
- `test_request_id_is_minted_once_per_request_and_passed_to_the_task`.
- `test_existing_daily_rate_limiter_429_behaviour_is_unchanged` — SS-011 regression guard.

`backend/tests/test_wardrobe_tagging_service.py`:
- `test_cache_hit_records_ledger_row_with_zero_cost_and_refunds_reservation`.
- `test_inflight_dedupe_refunds_and_records_no_row` (edge case 12).
- `test_provider_failure_records_failed_outcome_row_without_refund` (edge case 15).
- `test_ledger_failure_does_not_break_the_tagging_pipeline` — tags still written.

`backend/tests/test_wardrobe_bg_removal_service.py`:
- `test_replicate_success_records_per_call_priced_row`.
- `test_skipped_already_transparent_refunds_and_records_no_row`.
- `test_circuit_open_refunds_and_records_no_row`.

`backend/tests/test_db_schema.py`: add `ai_cost_ledger` existence, the `cost_paise` generated column, the three indexes, RLS enabled, and **zero policies for `anon`/`authenticated`**. (Note this module is `skipif`-guarded on a live `SUPABASE_DB_URL` — `BL-005` — so these will skip in CI; QA must state that plainly rather than reporting a pass.)

### 6.8 Manual / live verification QA must perform

1. Apply `011_ai_cost_ledger.sql` via `supabase db push`, then confirm `supabase db diff --linked` is empty. If it is not, **report the exact diff output — do not loosen the CI drift filter a second time** (`BL-060`'s standing directive; this migration adds a view and a generated column, both new object classes for `db diff` here).
2. Seed the two `app_config` rows and demonstrate a budget change taking effect within the cache TTL with **no redeploy and no restart** (reuses SS-026's `ss026_verify_config_live_reload.py` pattern).
3. Drive one real `POST /wardrobe/tag` end-to-end and show the resulting `ai_cost_ledger` row with a non-zero `cost_paise` and a populated `unit_price_snapshot`.
4. Confirm the verified Upstash `/incrby/` `/decrby/` command shapes (§3.7) against the live docs and record the dated `[VERIFIED …]` marker in the module docstring.

---

## 7. Open questions / blockers

These need a human decision at the design gate. This ticket is full-lane precisely so they get one.

**Q1 — Does the installed `google-genai==2.14.0` actually expose per-call token usage?** `[trained-knowledge: the Gemini API returns `usage_metadata` with `prompt_token_count` / `candidates_token_count` — NOT verified against the installed package this pass; this Architect session has no web tooling]`. `tokens_in`/`tokens_out` are AC-mandated, and cost for a `per_token` model is unobtainable without them. **Directive for the Developer:** inspect the installed SDK source/response object directly (exactly as SS-012's Developer did — see `gemini_vision_adapter.py`'s "Call shape live-verified 2026-07-25" docstring), record the real field names dated, and if usage genuinely is not exposed, fall back to the price row's `default_tokens_*` with `pricing_status='estimated'` and a logged warning. Never write a confidently-wrong token count. Not a blocker — the fallback is designed — but it must not be assumed away.

**Q2 — `gemini-3.5-flash-lite` has no published price in any source document.** It is the model this backend actually calls today, yet every price table in `docs/proposals/` covers 2.5/3.1 Flash-Lite and 2.5 Flash only. The design seeds it at 2.5-Flash-Lite's rate marked `verified: false`, so every tagging call lands as `estimated` and logs. **Needs a human to look up the real rate** and flip `verified: true`. Until then, per-tagging cost figures are indicative, not billable-accurate. Same status for `replicate/bria-rmbg`'s $0.0023, which `BL-086` records as never having been checked.

**Q3 — RESOLVED 2026-07-30 (user decision).** Approved as designed: free ₹5/day, ₹25/month; paying ₹50/day, ₹500/month. User explicitly asked these stay easily adjustable — already satisfied by the design as written (§3.3's numbers live in `app_config.ai_cost_budgets`, so a change is an `UPDATE` to that table, not a redeploy; the coded defaults in §3.3's table exist only as the fallback for `AppConfigService`'s degrade-to-safe-default path per §7 item 17, not as the operative values in normal operation).

**Q4 — Should the existing call-count limiters be retired now that budgets exist?** `DailyRateLimiter` (20 bg-removals/day, an explicit SS-011 AC), `RateLimiter` (5/60s), and `GeminiRateLimiter` (15 RPM global) will now coexist with the budget gate. This design **keeps all three untouched** — retiring a shipped AC's enforcement inside an infra ticket is scope the ticket does not authorise, and defence-in-depth on a money path is not obviously wrong. But two gates on the same endpoint means two different 429 messages and two ceilings to reason about. Logged as `BL-105`; no action needed for this ticket to proceed.

**Q5 — `ai_cost_ledger` is `service_role`-only, with no user-facing read path.** §3.5 explains why (a user must not be able to delete their own spend record). The consequence: there is no "your AI usage" screen possible without a later additive `SELECT` policy, and the cost breakdown is queryable only with DB access — no operator endpoint or dashboard is built here (no AC asks for one, and an admin cost endpoint is auth surface that deserves its own ticket). Logged as `BL-106` (Parked). Flagging in case "queryable" was intended to mean "queryable *by an operator through the app*", which would change scope.

**Q6 — The raw ticket's `BL-083` reference is wrong.** SS-029's Technical Notes cite `BL-083` for the "future Upstash → Cloudflare Durable Objects migration". `BL-083` is *pgvector adoption at first similarity-search need*; the Durable Objects row is **`BL-082`** (Parked), which itself already names SS-029's `IRateLimiter` as the thing that keeps that migration a two-week adapter swap. This design targets `BL-082`. I have no `Edit` tool in Ticket Design mode, so the raw ticket still carries the wrong ID — worth a one-character fix by whoever next touches it.

**Not blockers, but stated plainly:**

- **`BL-037` — no deployed multi-instance backend.** Distributed correctness of a revenue gate cannot be fully exercised until Railway exists. Unlike SS-011's in-process `asyncio.Semaphore` and SS-012's in-process `GeminiRateLimiter`, this gate's state lives entirely in Upstash, so it is *designed* to be correct across instances — but "designed to be" is not "observed to be", and §6.5 says exactly what the tests do and do not prove.
- **`BL-062` is resolved by this design** (see §8), but only because the gate is wired into `POST /wardrobe/tag` — the specific gap that row describes. If the Developer descopes that wiring, `BL-062` must be re-opened, not quietly left closed.
- **`BL-096`** (`outfit_suggestion_service.py` raising `HTTPException` in a background task) is live and untouched here; §2.3 explains why this ticket stays out of that file.
- **`BL-080`** is *not* resolved: SS-029's dated price table handles the 2026-08-31 Sonnet step-up in *code*, which `BL-080` already anticipated, but that row's actual subject is the stale ₹/call figures in the execution plan, consolidation proposal and business memo. Documents still need re-deriving from 2026-09-01.

---

## 8. Backlog deltas

**Resolved:**
- `BL-062` (no per-user cost cap/quota on Gemini auto-tagging) → **Resolved by SS-029 / Architect**. The design puts a per-user, per-tier budget gate in front of `POST /wardrobe/tag` (and `/remove-bg`), in paise rather than call counts, superseding the per-vendor patching approach the row describes — exactly as the raw ticket states.

**Added:**
- `BL-102` (ai, Active) — `IStylingProvider`/`OutfitSuggestionResult` carry no token usage and `outfit_suggestion_service.py` is deliberately unwired from the ledger (BL-096 landmine); SS-020/SS-028 must close it.
- `BL-103` (infra, Active) — USD→INR FX rate is a back-solved, unverified constant (~84.0) with no live source.
- `BL-104` (infra, Active) — per-tier budget ceiling values are an Architect derivation pending product sign-off.
- `BL-105` (infra, Active) — call-count limiters now coexist with the budget gate; decide which are superseded.
- `BL-106` (infra, Parked) — no operator-facing cost dashboard/endpoint; the breakdown is SQL-view-only.

**Re-scan notes appended (rows stay Active):** `BL-037` (distributed correctness of a revenue gate), `BL-056` (ledger writes join the durable-queue gap), `BL-080` (code handles the Sonnet cliff; documents still stale).

---

**Risk: high** — this design creates a DB migration with new RLS (a table deliberately unreadable and unwritable by `authenticated`, the second `service_role`-only exception in the codebase), and it *is* the free-tier revenue gate: an off-by-one or a reintroduced read-then-write lets a user spend past their ceiling and throws no error, which is precisely the silent-failure class `docs/OPERATOR_RULEBOOK.md` §C2's one-way-door scrutiny exists to catch.
