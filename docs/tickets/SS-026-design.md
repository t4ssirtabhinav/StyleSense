# SS-026 — Runtime Config Substrate (`app_config` + Feature Flags) — Design

Ticket: [`docs/tickets/raw/SS-026.md`](raw/SS-026.md) · Source: [`docs/proposals/EXECUTION-PLAN.md`](../proposals/EXECUTION-PLAN.md) §3.2/§3.4
Architect pass: 2026-07-29 (Sonnet, fast lane)

**This document is the Developer's spec.** Distilled from the raw ticket and the execution plan — do not re-open either. Every value below is fixed; where a value is my own judgement (nothing upstream pins it), it says so inline, mirroring `docs/tickets/SS-025-design.md`'s own convention.

---

## 1. Scope restatement

This ticket builds the generic mechanism for changing backend behaviour without a deploy: a new `app_config` Postgres table (key/value JSONB/scope/description/audit columns), read through exactly one typed accessor (`AppConfigService`) that holds a short, self-tuning, TTL-bounded in-process cache and validates every value against a Pydantic model before handing it to a caller — a missing, malformed, or unreachable row degrades to a hardcoded-in-code safe default and logs, never throws, never blocks a request, and is never consulted at backend boot. RLS defaults every row to `service_role`-only; a row can opt in to being readable by `authenticated` clients by explicit, per-row, enumerated flag — never a wildcard. Separately, and deliberately not merged with the above, this ticket wires PostHog feature flags on both mobile (a typed wrapper around the already-installed, already-initialised `posthog-react-native` client from SS-009) and backend (a new, first-of-its-kind `posthog` Python client), for user-targeted product experiments (paywall copy, tier gating) — a categorically different kind of "config" (cohort-scoped, eventually-consistent-by-nature, vendor-owned) from `app_config`'s server-side, atomic, auditable settings. This ticket seeds exactly two demonstration keys (the cache-TTL-is-itself-a-key value, and the Gemini quota-ceiling value BL-076 points at) to prove the substrate against real acceptance criteria; it wires **no real consumer** — SS-028's model-routing table is the first one, and `GeminiRateLimiter`'s hardcoded `15` is deliberately left untouched (BL-076 stays open, only its future fix path now exists).

---

## 2. File-by-file blast radius `[VERIFIED 2026-07-29 — ripgrep + Glob over the working tree]`

| Surface | Finding |
|---|---|
| Migrations | `supabase/migrations/001`…`009` exist; this ticket adds **`010_app_config.sql`**, the next sequential number. |
| `posthog`/`PostHog` repo-wide | 18 files reference it today — all mobile-side (SS-009's `lib/analytics.ts`, `constants/analyticsEvents.ts`, `app/_layout.tsx`, two test files) plus docs. **Zero backend references** — `backend/requirements.txt` has no `posthog` package; this ticket adds the first backend PostHog usage in the repo. |
| `SERVICE_ROLE`/`service_role` in `backend/` | Used today only in `backend/scripts/ss015_verify_wear_history.py` (a manual verification script) and asserted-**absent** in `adapters/wardrobe_repository.py`/`occasion_repository.py`'s docstrings and tests ("never `service_role`"). **This ticket's `AppConfigRepository` is the first `adapters/` class in this repo whose entire contract is to use `service_role`** — a deliberate, documented deviation (§3.4), not an oversight. |
| `backend/adapters/interfaces.py`, `backend/services/`, `backend/routers/wardrobe.py` | Read for DI/port conventions (§3.5); not modified except `adapters/interfaces.py` (new port) and `backend/tests/conftest.py` (new baseline env var). |
| `mobile/lib/analytics.ts` | One new exported function (`getAnalyticsClient`); no behavioural change to `capture`/`identify`/`reset`/`initAnalytics`. |

---

## 3. `app_config` — schema, RLS, accessor contract

### 3.1 Column contract (the ticket's own AC list, transcribed verbatim, six columns — no more, no less)

```sql
key         TEXT PRIMARY KEY CHECK (key ~ '^[a-z][a-z0-9_]*$'),
value       JSONB NOT NULL,
scope       TEXT NOT NULL DEFAULT 'server' CHECK (scope IN ('server', 'client_visible')),
description TEXT NOT NULL,
updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
updated_by  TEXT
```

**`scope`'s meaning is the Architect's call** — the raw ticket names the column but does not define its values. I make it do double duty as both a semantic label and the RLS visibility switch: `'server'` (default) is `service_role`-only; `'client_visible'` on a specific row is what exposes *that row* to `authenticated`. This is an explicit, per-row, enumerated opt-in (default `false`-equivalent), never a wildcard or negation predicate — directly answering the ticket's own edge case ("whitelist is explicit and enumerated, never a wildcard or a negation"). No config key shipped by this ticket sets `scope = 'client_visible'` — both seeded keys (§3.6) are internal.

**`updated_by` is nullable, no default.** I considered a DEFAULT (e.g. `'migration:010'`) but rejected it: a fake default that a lazy future writer never overrides is indistinguishable from a deliberately-recorded identity and actively undermines "auditable." NULL is the honest signal "nobody recorded who." Migration seed rows supply an explicit value (`'migration:010_app_config'`) as literal INSERT data, not a column default. Flagged as a residual gap in §8 and logged to the backlog (§10) — nothing enforces that a future `UPDATE` actually sets it.

**`updated_at` is enforced, not just conventional.** A `BEFORE UPDATE` trigger stamps `now()` unconditionally, so a writer that forgets to set it explicitly still produces a truthful timestamp:

```sql
CREATE OR REPLACE FUNCTION public.app_config_touch_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

CREATE TRIGGER app_config_set_updated_at
BEFORE UPDATE ON app_config
FOR EACH ROW EXECUTE FUNCTION public.app_config_touch_updated_at();
```

Not `SECURITY DEFINER` (touches no other table, only the row being written by whoever already has UPDATE rights — which is `service_role` only, see §3.2) — unlike `007_occasions_registry.sql`'s normalisation functions, which needed elevated rights specifically to write a *different* table (`occasion_unknown_tags`) from inside a trigger on someone else's data.

**No index beyond the primary key.** Same reasoning as `007_occasions_registry.sql` §3.1's `occasions` table: this will be a low-hundreds-of-rows table at most; a sequential scan is correct. Revisit only if profiling says otherwise.

### 3.2 RLS — exact policies

```sql
ALTER TABLE app_config ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated_read_client_visible_config" ON app_config
  FOR SELECT USING (auth.role() = 'authenticated' AND scope = 'client_visible');
```

**Deliberately no INSERT/UPDATE/DELETE policy for anyone.** Identical posture to `007_occasions_registry.sql`'s `occasions`/`occasion_aliases` tables: absence of a policy *is* the write-protection mechanism (`service_role` bypasses RLS entirely; `anon`/`authenticated` get a hard deny on every write). Config changes happen via the Supabase Dashboard SQL editor or a `service_role` script — never via the app on a user's behalf. Do not "fix" this by adding a permissive write policy.

`[trained-knowledge, same as SS-025's precedent — not re-verified this session]` `service_role` bypasses RLS via the `bypassrls` role attribute; QA must prove both directions empirically (§7.4), not assume them.

An `authenticated` `SELECT` against `app_config` is not an error — RLS silently *filters* rows for `SELECT` (unlike `INSERT` with no matching policy, which raises `42501`). So the correct verification for a `scope='server'` row is "0 rows returned," not "request fails" — QA's script (§7.4) tests this distinction explicitly rather than assuming SS-025's `INSERT`-failure precedent transfers unchanged.

### 3.3 Cross-instance consistency — which keys tolerate skew

Per the ticket's own edge case, this needs an explicit answer, not just a forward-looking caveat: **neither key seeded by this ticket needs strict cross-instance consistency.** `config_cache_ttl_seconds` (an operational tuning knob) and `gemini_quota_ceiling_rpm` (a soft ceiling, not consumed yet) both tolerate two instances briefly disagreeing during a TTL window — that's the entire design point of a TTL cache. **Any future key that needs atomic, strongly-consistent enforcement across instances does not belong in `app_config` at all** — it belongs behind Redis/`ICostLedger` (SS-029) or Cloudflare Durable Objects (`BL-082`), which are built for exactly that. This is a standing design boundary, not a one-off note: `app_config` is for TTL-cached, eventually-consistent settings only.

### 3.4 Why `AppConfigRepository` uses `service_role` (a deliberate deviation)

Every other `adapters/` repository in this codebase (`SupabaseWardrobeRepository`, `SupabaseOccasionRepository`) is explicitly documented as "never `service_role` — scope to the caller's own JWT" (`adapters/interfaces.py`'s existing docstrings), because that data is per-user and RLS's `auth.uid() = user_id` policies are a real defense-in-depth backstop against an application bug passing the wrong `user_id`. `app_config` is categorically different: it is not user data, there is no caller to scope it to, and the ticket's own AC requires reads to be `service_role`-only by default. Using the anon key + a caller JWT here would be actively wrong (an unauthenticated background task has no JWT to pass, and would only ever see the empty `client_visible` subset regardless). This is compliant with CLAUDE.md's Security section ("Never use `service_role` key in client-side code" — this is backend-only; "All user data queries MUST use authenticated Supabase client" — `app_config` is not user data) but is a new pattern in `adapters/`, flagged explicitly here rather than silently introduced.

### 3.5 The typed accessor — `AppConfigService`

```
backend/adapters/interfaces.py        (modify)  — new IAppConfigRepository port
backend/adapters/app_config_repository.py (new) — SupabaseAppConfigRepository (service_role)
backend/services/app_config.py        (new)     — ConfigSpec, AppConfigSnapshot, AppConfigService,
                                                    CacheTtlConfig/CACHE_TTL_SPEC, TTL clamp constants,
                                                    module-scope singleton `app_config_service`
backend/services/app_config_specs.py  (new)     — demo-only specs for THIS ticket's seeded keys
```

**Port** (`adapters/interfaces.py`, mirrors `IOccasionRepository`'s shape exactly):

```python
class IAppConfigRepository(ABC):
    """(SS-026) ALWAYS uses service_role -- see design §3.4 for why this port
    deliberately breaks the "never service_role" pattern every other
    adapters/ repository in this file follows. Raises on transport failure;
    AppConfigService owns the fallback/caching/typed-validation policy."""

    @abstractmethod
    async def fetch_all(self) -> dict[str, Any]:
        """Return {key: raw JSONB value} for every row. No filtering, no
        parsing -- AppConfigService validates per-key, lazily, on read()."""
        raise NotImplementedError
```

**Repository** (`adapters/app_config_repository.py`), same shape as `occasion_repository.py` but service_role, no `.postgrest.auth(jwt)` call (the service_role key itself is the credential):

```python
async def _client() -> AsyncClient:
    url = os.environ["SUPABASE_URL"]
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return await acreate_client(url, service_key)

class SupabaseAppConfigRepository(IAppConfigRepository):
    async def fetch_all(self) -> dict[str, Any]:
        client = await _client()
        response = await client.table("app_config").select("key, value").execute()
        rows = response.data or []
        return {str(row["key"]): row["value"] for row in rows}
```

**Engine** (`services/app_config.py`) — the core contract every requirement in the raw ticket maps onto:

```python
MIN_CACHE_TTL_SECONDS = 5.0
MAX_CACHE_TTL_SECONDS = 3600.0
DEFAULT_CACHE_TTL_SECONDS = 60.0  # matches OccasionNormalizer's own precedent exactly

T = TypeVar("T", bound=BaseModel)

@dataclass(frozen=True)
class ConfigSpec(Generic[T]):
    key: str
    model: type[T]
    default: T                 # the hardcoded safe default, required by AC #4
    client_visible: bool = False  # informational only -- DB `scope` is the real enforcement point

@dataclass(frozen=True)
class AppConfigSnapshot:
    """Immutable, point-in-time. A caller fetches ONE of these per
    request/task and calls read() against it repeatedly -- this is what
    satisfies "a single request must see one consistent config snapshot."
    Never re-fetched mid-lifetime; never mutated."""
    values: dict[str, Any] = field(default_factory=dict)
    fetched_at: float = 0.0
    stale: bool = False   # True = this snapshot is a fetch-failure fallback

class CacheTtlConfig(BaseModel):
    seconds: float = DEFAULT_CACHE_TTL_SECONDS

CACHE_TTL_SPEC: ConfigSpec[CacheTtlConfig] = ConfigSpec(
    key="config_cache_ttl_seconds", model=CacheTtlConfig, default=CacheTtlConfig()
)

def _clamp_ttl(seconds: float) -> float:
    """Requirement #4: a bad TTL value must NEVER make config unreachable.
    Two independent defenses layer here: (1) a value that fails Pydantic
    validation entirely (wrong shape/type) never reaches this function --
    read() already fell back to CACHE_TTL_SPEC.default before calling it;
    (2) a value that parses fine but is an extreme/degenerate number (0,
    negative, NaN, a week) is clamped here, never trusted raw."""
    try:
        f = float(seconds)
    except (TypeError, ValueError):
        return DEFAULT_CACHE_TTL_SECONDS
    if f != f:  # NaN
        return DEFAULT_CACHE_TTL_SECONDS
    return max(MIN_CACHE_TTL_SECONDS, min(MAX_CACHE_TTL_SECONDS, f))

class AppConfigService:
    def __init__(self, repository: IAppConfigRepository, *,
                 initial_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS) -> None:
        self._repository = repository
        self._ttl_seconds = _clamp_ttl(initial_ttl_seconds)
        self._snapshot: AppConfigSnapshot | None = None

    async def snapshot(self) -> AppConfigSnapshot:
        """Never raises. Cache-hit: return the held snapshot while fresh.
        Cache-miss/expired: refetch; on failure, fall back to the last-good
        snapshot (marked stale) or an empty one if there has never been a
        successful read -- read() then serves every key's coded default."""
        now = time.monotonic()
        if self._snapshot is not None and (now - self._snapshot.fetched_at) < self._ttl_seconds:
            return self._snapshot
        try:
            values = await self._repository.fetch_all()
        except Exception as exc:  # noqa: BLE001 -- config read must never break the caller
            logger.warning("app_config_fetch_failed", extra={"error": str(exc)})
            if self._snapshot is not None:
                return dataclasses.replace(self._snapshot, stale=True)
            return AppConfigSnapshot(values={}, fetched_at=now, stale=True)
        snap = AppConfigSnapshot(values=values, fetched_at=now, stale=False)
        self._snapshot = snap
        # Self-referential TTL: adopt the freshly-read cache-TTL value
        # (clamped) as the interval for the NEXT refresh cycle. This is what
        # makes "the cache TTL is itself a config key" actually live-tunable
        # without ever risking unreachability.
        self._ttl_seconds = _clamp_ttl(self.read(snap, CACHE_TTL_SPEC).seconds)
        return snap

    def read(self, snapshot: AppConfigSnapshot, spec: ConfigSpec[T]) -> T:
        """Pure, no I/O, never raises. MISSING key -> default, logged at
        INFO (routine -- most keys won't be seeded by every ticket).
        MALFORMED value (wrong shape for spec.model) -> default, logged at
        ERROR (a real data-quality problem in a stored row) -- per the
        ticket's own "logs at error level" wording. Never touches any OTHER
        key's value -- one bad row cannot break the rest of the read."""
        raw = snapshot.values.get(spec.key)
        if raw is None:
            logger.info("app_config_key_missing", extra={"key": spec.key})
            return spec.default
        try:
            return spec.model.model_validate(raw)
        except ValidationError as exc:
            logger.error("app_config_value_invalid", extra={"key": spec.key, "error": str(exc)})
            return spec.default

# Module-scope singleton, constructed at import with ZERO I/O (mirrors
# routers/wardrobe.py's `_occasion_normalizer` pattern exactly) -- this is
# what makes "config is never a startup dependency" true even stronger than
# graceful degradation: nothing calls .snapshot() until a real consumer
# (SS-028+) actually reads a value, and main.py never imports this module.
app_config_service = AppConfigService(SupabaseAppConfigRepository())
```

**Forward-compat note for SS-027/028/029 (not built here):** a future router wraps this singleton in a FastAPI `Depends()` exactly as `routers/wardrobe.py::get_occasion_normalizer()` wraps `_occasion_normalizer` — `from services.app_config import app_config_service`, call `.snapshot()` once per request (e.g. as its own `Depends()`), then pass that snapshot into every `.read()` call for that request. **This is the concrete mechanism that satisfies "one request, one consistent snapshot"** — a route must never call `app_config_service.snapshot()` more than once per request.

### 3.6 Concrete seed data — demonstrates the mechanism, wires no consumer

`services/app_config_specs.py` (demo-only; a future domain ticket may add its own specs file near its own service rather than growing this one indefinitely — flagged, not decided, in §10):

```python
class GeminiQuotaCeilingConfig(BaseModel):
    rpm: int = 15  # matches GeminiRateLimiter's CURRENT hardcoded default (BL-076) --
                   # if this key is ever read and the row is missing/malformed,
                   # behaviour is IDENTICAL to today's, never a silent regression.

GEMINI_QUOTA_CEILING_SPEC: ConfigSpec[GeminiQuotaCeilingConfig] = ConfigSpec(
    key="gemini_quota_ceiling_rpm", model=GeminiQuotaCeilingConfig,
    default=GeminiQuotaCeilingConfig(),
)
```

Migration seed (`010_app_config.sql`):

```sql
INSERT INTO app_config (key, value, scope, description, updated_by) VALUES
  ('config_cache_ttl_seconds',
   '{"seconds": 60}'::jsonb, 'server',
   'In-process cache TTL for AppConfigService.snapshot(), seconds. Clamped to [5, 3600] in code -- a bad value here degrades to the clamp bound or the coded default, never to unreachable.',
   'migration:010_app_config'),
  ('gemini_quota_ceiling_rpm',
   '{"rpm": 15}'::jsonb, 'server',
   'Provider quota ceiling for Gemini tagging calls (requests/minute). Seeded conservative, matching backend/services/gemini_rate_limiter.py''s current hardcoded default, pending BL-076''s real paid-tier RPM verification. NOT YET CONSUMED -- GeminiRateLimiter still reads its own hardcoded constant. Update via UPDATE once verified; no migration needed either way.',
   'migration:010_app_config');
```

**No model-routing table, no cost-budget key, no pre-filter-threshold key is seeded here** — the ticket's own Status note is explicit that those are SS-027/028/029's job; seeding them now would be inventing product-facing values nobody has specified.

---

## 4. PostHog feature flags — mobile

```
mobile/lib/analytics.ts       (modify) — export getAnalyticsClient(): PostHog | null
mobile/lib/featureFlags.ts    (new)    — isFeatureEnabled(), useTypedFeatureFlag()
mobile/constants/featureFlags.ts (new) — FEATURE_FLAGS, FeatureFlagKey
```

**One shared client, not a second one.** `lib/analytics.ts` already constructs the process's one `PostHog` instance (`initAnalytics()`); a second `new PostHog(...)` instance would diverge `distinct_id`/session state from the one already `.identify()`-ing users. `lib/analytics.ts` gains exactly one new export:

```ts
export function getAnalyticsClient(): PostHog | null {
  return client;
}
```

No other line of `analytics.ts` changes — `capture`/`identify`/`reset`/`initAnalytics` and the PII guard are untouched.

**`lib/featureFlags.ts`:**

```ts
import { useFeatureFlag } from 'posthog-react-native';
import { getAnalyticsClient } from './analytics';
import type { FeatureFlagKey } from '../constants/featureFlags';

// Non-hook path (stores, one-off checks outside a component).
export function isFeatureEnabled(flag: FeatureFlagKey, defaultValue = false): boolean {
  const client = getAnalyticsClient();
  if (!client) {
    return defaultValue;
  }
  try {
    const result = client.isFeatureEnabled(flag);
    return typeof result === 'boolean' ? result : defaultValue;
  } catch {
    return defaultValue; // a flags outage must never crash the app
  }
}

// Hook path. Always passes the shared client explicitly rather than relying
// on a <PostHogProvider> context -- none is mounted anywhere in this repo
// [VERIFIED 2026-07-29, grep: no PostHogProvider/usePostHog reference
// anywhere in mobile/]. posthog-react-native's useFeatureFlag falls back
// to a context client when none is passed, and that context is unmounted
// here -- it logs one console.error and returns undefined rather than
// throwing [VERIFIED 2026-07-29 against the installed
// posthog-react-native@4.52.0 dist/hooks/utils.js's useOverridablePostHog],
// so passing our own client explicitly is both correct and avoids that log
// entirely.
export function useTypedFeatureFlag(flag: FeatureFlagKey, defaultValue = false): boolean {
  const client = getAnalyticsClient() ?? undefined;
  const value = useFeatureFlag(flag, client);
  return typeof value === 'boolean' ? value : defaultValue;
}
```

`[VERIFIED 2026-07-29 against the installed posthog-react-native@4.52.0 dist/posthog-rn.d.ts]`: `isFeatureEnabled(key: string): boolean | undefined`; `useFeatureFlag(flag: string, client?: PostHog): FeatureFlagValue | undefined` (`dist/hooks/useFeatureFlag.d.ts`). Both signatures match the sketch above exactly — no cast needed.

**`constants/featureFlags.ts`** (mirrors `constants/analyticsEvents.ts`'s exact pattern — `as const` object + derived union type):

```ts
export const FEATURE_FLAGS = {
  PAYWALL_COPY_VARIANT: 'paywall_copy_variant',
} as const;

export type FeatureFlagKey = (typeof FEATURE_FLAGS)[keyof typeof FEATURE_FLAGS];
```

One flag only — `paywall_copy_variant`, matching the epics doc's Sprint-5 "A/B ready: paywall copy and pricing can be remote-configured" requirement the ticket's own Technical Notes cites. **This flag does not exist in the PostHog dashboard yet** — no agent in this pipeline has dashboard access (same precedent as `BL-047`/`BL-048`). The typed constant + wrapper ship and are unit-tested against a mocked client; true end-to-end verification needs a human to create the flag first. Logged to backlog (§10), not a blocker for this ticket's own ACs.

---

## 5. PostHog feature flags — backend

```
backend/services/feature_flags.py (new)
backend/requirements.txt          (modify) — add `posthog`
.env.example                      (modify) — add POSTHOG_HOST=
```

`[trained-knowledge, NOT verified this session — no `posthog` package exists in `backend/requirements.txt` today `[VERIFIED 2026-07-29, grep]`, so there is nothing installed to check the real API against. **Developer must, before writing this file:** `pip install posthog`, record the resolved version in `requirements.txt` as an exact pin (matching every other entry's `==` style), then `python -c "import posthog; print(posthog.__version__)"` and inspect the actual installed `Posthog` client class's constructor/method signatures. The sketch below assumes the `posthog-python>=3.x` client-instance shape (`Posthog(api_key, host=...)`, `.feature_enabled(key, distinct_id)`); older `<3.x` releases only exposed module-level functions configured via `posthog.api_key = ...`. Correct the sketch if the installed version differs — do not ship this file unverified per `docs/OPERATOR_RULEBOOK.md` §E.]`

```python
from posthog import Posthog

class FeatureFlagKey:
    PAYWALL_COPY_VARIANT = "paywall_copy_variant"  # mirrors mobile's constants/featureFlags.ts.
    # Kept in sync BY HAND -- no shared codegen exists between the two
    # lists (logged to backlog, §10).

class FeatureFlagService:
    def __init__(self) -> None:
        api_key = os.getenv("POSTHOG_API_KEY")
        host = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com")
        self._client: Posthog | None = Posthog(api_key, host=host) if api_key else None

    def is_enabled(self, flag_key: str, distinct_id: str, *, default: bool = False) -> bool:
        if self._client is None:
            return default
        try:
            result = self._client.feature_enabled(flag_key, distinct_id)
        except Exception as exc:  # noqa: BLE001 -- a flags outage must never break the caller
            logger.warning("feature_flag_check_failed", extra={"flag": flag_key, "error": str(exc)})
            return default
        return bool(result) if result is not None else default

feature_flag_service = FeatureFlagService()
```

Same fail-safe posture as `mobile/lib/analytics.ts`'s `initAnalytics()` (no-op when the credential is absent) and `backend/main.py`'s existing `if sentry_dsn: sentry_sdk.init(...)` guard — reuses the **already-provisioned** root `.env`'s `POSTHOG_API_KEY` (confirmed real and non-empty by SS-009's Architect pass; the same key mobile's `EXPO_PUBLIC_POSTHOG_API_KEY` copies from). `POSTHOG_HOST` is new — add to `.env.example`'s Monitoring section, defaulting to `https://us.i.posthog.com` (US Cloud, confirmed the correct region by `BL-048`'s 2026-07-28 resolution).

**Unlike `AppConfigService`, `feature_flag_service` is constructed at import time** (mirrors `main.py`'s own Sentry-init precedent, not `AppConfigService`'s fully-lazy pattern) — acceptable because (a) nothing in this ticket imports `feature_flags.py` from `main.py` or any router (no consumer yet, same as `app_config`), so it stays entirely dormant until a future ticket wires it in, and (b) the ticket's explicit "never a startup dependency" requirement (#3) was stated for `app_config` specifically, not PostHog flags. Flagged as a deliberate, minor asymmetry, not an oversight.

`[trained-knowledge, unverified]`: some `posthog-python` configurations need a *personal* API key (not the project key) for efficient local flag-definition polling rather than an HTTP round-trip per `feature_enabled()` call. Not addressed here — logged to backlog (§10) as a performance question for whoever wires the first real consumer.

---

## 6. Files to create/modify — full list

| Path | Action |
|---|---|
| `supabase/migrations/010_app_config.sql` | **new** — §3.1–§3.2, §3.6 |
| `backend/adapters/interfaces.py` | **modify** — add `IAppConfigRepository` (§3.5) |
| `backend/adapters/app_config_repository.py` | **new** — `SupabaseAppConfigRepository` (§3.5) |
| `backend/services/app_config.py` | **new** — `ConfigSpec`, `AppConfigSnapshot`, `AppConfigService`, `CacheTtlConfig`/`CACHE_TTL_SPEC`, singleton (§3.5) |
| `backend/services/app_config_specs.py` | **new** — `GeminiQuotaCeilingConfig`/`GEMINI_QUOTA_CEILING_SPEC` (§3.6) |
| `backend/services/feature_flags.py` | **new** — `FeatureFlagService`, `FeatureFlagKey`, singleton (§5) |
| `backend/requirements.txt` | **modify** — add `posthog==<version Developer resolves and pins>` |
| `backend/tests/conftest.py` | **modify** — add `monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")` to `_baseline_backend_env` (currently sets `SUPABASE_URL`/`SUPABASE_ANON_KEY`/`CLOUDFLARE_R2_*` only — `AppConfigRepository` is the first adapter needing `SUPABASE_SERVICE_ROLE_KEY`, and its absence will `KeyError` in CI exactly per this file's own documented gap) |
| `backend/scripts/ss026_verify_config_live_reload.py` | **new** — manual live-verification script (§7.4), same pattern as `backend/scripts/ss015_verify_wear_history.py` |
| `.env.example` | **modify** — add `POSTHOG_HOST=` under Monitoring |
| `mobile/lib/analytics.ts` | **modify** — export `getAnalyticsClient()` (§4); no other change |
| `mobile/lib/featureFlags.ts` | **new** — §4 |
| `mobile/constants/featureFlags.ts` | **new** — §4 |
| `mobile/__tests__/lib/analytics.test.ts` | **modify** — one new test for `getAnalyticsClient()` |
| `mobile/__tests__/lib/featureFlags.test.ts` | **new** — §7.3 |
| `mobile/__tests__/constants/featureFlags.test.ts` | **new** — §7.3 |

**Explicitly not touched:** `backend/services/gemini_rate_limiter.py` (per the ticket's own Status note — the constant stays hardcoded; only the future path to fixing it now exists), `backend/main.py` (no import of either new service — nothing about backend boot changes), `routers/wardrobe.py` or any other router (no consumer wired), `mobile/app/_layout.tsx` (feature flags don't need an app-launch side effect the way analytics/Sentry init did — the SDK is already initialised by `initAnalytics()`).

---

## 7. Test plan

### 7.1 Backend — `backend/tests/test_app_config_service.py` (new)

| # | Test |
|---|---|
| 1 | `snapshot()` cache-hit: two calls within the TTL window call `repository.fetch_all()` exactly once |
| 2 | `snapshot()` cache-miss/expiry: after the TTL elapses (fake/monkeypatched clock), a third call refetches |
| 3 | `read()` for a missing key returns `spec.default`, logs at `INFO`, does not raise |
| 4 | `read()` for a value that fails `model.model_validate()` returns `spec.default`, logs at `ERROR` |
| 5 | **Malformed-one-row-doesn't-break-others:** a snapshot with one key holding a shape that fails validation for spec A and a second, well-formed key for spec B — `read(snap, specA)` degrades to default while `read(snap, specB)` returns the real value |
| 6 | **Supabase-unreachable fallback:** `repository.fetch_all()` raises → `snapshot()` never raises, returns an empty (first call) or last-good-marked-stale (subsequent calls) snapshot; every `read()` against it returns coded defaults |
| 7 | **One-request-one-snapshot:** obtain a snapshot, then have the repository's next `fetch_all()` return different data; two `read()` calls against the **same already-held snapshot object** return identical values (proves `read()` never triggers a hidden refetch) |
| 8 | `_clamp_ttl`: a value under `MIN_CACHE_TTL_SECONDS`, over `MAX_CACHE_TTL_SECONDS`, `NaN`, and a non-numeric string all clamp/degrade to a safe bound, never propagate raw |
| 9 | Self-referential TTL: after a successful `snapshot()`, the service's next refresh interval reflects the freshly-read `config_cache_ttl_seconds` value (clamped), not the constructor's `initial_ttl_seconds` |
| 10 | `GEMINI_QUOTA_CEILING_SPEC`'s coded default (`rpm=15`) matches `GeminiRateLimiter`'s own current hardcoded default (regression guard — if someone changes one without the other, this test catches the drift even though nothing consumes the config key yet) |

### 7.2 Backend — `backend/tests/test_app_config_repository.py` (new)

Mirrors `test_occasion_repository.py`'s fake-`AsyncClient`-builder style, inverted assertion:

| # | Test |
|---|---|
| 1 | `fetch_all()` builds its client with `SUPABASE_SERVICE_ROLE_KEY`, **not** the anon key (the opposite assertion from `test_occasion_repository.py`'s "never service_role" — here it must be present) |
| 2 | Maps `{key: value}` rows into the returned dict correctly |
| 3 | Zero rows resolves to an empty dict, not an error |

### 7.3 Backend — `backend/tests/test_feature_flags.py` (new)

| # | Test |
|---|---|
| 1 | No `POSTHOG_API_KEY` env var → `is_enabled()` returns `default`, no `Posthog` client constructed |
| 2 | API key present, `feature_enabled()` returns `True`/`False` → passed through |
| 3 | API key present, `feature_enabled()` returns `None` → falls back to `default` |
| 4 | API key present, `feature_enabled()` raises → logs a warning, returns `default`, does not propagate the exception |
| 5 | `distinct_id` is passed through to `feature_enabled()` unchanged |

### 7.4 Manual / live verification — `backend/scripts/ss026_verify_config_live_reload.py`, run by Developer/QA against the live `mefpfykuinasgkpfhmzk` project

Same shape as `ss015_verify_wear_history.py` (`httpx.Client`, `admin_headers()`/`user_headers()`, a `check()` accumulator, creates/tears down one throwaway user), plus a direct in-process use of the real `AppConfigService`/`SupabaseAppConfigRepository` classes (run with `backend/` on the path, e.g. `python -m scripts.ss026_verify_config_live_reload`):

1. **RLS, both directions.** `service_role` `SELECT` sees the seeded `gemini_quota_ceiling_rpm` row; an `authenticated` `SELECT` of the same (server-scoped) row returns **zero rows**, not an error (§3.2's SS-025-precedent correction). An `authenticated` `INSERT`/`UPDATE` against `app_config` fails with a row-level-security error (`403`/`42501`).
2. **The AC's headline demo — no redeploy, no restart.** Construct `AppConfigService(SupabaseAppConfigRepository(), initial_ttl_seconds=2)` in the running script process. Read `gemini_quota_ceiling_rpm` → `15` (seeded value). Via `service_role` REST, `PATCH` the row's `value` to `{"rpm": 999}` — same process, no restart of anything. Read again immediately → **still `15`** (proves the cache, not a live-read). Sleep past the 2s TTL. Read a third time → **now `999`**, in the same process, with nothing redeployed and nothing restarted. Restore the row to `{"rpm": 15}` afterward so the seed stays truthful for the next run.
3. **Malformed-row live check.** `PATCH` a throwaway probe row's `value` to a shape `GeminiQuotaCeilingConfig` rejects (e.g. `{"rpm": "not-a-number"}`); confirm `read()` degrades to the coded default and the *other* seeded key still reads correctly in the same snapshot.

### 7.5 Mobile — `mobile/__tests__/lib/featureFlags.test.ts` (new)

Same `jest.isolateModules` + `jest.mock('posthog-react-native', ...)` pattern as `__tests__/lib/analytics.test.ts`:

| # | Test |
|---|---|
| 1 | `isFeatureEnabled()` returns `defaultValue` when `getAnalyticsClient()` is `null` (no API key set) |
| 2 | `isFeatureEnabled()` returns the client's `.isFeatureEnabled()` boolean result when present |
| 3 | `isFeatureEnabled()` returns `defaultValue` when the client throws |
| 4 | `isFeatureEnabled()` returns `defaultValue` when the underlying value is a non-boolean (multivariate) flag |
| 5 | `useTypedFeatureFlag()` calls the mocked `useFeatureFlag(flag, client)` with the shared client instance, not `undefined`, when a client exists |
| 6 | `useTypedFeatureFlag()` returns `defaultValue` when the underlying hook resolves to a non-boolean or `undefined` |

### 7.6 Mobile — `mobile/__tests__/constants/featureFlags.test.ts` (new)

`FEATURE_FLAGS` has exactly 1 entry today, a unique non-empty snake_case string, matching `constants/analyticsEvents.test.ts`'s existing shape-assertion pattern.

### 7.7 Mobile — `mobile/__tests__/lib/analytics.test.ts` (modify)

One new test: `getAnalyticsClient()` returns the same constructed instance `initAnalytics()` built (identity check via the mocked constructor), and returns `null` before `initAnalytics()` has been called or when the API key was absent.

---

## 8. Edge cases

Carried forward from the ticket, plus what this design adds:

1. **Supabase unreachable at boot** → every key serves its coded default, app still starts. Stronger than graceful degradation: nothing in `main.py` imports `services/app_config.py` at all, so there is no boot-time coupling to break (§3.5).
2. **Malformed JSONB in one row** → that key falls back to default and logs at `ERROR`; every other key is read independently and is unaffected (§3.5 `read()`, tested §7.1 #5).
3. **Config changed mid-request** → a caller takes one `AppConfigSnapshot` per request/task and reads every value from it; `read()` never re-fetches (§3.5, tested §7.1 #7).
4. **Cross-instance cache skew** → tolerated for both of this ticket's seeded keys; no key here needs strict consistency; a future key that does belongs on `ICostLedger`/Redis, not `app_config` (§3.3).
5. **A `client_visible` key accidentally exposing an internal budget/quota** → prevented structurally: `scope` defaults to `'server'`, every exposure is a deliberate per-row `UPDATE`, and the RLS predicate is a positive `scope = 'client_visible'` assertion, never a negation (§3.1–§3.2).
6. **(new) A bad cache-TTL value** → two independent defenses: a shape/type failure never reaches the numeric clamp (falls back to `CacheTtlConfig()`'s default first); a shape-valid-but-extreme number is clamped to `[5, 3600]` seconds (§3.5 `_clamp_ttl`, tested §7.1 #8).
7. **(new) `updated_by` can be `NULL`** if a writer forgets to pass it — a visible, honest audit-trail gap (empty, not fabricated), not enforced by any constraint. Logged to backlog (§10) rather than silently accepted or silently fixed with a fake default.
8. **(new) Two concurrent `snapshot()` calls when the cache has just expired** can both trigger a `fetch_all()` — no single-flight lock, same accepted limitation as `OccasionNormalizer.get_registry()`'s existing precedent in this exact codebase. Not a correctness bug, just occasionally-redundant work.
9. **(new) `GeminiRateLimiter` is unchanged** — `gemini_quota_ceiling_rpm` is seeded and readable, but nothing consumes it. `BL-076` is not resolved by this ticket, only its fix path now exists (§9).
10. **(new) `posthog-python`'s real API may differ from this design's sketch** — explicitly unverified (§5); Developer must confirm against the actually-installed version before shipping.
11. **(new) Mobile's and backend's typed flag-key lists (`FEATURE_FLAGS` / `FeatureFlagKey`) have no shared source of truth** — kept in sync by hand. Logged to backlog (§10).

---

## 9. Risk confirmation (fast lane — no human gate here; flag loudly instead if this should escalate)

**Risk: med — confirmed, not escalated.**

The literal keyword scan that would flag this ticket (`schema`, `migration`, `RLS`) is present, but the substance is materially different from SS-025's `Risk: high` schema ticket, which is the only comparable precedent in this repo:

- **Purely additive.** A brand-new, empty table with zero existing consumers and zero existing data touched — no `ALTER`/`DROP` on any table another shipped ticket reads or writes, no backfill of live user data, no type drop. Trivially revertible with zero blast radius on anything already shipped (contrast SS-025's `DROP TYPE`/`DROP TABLE` against 7 shipped tickets' live data).
- **RLS posture is the already-established safe pattern**, not a new risky one: default-deny, explicit per-row opt-in, no wildcard — copied directly from `007_occasions_registry.sql`'s proven shape, not invented under time pressure.
- **No new externally-reachable endpoint.** Nothing in this ticket adds an HTTP route; the accessor is an internal backend mechanism with no consumer wired yet. The actual external/AI-facing stakes (model routing, real money-adjacent quota enforcement) land with SS-028/SS-029, which the execution plan's own Wave-0/Wave-1 table already classifies `high` — this ticket is deliberately the boring, low-stakes plumbing underneath those.
- **No new secret.** Reuses `SUPABASE_SERVICE_ROLE_KEY` and `POSTHOG_API_KEY`, both already provisioned, already real, already used server-side in this exact codebase (`ss015_verify_wear_history.py`, SS-009's Sentry/PostHog wiring) — nothing new to leak, no new credential class introduced.
- **`service_role`-only reads for a non-user-data table** is compliant with, not a violation of, CLAUDE.md's Security section (§3.4) — it is a deliberate first-of-its-kind pattern in `adapters/`, called out explicitly rather than smuggled in, but it is not itself a risk escalation: there is no per-user data this could leak, and the write side is fully locked down by RLS's absence-of-policy mechanism either way.

This ticket stays on the **fast lane**: Architect → Developer → QA auto-chain, human review consolidated at the PR gate.

---

## 10. Backlog deltas

**Active-table resurfacing scan** (tags `infra`/`schema`/`ai`/`ci`, per the orchestrator's hand-off and my own re-scan):

- **`BL-076`** (infra) — stays **Active**, note updated: SS-026 builds the *mechanism* (`gemini_quota_ceiling_rpm` config key, seeded conservative at `15` matching today's hardcoded value, readable via `AppConfigService`) but deliberately does **not** wire consumption — `backend/services/gemini_rate_limiter.py` is untouched, per the ticket's own explicit instruction. BL-076's underlying problem (an artificially-low, stale RPM ceiling) is **not fixed by this ticket**; it needs a follow-up (likely folded into SS-028's router work, or a small standalone ticket) that actually reads `GEMINI_QUOTA_CEILING_SPEC` and passes the result into `GeminiRateLimiter(max_requests=...)`.
- **`BL-037`** (infra) — stays Active, note added: does not block this ticket. The "no redeploy, no restart" AC is demonstrated (§7.4) against a locally-run script/process, not a deployed Railway instance — Railway's absence doesn't change what this ticket can prove, since the property being demonstrated (TTL-cache reload within one running process) is deployment-topology-independent.
- **`BL-062`** (infra) — stays Active, note added: `app_config`/`AppConfigService` is confirmed as *a* mechanism SS-029 can use for cost-cap thresholds, but this ticket builds no cap and enforces nothing — SS-029's own `ICostLedger` port is still the actual enforcement point (likely Redis-backed for atomicity, per §3.3's "strict consistency doesn't belong in `app_config`" boundary).

**New rows** (Active, tags as marked):

- **`BL-091`** (infra) — `posthog-python` is a brand-new backend dependency; this ticket's `FeatureFlagService` sketch is `[trained-knowledge, unverified]` against the actually-installed version's real API (client-class shape vs. older module-level-function shape), and separately, efficient server-side flag evaluation may need a *personal* API key (not the project key) for local flag-definition polling rather than one HTTP round-trip per check — neither is confirmed. Needs verification once a real consumer (the paywall ticket) makes evaluation-latency/quota actually matter.
- **`BL-092`** (infra) — mobile's `constants/featureFlags.ts` (`FEATURE_FLAGS`) and backend's `services/feature_flags.py` (`FeatureFlagKey`) are two independently-maintained lists of the same logical flag keys, kept in sync by hand — same class of drift risk as any dual-implementation contract in this codebase (c.f. the SQL/Python/TypeScript occasion-normalisation triad in SS-025, which at least has a byte-identical-contract test; this pair does not yet).
- **`BL-093`** (infra) — zero real PostHog feature flags exist in the dashboard yet; `paywall_copy_variant` is a typed placeholder requiring a human to actually create the flag in PostHog before any code path can exercise it live. Same class as `BL-047`/`BL-048` (no agent in this pipeline has PostHog dashboard access).
- **`BL-094`** (schema) — `app_config.updated_by` is nullable with no default and no constraint forcing a real caller identity on every write; a script/dashboard edit that forgets to pass it leaves a visible but silent audit-trail gap. Deliberate (a fake default would be worse — §3.1) but not enforced; revisit if config writes become frequent enough for this to matter in practice.

No Active/Parked row is fully **Resolved** by this ticket — everything it touches (`BL-076`, `BL-037`, `BL-062`) gets a mechanism it can eventually be built on, not a closure. This is consistent with the ticket's own Status note ("do not patch the constant... move the mechanism") and is called out explicitly rather than silently claimed.

---

**Risk: med** — confirmed per §9: purely additive schema (new, unconsumed table; zero existing data/consumers touched), RLS copies an already-proven default-deny/explicit-opt-in pattern, no new externally-reachable endpoint, no new secret. Fast lane: Architect → Developer → QA auto-chain, human review consolidated at the PR.
