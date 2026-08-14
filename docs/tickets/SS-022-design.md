# SS-022 — Weather Integration (City-Based) — Design

**Risk: med** (see "Risk classification" at the end for the full justification.)

## Scope restatement

Enrich the already-shipped `POST /outfit-suggestions/portfolio` pipeline (SS-020, extended by SS-023) with current weather for the user's saved city, so that (a) Engine v2's eligibility stage applies a real, code-level hard exclusion in heavy rain (no white, no silk), (b) the narration LLM receives weather context in its prompt, (c) the response carries a `weather` block the Style tab renders as a chip ("Dressing for 28°C, partly cloudy"), and (d) every one of those degrades silently to today's exact behaviour when the user has no usable city or Open-Meteo is unreachable. Weather is fetched **server-side inside the same request** from Open-Meteo (no API key), cached per city per hour in the existing Upstash Redis instance using `services/tag_cache.py`'s already-verified JSON-blob command shape. **No migration, no new table, no new secret, no new auth surface** — `users.city` already exists (`001_initial.sql:29`, literally commented `-- For weather API`) and is written by SS-004's onboarding Step 1.

This design deliberately places the fetch in the **FastAPI backend, not a Supabase Edge Function**, contradicting the raw ticket's opening sentence. That deviation is argued in full in "Concrete values" §1 and re-raised in Open Questions #1 — it is the single most consequential decision in this pass and the one the user should sanction or overrule.

## Verification of the ticket's own flagged assumptions

Four things the ticket told me to verify rather than assume. All four were checked against the repo as it stands on `develop` today (2026-08-14):

1. **`users.city` exists and is populated — CONFIRMED, with one caveat.** `supabase/migrations/001_initial.sql:29` declares `city TEXT` (nullable, no default) on `users`, with the inline comment `-- For weather API`. It is written by `mobile/features/onboarding/onboarding.service.ts::saveStep1Profile` on Step 1's "Next" (an incremental partial update, not deferred to "Get Started"), and read back by `fetchOnboardingProgress`. **Caveat that changes the design:** the value stored is the city's **display name** (`city.name`, e.g. `"Mumbai"`), not its `id` — see `mobile/features/onboarding/components/CityPicker.tsx:70` (`onSelect(city.name)`). And the picker has an **"Other" free-text row** (`CityPicker.tsx:53-56`) whose raw text is stored verbatim. So `users.city` is one of: `NULL`/`''` (skipped onboarding), one of the 50 names in `TOP_50_INDIAN_CITIES`, or arbitrary user-typed text. The design must handle all three, and cannot assume a joinable key.
2. **SS-020's prompt-building code — READ, not re-derived.** The narration prompt is `backend/ai/adapters/styling_prompt.py::build_narration_prompt` (+ the `NarrationPromptBuilder` Protocol), called through `IStylingProvider.narrate_candidates` → `StylingRouter.narrate_candidates_with_decision` → `OutfitPortfolioService._narrate`. Weather is threaded through that existing chain as an optional kwarg (§4), not bolted on elsewhere. **The finding that matters most:** `services/suggestion_narration_cache.py::compute_narration_signature` does *not* currently include any weather dimension, so putting weather in the prompt without also putting it in the cache key would serve rainy-day prose on a sunny day. §5 handles this.
3. **Open-Meteo — NOT VERIFIED in this pass.** This Architect session has no web-fetch tool. Every statement below about Open-Meteo's URL, query parameters, response shape, WMO weather-code table, and fair-use limits is `[trained-knowledge, NOT verified 2026-08-14]` and is written as a *proposal to verify*, never as fact. Developer must verify live against `https://open-meteo.com/en/docs` before hardcoding, and record `[VERIFIED <date>]` in `docs/worklog/SS-022.md` — the SS-029/SS-012 precedent for behavioural verification when no doc-fetch tool is available, and the `BL-001`/`BL-039` precedent for what happens when this is skipped. See Open Question #2.
4. **Upstash Redis infra exists and is reachable from the backend — CONFIRMED.** `UPSTASH_REDIS_REST_URL`/`UPSTASH_REDIS_REST_TOKEN` are consumed by four existing Python modules (`services/rate_limiter.py`, `services/tag_cache.py`, `services/circuit_breaker.py`, `adapters/upstash_rate_limiter.py`). Critically, `services/tag_cache.py` already does exactly the thing this ticket needs — cache an arbitrary **JSON blob** with a TTL — using Upstash's "POST command in body" form, with the command shapes `[VERIFIED 2026-07-25, upstash.com/docs/redis/features/restapi.md]` in that module's own docstring. `WeatherCache` mirrors it verbatim, so this ticket introduces **zero unverified Redis surface**. Note the asymmetry that drives §1: this infra is Python-side only — a Deno Edge Function would need its own client, its own env wiring, and its own re-verification.
5. **Both failure modes degrade — designed for explicitly.** §6 and the Edge Cases section. The single invariant: `resolve_weather()` returns `WeatherContext | None` and **never raises**; every consumer treats `None` as "today's pre-SS-022 behaviour, byte-for-byte."
6. **"Heavy rain → no white or silk" has a code-level mechanism, not a prompt hint.** §3. It reuses `engine_v2_eligibility.filter_eligible`'s existing hard-exclusion stage — the same one that already enforces `wedding_guest` → no white via `item_is_hard_excluded_white` — so the AC is provable by unit test on a pure function, not inferred from LLM output.

## Files to create/modify

### Backend — new files

| Path | Contents |
|---|---|
| `backend/services/india_city_coordinates.py` | `CITY_COORDINATES: dict[str, tuple[float, float]]` — the 50 rows of `mobile/features/onboarding/onboarding.constants.ts::TOP_50_INDIAN_CITIES` transcribed **verbatim** (keyed by normalised name), plus `CITY_ALIASES` and `resolve_city(raw: str | None) -> ResolvedCity | None`. Pure, no I/O. See §2. |
| `backend/services/weather_rules.py` | Pure. `WeatherContext` model, `WEATHER_CODE_TO_CONDITION`, `is_heavy_rain()`, `weather_excluded_color_families()`, `weather_excluded_fabrics()`, `weather_cache_bucket()`, `render_weather_for_prompt()`. Every weather→behaviour decision in this ticket lives here and nowhere else. See §3/§4/§5. |
| `backend/adapters/open_meteo_weather_adapter.py` | `OpenMeteoWeatherAdapter(IWeatherProvider)` — one `httpx` GET, 3.0s timeout, no retry, **never raises** (returns `None`). See §2. |
| `backend/services/weather_cache.py` | `WeatherCache` — Upstash JSON-blob cache, a near-verbatim structural copy of `services/tag_cache.py` (same `_command()` POST-command-in-body helper, same fail-open posture). See §2. |
| `backend/services/weather_service.py` | `WeatherService.resolve_for_user(*, jwt, user_id) -> WeatherContext \| None` — city read → cache get → adapter fetch → cache put → `WeatherContext`. The one never-raising, timeout-capped entry point the portfolio service calls. See §2. |

### Backend — modified files (all additive; every new parameter defaults to today's behaviour)

- **`backend/adapters/interfaces.py`** — add `WeatherObservation` (frozen dataclass: raw provider output) + `IWeatherProvider` ABC; add `IWardrobeRepository.get_city(*, jwt, user_id) -> str | None` (abstract). Placement follows this file's own documented precedent for non-AI infrastructure ports (`IRateLimiter`, `ICostLedger`, `IFabricRegistryRepository`) — **not** `ai/ports/interfaces.py`, which that file's own comment scopes to "AI *provider capabilities*."
- **`backend/adapters/wardrobe_repository.py`** — implement `get_city` (`select city from users`, RLS-scoped via the caller's own JWT, mirroring `get_plan_tier`/`get_style_preferences` exactly — never `service_role`).
- **`backend/services/app_config_specs.py`** — add `WeatherHeavyRainConfig` + `WEATHER_HEAVY_RAIN_SPEC` (coded default, **no seed migration** — SS-026's documented "missing row degrades to the coded default" pattern). See §3.
- **`backend/services/styling_rules_types.py`** — `GapReport` gains `weather_exclusions_relaxed: bool = False` (additive, defaulted; no existing assertion changes).
- **`backend/services/engine_v2_types.py`** — `EligibilityResult` gains `weather_exclusions_relaxed: bool = False`.
- **`backend/services/engine_v2_eligibility.py`** — `filter_eligible(..., weather: WeatherContext | None = None)`. The whole AC-3 mechanism. See §3.
- **`backend/services/engine_v2.py`** — `generate_portfolio(..., weather: WeatherContext | None = None)`, forwarded to `filter_eligible` and folded into the `GapReport` it builds. Fourth additive widening of this method (SS-020 added five kwargs, SS-023 added one) — same established pattern, `None` reproduces pre-SS-022 output byte-for-byte.
- **`backend/services/outfit_portfolio_service.py`** — kick off `asyncio.create_task(weather_service.resolve_for_user(...))` as the first statement, `await` it just before the engine call; forward to the engine, the narration path, the cache signature, and the response dict. Constructor gains `weather_service: WeatherService`. See §6.
- **`backend/services/suggestion_narration_cache.py`** — `compute_narration_signature(..., weather_bucket: str)` — a new **required** keyword arg. See §5 and Open Question #3.
- **`backend/ai/adapters/styling_prompt.py`** — `build_narration_prompt(..., weather: dict[str, Any] | None = None)` + the matching `NarrationPromptBuilder` Protocol widening, + two new lines in `_NARRATION_INSTRUCTIONS`. See §4.
- **`backend/ai/ports/interfaces.py`** — `IStylingProvider.narrate_candidates(..., weather: dict[str, Any] | None = None)`.
- **`backend/ai/adapters/mock_styling_adapter.py`**, **`gemini_styling_adapter.py`**, **`claude_styling_adapter.py`** — accept and forward `weather` (plus each adapter's `narrate_candidates_with_metrics` sibling). Mechanical; no schema/SDK change (weather only enters the prompt *text*, never the structured-output schema).
- **`backend/services/styling_router.py`** — `narrate_candidates` / `narrate_candidates_with_decision` accept and forward `weather` to both the chain call and the `_degrade` fallback.
- **`backend/routers/outfit_suggestions.py`** — add `WeatherResponse` Pydantic model; `GeneratePortfolioResponse.weather: WeatherResponse | None = None`; a `get_weather_service()` `Depends()` provider alongside the existing ones; wire it into `get_outfit_portfolio_service`.

### Frontend — new files

- `mobile/features/outfit-ai/weather.format.ts` — pure `formatWeatherChipLabel(weather) -> string`. Split out from the component specifically so the copy is unit-testable without rendering.
- `mobile/features/outfit-ai/components/WeatherChip.tsx` — wraps `components/ui/Badge`; renders nothing (`null`) when `weather` is `null`.

### Frontend — modified files

- `mobile/features/outfit-ai/outfit-ai.types.ts` — `WeatherCondition` union, `WeatherResponse`, `GeneratePortfolioResponse.weather: WeatherResponse | null`, `GapReport.weather_exclusions_relaxed: boolean`. Mirrors the backend Pydantic models verbatim, per that file's own header rule.
- `mobile/features/outfit-ai/outfit-ai.constants.ts` — `WEATHER_CONDITION_LABELS`, `WEATHER_CHIP_PREFIX`.
- `mobile/app/(tabs)/style.tsx` — render `<WeatherChip weather={result.weather} />` inside the existing `result && selectedOccasionKey` branch, above `<OutfitCardDeck …>`. No other branch changes; the occasion-grid, loading, error and zero-wardrobe branches are untouched.

### Explicitly NOT created

- **No `supabase/functions/weather/`** — see §1.
- **No migration.** No new table, no column, no RLS policy, no seed. A `cities` reference table (the eventual right home for the coordinate data, alongside `occasions`/`fabrics`/`garment_types`) is out of scope and logged as `BL-151`.
- **No new env var / secret.** Open-Meteo needs no key; Upstash's two vars are already provisioned and in use by four modules.

## Concrete values to use, not invent

### §1. Placement: FastAPI backend, not a Supabase Edge Function

The raw ticket says "Supabase Edge Function calls the Open-Meteo API." **This design puts the fetch in the FastAPI backend instead.** Five reasons, in descending weight:

1. **Untrusted input into a hard exclusion.** If an Edge Function serves weather to the *client*, the client must then pass it back to `/portfolio` for the AI and the exclusion rules to use it — which means a user-supplied `condition: "clear"` can switch off a styling rule, and a user-supplied string reaches an LLM prompt. Fetching server-side inside the same request makes that structurally impossible. (Having the *backend* call the Edge Function instead avoids the trust problem but adds an HTTP hop, a second auth boundary, and a second failure mode to a latency-AC'd endpoint, for zero gain.)
2. **Everything it must integrate with is Python.** The prompt builder, the narration cache signature, Engine v2's eligibility stage, and the Upstash client all live in `backend/`. An Edge Function would duplicate the Upstash client, the city→coordinate table, and the WMO-code mapping in Deno, then need all three kept in sync with the Python copies.
3. **One source of truth for the chip.** Because the weather block is part of the `/portfolio` response, the chip the user sees is provably the same data the exclusion rules and the prompt used. Two independent fetches (client-side chip + server-side rules) could disagree across an hour boundary — a visible, hard-to-debug inconsistency.
4. **`BL-042`** — no CI job runs Deno tests. A new Edge Function would ship with no CI-enforced coverage; the Python path is covered by the existing `backend-quality` job on every PR.
5. **`BL-045`** — Edge Function invocations have no rate limiting, and each is separately billed. A backend call reuses the request the user already made.

**Reversibility:** the fetch sits behind `IWeatherProvider`. If the Edge Function placement is later wanted (e.g. to serve weather to a screen that doesn't call `/portfolio`), it's a new adapter implementing the same port, not a rewrite. This is why it isn't a one-way door.

**What choosing Python costs (stated, not hidden):** per `BL-037` the backend is not deployed anywhere, so weather — like `/portfolio` itself — only works against a locally-running `uvicorn` today. This adds no *new* gap (the endpoint being enriched already has it), but it does forgo the one property an Edge Function would have had: being deployable right now.

### §2. Fetching, resolving and caching

**City resolution** (`services/india_city_coordinates.py`, pure):

```python
@dataclass(frozen=True)
class ResolvedCity:
    slug: str        # "mumbai" -- cache-key component, never user-facing
    name: str        # "Mumbai" -- the display name echoed in the response
    lat: float
    lng: float

def _normalise(raw: str) -> str:   # raw.strip().casefold(), spaces/hyphens -> "_", collapse repeats
def resolve_city(raw: str | None) -> ResolvedCity | None
```

- `CITY_COORDINATES` is the 50 rows of `TOP_50_INDIAN_CITIES` **transcribed verbatim** (`id`, `name`, `lat`, `lng`) from `mobile/features/onboarding/onboarding.constants.ts:57-384`. Do not re-derive coordinates from another source; do not round them.
- Matching is on the normalised **name** (that's what `users.city` stores), with the `id` accepted as a fallback key (they coincide for most rows, and `kalyan_dombivli`/`pimpri_chinchwad`/`vasai_virar` normalise identically either way).
- `CITY_ALIASES` — a short, explicit map for the renamed-city case, since a user typing free text will use the old name: `bangalore→bengaluru`, `bombay→mumbai`, `calcutta→kolkata`, `madras→chennai`, `poona→pune`, `baroda→vadodara`, `mysore→mysuru`(absent → no match, fine), `gurgaon`/`noida`/`new_delhi`→`delhi` (NCR; a deliberate approximation — same weather within a few km), `trivandrum→thiruvananthapuram`, `vizag→visakhapatnam`, `allahabad→prayagraj`, `cochin`/`kochi`→ absent, no match.
- **Unknown/free-text city → `None`.** No geocoding fallback. This is the same graceful path as "no city at all" (`BL-152`).
- **No network geocoding call.** Rejected deliberately: it adds a second external dependency, a second failure mode, and unbounded/ambiguous results for arbitrary user text, to serve a picker that is 50 fixed rows plus an "Other" escape hatch.

**Provider port** (`adapters/interfaces.py`):

```python
@dataclass(frozen=True)
class WeatherObservation:
    temp_c: float
    humidity: int          # relative humidity %
    weather_code: int      # WMO code, raw
    precipitation_mm: float
    observed_at: str       # ISO-8601 as returned by the provider

class IWeatherProvider(ABC):
    @abstractmethod
    async def fetch_current(self, *, lat: float, lng: float) -> WeatherObservation | None:
        """MUST NEVER RAISE -- every timeout/HTTP/parse failure returns None.
        Same never-raise contract as ISuggestionLogRepository and
        ISuggestionNarrationCacheRepository (SS-020)."""
```

**`OpenMeteoWeatherAdapter`** — `[trained-knowledge, NOT verified 2026-08-14; Developer MUST verify live and record `[VERIFIED <date>]` in the worklog — Open Question #2]`:

```
GET https://api.open-meteo.com/v1/forecast
    ?latitude={lat}&longitude={lng}
    &current=temperature_2m,relative_humidity_2m,weather_code,precipitation
    &timezone=Asia%2FKolkata
-> {"current": {"time": "2026-08-14T13:00", "temperature_2m": 28.4,
                "relative_humidity_2m": 71, "weather_code": 3,
                "precipitation": 0.0}, ...}
```
- Base URL in a module constant, overridable via an optional `OPEN_METEO_BASE_URL` env var **for tests only** (unset in production; not a secret, not required, not added to `.env.example` as a mandatory key).
- `httpx.AsyncClient(timeout=3.0)` — deliberately tighter than the 5.0s every other client in this repo uses, because unlike them this call sits on the synchronous critical path of an endpoint with a stated latency AC. No retry (a retry would double the worst case for a purely decorative-plus-advisory signal).
- Every `httpx.HTTPError` / `ValueError` / `TypeError` / `KeyError` → log `open_meteo_fetch_failed` at WARNING and return `None`.

**`WeatherCache`** (`services/weather_cache.py`) — structural copy of `services/tag_cache.py`:
- Key: `weather:v1:{city_slug}:{ist_hour}` where `ist_hour = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%dT%H")` (the same inline-`_IST` idiom `DailyRateLimiter` already uses).
- `SET … EX 3600` via the POST-command-in-body form (`["SET", key, json.dumps(payload), "EX", "3600"]`) — belt and braces: the key rolls at the hour boundary *and* expires. This is literally the ticket's "cached per city per hour."
- `GET` returns the JSON blob; a corrupt/non-dict entry logs `weather_cache_corrupt_entry` and is treated as a miss.
- **Fails open in both directions**: unset env / HTTP error / bad JSON → `get` returns `None` (fetch fresh), `set` is a silent no-op. Never raises.
- **Cache-miss stampede is accepted, not solved.** N concurrent first-requests for the same city in the same hour each fetch once. Open-Meteo is free and idempotent, the worst case is ~50 cities × 24 h ≈ 1,200 calls/day against a fair-use allowance believed to be far larger `[trained-knowledge, unverified]`. `tag_cache.py`'s `mark_inflight` NX-marker pattern is available if this ever matters — deliberately not built here (`BL-045`-class complexity for no current benefit).

**`WeatherService.resolve_for_user`** — the orchestrator, and the only thing the portfolio service knows about:
1. `raw_city = await wardrobe_repo.get_city(jwt=jwt, user_id=user_id)`
2. `city = resolve_city(raw_city)`; `None` → return `None` (log `weather_skipped_no_city` at INFO, not WARNING — this is a normal state, not a fault).
3. `cached = await cache.get(city.slug)`; hit → build `WeatherContext` from it.
4. Miss → `obs = await provider.fetch_current(lat, lng)`; `None` → return `None`.
5. `await cache.set(city.slug, obs)` (best-effort), return `WeatherContext`.
- The **entire body** is wrapped in `try/except Exception` → log + return `None`, and the *whole call* is additionally wrapped by the caller in `asyncio.wait_for(..., timeout=4.0)` (cache round-trip + provider round-trip + DB read, with headroom over the 3.0s provider timeout). A `TimeoutError` is caught and degrades to `None`. **This method can only ever return a `WeatherContext` or `None`. It cannot raise, and it cannot hang the request.**

**`WeatherContext`** (`services/weather_rules.py`) — the derived, in-app shape:

```python
class WeatherContext(BaseModel):
    city: str                # display name, e.g. "Mumbai"
    temp_c: float
    condition: WeatherCondition   # canonical, see below
    humidity: int
    is_heavy_rain: bool
    observed_at: str
```

### §3. AC #3 — "Heavy rain → no white or silk," as a code-level filter

**Canonical condition vocabulary** (closed set, shared by backend and mobile): `clear` · `partly_cloudy` · `cloudy` · `fog` · `drizzle` · `rain` · `heavy_rain` · `thunderstorm` · `snow`.

**WMO code → condition** `[trained-knowledge, NOT verified 2026-08-14 — Developer must confirm against Open-Meteo's own published code table before hardcoding]`:

| WMO code(s) | condition |
|---|---|
| 0 | `clear` |
| 1, 2 | `partly_cloudy` |
| 3 | `cloudy` |
| 45, 48 | `fog` |
| 51, 53, 55, 56, 57 | `drizzle` |
| 61, 63, 66, 67, 80, 81 | `rain` |
| 65, 82 | `heavy_rain` |
| 71, 73, 75, 77, 85, 86 | `snow` |
| 95, 96, 99 | `thunderstorm` |
| anything else / missing | `cloudy` (neutral fallback — never raise on an unknown code) |

**Heavy-rain predicate** — the single decision AC #3 hangs on:

```python
_HEAVY_RAIN_CODES = frozenset({65, 82, 95, 96, 99})   # heavy rain, violent showers, all thunderstorm

def is_heavy_rain(obs, *, precip_threshold_mm_per_hour: float) -> bool:
    return obs.weather_code in _HEAVY_RAIN_CODES or obs.precipitation_mm >= precip_threshold_mm_per_hour
```

`precip_threshold_mm_per_hour` comes from `app_config`, coded default **7.6** — an Architect inference (the commonly-cited "heavy rain" hourly rate), **not** a verified IMD/WMO standard, in exactly the same unvalidated class as `ENGINE_V2_RULE_WEIGHTS` and the near-white thresholds before it. Folded into `BL-077`'s eventual quality eval, not blocking:

```python
class WeatherHeavyRainConfig(BaseModel):
    precip_mm_per_hour: float = 7.6

WEATHER_HEAVY_RAIN_SPEC: ConfigSpec[WeatherHeavyRainConfig] = ConfigSpec(
    key="weather_heavy_rain_threshold",
    model=WeatherHeavyRainConfig,
    default=WeatherHeavyRainConfig(),
)
```
No seed migration: `AppConfigService.read` degrades to the coded default when the row is absent (SS-026's pattern, same as `GEMINI_QUOTA_CEILING_SPEC` which is likewise unseeded). The snapshot is already fetched inside `EngineV2.generate_portfolio` and by the router dependency, so no extra I/O.

**Exclusion sets:**

```python
WEATHER_EXCLUDED_COLOR_FAMILIES: dict[str, frozenset[str]] = {"heavy_rain": frozenset({"white"})}
WEATHER_EXCLUDED_FABRICS:        dict[str, frozenset[str]] = {"heavy_rain": frozenset({"silk"})}
```
Keyed by a *condition-class* string (`"heavy_rain"` when `is_heavy_rain` else `"other"`) rather than by raw code, so the table stays readable and a future "no suede in the rain" row is a one-line addition.

**Where they are applied** — `engine_v2_eligibility.filter_eligible`, the existing hard-constraint stage, extended additively:

```python
def filter_eligible(wardrobe, occasion, rules, *, near_white_thresholds,
                    weather: WeatherContext | None = None) -> EligibilityResult:
```
1. Everything currently in that function runs unchanged, producing `eligible` (call it `pre_weather`).
2. If `weather is not None and weather.is_heavy_rain`:
   - **White:** union `{"white"}` into the already-computed `effective_excluded` set **before** the existing `if "white" in effective_excluded:` branch. This means the near-white guard reuses `engine_v2_colour.item_is_hard_excluded_white` and the app_config/per-occasion HSV thresholds **verbatim** — there is exactly one definition of "white" in this codebase and this ticket does not add a second. Cream/ivory/off-white are therefore excluded too, for free, and consistently with `wedding_guest`.
   - **Silk:** drop any item whose `fabric` is in `WEATHER_EXCLUDED_FABRICS["heavy_rain"]`. **Exact string equality against the canonical `fabrics.key` — no fuzzy matching needed**, because `wardrobe_items.fabric` is normalised to a canonical key on every INSERT/UPDATE by `trg_wardrobe_items_normalize_pattern_fabric_ins`/`_upd` (migration `016`), with `fabric_aliases` already mapping `pure_silk`, `raw_silk`, `tussar_silk`, `banarasi_silk` → `silk`. Note the deliberate consequence: `art_silk` maps to `rayon` (artificial silk) and is **not** excluded — correct, it is not silk. Compare case-insensitively anyway as belt-and-braces for any pre-`016` unnormalised row.
3. **Relax-if-empty guardrail (mandatory).** If the post-weather set is empty and `pre_weather` was non-empty, **discard the weather exclusions entirely**, return `pre_weather`, and set `weather_exclusions_relaxed=True`. A monsoon user whose wardrobe is mostly white and silk must still get suggestions — degraded advice beats an empty screen. The flag propagates `EligibilityResult` → `GapReport` → the API response so the behaviour is observable rather than mysterious.
   - Scope note: the guardrail is deliberately **all-or-nothing at the item-pool level**, not per-slot. A per-slot relaxation ("only relax for footwear") is finer-grained but needs slot-aware logic in a stage that is currently slot-agnostic; the existing `missing_slots` gap-report signal already surfaces the "no eligible footwear" case downstream.

**Why not a prompt instruction:** the LLM only ever *narrates* candidates Engine v2 already assembled (`narrate_candidates`' contract: "MUST NEVER invent an item"). A prompt hint therefore cannot remove a white silk saree from the deck — only the eligibility stage can. Putting the rule in code also makes AC #3 provable by a pure unit test with no provider call.

### §4. AC #2 — weather in the narration prompt

`build_narration_prompt` gains `weather: dict[str, Any] | None = None`, rendered by `render_weather_for_prompt(ctx)` into a compact block appended after the preferences block:

```
Current weather where the user is: 28°C, partly cloudy, humidity 71%.
```
and, when `is_heavy_rain`, one extra line:
```
It is raining heavily -- white and silk items have ALREADY been removed from the candidates below; do not mention their absence.
```
Two new standing lines in `_NARRATION_INSTRUCTIONS` (only emitted when a weather block is present):
- `- Take the weather into account in your rationale (comfort, breathability, layering) where it is genuinely relevant. Do not force a weather mention into every rationale.`
- `- Do NOT quote a specific temperature or humidity figure in your rationale — the app displays those separately.` **This line is load-bearing, not stylistic:** it is what makes a cached narration safe to reuse across a coarse temperature band (§5). It is the exact analogue of the existing "keep each rationale generic enough to be true regardless of exact colour shade" instruction that already makes the colour coarsening safe.

Threading: `OutfitPortfolioService._narrate` → `StylingRouter.narrate_candidates_with_decision(weather=…)` → each adapter's `narrate_candidates(weather=…)` → `build_narration_prompt(weather=…)`. All optional kwargs defaulting to `None`.

**Rejected alternative:** injecting the weather line into each rendered candidate dict, which would avoid touching the port. Rejected because it duplicates the same text N times in the payload (directly worsening `BL-130`'s size budget, per candidate, N times over) and because it corrupts `render_candidate_for_prompt`'s documented contract of describing *one candidate*.

### §5. The narration cache key must include weather

`compute_narration_signature` gains a **required** keyword arg `weather_bucket: str`, spliced into the existing shape string:

```python
shape_string = f"{occasion_key}|{engine_version}|{llm_candidate_count}|{weather_bucket}|" + "||".join(...)
```

```python
def weather_cache_bucket(weather: WeatherContext | None) -> str:
    if weather is None:
        return "none"
    if weather.is_heavy_rain:
        return "heavy_rain"
    wet = weather.condition in {"drizzle", "rain", "thunderstorm", "snow"}
    band = int(round(weather.temp_c / 5.0) * 5)     # 5-degree bands
    return f"{'wet' if wet else 'dry'}:{band}"
```
Coarse on purpose — three condition classes × ~8 realistic Indian temperature bands — so cross-user cache sharing (the entire economic point of SS-020's cache) survives. Humidity is deliberately **excluded** from the bucket: it varies almost continuously and would shatter the key space; the prompt still receives the exact figure, and §4's "do not quote a figure" instruction keeps the shared prose honest.

**Consequence, stated loudly** (SS-020's design doc §Test-plan explicitly asked for this to be flagged rather than silently updated): adding a segment to the shape string changes **every** signature. Every existing `suggestion_narration_cache` row becomes unreachable. This is safe and self-healing — those rows carry a ≤6 h TTL (`SUGGESTION_NARRATION_CACHE_TTL_SPEC`) and are swept by the migration-`019` `pg_cron` job — so there is no data loss, no migration, and no correctness window; the only cost is a one-time cold cache. SS-020's golden-file signature test **must** be updated in this ticket's PR, and the PR description must say so explicitly. See Open Question #3.

### §6. Wiring in `OutfitPortfolioService`, and latency

```python
# first statement of generate_portfolio_for_request
weather_task = asyncio.create_task(self._resolve_weather(jwt=jwt, user_id=user_id))
...                                    # existing occasion/wardrobe/prefs/tier reads, untouched
weather = await weather_task           # immediately before the engine call
```
- `_resolve_weather` = `asyncio.wait_for(self._weather_service.resolve_for_user(...), timeout=4.0)` inside a `try/except (Exception, asyncio.TimeoutError)` → `None`.
- **Why a task rather than a plain `await`:** the weather round-trips (Supabase `users` read + Redis + possibly Open-Meteo) then overlap the four reads SS-020 already performs, so the added wall-clock cost on a warm cache is ~0 and on a cold fetch is bounded by whatever the existing reads don't already cover. This is a two-line change; it does **not** restructure SS-020's existing sequential awaits into a `gather` (a larger diff on a shipped, `PASS`-verdict file for marginal gain).
- SS-020's "cache hit < 200 ms" AC must not regress. The weather path on a warm hour-cache is one Upstash GET plus one `users` SELECT, fully overlapped. Developer must re-measure and record the number, not assume it (the `BL-058`/`BL-067` precedent for latency claims).
- Forwarding: `weather` → `generate_portfolio(weather=weather)`; `weather_cache_bucket(weather)` → `compute_narration_signature`; `render_weather_for_prompt(weather)` → `_narrate` → router → adapters; `weather.model_dump()` → the response dict's `"weather"` key (`None` when absent).

### §7. The chip (AC #4)

Response model:
```python
class WeatherResponse(BaseModel):
    city: str
    temp_c: float
    condition: Literal["clear","partly_cloudy","cloudy","fog","drizzle","rain","heavy_rain","thunderstorm","snow"]
    humidity: int
    is_heavy_rain: bool
```
`GeneratePortfolioResponse.weather: WeatherResponse | None = None`.

Copy (`outfit-ai.constants.ts`):
```ts
export const WEATHER_CHIP_PREFIX = 'Dressing for';
export const WEATHER_CONDITION_LABELS: Record<WeatherCondition, string> = {
  clear: 'clear',            partly_cloudy: 'partly cloudy', cloudy: 'cloudy',
  fog: 'foggy',              drizzle: 'drizzly',             rain: 'rainy',
  heavy_rain: 'heavy rain',  thunderstorm: 'thunderstorms',  snow: 'snow',
};
```
`formatWeatherChipLabel({temp_c, condition})` → `` `${WEATHER_CHIP_PREFIX} ${Math.round(temp_c)}°C, ${WEATHER_CONDITION_LABELS[condition]}` `` → **"Dressing for 28°C, partly cloudy"**, matching the ticket's own example string verbatim. `Math.round` (not `toFixed`) — no decimal on a chip. No `en-IN` number formatting needed for a 2-digit integer; the ₹/`en-IN` rules in CLAUDE.md govern currency and dates, neither of which appears here.

`WeatherChip` renders `<Badge>` from `components/ui` (never a bare `View`/`Text`, per CLAUDE.md), `testID="weather-chip"`, and returns `null` when `weather` is `null` — no placeholder, no skeleton, no "weather unavailable" copy. Silent absence is the designed degradation.

## Edge cases

**Carried forward from the raw ticket (both):**

- **User has no saved city** — `users.city` is `NULL` or `''` (onboarding skipped, or Step 1 abandoned before "Next"). `resolve_city` returns `None`, `resolve_for_user` returns `None`, and every downstream consumer takes the `weather is None` path: no exclusions, no prompt block, `weather_bucket="none"`, no chip. The response is byte-identical to today's. Logged at INFO, never WARNING.
- **Open-Meteo unavailable** (timeout, 5xx, DNS, malformed body, unknown response shape) — the adapter returns `None`, nothing is cached, the request proceeds exactly as the no-city case. Never a retry, never a 5xx to the caller.

**New, from the current codebase state:**

- **`users.city` holds free text from the "Other" row** (`CityPicker.tsx:53-56` writes raw input verbatim, and `handleOtherTextChange` fires `onSelect` on *every keystroke*, so a partial string like `"Kanp"` can legitimately be persisted if the user navigates away mid-type). Unresolvable → `None`, same graceful path. `BL-152`.
- **`users.city` holds a renamed/colloquial city** ("Bangalore", "Bombay", "Gurgaon") — handled by `CITY_ALIASES`; anything not in that short list degrades to no-weather rather than to a wrong city. Never fuzzy-match to a "nearest" name: silently reporting Kanpur's weather to someone in Kannur is worse than no chip.
- **Heavy rain, and the weather exclusions would empty the wardrobe** — relax-if-empty (§3 step 3), `weather_exclusions_relaxed=True`. Must be a test, not a hope.
- **Heavy rain, and the wardrobe was *already* empty/ineligible** — `pre_weather` is empty too, so the guardrail does **not** fire (it requires `pre_weather` non-empty). `weather_exclusions_relaxed` stays `False` and `limited_options` behaves exactly as today. The flag must mean "we relaxed a rule," never "you own nothing."
- **`wardrobe_items.fabric` is `NULL` or an unknown/unnormalised value** — never excluded (only exact membership in the excluded set excludes). Items with no fabric survive heavy rain, which is the safe direction.
- **`art_silk` / `rayon`** — normalised to `rayon` by migration `016`'s alias table, therefore **not** excluded. Deliberate and correct; assert it in a test so a future contributor doesn't "fix" it.
- **Hour boundary between two requests** — the cache key embeds the IST hour, so the first request after `:00` refetches. Two requests seconds apart across a boundary can legitimately show a 1°C difference. Accepted; not worth a lock.
- **Clock/timezone** — the key and the `timezone=Asia/Kolkata` query param both use IST, matching CLAUDE.md's India rules. A user physically outside India still gets their saved Indian city's weather; the app has no other location signal (no geolocation permission is requested anywhere in this repo).
- **Upstash env vars unset** (a fresh clone, or CI) — `WeatherCache` fails open: every request fetches fresh from Open-Meteo. Correct behaviour, more calls. Unit tests must not require Redis.
- **A previously-cached blob's schema changes** — the key carries a `v1` segment; any future field change bumps it to `v2` rather than trying to migrate blobs.
- **Weather is present but the narration LLM is never called** (E0 tier, or budget-denied — `tier_params.llm_candidate_count is None`) — exclusions and the chip still apply; only the prompt block is skipped, since there is no prompt. AC #1, #3 and #4 hold on the free tier; AC #2 is vacuous there by construction.
- **Cache hit on a narration generated in a *different* temperature band** — impossible by construction after §5 (the band is in the key). Within the same band, §4's "do not quote a figure" instruction is what keeps the shared prose true.
- **Provider returns a plausible but absurd value** (e.g. `temp_c: -50` for Chennai, or `humidity: 150`) — no sanity clamping is performed, deliberately: an out-of-range value can only make the chip look odd, never break a rule (only `weather_code`/`precipitation` drive exclusions). Flagged rather than silently defended.
- **A malformed `weather` block cannot break the response** — `WeatherResponse` is a `Literal`-constrained Pydantic model; an unmappable WMO code has already degraded to `cloudy` in the mapping table, so validation cannot fail at the router boundary.

## Test plan

### Backend (Pytest, `backend/tests/`)

**`test_india_city_coordinates.py`**
- Every one of the 50 `TOP_50_INDIAN_CITIES` display names resolves (parametrised over the transcribed table) — the direct guard against a transcription typo.
- `"  mumbai "`, `"MUMBAI"`, `"Mumbai"` all resolve to the same `ResolvedCity`.
- `"Bangalore"` → `bengaluru`; `"Bombay"` → `mumbai`; `"Gurgaon"` → `delhi`.
- `None`, `""`, `"   "`, `"Kanp"`, `"Springfield"` → `None`.
- `"Pimpri-Chinchwad"` and `"pimpri_chinchwad"` resolve identically (hyphen/underscore normalisation).

**`test_weather_rules.py`** — the AC-3 proof, all pure:
- WMO code → condition for every row of §3's table, plus an unknown code (`999`) → `cloudy`, and a `None`/missing code → `cloudy`.
- `is_heavy_rain` is `True` for codes 65/82/95/96/99 and for `precipitation_mm=8.0` at the default threshold; `False` for code 61 with `precipitation_mm=1.0`.
- `is_heavy_rain` honours a non-default `precip_threshold_mm_per_hour` (proves the app_config wiring is real, not decorative).
- `weather_excluded_color_families` / `_fabrics` return `{"white"}` / `{"silk"}` only when `is_heavy_rain`, and empty sets for `rain`, `drizzle`, `thunderstorm`-without-heavy, `clear`.
- `weather_cache_bucket`: `None` → `"none"`; heavy rain → `"heavy_rain"`; 28 °C clear → `"dry:30"`; 29 °C clear → `"dry:30"` (same band, proving coarsening); 22 °C clear → `"dry:20"` (different band); 28 °C rain → `"wet:30"` (condition class flips the bucket at the same temperature).
- `render_weather_for_prompt` includes the temp/condition/humidity, and emits the extra "already removed" line **only** when `is_heavy_rain`.

**`test_engine_v2_eligibility_weather.py`** — the acceptance criterion itself:
- **AC #3 (white):** heavy rain + a wardrobe containing `#FFFFFF` and `#FFFEF8` (near-white/ivory) items → both excluded; the same wardrobe with `weather=None` → both retained. Proves reuse of `item_is_hard_excluded_white`, not a second white definition.
- **AC #3 (silk):** heavy rain + items with `fabric="silk"` → excluded; `fabric="cotton"` → retained; `fabric="rayon"` (i.e. what `art_silk` normalises to) → **retained**; `fabric=None` → retained; `fabric="SILK"` → excluded (case-insensitive belt-and-braces).
- Non-heavy rain (`condition="rain"`, `is_heavy_rain=False`) excludes **nothing** — the rule fires on heavy rain only, per the AC's literal wording.
- `weather=None` produces an `EligibilityResult` identical to the pre-SS-022 call for the same fixture (the byte-for-byte no-regression pin).
- **Relax-if-empty:** an all-white-silk wardrobe in heavy rain returns the *pre-weather* eligible set with `weather_exclusions_relaxed=True`; an already-empty wardrobe in heavy rain returns empty with `weather_exclusions_relaxed=False`.
- A `wedding_guest` occasion **plus** heavy rain excludes white exactly once (no double-filter crash, no interaction bug between the two sources of the same exclusion).

**`test_open_meteo_weather_adapter.py`** (mocked `httpx`, no network):
- A well-formed response body maps to the right `WeatherObservation` field-by-field.
- HTTP 500, a connect timeout, a read timeout, invalid JSON, a `200` with `{"current": {}}`, and a body missing `weather_code` each return `None` and **never raise**.
- The request URL contains the expected latitude/longitude/current/timezone parameters (pins the contract the live verification confirms).

**`test_weather_cache.py`** (mocked `httpx`):
- `set` issues a `["SET", key, <json>, "EX", "3600"]` body command; the key matches `weather:v1:{slug}:{YYYY-MM-DDTHH}` with the hour computed in IST (freeze the clock and assert the exact string).
- Round-trip: `set` then `get` returns the same payload.
- Unset env vars → `get` → `None`, `set` → no-op, neither raises.
- A corrupt (non-JSON, or JSON-but-not-a-dict) cached value → `get` returns `None`.

**`test_weather_service.py`** (fakes for repo/cache/provider):
- No city / empty city / unresolvable city → `None`, and the provider is **never called** (assert call count 0 — the "don't burn an API call on a user with no city" property).
- Cache hit → the provider is never called.
- Cache miss → provider called once, result written back to cache.
- Provider returns `None` → service returns `None`, and **nothing is written to the cache** (never cache a failure).
- The repository raising, the cache raising, and the provider raising each degrade to `None` rather than propagating.
- A provider that sleeps past the timeout → `None` within the bound (`asyncio` timeout test, not a wall-clock sleep in CI).

**`test_outfit_portfolio_service_weather.py`** (extends SS-020/SS-023's existing service fakes):
- Weather present → `generate_portfolio` receives it, `compute_narration_signature` receives the matching bucket, the narration path receives the rendered block, and the response dict's `"weather"` matches.
- Weather `None` → engine receives `weather=None`, signature receives `"none"`, prompt receives `None`, response `"weather"` is `None` — and the rest of the response is identical to the SS-023 baseline fixture.
- `WeatherService` raising / timing out → the request still returns a full `200` payload with `weather=None` (the headline degradation test).
- Two otherwise-identical requests in different temperature bands produce **different** signature hashes; in the same band, the **same** hash.

**`test_suggestion_narration_cache.py`** (extend the existing file):
- New dimension: signature changes with `weather_bucket`, holding everything else fixed.
- **Update the existing golden-file signature test** to its new expected value, with a comment naming SS-022 as the reason and pointing at §5. This is the "flag loudly" event SS-020's design doc anticipated — it must also appear in the PR description.

**Adapters/router/prompt (extend existing files):**
- `test_narrate_candidates_mock.py` / `_gemini.py` / `_claude.py`: `narrate_candidates` accepts `weather=None` (default) and a populated dict without changing the structured-output schema or the returned shape.
- `test_styling_router_narration.py`: `weather` is forwarded to the chain call **and** to the `_degrade` fallback.
- `test_outfit_suggestions_router_portfolio.py`: the response validates with `weather` present and with `weather=None`; a request from a user with no city returns `200` with `weather: null`.
- Prompt-size check (`BL-130`-adjacent): assert the rendered weather block is under 200 chars, and assert `render_candidate_for_prompt`'s per-candidate output is **unchanged** by this ticket (the weather text must never land inside a candidate dict).

### Frontend (Jest + RNTL, `mobile/__tests__/`)

- `features/outfit-ai/weather.format.test.ts` — `{temp_c: 28.4, condition: 'partly_cloudy'}` → exactly `"Dressing for 28°C, partly cloudy"` (the ticket's own literal string); `27.6` → `"28°C"` (rounding, no decimals); every `WeatherCondition` has a label (parametrised over the union, so a future condition can't silently render `undefined`).
- `features/outfit-ai/components/WeatherChip.test.tsx` — renders the label with `weather` present; renders **nothing** (`queryByTestId('weather-chip')` is `null`) when `weather` is `null`.
- `app/(tabs)/style.weather.test.tsx` — the deck branch shows the chip when the mocked `/portfolio` response includes `weather`, and shows the deck with no chip when it doesn't. Pins that a missing `weather` field never blanks the screen.

### Manual / live verification (must be recorded in `docs/worklog/SS-022.md`, not asserted)

1. **Open-Meteo contract** — one real `curl`/`httpx` call for Mumbai's coordinates, with the actual response body pasted into the worklog and labelled `[VERIFIED <date>]`. Confirm: parameter names, the `current` object's field names, that `weather_code` is the field name (not `weathercode`), and the units of `precipitation`. **This is a hard prerequisite for the WMO mapping table being correct**, not a nice-to-have.
2. **Fair-use limits** — check Open-Meteo's published free-tier limits and record them; confirm the per-city-per-hour cache keeps us comfortably inside.
3. **End-to-end** — with a real `users.city`, hit `POST /outfit-suggestions/portfolio` against local `uvicorn` and confirm the `weather` block, then hit it again and confirm the second call served from cache (assert on the Upstash key's existence/TTL, not on wall-clock timing alone).
4. **Latency** — record the measured cache-warm end-to-end latency before and after this ticket, to show SS-020's "<200 ms cache hit" AC hasn't regressed. Measured, not inferred (`BL-058`/`BL-067` precedent).

## Open questions / blockers

1. **Backend vs. Edge Function — a direct, deliberate contradiction of the raw ticket's own first sentence.** The ticket says "Supabase Edge Function calls the Open-Meteo API"; §1 argues for FastAPI on five grounds, the strongest being that an Edge-Function-plus-client round trip would let untrusted client input drive a styling exclusion and reach an LLM prompt. **This is the one decision worth a human nod before Developer starts** (it is not a blocker — the design is complete and internally consistent either way — but overruling it later costs the whole backend implementation). Not silently picked: raised here, in the Scope restatement, and in the final message.
2. **Open-Meteo's API contract is unverified in this pass.** No web-fetch tool was available to this Architect session, so §2's URL/params/response shape and §3's WMO-code table are `[trained-knowledge, NOT verified 2026-08-14]`. Developer must verify live and record `[VERIFIED <date>]` before hardcoding — including the exact field spelling (`weather_code` vs. `weathercode` differ between Open-Meteo's older and newer parameter styles) and `precipitation`'s unit. `BL-001`/`BL-039` are the standing precedent for what skipping this costs. **Not a blocker to starting**, but it is a blocker to QA passing AC #1.
3. **Changing `compute_narration_signature` invalidates SS-020's live narration cache.** Adding the `weather_bucket` segment changes every hash, so every existing `suggestion_narration_cache` row becomes unreachable and ages out on its ≤6 h TTL. No data loss, no migration, no correctness window — but SS-020's design named its cache key as a "must be right the first time" one-way door, and its golden-file signature test must be updated in this PR. **Flagging, per SS-020's own explicit instruction to flag rather than silently update.** The alternative (leave weather out of the key) is rejected outright: it would serve monsoon prose on a clear day, which is a user-visible correctness bug, not a cost trade.
4. **`precip_mm_per_hour = 7.6` is an Architect judgment call, not a verified standard.** Same unvalidated class as `ENGINE_V2_RULE_WEIGHTS` / the near-white HSV thresholds / `fabric_weather_score`'s breathability cut-offs. It is `app_config`-tunable without a deploy, so it's cheap to correct — but if the user has a view on "what counts as heavy rain in an Indian monsoon," now is the moment. Folds into `BL-077`'s eventual quality eval.
5. **"No white or silk" is the ticket's own rule, transcribed, not a validated styling rule.** Silk in heavy rain is a defensible real-world call (water-spotting); white is more debatable (the actual concern is translucency when wet, which correlates with fabric more than colour). Transcribed verbatim from the AC rather than re-litigated, but worth a product sanity-check — it is the first weather-driven rule in the app and sets the pattern. Logged as part of `BL-153`.
6. **The weather chip's copy is English-only**, while the narration it sits above can already return Hindi (`rationale_language: 'hi'`). No i18n layer exists in `mobile/` at all, so this ticket cannot solve it without inventing one. Logged as `BL-154`.
7. **No frontend/backend deployment** (`BL-037`) — verification is against local `uvicorn` + `npx expo start --web`, the same precedent as every backend ticket so far. Not a blocker; reaffirmed rather than re-litigated.
8. **`users.city` has no UI to change it after onboarding** — `mobile/app/edit-preferences.tsx` (SS-007) edits `style_preferences` only, not `full_name`/`gender`/`city`. So a user who picked the wrong city, or typed free text into "Other," has no in-app way to fix their weather. Out of scope (it's a profile-editing ticket, not a weather ticket) but it directly limits this feature's reach. Logged as `BL-155`.

## Backlog

### Active rows checked (tags `ai` / `infra` / `ci` / `test`)

| Row | Verdict for SS-022 |
|---|---|
| **BL-042** (ci — no CI job runs Deno/Edge Function tests) | **Unaffected, and deliberately kept that way.** §1 places the fetch in FastAPI, so this ticket adds **no** new Edge Function and no new untested Deno surface. All new code lands under the existing `backend-quality` CI job. Row stays Active, unchanged — it is in fact one of the five arguments *for* the placement decision. |
| **BL-045** (infra — no rate limiting on `get-upload-url` Edge Function invocations) | **Unaffected.** No new Edge Function ⇒ no new per-invocation billing surface, no second instance of this pattern. Also relevant in the inverse: the outbound Open-Meteo call needs no new limiter (§2 — the per-city-per-hour cache bounds it at ~1,200 calls/day worst case). Row stays Active, unchanged. |
| **BL-130** (test — prompt-payload size budget needs re-verification) | **Touched, not resolved.** SS-022 adds to the prompt *envelope* (one ~120-char weather block per request), never to `render_candidate_for_prompt`'s per-candidate output, so the 600-char and 700-char per-candidate budgets this row is about are untouched. The test plan pins that explicitly (a regression test asserting the candidate dict is unchanged, plus a <200-char bound on the new block). Row stays Active with this note. |
| **BL-105** (infra — three call-count limiters coexist with the paise budget gate) | **Unaffected.** No new rate limiter is added; weather is gated by a cache, not a limiter. |
| **BL-099** (infra — one Gemini quota, two in-process limiters) | **Unaffected.** No change to provider selection, quota accounting or call *count*. One second-order effect worth stating: the weather block adds ~30-40 tokens to each narration prompt, so `tokens_in` (and therefore reconciled cost) rises marginally per call. Immaterial against the per-call estimate, and `PriceTable`'s shape is unchanged. |
| **BL-037** (infra — no backend deployment) | **Reaffirmed, does not block.** Verified against local `uvicorn`, the standing precedent for every backend ticket. Noted honestly in §1: choosing FastAPI forgoes the one property an Edge Function would have had (deployable today). No *new* gap, since `/portfolio` itself already has this constraint. |
| **BL-125** (silk/khadi carry `NULL season_affinity` in `fabrics`) | **Unaffected by design, worth stating.** SS-022's silk exclusion keys on the canonical `fabrics.key` value `'silk'` directly, **not** on `season_affinity` — so the very row this backlog item flags as under-populated cannot weaken AC #3. |
| **BL-052** (auth — the `/generate` JWT stub) | **Unaffected.** `/portfolio` already runs on the real `get_current_user_id`; SS-022 adds no route and no auth surface. |

### New rows to append (Active, starting at `BL-151`)

- **`BL-151` | `infra`** — India city→coordinate data now exists twice with no single source of truth: `mobile/features/onboarding/onboarding.constants.ts::TOP_50_INDIAN_CITIES` (TS, used by the picker) and `backend/services/india_city_coordinates.py` (Python, used by weather). A drift between them means the picker offers a city the backend can't resolve. The eventual right answer is a `cities` reference table alongside `occasions`/`fabrics`/`garment_types` (with the same registry-repository pattern), which is schema surface and deliberately out of a 1-point ticket's scope. Until then, a test asserting the two lists have identical membership would be a cheap partial guard (cross-language, so it needs a small script or a generated fixture).
- **`BL-152` | `ai`** — Users who chose "Other" in the city picker, or skipped onboarding Step 1, get **no weather at all, permanently** — there is no geocoding fallback and no in-app way to correct the value (see `BL-155`). The size of this cohort is unknown (no analytics event records city-picker "Other" usage). Revisit with either an Open-Meteo geocoding fallback or a "your city isn't supported yet" prompt once real usage data exists.
- **`BL-153` | `ai`** — Weather currently drives exactly one binary decision (heavy rain → exclude white + silk) plus prompt context. It does **not** inform `season` resolution or `fabric_weather_score`, even though Engine v2 already has a season-aware fabric-scoring term that today only ever receives a client-supplied/absent `season`. Deriving `season` from live temperature (or scoring breathability against real temperature rather than a season label) is the obviously richer integration and is where this feature's actual styling value is. Also folds in the unvalidated "no white or silk in heavy rain" rule itself (Open Question #5) — both belong in `BL-077`'s quality eval.
- **`BL-154` | `infra`** — No i18n layer exists in `mobile/`. SS-022's weather chip copy ("Dressing for 28°C, partly cloudy") is hardcoded English and sits directly above outfit rationales that can already be returned in Hindi (`rationale_language: 'hi'`, SS-020). The mixed-language surface is now visible in the product, not just theoretical. Needs a real i18n decision before any Hindi-first user testing.
- **`BL-155` | `infra`** — `users.full_name` / `gender` / `city` are write-once at onboarding Step 1: `mobile/app/edit-preferences.tsx` (SS-007) edits only `style_preferences`. A user cannot correct their city after onboarding, which directly caps SS-022's reach (a mistyped "Other" city means no weather forever). Needs a small profile-editing surface; not weather scope.

### Rows resolved by this ticket

None. No Active row is closed by SS-022.

## Risk classification

`Risk: med` — **lowered from the provisional `high`** that model triage inherited mechanically from `Depends on: SS-020`. Checked against `OPERATOR_RULEBOOK.md` §C2's one-way-door list item by item: **no auth** (reuses `get_current_user_id`; the only new DB read is the caller's own `users.city` through the RLS-scoped JWT client, never `service_role`), **no payments**, **no DB schema, migration or RLS change of any kind** (`users.city` already exists; the one new tunable rides `app_config`'s missing-row-degrades-to-coded-default path, so it needs no seed), **no new secret or env var** (Open-Meteo needs no key; Upstash is already provisioned), and **nothing external-facing** beyond one read-only, unauthenticated outbound GET that transmits no user identity — only a city's public coordinates.

It is not `low`, because it is not inert: it adds a **hard exclusion filter to a shipped suggestion engine** (a bug there silently removes real clothes from real users' results — mitigated by the relax-if-empty guardrail and pure-function tests), it **changes a cache-key function that SS-020 designated a one-way door** (mitigated to near-zero: TTL-bounded, self-healing, no data loss, no migration), and it puts a **third-party call on the critical path of a latency-AC'd endpoint** (mitigated by a 3 s provider timeout, a 4 s outer cap, concurrent execution, and a never-raise contract at every layer).

Two changes would flip this to `high`, and neither is in scope: introducing a `cities` reference table (schema + RLS surface, `BL-151`), or accepting client-supplied weather (untrusted input driving a styling rule and an LLM prompt — the exact thing §1 is designed to prevent). Fast lane: Architect→Developer→QA auto-chain, human review consolidated at the PR — with the caveat that Open Question #1 (backend vs. Edge Function) and Open Question #3 (cache-key invalidation) are surfaced now rather than at PR time, because overruling either after implementation is expensive.
