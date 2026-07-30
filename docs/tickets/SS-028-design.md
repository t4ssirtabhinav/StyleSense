# SS-028 — Multi-Provider AI Router & Gemini Styling Adapters — Design

Ticket: [`docs/tickets/raw/SS-028.md`](raw/SS-028.md) · `[Feature]` `[P0]` `[Sprint 5]` `[5 pts]` · Depends on: SS-006, SS-026
Architect pass: 2026-07-29 (Opus, full lane — `Risk: high`)
Wave 1 of the Epic 3 re-sequencing ([`docs/proposals/EXECUTION-PLAN.md`](../proposals/EXECUTION-PLAN.md) §5), parallel with SS-027 and SS-029.

---

## 1. Scope restatement

Today `IStylingProvider` (SS-006) has exactly one implementation — `MockStylingAdapter`, a rule-based stub with no network calls — and `routers/outfit_suggestions.py` hardwires it. This ticket adds two *real* implementations (`GeminiStylingAdapter`, `ClaudeStylingAdapter`, each parameterised by model ID rather than hardcoding one) and, in front of them, a `StylingRouter` that is *itself* an `IStylingProvider`: callers keep depending on the same port while the router decides, per request, which provider and model actually serves it. That decision reads three inputs — task complexity (occasion/first-suggestion), user tier, and live provider capacity/health — from the `app_config` routing table SS-026 shipped, so changing the routing mix is an `UPDATE app_config` and not a redeploy. When the chosen provider fails, is quota-exhausted or returns unparseable output, the router retries once, then fails over to the other vendor, then degrades to an injected deterministic fallback (`MockStylingAdapter` today; SS-027's pre-filter candidates once SS-020 assembles them) — so the user always gets an answer, never a hard error. Every attempt emits one structured, dashboard-able log line carrying `user_id`/`provider`/`model`/`tokens_used`/`latency_ms`/`routing_reason`, and an in-process monitor raises a Sentry warning when the expensive-model share drifts or a provider has been failing over for an extended period — the production assertion the ticket's own Status note makes part of "done". `IStylingProvider` is **not modified**: every new input the router needs arrives by constructor injection, exactly as SS-012 did for `GeminiVisionAdapter`.

---

## 2. Non-negotiable constraints (read before writing any code)

1. **`backend/ai/ports/interfaces.py` is not edited by this ticket.** Not the `IStylingProvider` ABC, not `StylePreferencesInput`, not `OutfitSuggestionItem`, not `OutfitSuggestionResult`. If a design pressure seems to require it, the answer is constructor injection or a *new, non-port* method on the concrete adapter — both are used below. A diff touching that file fails QA.
   - `OutfitSuggestionResult.source` is already `Literal["mock", "gemini", "claude"]`. That is why this design uses **`"claude"`, not `"anthropic"`, as the provider key everywhere** — code, config JSON, log fields and seed rows — so no mapping layer and no port edit is ever needed.
2. **Zero pricing constants in code.** The ₹/call figures in the raw ticket are documentation for the human deciding the routing table; they are *not* to be transcribed into Python. Claude Sonnet 5's introductory pricing expires **2026-08-31** (`BL-080`), and the dated price table is SS-029's job. This ticket's `cost_class` field is a routing *label* (`everyday` / `high_stakes`), not a price.
3. **Ship on the conservative default.** Gemini everyday, Claude for `wedding_guest` / ceremony+festival occasions / first-ever suggestion / Atelier tier. Do **not** default anything to Flash-Lite; that promotion is a post-eval config `UPDATE` (`BL-077`).
4. **Unknown context routes cheap, not expensive.** If the caller supplies no tier/occasion (true for every caller until SS-020 lands), the router takes the `default` everyday route. Defaulting to the high-stakes model "to be safe" is precisely the silent 3× cost drift this ticket exists to prevent.
5. **No third-party call shape asserted from memory.** §9 lists exactly what the Developer must live-verify against the installed package source before writing the adapter bodies, and what must not be guessed.

---

## 3. Files to create / modify

### 3.1 Create — `backend/ai/adapters/`

| Path | Contents |
|---|---|
| `backend/ai/adapters/styling_call.py` | Shared, port-free support types: `StylingCallMetrics` dataclass (`provider`, `model`, `tokens_in`, `tokens_out`, `latency_ms`, `attempt`) and the provider error hierarchy — `ProviderCallError` (base) → `ProviderTransientError`, `ProviderQuotaExhaustedError`, `ProviderPermanentError`, `ProviderParseError`, `ProviderTimeoutError`. Also `MeteredStylingProvider` (a `typing.Protocol`, **not** an ABC and **not** in `ports/`) declaring `suggest_outfits_with_metrics(...) -> tuple[OutfitSuggestionResult, StylingCallMetrics]`. |
| `backend/ai/adapters/styling_prompt.py` | `build_styling_prompt(preferences, *, max_suggestions) -> str` — **one** prompt template shared by both real adapters, plus the `StylingPromptBuilder` callable type alias the adapters accept for injection. See §8.3 for the SS-027 hand-off. |
| `backend/ai/adapters/gemini_styling_adapter.py` | `GeminiStylingAdapter(IStylingProvider)` — model ID is a constructor arg, no module-level model constant is baked into behaviour. |
| `backend/ai/adapters/claude_styling_adapter.py` | `ClaudeStylingAdapter(IStylingProvider)` — same shape, `anthropic` SDK. |
| `backend/ai/adapters/styling_provider_registry.py` | `StylingProviderRegistry.get(provider: str, model: str) -> MeteredStylingProvider` — lazily constructs and caches one adapter instance per `(provider, model)` pair over a shared, lazily-constructed SDK client. This is what makes "any model the config names" work without a redeploy. |

### 3.2 Create — `backend/services/`

| Path | Contents |
|---|---|
| `backend/services/ai_routing_specs.py` | The three `ConfigSpec`s + their Pydantic models (§4). Follows SS-026 design §10's explicit guidance that a domain ticket adds its own specs module rather than growing `app_config_specs.py`. |
| `backend/services/provider_quota.py` | `ProviderQuotaTracker` — per-provider sliding-window RPM **and** TPM, non-blocking `try_reserve()`, ceilings from config (§5). |
| `backend/services/styling_router.py` | `RoutingContext`, `RoutingDecision`, the pure `resolve_route()` function, and `StylingRouter(IStylingProvider)` (§6). |
| `backend/services/routing_mix_monitor.py` | `RoutingMixMonitor` — rolling routing-mix + provider-outage detector that emits the production assertions (§7). |

### 3.3 Create — other

| Path | Contents |
|---|---|
| `supabase/migrations/011_seed_ai_routing_config.sql` | Seeds the three `app_config` rows with values **byte-identical to the coded defaults**, and `UPDATE`s `gemini_quota_ceiling_rpm`'s now-stale "NOT YET CONSUMED" description. Insert-only; no DDL. |
| `backend/scripts/ss028_verify_routing_live_reload.py` | Live proof of AC #2 (routing changes with no redeploy) against the real `app_config` table — direct mirror of `backend/scripts/ss026_verify_config_live_reload.py`, which is this repo's established way to demonstrate a "no redeploy" AC that no unit test can honestly claim. |

### 3.4 Modify (three files, all small and additive)

| Path | Change | Why it is in scope |
|---|---|---|
| `backend/routers/outfit_suggestions.py` | Replace `get_styling_provider()`'s body so it builds a `StylingRouter` per request via new `Depends()` helpers (`get_app_config_snapshot`, `get_provider_quota_tracker`, `get_routing_mix_monitor`, `get_styling_provider_registry`, `get_routing_context`). **Do not touch `get_current_user_id_stub`** (`BL-052`) and **do not change** the `202`/`BackgroundTasks` contract. | Without this the router is dead code; the ticket's own framing ("the first real proof the ports architecture pays for itself") is the port swap actually happening at the composition root. |
| `backend/services/gemini_rate_limiter.py` | Add a `max_requests` property + `set_max_requests(int)` setter (clamped to ≥ 1), and correct the stale "15 RPM free-tier limit" docstring. **Keep the constructor default at `15`** — `test_app_config_service.py::test_gemini_quota_ceiling_default_matches_gemini_rate_limiter_hardcoded_default` reads that default off the signature and must keep passing. | This is the literal subject of `BL-076`: move the ceiling from a code constant to a config-consumed value. |
| `backend/routers/wardrobe.py` | Make `get_gemini_rate_limiter()` `async`, read one `AppConfigSnapshot`, apply `GEMINI_QUOTA_CEILING_SPEC`'s value via `set_max_requests()`, return the existing module-scope singleton unchanged. Zero I/O still happens at import. | Completes `BL-076`. Nothing else in that file changes. |

### 3.5 Explicitly out of scope

- `backend/ai/ports/interfaces.py` (constraint §2.1).
- SS-027's `styling_rules` / pre-filter modules and SS-029's ledger/price-table modules — separate worktrees, no file overlap by design. This design consumes both only through injected seams (§8).
- `BL-096`'s `HTTPException`-inside-a-background-task bug in `outfit_suggestion_service.py` (that row's own recommendation is to fix it with SS-020) and `BL-052`'s auth stub. Both are reaffirmed, not fixed. **`outfit_suggestion_service.py` is not modified by this ticket at all** — that keeps SS-029 (which will add ledger writes there) collision-free.
- Any mobile file. This is a backend-only ticket.

---

## 4. Config contract — concrete values to use, not invent

Three keys, three `ConfigSpec`s, three coded defaults, all in `backend/services/ai_routing_specs.py`. Per SS-026's substrate: a **missing** key logs INFO and serves the coded default; a **malformed** key logs ERROR and serves the coded default; one bad row never affects the other two. That is exactly the raw ticket's "config routing table is malformed → coded default routing" edge case, and it is inherited, not re-implemented.

### 4.1 `ai_styling_routing_table` (`scope = 'server'`)

```json
{
  "version": 1,
  "default": {"provider": "gemini", "model": "<EVERYDAY_MODEL_ID>",   "cost_class": "everyday",    "reason": "default_everyday"},
  "rules": [
    {"when": {"tier": ["atelier"]},                          "route": {"provider": "claude", "model": "<HIGH_STAKES_MODEL_ID>", "cost_class": "high_stakes", "reason": "tier_atelier"}},
    {"when": {"is_first_suggestion": true},                  "route": {"provider": "claude", "model": "<HIGH_STAKES_MODEL_ID>", "cost_class": "high_stakes", "reason": "first_ever_suggestion"}},
    {"when": {"occasion": ["wedding_guest"]},                "route": {"provider": "claude", "model": "<HIGH_STAKES_MODEL_ID>", "cost_class": "high_stakes", "reason": "high_stakes_occasion"}},
    {"when": {"occasion_kind": ["ceremony", "festival"]},    "route": {"provider": "claude", "model": "<HIGH_STAKES_MODEL_ID>", "cost_class": "high_stakes", "reason": "high_stakes_occasion_kind"}}
  ],
  "failover": {"gemini": ["claude"], "claude": ["gemini"]}
}
```

Fixed elsewhere, transcribe verbatim — do not restyle:

- `tier` values are **`free` | `premium` | `atelier`**, transcribed from `supabase/migrations/007_occasions_registry.sql:50-51`'s `tier_gate` CHECK.
- `occasion_kind` values are the nine from `007_occasions_registry.sql:42-44`: `everyday`, `ceremony`, `festival`, `travel`, `sport`, `professional`, `social`, `milestone`, `religious`. `wedding_guest` and `formal_event` are `ceremony`; `festival` is `festival`; **`puja` is `religious` and is deliberately NOT in the initial high-stakes set — that is a judgment call, not an omission; see B6.**
- `occasion` values are registry slugs (`007_occasions_registry.sql:122-134`), not an enum. `wedding_guest` is the seeded key; `wedding` is an *alias* (line 143) — the router matches on the **normalised** key it is handed, it does not normalise anything itself.
- Provider keys are `gemini` / `claude` (constraint §2.1).

Matching semantics, to be implemented exactly:
- Rules are evaluated **in array order; first match wins**; if none match, `default` is used.
- Inside one `when`, **every** stated field must match (AND). A list field matches by membership; `is_first_suggestion` matches by equality. An absent field is a wildcard.
- An unknown field inside `when` makes that **one rule** inert (skipped, logged once at WARNING) — it must never invalidate the whole table.
- `reason` is required on every route and is what lands in the `routing_reason` log field. Never synthesise a reason string in code.
- `version` is informational for now (logged with each decision so a bad table can be traced to a config edit); the Developer must not branch on it.

`<EVERYDAY_MODEL_ID>` = `gemini-2.5-flash-lite`; `<HIGH_STAKES_MODEL_ID>` = an unresolved Claude/Anthropic model ID string — see resolved Blocker B1 in §12 for both the values and the remaining Developer verification step. The everyday-tier in-provider fallback (`gemini-3.1-flash-lite`, also from B1) is a retry-hop detail inside the Gemini adapter's call logic, not a slot in this routing table's JSON — it never appears as a `model` value here.

### 4.2 `ai_provider_quota` (`scope = 'server'`)

```json
{
  "gemini": {"rpm": 15, "tpm": 500000},
  "claude": {"rpm": 50, "tpm": 30000}
}
```

- Gemini's `rpm: 15` / `tpm: 500000` are the values already recorded in this repo (`services/gemini_rate_limiter.py`'s docstring, `app_config_specs.py`, and migration `010`'s seed) — **conservative and stale-by-admission**; `BL-076`'s own text says the real paid-tier numbers were never checked. Keeping 15 here means SS-028 cannot *regress* throughput relative to today, and raising it is a one-row `UPDATE`.
- Claude's numbers are **`[UNVERIFIED — trained-knowledge shaped guess]`** and are seeded conservatively on purpose: a too-low ceiling costs throughput and triggers failover (recoverable); a too-high ceiling means we discover the real limit as provider 429s under load. See `BL-098`.
- An unknown provider key in this object is ignored; a provider absent from it is treated as **unlimited** (no local gate) — the provider's own 429 then drives failover. Document that in the module docstring so it is a decision, not an accident.
- The `description` column of this row must state, in words, that Gemini's ceiling here is a **share of the same account-wide pool** the tagging path also spends (`BL-099`).

### 4.3 `ai_router_policy` (`scope = 'server'`)

```json
{
  "attempt_timeout_seconds": 6.0,
  "total_deadline_seconds": 12.0,
  "parse_retry_attempts": 1,
  "expensive_share_alert_threshold": 0.30,
  "alert_min_sample": 20,
  "alert_cooldown_seconds": 3600,
  "provider_outage_alert_seconds": 900
}
```

All are clamped in code the way SS-026 clamps its TTL (a shape-valid but degenerate number must never disable the feature): `attempt_timeout_seconds` → `[1.0, 60.0]`, `total_deadline_seconds` → `[attempt_timeout_seconds, 120.0]`, `parse_retry_attempts` → `[0, 2]`, `expensive_share_alert_threshold` → `[0.0, 1.0]`, `alert_min_sample` → `[1, 10000]`, `alert_cooldown_seconds` → `[60, 86400]`, `provider_outage_alert_seconds` → `[60, 86400]`.

`total_deadline_seconds: 12.0` is **larger than SS-020's "cold call under 4s" AC**. That is a deliberate, flagged conflict, not an oversight — see Blocker B2 and `BL-100`.

### 4.4 Snapshot discipline

Per `services/app_config.py`'s own forward-compat note, written for this ticket: **one `AppConfigSnapshot` per request**, obtained by a dedicated `Depends()`, then passed into every `read()`. The router must never call `app_config_service.snapshot()` itself more than once per request, and must never call it per attempt — a failover must not be able to observe a *different* routing table than the initial decision did.

---

## 5. Provider quota tracking (`ProviderQuotaTracker`)

Mechanism, not policy — modelled on `services/gemini_rate_limiter.py`'s sliding window, with three deliberate differences:

| | `GeminiRateLimiter` (SS-012, tagging) | `ProviderQuotaTracker` (this ticket, styling) |
|---|---|---|
| On exhaustion | **blocks/queues** until a slot frees | **returns `False` immediately** |
| Dimensions | RPM only | RPM **and** TPM |
| Ceiling source | constructor constant | `ai_provider_quota` config, per provider |

`try_reserve(provider, *, estimated_tokens) -> bool` is non-blocking **because the raw ticket says so**: *"quota exhausted mid-request-burst → route new requests to the alternate provider; do not queue behind an exhausted pool."* A blocking acquire here would silently convert a capacity problem into a latency problem and break the deadline in §4.3.

- `estimated_tokens` is the router's pre-call estimate (prompt characters ÷ 4, floored at a documented minimum, plus a configured output allowance). It is an estimate and must be labelled as one in the docstring; `record_usage(provider, tokens_in, tokens_out)` reconciles the window with the real count after the call returns. Over-estimating is the safe direction.
- The window is per `(provider, dimension)`. It carries **no `user_id`** — this is an account-wide capacity gate, exactly like `GeminiRateLimiter`'s "global, since RPM is a per-API-key limit, not a per-user one".
- **This is not a substitute for the per-user rate limit.** `OutfitSuggestionService` already runs SS-018's Upstash `RateLimiter` before the provider is touched, satisfying CLAUDE.md's "rate limit checks via Upstash Redis BEFORE expensive AI calls". The tracker is a *second, orthogonal* gate on vendor capacity. Say this in the module docstring so QA does not read it as a duplicated limiter.
- **In-process only.** Same known limitation as `GeminiRateLimiter`, `CircuitBreaker`, `TagCache` and SS-011's semaphore; with >1 worker each process holds a partial view and the account ceiling can be exceeded. Reaffirms `BL-037`; do not claim distributed correctness.
- Clock is injectable (`clock: Callable[[], float] | None`), mirroring `GeminiRateLimiter`, so every window test is deterministic and none sleep.

---

## 6. The router (`StylingRouter`)

### 6.1 Shape

```
StylingRouter(IStylingProvider)
  __init__(*, registry, routing_table, policy, quota, monitor, fallback, context, snapshot_stale, clock=None)
  async suggest_outfits(preferences, *, max_suggestions=5) -> OutfitSuggestionResult          # the port method
  async suggest_outfits_with_decision(preferences, *, max_suggestions=5)
        -> tuple[OutfitSuggestionResult, RoutingDecision]                                      # richer, non-port
```

- `suggest_outfits` delegates to `suggest_outfits_with_decision` and discards the decision. The port signature is therefore satisfied byte-for-byte, and richer callers (SS-020, SS-029) use the second method. **This "add a method, never widen the port" move is the same one used for `MeteredStylingProvider` in §3.1, and is the design's answer to every "but the port doesn't carry X" pressure.**
- `RoutingContext` is a frozen dataclass constructed **per request**, carrying `request_id: str` (uuid4 when the caller has none), `user_id: str`, `tier: str = "free"`, `occasion: str | None = None`, `occasion_kind: str | None = None`, `is_first_suggestion: bool = False`. Constructor injection of per-request context is exactly the precedent `GeminiVisionAdapter` set in SS-012 (`occasion_normalizer`/`registry_jwt`) specifically to avoid changing a port signature.
- The router does **no I/O of its own** other than the injected adapters: it does not read `occasions`, does not normalise slugs, does not fetch config. Whoever builds the context supplies already-resolved values. This keeps `resolve_route()` a pure function and the whole routing table exhaustively unit-testable with no fakes.
- `resolve_route(table, context) -> RoutingDecision` is a module-level pure function (`provider`, `model`, `cost_class`, `reason`, `table_version`, `matched_rule_index | None`).

### 6.2 The attempt ladder (implement exactly this order)

For a decision `D = resolve_route(...)`, with `chain = [D.provider] + table.failover.get(D.provider, [])`:

1. **Deadline check.** If elapsed + `attempt_timeout_seconds` would exceed `total_deadline_seconds`, stop and degrade (step 6). Checked before *every* attempt, never only at the start.
2. **Quota check.** `quota.try_reserve(provider, estimated_tokens=...)`. `False` → record `routing_reason` suffix `:quota_exhausted`, move to the next provider in `chain` (never queue).
3. **Call**, wrapped in `asyncio.wait_for(..., timeout=attempt_timeout_seconds)` at the call site — *not* trusting any SDK-internal timeout. This repo already learned that lesson: see `gemini_vision_adapter.py`'s module docstring on `HttpOptions.timeout` being unreliable.
4. **Classify the outcome**:
   - success → `record_usage`, log, return.
   - `ProviderParseError` (malformed/unparseable JSON) → **retry once on the same provider** (`parse_retry_attempts`, default 1), then treat as failed and move to the next provider. The raw ticket pins this ladder: *"retry once on the same provider, then fail over, then degrade. Never surface a parse error to the user."*
   - `ProviderTransientError` (5xx/network) → next provider immediately (no same-provider retry; the failover *is* the retry, and a second call on a sick provider spends the deadline).
   - `ProviderQuotaExhaustedError` (a provider-side 429 our local ceiling did not predict) → mark the provider quota-exhausted locally for the remainder of the request, next provider.
   - `ProviderPermanentError` (4xx: bad model ID, auth) → next provider, and log at ERROR — a permanently-broken model ID in config is a config bug someone must see.
   - `ProviderTimeoutError` → next provider.
5. Repeat 1–4 for each provider in `chain`, each provider used **at most once** (plus its one parse-retry).
6. **Degrade.** Call the injected `fallback: IStylingProvider` (default `MockStylingAdapter()`), log with `routing_reason="degraded_all_providers_failed"` and `degraded=True`, notify the monitor, and return its result. `suggest_outfits` **never raises** — that is the router's contract even though individual adapters do raise, and it is what upgrades SS-020's *"graceful fallback … never a hard error to the user"* AC from rule-based degradation to a real answer from the other vendor.
7. If the fallback itself raises (it should not — `MockStylingAdapter` is pure), catch, log at ERROR, and return an empty-but-valid `OutfitSuggestionResult(user_id=context.user_id, suggestions=[], generated_at=<now ISO8601 UTC>, is_personalized=False, source="mock")`. A failing degrade path must still not raise into a `BackgroundTasks` callback (that class of crash is live in Sentry today — `BL-096`).

### 6.3 The log line (AC #5 + AC #6)

One `logger.info("ai_styling_call", extra={...})` per **attempt** (so failovers are individually visible, which is what `BL-099`/SS-029 need), with:

`request_id`, `user_id`, `provider`, `model`, `cost_class`, `routing_reason`, `table_version`, `attempt`, `outcome` (`success|parse_error|transient|quota|permanent|timeout`), `tokens_in`, `tokens_out`, `tokens_used` (= in + out, because CLAUDE.md names `tokens_used` specifically), `latency_ms`, `degraded`, `config_stale` (from `AppConfigSnapshot.stale`).

Event name is fixed at `ai_styling_call` — it is the dashboard/grep key, so it must not be reformatted later. None of these keys collide with `logging`'s reserved `LogRecord` attributes; do not add `module`, `name`, `args`, `message` or `filename` to `extra`.

### 6.4 Adapter contract

Each real adapter:
- takes `model: str` as a **required constructor argument** (AC #1: "use Flash-Lite vs use Sonnet is a config value, not a class"), plus injectable `client`, `timeout_seconds`, `prompt_builder`;
- constructs its SDK client lazily via `os.environ[...]` inside a `_get_client()` (mirrors `GeminiVisionAdapter._get_client`), so importing the module never requires credentials and CI's dummy env stays sufficient;
- requests structured JSON and validates it into `list[OutfitSuggestionItem]`, raising `ProviderParseError` on any `JSONDecodeError`/`ValidationError`;
- sets `source="gemini"` / `source="claude"` and `generated_at` as ISO8601 UTC (`datetime.now(UTC).isoformat()`, matching `MockStylingAdapter`);
- honours the port's degrade rule: **effectively-empty preferences must not raise** — return `is_personalized=False` generic suggestions. Reuse `MockStylingAdapter`'s `_is_effectively_empty` predicate by importing it (do not re-implement the six-field check a third time; if it needs to be shared, promote it to `styling_call.py` and have `mock_styling_adapter.py` import it — that is the one acceptable edit to that file);
- returns `user_id=""` in the result exactly as `MockStylingAdapter` does; `OutfitSuggestionService` already stamps the real `user_id` via `model_copy`. Do not duplicate that responsibility.
- enforces `max_suggestions` in code by slicing, never only in the prompt.

---

## 7. Production assertions (part of "done", not a follow-on)

`RoutingMixMonitor`, in-process, fed one `record(decision, outcome)` per attempt:

1. **Expensive-drift detector.** Rolling window of the last `alert_min_sample`+ decisions; when `high_stakes / total > expensive_share_alert_threshold`, emit `sentry_sdk.capture_message("ai_routing_expensive_share_exceeded", level="warning")` with the mix breakdown, then suppress for `alert_cooldown_seconds`. This is the ticket's "silent drift to an expensive model is caught within a day, not on a bill."
2. **Persistent-outage detector.** Per provider, track the timestamp of the last success and of the first failure in the current failure streak; when a provider has been failing continuously for `provider_outage_alert_seconds`, emit a Sentry warning once per cooldown. This is the raw ticket's *"failover masks a persistent outage — if provider A has been failing for hours, that must alert, not silently cost 3× on provider B forever."*
3. **Every alert also emits a plain `logger.warning`**, so the signal survives Sentry being unconfigured.

Sentry hygiene: `sentry_sdk` calls must be no-ops under test. `backend/tests/conftest.py` already blanks `SENTRY_DSN_BACKEND` at collection time (added by SS-026's DevOps pass after real pytest runs leaked into the live project — `PYTHON-FASTAPI-1`/`-2`); tests for the monitor must assert on an **injected notifier callable**, not by capturing real Sentry traffic. Give `RoutingMixMonitor` a `notify: Callable[[str, dict], None] | None` constructor arg defaulting to the Sentry+logger implementation.

**Honest limitation to state in the docstring and the worklog:** this is in-process. With >1 worker each process sees a fraction of traffic, so the share is directionally right but not exact, and there is no deployed multi-worker backend to verify against yet (`BL-037`). The durable, queryable version of this signal is SS-029's ledger; these two are complementary, and SS-028 must not depend on SS-029 to satisfy AC #6.

---

## 8. Seams to the parallel Wave-1 tickets (no file overlap, by construction)

SS-027 and SS-029 are being built in separate worktrees and do not exist on this branch. Every interaction is therefore an **injected seam with a working default**, never an import.

1. **Degrade → SS-027 (`fallback`).** `StylingRouter(fallback=...)` takes an `IStylingProvider`, defaulting to `MockStylingAdapter()`. SS-020 will inject an adapter wrapping SS-027's deterministic candidates. The raw ticket's *"the pre-filter is the last line of defence, and it always works"* is satisfied structurally: the fallback is typed as the port, so it can be swapped without touching the router.
2. **Cost → SS-029 (`StylingCallMetrics` + `request_id`).** The router emits per-attempt metrics carrying `request_id`, so SS-029 can *"bill all of them, but attribute them to one `request_id`"* (its own edge case). SS-028 writes no ledger and holds no price table. Optionally accept an injected `on_call: Callable[[StylingCallMetrics, RoutingDecision], None]` sink defaulting to `None`; do not build a ledger behind it.
3. **Prompt → SS-027 (`prompt_builder`).** SS-027's ticket makes it non-negotiable that colour/formality/occasion rules live in **one** module consumed by both the scorer and the prompt template. SS-028 cannot import that module (it does not exist here), so it ships `styling_prompt.py` as the single copy for now and accepts a `prompt_builder` injection point. **At SS-020 assembly, `styling_prompt.py`'s rule content must be replaced by SS-027's module, not duplicated alongside it** — logged as `BL-101` so this cannot be forgotten between two branches that never see each other.

---

## 9. Verification obligations before code is written

Per CLAUDE.md's "verify, don't recite" and `docs/OPERATOR_RULEBOOK.md` §E. This Architect pass has **no Bash and no web access**, so the items below are labelled honestly and handed to the Developer rather than guessed into the design.

### 9.1 Model IDs — `[UNVERIFIED]`, and genuinely uncertain

The raw ticket's cost table names *"Gemini 2.5 Flash"* and *"Claude Sonnet 5"* as prose, not as API model ID strings. This repo's own live-verified vision model is **`gemini-3.5-flash-lite`** (`[VERIFIED 2026-07-25]` in `gemini_vision_adapter.py`, after `gemini-1.5-flash` was found *dead*, not merely stale) — i.e. the account is on a model generation *newer* than the ticket's table describes. Do not assume `gemini-2.5-flash` exists or is the intended everyday model, and do not silently substitute a neighbour.

Developer must: list available models via the installed SDKs' real APIs (verified against the installed package source, as SS-012's Developer did), record the exact strings + date in the worklog, and use them for both the coded constant and the seed migration. If the intended everyday/high-stakes model is unavailable, **escalate — do not substitute** (a substitution silently changes both the cost and the quality assumptions this ticket's whole "conservative default" argument rests on). See Blocker B1.

### 9.2 SDK call shapes

- **Gemini**: reuse `gemini_vision_adapter.py`'s call shape — `client.aio.models.generate_content(model=..., contents=[...], config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=<pydantic class>))`, `response.text` may be `None`, `errors.ClientError` (4xx, `.code`) vs `errors.ServerError` (5xx). That is `[VERIFIED 2026-07-25 in this repo]` against `google-genai==2.14.0` and is the one shape here that does **not** need re-verifying, only re-using. Map `ServerError`→`ProviderTransientError`, `ClientError` 429→`ProviderQuotaExhaustedError`, other `ClientError`→`ProviderPermanentError`.
- **Anthropic**: `anthropic==0.116.0` is already pinned in `backend/requirements.txt` but **has zero usages in this codebase** — no call shape, no async client name, no error-class hierarchy, no structured-output mechanism has ever been exercised here. Everything about it in an implementation is `[UNVERIFIED]` until the Developer reads the installed package source (`inspect.signature`, the `_client`/`resources`/`types` modules) and confirms: the async client class, the messages-create signature, how `max_tokens` is required/defaulted, the tool-use-or-JSON mechanism used to get structured output, the usage-token attribute names for `tokens_in`/`tokens_out`, and the exception classes for 4xx/429/5xx. No requirements change is expected; if one is, flag it rather than adding a dependency silently.

### 9.3 Quota ceilings

Neither Gemini's real paid-tier limits nor Anthropic's are known in this repo (`BL-076` says so explicitly for Gemini). The seeded values in §4.2 are conservative placeholders; reading the real numbers off the two vendor dashboards is a human action tracked as `BL-098`, and closing it needs no code change — only an `UPDATE`.

---

## 10. Edge cases

Carried forward from the ticket (**T**), plus ones found in the current codebase (**N**).

| # | Case | Handling |
|---|---|---|
| T1 | Both providers down | Degrade to the injected `fallback` (§6.2 step 6). Never raises. |
| T2 | Malformed/unparseable provider JSON | Retry once same provider → fail over → degrade. Parse errors never reach the user. |
| T3 | Quota exhausted mid-burst | `try_reserve()` returns `False` → next provider immediately. **No queuing.** |
| T4 | Routing table malformed | SS-026's `read()` serves the coded default table, logged at ERROR. A single malformed rule (unknown `when` field) makes that one rule inert, not the table. |
| T5 | Failover masks a persistent outage | `RoutingMixMonitor` outage detector (§7.2). |
| T6 | Latency differs by provider; SS-020's `<4s` must hold on the slowest path | Deadline-aware ladder (§6.2 step 1) with `total_deadline_seconds`. The default (12s) does **not** meet 4s — Blocker B2 / `BL-100`. |
| N1 | Config snapshot is `stale=True` (Supabase unreachable) | Routing still proceeds on the last-good or coded-default table; `config_stale=true` is logged on every line so a stale-config incident is visible after the fact. |
| N2 | Config row changes *between* the initial decision and a failover attempt | Impossible by construction: one snapshot per request (§4.4). Assert it in a test. |
| N3 | Routing table names a model the code has never seen | Works — the registry constructs an adapter for any `(provider, model)`. A *bogus* ID surfaces as `ProviderPermanentError` → failover → degrade, logged at ERROR. There is deliberately **no allow-list**; the table *is* the allow-list. |
| N4 | Routing table names an unknown *provider* | No registry entry → treated as an immediately-failed attempt, logged at ERROR, move to the next in `chain`. Must not `KeyError`. |
| N5 | `failover` maps a provider to itself, or a cycle | De-duplicate the chain and cap each provider to one attempt (§6.2 step 5). |
| N6 | Empty/effectively-empty `StylePreferencesInput` reaches a *real* adapter | Port contract: generic suggestions, `is_personalized=False`, no raise (§6.4). This is SS-006's rule and applies to every implementation, not just the mock. |
| N7 | Provider returns valid JSON but zero suggestions, or more than `max_suggestions` | Slice to `max_suggestions`; an empty list after slicing is treated as `ProviderParseError` (the model did not do the job) → retry/failover ladder. Never return a silently empty list from a "successful" call. |
| N8 | `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` unset | `os.environ[...]` `KeyError` at first use is caught by the router's attempt classifier as `ProviderPermanentError` → failover → degrade, logged at ERROR. **Never at import time**, so CI (which has no real keys) is unaffected. Add `ANTHROPIC_API_KEY` to `.env.example` if absent. |
| N9 | The two Gemini limiters double-spend one account pool | Tagging's `GeminiRateLimiter` and styling's `ProviderQuotaTracker` gate the **same** Gemini account quota independently, so their ceilings must be hand-apportioned to sum within the account limit. Documented in the config row's `description`; logged as `BL-099`. |
| N10 | Concurrent requests race the quota window | The tracker's reservation is done under an `asyncio.Lock` (same as `GeminiRateLimiter`), so within one process it is correct; across processes it is not (`BL-037`). Test with real `asyncio.gather`, not sequential calls. |
| N11 | Router used from a `BackgroundTasks` callback (the only current caller) | It must never raise — see §6.2 step 7. `BL-096` is live proof that raising inside a background task produces `RuntimeError: … response already started`. |
| N12 | `logging` `extra` key collision | Fixed field list in §6.3; no reserved `LogRecord` attribute names. |

---

## 11. Test plan

All backend, `pytest` + `pytest-asyncio`, no network, no real credentials, deterministic clocks. New unless marked *(modify)*.

**`backend/tests/test_styling_provider_contract.py`** — AC #7, parametrized over `MockStylingAdapter()`, `GeminiStylingAdapter(model=..., client=<fake>)`, `ClaudeStylingAdapter(model=..., client=<fake>)`:
- asserts each is a genuine `IStylingProvider` subclass and instantiable;
- asserts empty `StylePreferencesInput()` returns `is_personalized=False` and does not raise;
- asserts `max_suggestions=2` returns at most 2 items;
- asserts `budget_range` and `gender` behave as **hard filters** (excluded, not merely down-ranked) per the port docstring's mapping table;
- asserts `styles`/`favourite_colours` behave as **soft signals** (never remove an otherwise-eligible suggestion);
- asserts `generated_at` parses as ISO8601 and `source` equals the adapter's own provider key;
- asserts every returned item validates as `OutfitSuggestionItem`.

**`backend/tests/test_gemini_styling_adapter.py`**
- fake client returning well-formed JSON → success, `source="gemini"`, model echoed from the constructor;
- two adapters constructed with two different model IDs call the SDK with those exact model strings (proves AC #1's "parameterised by model ID");
- malformed JSON → `ProviderParseError`;
- `errors.ServerError` → `ProviderTransientError`; `ClientError(code=429)` → `ProviderQuotaExhaustedError`; `ClientError(code=404)` → `ProviderPermanentError`;
- `response.text is None` (safety-blocked/empty) → `ProviderParseError`, not an `AttributeError`;
- a hanging fake client → `ProviderTimeoutError` within `timeout_seconds`;
- `suggest_outfits_with_metrics` returns non-zero `tokens_in`/`tokens_out` parsed from the SDK usage object.

**`backend/tests/test_claude_styling_adapter.py`** — the same seven cases against the Anthropic client's real error classes and usage attribute names (as live-verified per §9.2).

**`backend/tests/test_ai_routing_specs.py`**
- each spec's coded default validates against its own model;
- **the seeded JSON in `011_seed_ai_routing_config.sql` parses to exactly the coded default** (read the SQL file, extract the JSONB literals, compare) — this is what makes "delete the row and behaviour is unchanged" a checked property rather than a claim;
- a malformed value for one key leaves the other two readable (SS-026 isolation, re-asserted at this ticket's boundary);
- every policy field clamps at both ends (§4.3), and `total_deadline_seconds < attempt_timeout_seconds` is clamped up rather than producing a zero-attempt router.

**`backend/tests/test_styling_router.py`** — `resolve_route()` first (pure, no async):
- no context → `default` everyday route, `reason="default_everyday"` (Constraint §2.4 — assert the *cheap* model, explicitly);
- `tier="atelier"` → high-stakes; `is_first_suggestion=True` → high-stakes; `occasion="wedding_guest"` → high-stakes; `occasion_kind="festival"` → high-stakes; `occasion_kind="religious"` (puja) → **everyday**, pinning B6's recorded decision so a later reader can see it was chosen, not missed;
- rule order decides when two rules match (atelier + wedding_guest → `reason="tier_atelier"`);
- an unknown `when` field skips only that rule;
- a malformed table falls back to the coded default routing.

Then the ladder, with fake providers:
- primary succeeds → one attempt, one log line, no failover;
- primary raises `ProviderParseError` → exactly one same-provider retry, then failover, then success on the secondary (assert the exact call sequence);
- primary quota-exhausted locally → secondary called **without** the primary ever being called;
- both providers fail → `fallback` result returned, `degraded=True`, `routing_reason="degraded_all_providers_failed"`, and **no exception raised**;
- fallback itself raises → a valid empty `OutfitSuggestionResult`, still no raise (N11);
- deadline exhausted before the second provider → degrade without calling it;
- unknown provider name in the table → no `KeyError`, failover proceeds (N4);
- self-referential/cyclic `failover` → each provider attempted at most once (N5);
- exactly one `AppConfigService.snapshot()` call per request, even across two failovers (N2);
- the log line for each attempt carries every field in §6.3 (assert with `caplog`, including `tokens_used == tokens_in + tokens_out`).

**`backend/tests/test_provider_quota.py`**
- allows exactly `rpm` reservations in a window, refuses the next, allows again after the window slides (injected clock, no sleeps);
- TPM ceiling refuses independently of RPM;
- `record_usage` reconciles an under-estimate so the next reservation reflects real spend;
- a provider absent from config is unlimited (documented behaviour, asserted);
- `asyncio.gather` of N concurrent reservations against a ceiling of M grants exactly M (CLAUDE.md's boundary sweep — concurrency, not sequential);
- boundary sweep: ceiling of 0 → clamped to ≥ 1 rather than a permanently-closed gate.

**`backend/tests/test_routing_mix_monitor.py`**
- share below threshold → no notification; above threshold with sample ≥ `alert_min_sample` → exactly one;
- below `alert_min_sample` → never fires, no matter the share (a single high-stakes first call must not page anyone);
- cooldown suppresses the second alert and permits one after it expires (injected clock);
- a provider failing continuously past `provider_outage_alert_seconds` fires the outage alert once; a single success resets the streak;
- notifications go through the injected notifier, never a real Sentry client.

**`backend/tests/test_gemini_rate_limiter.py`** *(modify)* — add: `set_max_requests()` changes the effective ceiling on the next `acquire()`; values < 1 are clamped; the constructor default is still `15`.

**`backend/tests/test_outfit_suggestions_router.py`** *(modify)* — `get_styling_provider()` now yields a `StylingRouter`; the endpoint still returns `202 {"status":"queued"}`; `app.dependency_overrides` still swaps the provider (the seam SS-006 documented must survive); no real network/credentials are touched by a request in CI.

**Not covered by tests, must be run manually and recorded in the worklog:** `backend/scripts/ss028_verify_routing_live_reload.py` — flip a routing rule in the real `app_config` table and observe the next decision change with the process still running (AC #2). No unit test can honestly claim "without a redeploy"; this is the same posture SS-026 took.

---

## 12. Open questions / blockers

**B1 — RESOLVED 2026-07-30 (user decision, clarified after a follow-up on provider mapping).** Multi-provider split stays as designed (Gemini everyday, Claude high-stakes) — the two Gemini IDs the user gave are **both within the Gemini/everyday tier**, not a replacement for Claude:
- `<EVERYDAY_MODEL_ID>` (primary) → `gemini-2.5-flash-lite`
- Everyday-tier retry/fallback model → `gemini-3.1-flash-lite` (used on the in-tier retry hop before the router fails over to Claude — this is a new third model slot the original 2-constant design didn't have; Developer should add it as `EVERYDAY_FALLBACK_MODEL_ID` alongside the existing two constants in `ai_routing_specs.py`, not overload `<HIGH_STAKES_MODEL_ID>`)
- `<HIGH_STAKES_MODEL_ID>` (provider `claude`) — **still unresolved.** No Claude/Anthropic model ID string has been verified anywhere in this repo. Developer must verify the exact API model ID (not marketing name) via the installed Anthropic SDK before wiring it as a constant, same escalate-don't-substitute rule as §9.1/§253. Do not guess `claude-sonnet-5` as an API string without checking the installed SDK's accepted model IDs.

None of the three Gemini/Claude strings above are `[VERIFIED]` against the installed SDKs yet — that verification is Developer's first step per §9.1/§253, unchanged from the original design.

**B2 — RESOLVED 2026-07-30 (user decision).** SS-020's "<4s cold call" AC applies to the happy path only; the failover/degrade path is allowed to exceed it. Ships as designed: `total_deadline_seconds` default 12s, configurable. `BL-100` stays open only as a "renegotiate SS-020's AC text to say happy-path-only" documentation task, not a design blocker.

**B3 — Quota ceilings are placeholders.** Gemini's real paid-tier RPM/TPM/RPD were never checked (`BL-076`'s own words) and Anthropic's are unknown to this repo. Ships conservative (Gemini stays at today's 15, so no regression). Closing needs a dashboard read and an `UPDATE`, no code. Logged as `BL-098`.

**B4 — One Gemini account pool, two independent in-process limiters.** Tagging (`GeminiRateLimiter`) and styling (`ProviderQuotaTracker`) both spend the same account quota without knowing about each other, so their configured ceilings must be apportioned by hand. Accepted for this ticket (unifying them would rewrite a shipped, working tagging path — the wrong risk trade for a `Risk: high` ticket); documented in the config row and logged as `BL-099`.

**B5 — Prompt ownership straddles two parallel branches.** SS-027 calls "one rules module, consumed twice" non-negotiable, but SS-027 does not exist on this branch, so SS-028 ships `styling_prompt.py`. Whichever merges second must not leave two copies of the colour/formality rules. Logged as `BL-101`; the reconciliation point is SS-020.

**B6 — RESOLVED 2026-07-30 (user decision).** Ship as designed: `puja`/`religious`/`date_night`/`party` route to the everyday model; only `ceremony`/`festival` (and `wedding_guest`) go high-stakes. No change to §4.1's rule.

**Reaffirmed, not fixed by this ticket:** `BL-037` (in-process quota tracker + in-process routing monitor; no deployed multi-worker backend to verify distributed behaviour against), `BL-052` (`outfit_suggestions.py`'s unverified-JWT stub stays — this ticket wires a real AI provider behind an endpoint that still has stub auth; nothing real calls it yet, but SS-020 must not ship without closing that row), `BL-096` (`HTTPException` raised inside a `BackgroundTasks` callback — the router is careful never to add a second instance, §6.2 step 7), `BL-077` (the provider-quality eval is still assumed, not proven — this design is what makes that assumption reversible with a config `UPDATE`), `BL-080` (all ₹/call figures expire 2026-08-31; none are in code), `BL-060` (migration `011` is insert-only, but any schema-touching PR should expect drift-check noise — run `supabase db push` then confirm `supabase db diff --linked` is empty, and report the diff rather than loosening the filter).

**Resolved by this design:** `BL-076` — quota ceilings move from a hardcoded constant to config-consumed values for both the styling path (new `ai_provider_quota`) and the existing tagging path (`get_gemini_rate_limiter()` now applies `GEMINI_QUOTA_CEILING_SPEC`). The row's own acceptance wording ("making it configurable … so a tier change doesn't require a code change again") is met; the still-outstanding half — reading the real numbers off the dashboard — is a human action carried forward as `BL-098` rather than silently closed.

**Backlog rows added by this pass:** `BL-098` (infra), `BL-099` (infra), `BL-100` (ai), `BL-101` (ai).

---

## 13. Acceptance-criteria trace

| AC | Where it is satisfied | Verified by |
|---|---|---|
| `GeminiStylingAdapter` implements the unchanged port, parameterised by model ID | §3.1, §6.4 | `test_styling_provider_contract.py`, `test_gemini_styling_adapter.py` (two model IDs → two SDK model strings); QA additionally greps the diff for any change to `ai/ports/interfaces.py` |
| Router selects provider+model from `app_config`; changing it changes routing with no redeploy | §4.1, §6.1 | `test_styling_router.py` (`resolve_route` matrix) + `scripts/ss028_verify_routing_live_reload.py` (manual, recorded in worklog) |
| Failure/quota exhaustion fails over and returns a real answer | §6.2 | `test_styling_router.py` ladder cases |
| Per-provider RPM/TPM tracking with ceilings from config | §5, §4.2 | `test_provider_quota.py`, `test_ai_routing_specs.py` |
| Every call logs `user_id`, `provider`, `model`, `tokens_used`, `latency_ms`, `routing_reason` | §6.3 | `test_styling_router.py` `caplog` assertions |
| Routing decisions observable; silent drift caught within a day | §7 | `test_routing_mix_monitor.py` |
| Both adapters pass an identical contract test suite | §3.1, §6.4 | `test_styling_provider_contract.py` (parametrized over all three implementations) |

---

`Risk: high` — this router decides what a paying user sees and what every request costs, it is the composition root for two live external AI vendors and their credentials, and its worst failure mode is silent: a table edit or a stale snapshot that quietly sends everyday traffic to the expensive model throws no error and surfaces on a bill, not in a stack trace. It also touches a shipped path (`routers/wardrobe.py`'s Gemini ceiling) and adds a migration. Full lane, every gate.
