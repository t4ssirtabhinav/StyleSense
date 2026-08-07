# SS-020 — Claude Outfit Suggestion API Endpoint — Design

## Scope restatement

Ship a real, authenticated `POST /outfit-suggestions/portfolio` endpoint that assembles everything Wave 0/1/1.5/2 built: it resolves the caller's occasion against the SS-025 registry, fetches the caller's wardrobe, runs it through SS-038's Engine v2 (`EngineV2.generate_portfolio`) — which is *itself already fully personalised* (novelty/wear-recency, style-preference soft signals, occasion rules) and costs nothing (pure Python) — then, for the top few candidates Engine v2 already scored and assembled, asks an LLM (via SS-028's `StylingRouter`, gated by SS-029's `CostBudgetGate` and dialled by SS-039's effort tiers) to *rank and narrate* them in prose, never to invent items. Because `IStylingProvider` as shipped by SS-006/SS-028 has no method that accepts pre-assembled candidates and no `item_id`-bearing return shape, this ticket adds one new capability to that port (`narrate_candidates`) and implements it on all three existing adapters (Mock/Gemini/Claude) plus `StylingRouter` — this is the "first real `IStylingProvider` implementation" work the raw ticket names, now concretely scoped. A new **combination-signature cache** (new table, new migration) is added at the narration layer only — Engine v2's own per-user personalisation is never cached, only the LLM's prose for a given *coarse, salted, cross-user-shareable* candidate-attribute signature. This ticket also closes `BL-052` (migrates this router's real endpoint off the non-production `sub`-claim-only JWT stub onto `dependencies/auth.py::get_current_user_id`) since it is the first time this router carries real, billable traffic.

## Files to create/modify

### New files

- **`backend/routers/outfit_suggestions.py`** (modified, not new) — add `POST /outfit-suggestions/portfolio` (`GeneratePortfolioRequest`/`GeneratePortfolioResponse`), the real `OutfitPortfolioService` wiring, and a `get_current_user_id`-backed auth dependency for this route only (the existing `/generate` stub + `get_current_user_id_stub` stay byte-identical, untouched — no caller depends on migrating them and doing so would expand this ticket's diff into an unrelated route).
- **`backend/services/outfit_portfolio_service.py`** — new orchestrator, analogous to (but not replacing) `outfit_suggestion_service.py`. Owns: occasion resolution → wardrobe fetch → effort-tier resolution → `EngineV2.generate_portfolio()` call → cache lookup → (on miss) `CostBudgetGate.reserve()` → narration call → cache write → `CostBudgetGate.reconcile()` → session cost-outcome update → response assembly. See "Concrete values" for the exact sequence.
- **`backend/services/suggestion_narration_cache.py`** — pure signature-computation (`compute_narration_signature(candidates, occasion_key, engine_version, llm_candidate_count) -> str`, salted HMAC — see "Concrete values") plus the cache-read/write orchestration wrapping `ISuggestionNarrationCacheRepository` (never raises; a cache failure degrades to "always call the LLM," never to a failed request).
- **`backend/adapters/suggestion_narration_cache_repository.py`** — `SupabaseSuggestionNarrationCacheRepository(ISuggestionNarrationCacheRepository)`. `service_role` (mirrors `IAppConfigRepository`/`ISuggestionLogRepository` precedent — this table has no per-user ownership at all, by design; see "Concrete values" for why that's the point, not a shortcut).
- **`supabase/migrations/019_suggestion_narration_cache.sql`** — new table `suggestion_narration_cache` (DDL — see "Concrete values"). **This is the one-way door the raw ticket calls out by name** ("cache keys are near-impossible to change once a populated cache is live") — hence Open Question #2 below must be signed off before this migration is written for real, not just designed.
- **`backend/tests/test_outfit_portfolio_service.py`**, **`test_suggestion_narration_cache.py`**, **`test_outfit_suggestions_router_portfolio.py`**, **`test_narrate_candidates_*.py`** (one per adapter) — see Test plan.

### Modified files (all additive — no existing method signature changes; new methods/fields only, per Open/Closed)

- **`backend/ai/ports/interfaces.py`** — add to `IStylingProvider` (ABC, so every existing implementer must add the new method — same class of change SS-039 made to `IRateLimiter` with `peek()`):
  ```python
  class NarratedCandidate(BaseModel):
      outfit_fingerprint: str  # ties back to engine_v2_portfolio.compute_outfit_fingerprint
      rationale: str           # English or Hindi prose, per AC #2
      rank: int | None = None  # LLM's own re-ranking within the supplied set, if it re-ranks; None = kept input order

  class NarratedPortfolioResult(BaseModel):
      narrations: list[NarratedCandidate]
      language: Literal["en", "hi"] = "en"
      source: Literal["mock", "gemini", "claude", "rules_only"] = "rules_only"

  class IStylingProvider(ABC):
      ...
      @abstractmethod
      async def narrate_candidates(
          self,
          candidates: list[dict[str, Any]],  # engine_v2_types.render_candidate_for_prompt(...) output, one dict per candidate, UNCHANGED shape
          *,
          occasion: str,
          preferences: StylePreferencesInput,
          max_suggestions: int,
      ) -> NarratedPortfolioResult:
          """MUST NEVER invent an item id/category not present in `candidates`
          -- this is what makes SS-020's 'no hallucinated item IDs' AC
          structurally provable (same posture Engine v2 already gives
          `ScoredCandidate.item_ids`). MUST NEVER raise -- any SDK/parse/
          timeout failure is caught and mapped to StylingCall's existing
          ProviderXxxError hierarchy exactly like suggest_outfits_with_metrics
          does, so StylingRouter's chain/failover/degrade logic (unmodified)
          works identically for this method."""
          raise NotImplementedError
  ```
- **`backend/ai/adapters/mock_styling_adapter.py`** — implement `narrate_candidates`: deterministic, offline, builds `rationale` directly from each candidate dict's `top_explanations` (already present in `render_candidate_for_prompt`'s output — no new logic needed, just string-join). This is also the literal implementation of the AC's "degrade to deterministic candidates with rule-based reasoning" path and of E0's `llm_candidate_count=None` tier — see "Concrete values."
- **`backend/ai/adapters/gemini_styling_adapter.py`**, **`backend/ai/adapters/claude_styling_adapter.py`** — implement `narrate_candidates` (+ a `narrate_candidates_with_metrics` mirroring each adapter's existing `suggest_outfits_with_metrics`) using each SDK's existing structured-output mechanism (Gemini `response_schema`, Claude forced tool-use) already verified live by SS-028 — same call-shape verification discipline, no new SDK surface to verify, only a new prompt/schema (candidates + occasion + preferences → per-candidate rationale, `outfit_fingerprint` echoed back verbatim so the caller can re-associate without trusting the LLM's ordering).
- **`backend/ai/adapters/styling_prompt.py`** — add `build_narration_prompt(candidates, occasion, preferences, max_suggestions)`, sibling to `build_styling_prompt`, rendering `render_candidate_for_prompt`'s dicts (never re-deriving colour/formality text itself, per that function's own stated contract).
- **`backend/services/styling_router.py`** — add `narrate_candidates`/`narrate_candidates_with_decision` to `StylingRouter`, mirroring `suggest_outfits`/`suggest_outfits_with_decision`'s exact chain-build/quota/timeout/failover/degrade structure (`_build_chain`, `_deadline_exceeded`, `_log_and_record` all reused unchanged). The degrade path (`_degrade`) for narration calls `self._fallback.narrate_candidates(...)` — with `MockStylingAdapter` as the default fallback (unchanged), whose implementation is the rule-based degrade described above. **This satisfies the AC's "never a hard error to the user" for the narration leg by construction**, the same way SS-028 already did for `suggest_outfits`.
- **`backend/services/engine_v2.py`** — additive-only signature widening of `generate_portfolio`: two new optional kwargs, `search_pool_size: int = CANDIDATE_SEARCH_TOP_K_BASES` (forwarded to `engine_v2_candidate_search.search_candidates(top_k_bases=search_pool_size)`, currently hardcoded to the module default and not forwarded at all) and `mmr_lambda: float = DEFAULT_MMR_LAMBDA` (forwarded to `engine_v2_portfolio.select_portfolio(lambda_=mmr_lambda)`, same gap). **Without this, SS-039's effort dial has no way to actually reach the engine** — `EngineV2.generate_portfolio()` as shipped only forwards `portfolio_size_range`/`max_exploration`, not the other two dial fields, even though `styling_rules_defaults.py`'s own comment says all four were named "specifically so SS-039's effort dial can supersede them ... without touching call sites" (SS-038 design doc, "Concrete values" #Portfolio constants). Defaults are unchanged from today's hardcoded values, so every existing SS-038 test keeps passing unmodified. Also add optional `effort_tier: str | None = None`, `tier: str | None = None`, `request_id: str | None = None` kwargs, forwarded into `SuggestionSessionLog` (see next bullet) — additive, defaults `None` preserve every existing test's assertions.
- **`backend/adapters/interfaces.py`**:
  - `IWardrobeRepository` gains `async def get_items_for_styling(self, *, jwt: str, user_id: str) -> list[dict[str, Any]]` (new abstract method — RLS-scoped via caller JWT, mirrors every other method on this port; selects `id, category, color_primary, color_secondary, pattern, fabric, occasion_tags, season_tags, wear_count, last_worn_at` for the caller's own rows) and `async def get_style_preferences(self, *, jwt: str, user_id: str) -> dict[str, Any] | None` (selects `users.style_preferences`, RLS-scoped, mirrors `get_plan_tier`'s existing shape).
  - `IOccasionRepository`'s `OccasionRegistrySnapshot` gains three new `dict[str, ...]` fields keyed by occasion key, all `default_factory=dict` (backward-compatible, no existing caller reads them so none breaks): `kinds: dict[str, str]`, `formalities: dict[str, int]`, `styling_rules: dict[str, dict[str, Any]]`. **Needed because nothing shipped today can turn "an occasion key" into the `kind`/`formality`/`styling_rules` triple `OccasionStylingInput` requires** — the registry snapshot as shipped by SS-025 only carries `keys`/`aliases`/`labels`/`badge_colors`. `SupabaseOccasionRepository.fetch_registry`'s query gains three more selected columns; no schema change, `occasions` already has all three columns (SS-025).
  - `ISuggestionLogRepository` gains `async def update_session_outcome(self, *, session_id: str, cost_incurred: bool, request_id: str | None, latency_ms: int | None) -> None` — **MUST NEVER RAISE**, same posture as every other method on this port. Needed because `EngineV2._log_session` always writes `cost_incurred=False, zero_cost_reason="rules_only"` (correct for Engine v2's own scope, since it never calls an AI provider) but SS-020's narration call, when it happens, is real spend that the same session row should reflect — this ticket's service calls this new method once the narration outcome (cache hit / LLM call / degrade) is known, rather than reopening `EngineV2`'s "no AI provider calls" boundary (SS-038's own stated design invariant).
  - New: `CachedNarration` (frozen dataclass: `narrations_by_signature_index: dict[int, str]`, `language: str`), `ISuggestionNarrationCacheRepository` (ABC, `service_role`, both methods **MUST NEVER RAISE**: `async def get(self, *, signature_hash: str) -> CachedNarration | None`, `async def put(self, *, signature_hash: str, occasion_key: str, engine_version: str, narrations_by_signature_index: dict[int, str], language: str, ttl_seconds: int) -> None`).
- **`backend/adapters/supabase_wardrobe_repository.py`** (the concrete `IWardrobeRepository` implementation — exact filename TBD by Developer, whatever the existing SS-011-era file is called) — implement the two new methods above.
- **`backend/adapters/occasion_repository.py`** (or wherever `SupabaseOccasionRepository` lives) — widen the `fetch_registry` SELECT to include `kind, formality, styling_rules` and populate the three new snapshot fields.
- **`backend/services/app_config_specs.py`** — add `SuggestionNarrationCacheTtlConfig(BaseModel)` (`seconds: int = 21600` — 6h) and `SUGGESTION_NARRATION_CACHE_TTL_SPEC`, same shape as `NEAR_WHITE_THRESHOLD_SPEC`.

### New migration

**`supabase/migrations/019_suggestion_narration_cache.sql`** (DDL — see "Concrete values" for the exact column list and why). Sequenced after `018` per `BL-110`'s standing discipline; re-confirm `019` is still free via `supabase migration list --linked` immediately before push.

## Concrete values to use, not invent

### 1. The endpoint contract

`POST /outfit-suggestions/portfolio`, auth via `Depends(get_current_user_id)` (real, signature-verified — closes `BL-052` **for this route only**; the old `/generate` stub is untouched, see Open Question #6).

```python
class GeneratePortfolioRequest(BaseModel):
    occasion: str                                  # raw text or registry key; normalised server-side
    season: SeasonTag | None = None
    as_of: date | None = None                       # default: today, IST (services/ist_window.py)
    style_preferences_override: dict[str, Any] | None = None  # None => server fetches users.style_preferences

class PortfolioItemResponse(BaseModel):
    item_ids: list[str]
    category_labels: dict[str, str]
    total_score: float
    rationale: str
    rationale_language: Literal["en", "hi"]
    is_exploration: bool
    gap_flags: list[str]

class GeneratePortfolioResponse(BaseModel):
    portfolio: list[PortfolioItemResponse]
    limited_options: bool
    gap_report: dict[str, Any]                      # GapReport.model_dump()
    engine_version: str
    effort_tier: str                                 # "E0" | "E1" | "E2"
    cache_hit: bool
    generated_at: str                                 # ISO-8601 UTC
```

Response is **awaited synchronously inside the request handler — no `BackgroundTasks`**. See Open Question #1; this is the single most load-bearing deviation from CLAUDE.md's literal "never call AI APIs synchronously" wording in this whole design and must be signed off explicitly, not defaulted.

### 2. `OutfitPortfolioService.generate_portfolio_for_request` — exact sequence

1. Resolve occasion: `OccasionNormalizer.get_registry(jwt=jwt)` → `.resolve(raw, snapshot)` → build `OccasionStylingInput(key=resolved_key, kind=snapshot.kinds[resolved_key], formality=snapshot.formalities[resolved_key], styling_rules=snapshot.styling_rules.get(resolved_key, {}))`. An unresolvable/unknown occasion (not in `snapshot.keys`, no alias hit) still gets a `kind`/`formality`/`styling_rules` — degrade to `kind="everyday", formality=5, styling_rules={}` (mirrors `default_styling_rules_for`'s own kind-based fallback philosophy; a request must never 500 merely because the occasion registry hasn't modelled a string yet — same "unknown occasion is a signal, not an error" posture SS-025/SS-012 already established).
2. Fetch wardrobe: `repository.get_items_for_styling(jwt=jwt, user_id=user_id)` → `[WardrobeItemInput.model_validate(row) for row in rows]`.
3. Fetch/normalise style preferences: `style_preferences_override` if the request supplied one, else `repository.get_style_preferences(jwt=jwt, user_id=user_id)` run through the existing `_normalize_preferences` (moved/reused from `outfit_suggestion_service.py`, not re-derived).
4. Resolve plan tier: `repository.get_plan_tier(jwt=jwt, user_id=user_id)` (already-shipped method, SS-011/SS-013).
5. Resolve effort tier: `resolve_effort_tier_for_request(monitor=_routing_mix_monitor, gate=CostBudgetGate(limiter, app_config_service), user_id=user_id, tier=plan_tier, config_snapshot=snapshot, app_config=app_config_service)` → `(effort_tier_key, tier_params)`.
6. Call Engine v2: `EngineV2.generate_portfolio(wardrobe=items, occasion=occasion_input, jwt=jwt, user_id=user_id, as_of=as_of, season=season, style_preferences=preferences, search_pool_size=tier_params.search_pool_size, mmr_lambda=tier_params.mmr_lambda, max_exploration=tier_params.max_exploration, effort_tier=effort_tier_key, tier=plan_tier, request_id=request_id)`.
7. If `tier_params.llm_candidate_count is None` (E0): skip straight to step 11 with `source="rules_only"`, no cache lookup, no budget reservation — this is E0's whole point (degraded = cheap = deterministic).
8. Else: take the top `tier_params.llm_candidate_count` portfolio entries (by `total_score`, ties broken by the existing deterministic `(-total_score, item_ids)` order Engine v2 already returns them in), render each via `render_candidate_for_prompt`, compute `compute_narration_signature(candidates=..., occasion_key=resolved_key, engine_version=ENGINE_VERSION, llm_candidate_count=tier_params.llm_candidate_count)`. Look up `ISuggestionNarrationCacheRepository.get(signature_hash=...)`.
9. **Cache hit**: map `narrations_by_signature_index` back onto the caller's own candidates by signature-array position (see below) — `cache_hit=True`, no budget touched, no LLM call.
10. **Cache miss**: `CostBudgetGate.reserve(user_id=user_id, tier=plan_tier, estimate_micropaise=PriceTable.estimate(...).default_cost_estimate, config_snapshot=snapshot)`. If `not allowed` (free-tier fail-closed): degrade to step 11's rule-based path — **never** a 429 to the caller, per the AC's literal "never a hard error." If allowed: call `styling_router.narrate_candidates_with_decision(candidates, occasion=resolved_key, preferences=preferences, max_suggestions=tier_params.llm_candidate_count)`, then `CostBudgetGate.reconcile(reservation=..., actual_micropaise=PriceTable.cost(...))`, then `narration_cache.put(...)` (best-effort, never blocks the response on a cache-write failure).
11. Rule-based fallback (E0, budget-denied, or `StylingRouter`'s own degrade already happened inside step 10 — in all three cases the candidates already carry `rule_scores`/`top_explanations`; `render_candidate_for_prompt`'s existing output already IS the rationale text): rationale = the two highest-scoring `RuleScore.explanation` strings, joined.
12. `repository_suggestion_log.update_session_outcome(session_id=engine_result.session_id, cost_incurred=<True iff step 10 actually called the LLM>, request_id=request_id, latency_ms=<end-to-end elapsed>)` — best-effort, wrapped in try/except, never blocks the response.
13. Assemble `GeneratePortfolioResponse` and return.

### 3. The combination-signature cache — exact key derivation

**What is cached:** only the LLM's *prose*, never Engine v2's item-level selection (which stays 100% per-user, computed fresh every request — cheap, per SS-038). This is what resolves the "personalisation must not leak" AND "novelty/wear-recency personalises the candidate SET itself, not just its narration" tension: by the time anything is cached, the *set of candidates* has already been fully and independently personalised per user; the cache only asks "has an LLM already narrated a candidate set that looks like this one (by coarse attribute shape), for this occasion?"

```python
def compute_narration_signature(
    candidates: list[dict[str, Any]],  # render_candidate_for_prompt(...) output, in the SAME order narrate_candidates was called with
    *, occasion_key: str, engine_version: str, llm_candidate_count: int,
) -> str:
    # 1. Per candidate: sorted tuple of (category, colour_family_bucket, formality_band) per item --
    #    NEVER the raw hex, NEVER the item id. colour_family_bucket = HARD_EXCLUDED_COLOR_FAMILIES's
    #    existing hue-bucket vocabulary (already used by styling_rules_engine for exclusion, reused
    #    here for coarsening -- no new colour taxonomy invented). formality_band = round(base_formality)
    #    to the nearest 2 (0/2/4/6/8/10) -- coarse on purpose, wider sharing, per the ticket's own
    #    "two users with a navy kurta and beige churidar ... share the answer" framing.
    # 2. Candidates themselves sorted by their own tuple-of-tuples (order-independent -- who computed
    #    the candidate is irrelevant, only its shape matters).
    # 3. shape_string = f"{occasion_key}|{engine_version}|{llm_candidate_count}|" + "||".join(candidate tuples)
    # 4. HMAC-SHA256(key=os.environ["SUGGESTION_CACHE_SALT"], msg=shape_string) -- a SALTED, KEYED hash,
    #    not a plain sha256: closes even the low-value "brute-force common wardrobes to probe which
    #    signatures are cache-warm" angle the raw ticket's privacy edge case implies, at zero extra cost.
    ...
```

`SUGGESTION_CACHE_SALT` is a new required env var (`.env`/`.env.example`) — **not yet provisioned**, flagged in Open Questions.

### 4. Migration `019` — table shape

```sql
CREATE TABLE suggestion_narration_cache (
  signature_hash   TEXT PRIMARY KEY,         -- HMAC-SHA256 hex, 64 chars
  occasion_key     TEXT NOT NULL,
  engine_version   TEXT NOT NULL,
  language         TEXT NOT NULL DEFAULT 'en',
  narrations       JSONB NOT NULL,            -- {"0": "...", "1": "...", ...} keyed by signature-array index, NEVER item_ids/user_id
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at       TIMESTAMPTZ NOT NULL,
  hit_count        INTEGER NOT NULL DEFAULT 0
);
-- No user_id column at all, by construction -- this is the structural half of "not reversible into
-- another user's wardrobe" (the other half is compute_narration_signature never hashing raw item
-- attributes or ids). RLS: default-deny for every client role (mirrors app_config's own posture) --
-- only service_role (this ticket's ISuggestionNarrationCacheRepository) ever touches this table.
ALTER TABLE suggestion_narration_cache ENABLE ROW LEVEL SECURITY;
-- (no policies created -- default-deny is the policy, per SS-025/026's established precedent for
-- non-user-owned tables with zero client access)
CREATE INDEX idx_suggestion_narration_cache_expires_at ON suggestion_narration_cache (expires_at);
```

Cleanup: a `pg_cron` job deleting expired rows, mirroring SS-033's own precedent (migration `013`) rather than inventing a new cleanup mechanism.

### 5. Effort-tier → engine wiring (ties SS-039's dial to a real caller for the first time)

| `EffortTierParams` field | Engine v2 / narration parameter | 
|---|---|
| `search_pool_size` | `EngineV2.generate_portfolio(search_pool_size=...)` → `search_candidates(top_k_bases=...)` (no-op today per `BL-136`, wired anyway — forward-compatible, correct) |
| `mmr_lambda` | `EngineV2.generate_portfolio(mmr_lambda=...)` → `select_portfolio(lambda_=...)` |
| `max_exploration` | `EngineV2.generate_portfolio(max_exploration=...)` (already forwarded today) |
| `colour_mode` | **not wired** — inert per `BL-135`, do not build a toggle in this ticket (out of scope, same reasoning SS-039's own Architect pass gave) |
| `llm_candidate_count` | `None` → skip narration entirely (E0); else the `max_suggestions` cap on `narrate_candidates` and the top-N slice of the portfolio sent to it |

## Edge cases

Carried forward from the raw ticket (all six), plus:

- Occasion string resolves to an unknown/never-seen key (registry miss) — degrades to `kind="everyday", formality=5, styling_rules={}` rather than a 400/500 (§2 step 1); the occasion is still passed through to Engine v2 verbatim so `occasions.styling_rules` gap-flags/novelty logging still records the unmodelled key for later review (same "signal, not error" posture as SS-012/SS-025).
- User has zero wardrobe items in the relevant slots at all — `EngineV2.generate_portfolio` already returns `limited_options=True` with an honest (possibly empty) portfolio; the router must return `200` with that payload, never a 404/422 — "what's available" per the AC, not an error.
- `style_preferences_override` is present but fails `StylePreferencesInput` validation — same degrade as `_normalize_preferences` already does (empty preferences, `is_personalized`-equivalent False), never a 422 on the whole request.
- Cache hit but the caller's own candidate set has a different *length* than `llm_candidate_count` (fewer real candidates available than the tier wants) — `compute_narration_signature` naturally produces a different hash (candidate count is part of the shape string), so this is structurally a cache miss, not a partial/misaligned hit — no special-casing needed.
- `CostBudgetGate.reserve()` degrades (`degraded=True`, Upstash unreachable) and `fail_open` for the tier is `True` (paying tiers) — proceed to the LLM call as normal (existing `CostBudgetGate` semantics, unchanged); `fail_open=False` (free tier) and degraded — denies, same as a real over-ceiling deny, degrades to rule-based reasoning per step 10/11, never a 429.
- `StylingRouter.narrate_candidates_with_decision`'s own degrade path (`_fallback.narrate_candidates`, i.e. `MockStylingAdapter`) fires — this happens *after* a budget reservation was already made; `reconcile()` must still run with the actual (near-zero, deterministic) cost so the reservation isn't silently left inflated at the estimate.
- The narration LLM returns fewer `NarratedCandidate` rows than requested, or omits an `outfit_fingerprint` that doesn't match any input candidate — any candidate without a matching narration falls back to its own rule-based explanation (§2 step 11's logic, applied per-candidate, not all-or-nothing) — a partial LLM response must never blank out an otherwise-good candidate's rationale.
- Two different users' Engine v2 runs produce candidate sets that hash to the *same* `signature_hash` but are semantically different outfits for cultural/regional reasons not captured by the coarse (category, colour-family, formality-band) tuple (e.g. two garments in the same colour family but very different regional context) — accepted, documented risk of coarsening (this is what makes cross-user sharing possible at all); the rationale text itself must stay generic/skeleton (no garment-specific claims beyond what `render_candidate_for_prompt`'s categories already state) precisely so a shared narration is never *wrong*, only generic — reinforces Open Question #2's sign-off need.

## Test plan

- `backend/tests/test_outfit_portfolio_service.py` — full sequence (§2) against fake repos/adapters: E0 skips narration and cache entirely; E1/E2 cache-miss calls `reserve()` before `narrate_candidates`, `reconcile()` after; cache-hit skips both; budget-denied (fail-closed free tier) degrades to rule-based reasoning with `200`, never `429`; unknown occasion degrades to `everyday`/formality 5 rather than erroring; zero-wardrobe-items path returns `limited_options=True` with `200`; `update_session_outcome` is called exactly once regardless of which path was taken, and never blocks the response if it raises (patched to raise, response still returns normally).
- `backend/tests/test_suggestion_narration_cache.py` — `compute_narration_signature` is order-independent across permuted candidate lists but sensitive to occasion/engine_version/llm_candidate_count/category/colour-family/formality-band changes (one assertion per dimension); same candidate set + different raw hex within the same colour family produces the SAME signature (coarsening proof); HMAC changes if `SUGGESTION_CACHE_SALT` changes (keyed-hash proof, not plain sha256); cache read/write repository failures degrade to "always call LLM" (never raise into the service).
- `backend/tests/test_narrate_candidates_mock.py` / `_gemini.py` / `_claude.py` — each adapter: never invents an item id/category outside the input `candidates` (constructs a candidate set, asserts every returned `NarratedCandidate.outfit_fingerprint` matches an input); malformed/timeout/quota SDK failure maps to the correct `ProviderXxxError` (mirrors each adapter's existing `suggest_outfits_with_metrics` test coverage); `MockStylingAdapter`'s rationale is built purely from `top_explanations`, no randomness, deterministic given the same input.
- `backend/tests/test_styling_router_narration.py` — `narrate_candidates_with_decision` reuses the exact chain/failover/timeout logic (parametrize existing `test_styling_router.py` cases against the new method where structurally identical); degrade path calls `MockStylingAdapter.narrate_candidates`, never raises.
- `backend/tests/test_outfit_suggestions_router_portfolio.py` — `POST /outfit-suggestions/portfolio` requires a real, signature-verified bearer token (`get_current_user_id`, not the stub) — a malformed/unsigned token gets `401`; end-to-end happy path returns `200` with the documented response shape; the pre-existing `/generate` route and its stub auth are unchanged (regression pin — a literal byte-diff-style check that that route's dependency is still `get_current_user_id_stub`, proving this ticket didn't silently touch it).
- **Latency AC proof** (manual verification step, matching SS-012's `BL-067` precedent — do not claim `<4s` from a synthetic 1-item wardrobe): a real call against a non-trivial (~40+ item) synthetic wardrobe, cold cache, E2 tier, against the **slowest** model in the live routing table (per the AC's own literal wording) — recorded in the worklog with the actual measured latency, not asserted from the timeout config.
- **Cache-key regression test** (Developer must add before first real traffic, per the raw ticket's own "must be right the first time" warning): a golden-file test locking `compute_narration_signature`'s exact output for a fixed input — if this test ever needs to change, that is the literal moment the "cache keys are near-impossible to change once live" risk fires, and it must be flagged loudly in that PR's description, not silently updated.

## Open questions / blockers

**All of the following require explicit user sign-off before Developer starts — full lane, per this ticket's `Risk: high`.**

1. **Synchronous await vs. `BackgroundTasks` (direct conflict with CLAUDE.md's literal "Never call AI APIs synchronously — use background tasks").** This design recommends awaiting the whole pipeline inside the request handler (§1/§2), because (a) the AC's own "cache hit <200ms; cold call <4s" wording only makes sense measured end-to-end against the HTTP response, and (b) there is no existing companion GET/poll/Realtime mechanism for this router the way SS-012/SS-013 built for tagging (`GET /wardrobe/items/{id}/image-url` + Realtime), and building one is squarely SS-023's job, not this ticket's. Recommended reading of the CLAUDE.md rule: it means "never block the event loop with sync (non-`async`) I/O," which this design never does (every I/O call is `await`ed) — not "never `await` a provider call inside a request handler." **Needs explicit confirmation**, since it's a literal-text deviation from a standing rule, on the single highest-traffic, most latency-sensitive endpoint in the product.
2. **The combination-signature cache design itself (§3/§4) is an Architect-designed resolution to a tension the raw ticket didn't fully spell out** — namely that Engine v2's own personalisation (novelty/wear-recency) happens *before* anything reaches the cache, so only LLM prose is ever shared, keyed on a coarsened (category, colour-family-bucket, formality-band) shape, HMAC-salted, with no `user_id`/item-id column at all. This is exactly the "must be right the first time" one-way door the raw ticket names explicitly. **Needs explicit sign-off on the coarsening granularity** (colour bucketed to family, formality rounded to bands of 2) before the migration is written — a narrower or wider bucket changes both privacy exposure and cross-user hit rate, and cannot be cheaply revisited once real rows exist.
3. **`SUGGESTION_CACHE_SALT` is a new, not-yet-provisioned secret** (`.env`/`.env.example`, Railway env vars once `BL-037` is resolved) — same class of gap SS-010/SS-012 hit for R2/Gemini credentials, but this one is entirely new (no prior ticket asked for it). Needs to be generated and provisioned before Developer can wire the real repository (a fake/test value is fine for unit tests).
4. **`IStylingProvider.narrate_candidates` is a new abstract method touching an already-shipped, already-reviewed port** (SS-006's design, SS-028's `Risk: high` implementation). Per this repo's Open/Closed convention (SS-039 set the precedent by adding `IRateLimiter.peek()`), this is additive and every existing adapter gains a new method rather than an existing one changing shape — but it is still real new work across four files (`mock_/gemini_/claude_styling_adapter.py` + `styling_router.py`) that the raw ticket's "assembly, not a monolith" framing did not anticipate at this depth. Flagging so the estimate (already 20h) is understood to include this, not treated as scope creep discovered mid-Developer-pass.
5. **`EngineV2.generate_portfolio`'s signature widening (`search_pool_size`, `mmr_lambda`, `effort_tier`, `tier`, `request_id`)** is a real, if small, edit to SS-038's shipped, merged, `PASS`-verdict file. All five are new optional kwargs with defaults matching current hardcoded behaviour, so no existing test's assertions change — but this is still touching a ticket that already shipped and passed QA. Flagged for explicit awareness, not because there's a real risk of regression (there isn't — every new kwarg is additive with a status-quo default).
6. **`BL-052` is only closed for the NEW `/portfolio` route, not the pre-existing `/generate` stub.** The stub (`get_current_user_id_stub`, SS-006) stays exactly as-is — it still has no real caller anywhere in the repo, and migrating it would be an unrelated, unreviewed change to a different route. If a future ticket ever wires a real caller to `/generate`, `BL-052` should be re-opened against that route specifically at that point.
7. **`get_items_for_styling`'s exact processing-status filter is unspecified by any prior ticket** — should an item with `processing_status='uploaded'` (not yet bg-removed/tagged, so `category`/`color_primary` are still `NULL`) be included at all? Engine v2's own eligibility stage already excludes items missing `category`/`color_primary` (`excluded_missing_color_or_category`, counted in the gap report) — so including untagged items is *safe* (they're excluded downstream and counted, not silently dropped) but wastes a row fetch. Recommends: fetch all rows regardless of `processing_status` and let Engine v2's existing eligibility filter do the work (simplest, no new filter logic, and the gap-report count becomes a genuinely useful signal of "how much of your wardrobe isn't tagged yet"). Low-stakes, included here for completeness rather than as a hard blocker.
8. **No frontend exists to call this endpoint yet** (SS-023 is unstarted) — this ticket is necessarily verified via `curl`/`httpx`/Pytest against local `uvicorn` only, same precedent as every backend-only ticket so far (SS-011/012/026/028/029/033-039), compounded by `BL-037`'s standing no-deployment note. Not a blocker, just carried forward explicitly per that row's own reaffirmed pattern.

## Backlog deltas (for the orchestrator to apply to `docs/BACKLOG.md`)

Scanned Active table for `ai`/`schema`/`auth`/`infra` rows relevant to this ticket, per the once-per-ticket resurfacing scan (see research above): `BL-037`, `BL-052`, `BL-097`, `BL-119`(resolved by SS-038, reaffirmed clean), `BL-120`, `BL-121`, `BL-134`, `BL-135`, `BL-136`.

**Resolve → Resolved (once Developer ships, not by this design pass alone):**
- `BL-052` — this design migrates the new `/portfolio` route onto `get_current_user_id` (real, signature-verified). The old `/generate` stub is explicitly NOT touched (Open Question #6) — mark `BL-052` resolved only for the route this ticket actually ships, and log a fresh note if `/generate` ever gets a real caller later.
- `BL-134` — this design's `compute_narration_signature` is a **new, third** hashing scheme, deliberately distinct from both existing `outfit_fingerprint` implementations (it hashes coarsened attribute shapes, not item ids, and is salted) — it does not consolidate `BL-134`'s two colliding implementations, but this ticket's own new session-outcome logging (`update_session_outcome`) reuses `engine_v2_portfolio.compute_outfit_fingerprint` (the SS-038 one, comma-joined) exclusively for its own internal bookkeeping, never `suggestion_log_service.py`'s colon-joined one — so this ticket doesn't make `BL-134` worse, but doesn't resolve it either. Stays Active, unchanged.

**Update note, stays Active:**
- `BL-120` — this design is the write half this row has been waiting for (`wardrobe_item_wears.outfit_id` still has no writer even after this ticket, since SS-020 doesn't create `outfits` rows — that's SS-023's `outfits`-table-creation job per `docs/worklog/README.md`'s own Epic 3 cross-ticket note). Reaffirmed unchanged, still SS-023's job specifically, not SS-020's.
- `BL-121` — unchanged; Mark Worn's `occasion_key=NULL` product question is still SS-023 UI work, not resolved by a backend-only ticket.
- `BL-097` — unchanged; this ticket still authors zero new `occasions.styling_rules` content.
- `BL-135`/`BL-136` — unchanged, reaffirmed: this design wires `search_pool_size`/`colour_mode` through exactly as SS-039 specified (§5 table above), inheriting both known-inert behaviours as documented, not attempting to fix either (out of scope, same reasoning SS-039's Architect pass gave).
- `BL-037` — reaffirmed, still doesn't block (verified locally against `uvicorn`, per Open Question #8).

**New rows (Active, next sequential IDs from `BL-137`):**
- `BL-137` | `ai` | SS-020 / Architect — `IStylingProvider.narrate_candidates` is a new port capability with no prior stylist/product validation of its prompt/schema design (same "unvalidated, folds into `BL-077`" class as `ENGINE_V2_RULE_WEIGHTS`/`RULE_WEIGHTS` before it) — the exact narration prompt structure is an Architect/Developer judgment call, not sourced from a design spec, and should be included in `BL-077`'s eventual quality eval.
- `BL-138` | `schema` | SS-020 / Architect — `suggestion_narration_cache`'s coarsening granularity (colour bucketed to family, formality rounded to bands of 2) is an Architect-chosen value with no A/B data on cross-user hit rate vs. narration genericness trade-off; revisit once real traffic exists to measure actual hit rate (the whole point of the cache, per the raw ticket's 8-79× cost framing) — if hit rate is too low to matter, the privacy/complexity cost of a shared cache at all should be re-litigated rather than just re-tuned.

## Risk classification

`Risk: high` — confirmed, not revised (raw ticket's own header already said `high`; this pass finds nothing that lowers it and several things that reinforce it). This ticket: (1) ships a new DDL migration and a genuinely new, hard-to-revise cache-key design over a shared cross-user table (`OPERATOR_RULEBOOK.md` §C2's one-way-door test, met literally — the raw ticket itself calls this out by name); (2) is the first ticket in this repo to move a real, billable external AI call behind a production auth boundary (closing `BL-052` for this route is a genuine auth-surface change, not cosmetic); (3) is the revenue-adjacent free-tier budget gate the whole Epic 3 pricing rework (`docs/proposals/EXECUTION-PLAN.md`) exists to protect; (4) touches an already-shipped, already-`PASS`-verdict port (`IStylingProvider`) and an already-shipped engine (`EngineV2`) with real (if additive) signature changes. Full lane: every gate stays, and Developer must not start until the eight open questions above — especially #1 (sync-vs-background) and #2 (cache coarsening) — are explicitly signed off by the user, not defaulted by this design.
