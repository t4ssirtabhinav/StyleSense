# SS-006 — Design: Outfit Styling AI: Preference Consumption Spec

## Scope restatement

This ticket defines the hexagonal port and consumption contract that turns a user's onboarding `style_preferences` into outfit suggestions, without building a real AI integration. Concretely: an `IStylingProvider` ABC in `ai/ports/interfaces.py` (typed input/output Pydantic models mirroring the mobile `StylePreferences` shape exactly), a `MockStylingAdapter` stub implementing it, an `OutfitSuggestionService` that owns preference normalization + rate-limit-check + background-task dispatch + AI-call logging, and one stub FastAPI router endpoint that exercises the whole chain end-to-end via `Depends()` with canned output — proving the wiring, not real personalization. The ticket also requires (and this doc records) three explicit decisions: whether any onboarding field is unused/missing (no field removed; skin tone/height explicitly still not collected, deferred per existing BL-027 reasoning), whether the deferred "first outfit suggestion" onboarding reward ships now (decision: the backend foundation ships now via this stub; the actual frontend hook is out of this backend-only ticket's scope and is logged as a follow-up), and the rate-limiting/background-task pattern for the first real AI call path.

## Current codebase state (verified, not assumed)

- `backend/` currently has only `main.py` (FastAPI app + `/health`), `models.py` (one `HealthResponse` model), and empty scaffolding packages (`adapters/__init__.py`, `prompts/__init__.py`, `routers/__init__.py`, `services/__init__.py`) — confirmed via directory listing. **No `ai/` directory exists at all yet** — this ticket creates it for the first time.
- **No JWT-verification dependency exists anywhere in the backend.** SS-002/SS-003 built Supabase phone-OTP auth entirely on the frontend/DB side; no FastAPI router has ever required a bearer token before. `.env.example` has no `SUPABASE_JWT_SECRET` (or equivalent) — only `SUPABASE_URL`/`SUPABASE_ANON_KEY`/`SUPABASE_SERVICE_ROLE_KEY`. This means CLAUDE.md's blanket "All endpoints: JWT auth dependency" rule has never actually been implemented once, and this ticket's stub router is the first place it would need to be. See "Open questions" — this ticket ships a clearly-labeled **non-production stub** auth dependency, not real signature verification, and logs the real gap to the backlog rather than quietly building unverified crypto under time pressure.
- `.env.example` already has `UPSTASH_REDIS_REST_URL`/`UPSTASH_REDIS_REST_TOKEN` (both blank) for the Upstash Redis rate-limiting CLAUDE.md requires. `backend/requirements.txt` has `redis==8.0.1` (the standard Redis **wire-protocol** client, which expects a `redis://`/`rediss://` connection string) — not `upstash-redis` (Upstash's own REST-API client) or anything else that natively speaks REST_URL/REST_TOKEN. There is a real mismatch between the configured env-var shape (REST) and the installed client (wire-protocol). See "Open questions."
- `mobile/features/onboarding/onboarding.types.ts`'s `StylePreferences` is the exact shape to mirror (verbatim, not restyled):
  ```ts
  export interface StylePreferences {
    styles: StyleKeywordKey[];       // StyleKeywordKey = string (DB-backed, since 2026-07-13 revision)
    wardrobe_type: WardrobeTypeKey;  // fixed union, 5 values
    occasions_priority: OccasionPriorityKey[]; // string[], max 3
    budget_range: BudgetRangeKey;    // fixed union, 4 values
    favourite_colours: string[];     // hex codes, max 5
    gender: GenderKey;               // fixed union, 4 values
  }
  ```
  `styles`/`occasions_priority` are `string`, not closed TS unions, because SS-004's 2026-07-13 revision widened them to DB-backed taxonomy tables (`style_keywords`/`occasion_types`) — the Python port must mirror this widening (`list[str]`), not reintroduce a fixed enum SS-004 deliberately moved away from.
- `mobile/types/supabase.ts` confirms `users.style_preferences: Json | null` — nullable at the DB level, with no enum/shape constraint enforced by Postgres. Confirms the null/partial edge cases in the raw ticket are real, reachable states, not hypothetical.
- `backend/pyproject.toml` sets `asyncio_mode = "auto"` and `testpaths = ["tests"]` — async test functions need no `@pytest.mark.asyncio` decorator; `IStylingProvider.suggest_outfits` should be `async def` per CLAUDE.md's async-everywhere backend convention.

## Files to create/modify

1. **`backend/ai/__init__.py`** (new) — empty package marker.
2. **`backend/ai/ports/__init__.py`** (new).
3. **`backend/ai/ports/interfaces.py`** (new) — `IStylingProvider(ABC)` + its typed contract models (`StylePreferencesInput`, `OutfitSuggestionItem`, `OutfitSuggestionResult`). The onboarding-field → suggestion-effect mapping table (this ticket's AC-required "written mapping doc") lives as a module-level docstring directly above `IStylingProvider`, since that's the file any future adapter author reads first.
4. **`backend/ai/adapters/__init__.py`** (new).
5. **`backend/ai/adapters/mock_styling_adapter.py`** (new) — `MockStylingAdapter(IStylingProvider)`: canned/rule-based stub (no external API calls) that actually implements the mapping table's "hard filter" vs "soft signal" distinction with simple logic, so the mapping doc is exercised by a real (if fake) code path, not just prose.
6. **`backend/services/outfit_suggestion_service.py`** (new) — `OutfitSuggestionService`: constructor-injected `IStylingProvider`; owns rate-limit check (via `RateLimiter`), background-task dispatch, preference-normalization (null/partial → `StylePreferencesInput()` defaults), and the AI-call logging call site (`user_id`, `tokens_used`, `latency_ms`).
7. **`backend/services/rate_limiter.py`** (new) — `RateLimiter`: thin wrapper around Upstash's REST API (via `httpx`, already a dependency — no new package needed for the stub), keyed per `user_id`; **fails open** (allows the request, logs a warning) when `UPSTASH_REDIS_REST_URL`/`UPSTASH_REDIS_REST_TOKEN` are unset (true today, per `.env.example`).
8. **`backend/routers/outfit_suggestions.py`** (new) — `POST /outfit-suggestions/generate`: a **non-production stub** `get_current_user_id_stub` bearer-token dependency (decodes the JWT payload's `sub` claim without verifying signature — explicitly commented as unsafe for real traffic), `Depends()`-injects `OutfitSuggestionService` (itself constructed with `MockStylingAdapter`), calls `background_tasks.add_task(...)`, returns `202` with a placeholder `{status: "queued", ...}` body. Router depends on `IStylingProvider`/`OutfitSuggestionService` via `Depends()` only — never imports `MockStylingAdapter` directly inside the route handler body (the binding lives in the dependency-provider function, so swapping in a real adapter later is a one-line change).
9. **`backend/main.py`** (modify) — `app.include_router(outfit_suggestions.router)`.
10. **`backend/tests/test_ai_ports.py`** (new).
11. **`backend/tests/test_mock_styling_adapter.py`** (new).
12. **`backend/tests/test_outfit_suggestion_service.py`** (new).
13. **`backend/tests/test_rate_limiter.py`** (new).
14. **`backend/tests/test_outfit_suggestions_router.py`** (new).

No `mobile/` files are touched by this ticket — the frontend hook that would call this endpoint is explicitly out of scope (see "Concrete values" and "Open questions").

## Concrete values to use, not invent

**Port contract** (`backend/ai/ports/interfaces.py`) — exact shape to implement:

```python
from abc import ABC, abstractmethod
from typing import Literal, Optional
from pydantic import BaseModel

GenderKey = Literal["woman", "man", "non_binary", "prefer_not_to_say"]
WardrobeTypeKey = Literal[
    "mostly_western", "mostly_ethnic", "equal_mix", "mostly_formal", "mostly_casual"
]
BudgetRangeKey = Literal["500_1000", "1000_3000", "3000_10000", "10000_plus"]

class StylePreferencesInput(BaseModel):
    """Mirrors mobile/features/onboarding/onboarding.types.ts's StylePreferences
    verbatim. All fields Optional[...] = None: style_preferences is a nullable
    JSONB column (types/supabase.ts) and onboarding is fully skippable per-step.
    styles/occasions_priority are list[str] (not a closed enum) because SS-004's
    2026-07-13 revision widened them to DB-backed taxonomies — do not
    reintroduce a fixed Python Literal/enum here.
    """
    styles: Optional[list[str]] = None
    wardrobe_type: Optional[WardrobeTypeKey] = None
    occasions_priority: Optional[list[str]] = None  # max 3, enforced client-side
    budget_range: Optional[BudgetRangeKey] = None
    favourite_colours: Optional[list[str]] = None  # hex codes, max 5
    gender: Optional[GenderKey] = None

class OutfitSuggestionItem(BaseModel):
    item_category: str
    label: str
    occasion: Optional[str] = None
    rationale: str

class OutfitSuggestionResult(BaseModel):
    user_id: str
    suggestions: list[OutfitSuggestionItem]
    generated_at: str          # ISO8601 UTC
    is_personalized: bool      # False on the null/empty-preferences degrade path
    source: Literal["mock", "gemini", "claude"] = "mock"

class IStylingProvider(ABC):
    """Never modify this signature to fit a new provider — add a new adapter
    class instead (Open/Closed, per CLAUDE.md)."""

    @abstractmethod
    async def suggest_outfits(
        self, preferences: StylePreferencesInput, *, max_suggestions: int = 5,
    ) -> OutfitSuggestionResult:
        """Must degrade gracefully (generic suggestions, is_personalized=False)
        when preferences is effectively empty, rather than raise."""
        raise NotImplementedError
```

**Mapping doc (this ticket's required deliverable)** — onboarding field → suggestion-engine effect, transcribed as the module docstring in `ai/ports/interfaces.py`:

| Field | Effect | Tier |
|---|---|---|
| `styles[]` | Biases which style tags (e.g. "ethnic", "streetwear") rank higher; does not exclude non-matching styles. | Soft signal |
| `wardrobe_type` | Skews the western/ethnic mix of returned suggestions (e.g. `mostly_ethnic` → ethnic-first ordering); doesn't exclude the other category. | Soft signal |
| `occasions_priority[]` (max 3) | Biases which occasion categories are ranked first in Discover/Home feed, in list order; non-priority occasions can still appear, just lower-ranked. | Soft signal |
| `budget_range` | Excludes suggestions outside the selected price band entirely. | **Hard filter** |
| `favourite_colours[]` (max 5, hex) | Biases colour-coordination scoring upward for matching/near hexes; doesn't exclude other colours. | Soft signal |
| `gender` | Excludes catalog categories not eligible for the selected gender. | **Hard filter** |

`MockStylingAdapter` implements the two "hard filter" rows as actual conditionals (drop suggestions outside `budget_range`'s tier / outside `gender`'s eligible categories) and the "soft signal" rows as simple reordering/weighting of a small static catalog — enough to prove the mapping is real behavior, not just prose, without needing any real AI call.

**Decision 1 — additional onboarding data**: no new field is added to SS-004's scope by this ticket. Skin tone/undertone and height/fit remain deliberately uncollected, per the reasoning already recorded in **BL-027** (Parked): better collected contextually right before first try-on than frontloaded into onboarding. This ticket's stub adapter does not need them (it only reasons over the 6 existing fields); a real colour-recommendation adapter would need skin tone/undertone as a genuinely new field, which is BL-027's existing scope, not reopened here.

**Decision 2 — "first outfit suggestion" onboarding reward (BL-026)**: this ticket ships the **backend foundation only** — `IStylingProvider` + `MockStylingAdapter` + the stub router. It does **not** implement the mobile-side reward screen itself (out of scope: this is a backend-only ticket per its own AC list, which has zero mobile ACs, and per the task framing, this ticket's file scope is `backend/`, distinct from SS-007's `mobile/features/onboarding/`). The recorded decision: **ship the reward as a follow-up ticket now, not defer further** — because `MockStylingAdapter` already produces a deterministic, preference-aware (if rule-based, not ML) canned response, a follow-up mobile ticket can wire "Get Started" to call this endpoint and render its result immediately, with zero further backend dependency. Logged as a new Active backlog row (see below) rather than assumed into this ticket's scope.

**Rate limiting / background-task pattern**: `OutfitSuggestionService.generate_suggestions(user_id, preferences)` — (1) `RateLimiter.check_and_increment(user_id)` first; if it returns `False`, raise `HTTPException(429)` before touching the provider; (2) if allowed, the router calls `background_tasks.add_task(service.generate_suggestions, ...)` rather than `await`-ing it directly in the request path, per CLAUDE.md's "never call AI APIs synchronously" — this holds even though the mock adapter is instant, so swapping in a real (slow) adapter later doesn't change the calling convention; (3) inside `generate_suggestions`, time the `provider.suggest_outfits(...)` call and log `logger.info("ai_call", extra={"user_id": ..., "tokens_used": 0, "latency_ms": ...})` — zero `tokens_used` for the mock, but the log call site exists exactly where a real adapter's real token count would go.

**Env vars used** (already present, blank, in `.env.example`): `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`. No new env vars are introduced by this ticket.

## Edge cases

Carried forward from the raw ticket, plus new ones found in this pass:

- `style_preferences: null` (user skipped all of onboarding) — `StylePreferencesInput()` with every field `None`; `MockStylingAdapter` must return `is_personalized=False` generic/popular suggestions, never raise.
- Partial preferences (onboarding abandoned mid-way, e.g. only Step 1+2 completed) — missing `occasions_priority`/`favourite_colours` (both `None`) must not crash the "soft signal" reordering logic; each optional field is null-checked before use.
- Malformed/unexpected JSONB (e.g. a `budget_range` value outside the 4 known literals, reachable only via a manual DB edit or a future onboarding bug, since Postgres enforces no shape/enum constraint on `style_preferences`) — the service layer must catch the `pydantic.ValidationError` when parsing raw JSONB into `StylePreferencesInput` and fall back to the empty/null-preferences degrade path, not `500`.
- Duplicate/rapid double-tap of the reward trigger for the same user — `RateLimiter` keys per `user_id`, so a second request within the window is denied `429` rather than double-queuing a background task.
- Upstash env vars unset (true today) — `RateLimiter` fails open with a logged warning, not a crash and not a silent, unlogged bypass. Explicitly **not** acceptable once a real (costed) adapter replaces the mock — flagged below.
- Stub auth dependency receiving no `Authorization` header, or a garbage/non-JWT-shaped token — returns `401`, not a `500` from a failed decode.
- `TestClient`'s handling of `BackgroundTasks` — verify (don't assume) whether the installed `fastapi==0.139.0`/`starlette==1.3.1` executes background tasks synchronously before `TestClient`'s request call returns, since the router test plan below depends on observing the task's side effect.

## Test plan

- `backend/tests/test_ai_ports.py`
  - `IStylingProvider` cannot be instantiated directly (`TypeError` — enforces the ABC).
- `backend/tests/test_mock_styling_adapter.py`
  - Full preferences → `is_personalized=True`, `len(suggestions) <= max_suggestions`.
  - All-`None` preferences (`StylePreferencesInput()`) → `is_personalized=False`, non-empty generic suggestions, no exception.
  - Partial preferences (only `styles` set) → no exception, returns suggestions.
  - Two different `budget_range` values → produce disjoint/different suggestion sets (proves the "hard filter" mapping is real, not just documented).
  - A `gender` value → excludes any category the mock catalog marks ineligible for that gender.
- `backend/tests/test_outfit_suggestion_service.py`
  - `generate_suggestions` calls the injected provider's `suggest_outfits` exactly once with the passed/normalized preferences.
  - Emits a log record containing `user_id`, `tokens_used`, `latency_ms` keys (via `caplog`).
  - When `RateLimiter.check_and_increment` returns `False`, the provider is never called and an `HTTPException(429)` is raised.
  - Raw dict with an invalid `budget_range` value degrades to the empty-preferences path instead of raising.
- `backend/tests/test_rate_limiter.py`
  - With `UPSTASH_REDIS_REST_URL`/`TOKEN` unset (monkeypatched empty), `check_and_increment` returns `True` and logs a warning.
  - With both set (mocked), `check_and_increment` calls `httpx.post`/`get` with the Bearer token in headers (asserts the request shape, not live Upstash behavior).
- `backend/tests/test_outfit_suggestions_router.py`
  - Valid stub bearer token → `202` with `{status: "queued", ...}` body shape.
  - Missing/malformed `Authorization` header → `401`.
  - `app.dependency_overrides[IStylingProvider]` swap works (proves the port is swappable without touching the router file) — override with a second fake adapter and assert its output flows through.
  - After the request completes, the mock provider was invoked exactly once (background task executed) — contingent on the `TestClient`/background-task verification above; if the installed version does *not* run tasks synchronously, this assertion must instead poll or use a synchronization primitive, and the Developer should note which behavior was actually observed.

## Open questions / blockers

1. **No backend JWT-verification dependency exists anywhere yet.** This ticket's stub router uses a clearly-labeled **non-production** dependency that reads the `sub` claim without verifying the token's signature. This is acceptable *only* because nothing behind this endpoint is real (mock adapter, no writes, no sensitive reads) and no real frontend calls it yet. **Before any real traffic reaches this or any future backend endpoint**, a proper Supabase JWT verification dependency must be built — and which signing scheme to verify against (legacy shared `SUPABASE_JWT_SECRET`/HS256 vs. newer JWKS-based asymmetric signing keys) is a genuine Supabase-behavior question this pass could not verify (no web-fetch tool available; per `docs/OPERATOR_RULEBOOK.md` §C3, this is a cutoff-exposed platform-behavior claim, not something to assert from memory). Logged as a new Active backlog row (BL-033, tag `auth`) rather than guessed at.
2. **Upstash Redis client/env-var mismatch.** `.env.example` has `UPSTASH_REDIS_REST_URL`/`REST_TOKEN` (Upstash's HTTP REST scheme), but `requirements.txt` only has the wire-protocol `redis==8.0.1` client, not `upstash-redis` or an established REST-calling convention. This ticket's `RateLimiter` uses `httpx` (already installed) to call Upstash's REST endpoints directly rather than adding a new dependency, but the exact REST command shape (e.g. `POST {url}/incr/{key}`) is **[trained-knowledge, not verified this session]** against Upstash's current REST API docs. Must be verified before this rate limiter is load-bearing for a real (costed) AI adapter — logged as BL-035 (tag `infra`).
3. **Rate limiter fails open when Upstash is unconfigured (true today).** Fine for a zero-cost mock adapter; **not** fine once a real, costed adapter is wired in — must flip to fail-closed (or block deploy) before that swap, called out explicitly so it isn't silently carried forward.
4. **No result-delivery mechanism to the client** (DB row, polling endpoint, or Supabase Realtime channel) is built by this ticket — the background task computes and logs a result but doesn't persist/push it anywhere the frontend could read it. Out of scope per this ticket's AC (which only requires proving the port/adapter/router wiring), but whichever ticket wires the real onboarding reward hook (see Decision 2 above) will need to build this. Logged as part of BL-034 below.
5. **This design doc does not resolve BL-026 outright** — it records the required decision (ship the backend foundation now; the frontend reward hook is separate, immediately-buildable follow-up scope) but the actual reward UI still doesn't exist. BL-026 is updated with this decision, not moved to Resolved.
6. **Backend folder-placement calls not explicitly named in CLAUDE.md's backend structure list**: the stub auth dependency is colocated directly in `routers/outfit_suggestions.py` (not a new `dependencies/` folder) since only one router needs it today — introduce a shared location once a second router needs auth, rather than duplicating. `RateLimiter` is placed under `services/` (closest existing fit; not literally a business-logic "service" like `OutfitSuggestionService`, but also not an AI or DB adapter) — flagging this placement call explicitly rather than silently picking a folder CLAUDE.md doesn't name.

## Risk classification

`Risk: low` — no schema/migration, no secrets committed, no payments, no RLS. The one new "auth-adjacent" surface (a stub bearer-token dependency) is explicitly non-production, verifies nothing behind real data or writes, and isn't called by any deployed frontend flow yet — its real-auth gap is flagged loudly (item 1 above) and logged to the backlog rather than shipped silently. Nothing here is a one-way door: worst case, this ticket's entire surface is deleted/replaced when a real adapter and real auth land, at zero data-loss cost.
