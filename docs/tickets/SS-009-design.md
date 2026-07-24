# SS-009 — Error Monitoring & Analytics Instrumentation — Design

## Scope restatement

This ticket wires up two already-installed-but-uninitialised SDKs — `@sentry/react-native` (mobile crash/error monitoring) and `posthog-react-native` (product analytics) — so both start capturing before any user-interaction code runs, and confirms backend Sentry (already initialised in `backend/main.py`) actually captures unhandled exceptions rather than just having been configured. Concretely: initialise Sentry on the mobile client with DSN/environment/release, wire user context (`user_id`, `plan_tier`) into every authenticated session (not just the OTP-verify moment), configure EAS-build-time source map upload, stand up a typed `useAnalytics()` hook backed by a PostHog singleton client with 13 typed event constants (the 12 named in the ticket description plus `app_opened`, which the AC also requires), wire the two events that have a real call site today (`app_opened`, `register`), and add automated proof that backend unhandled exceptions actually reach Sentry's capture path. It does not build any of the not-yet-existing features (wardrobe upload, styling AI reward screen, premium paywall, social share, try-on) that the other 10 named events belong to — those ship their own `track()` call when each feature is actually built.

## Current repo state (verified this session)

- Backend: `backend/main.py` already calls `sentry_sdk.init(dsn=..., traces_sample_rate=0.1, environment=...)` guarded by `if sentry_dsn:`, reading `SENTRY_DSN_BACKEND`. `sentry-sdk==2.64.0` is pinned in `backend/requirements.txt`. No test exists anywhere in `backend/tests/` that exercises Sentry capture behavior.
- Mobile: `@sentry/react-native@^8.15.1` and `posthog-react-native@^4.52.0` are both real dependencies in `mobile/package.json`. `mobile/app/_layout.tsx` already `import * as Sentry from '@sentry/react-native'` and calls `Sentry.captureException(fontError)` in a font-load-error handler — but **`Sentry.init()` is never called anywhere in the mobile codebase** (confirmed via repo-wide grep for `Sentry.init`), so that existing `captureException` call is currently a silent no-op. PostHog has zero references anywhere in `mobile/` outside `package.json`/`package-lock.json`.
- Root `.env` (gitignored, confirmed via `.gitignore` lines 2–4) already has **non-empty** real values for `SENTRY_DSN_BACKEND`, `SENTRY_DSN_MOBILE`, and `POSTHOG_API_KEY` — checked presence only (`^KEY=.+` regex match), values not read or transcribed here. This is a materially better starting position than SS-010's R2-credentials gap: the credentials exist, they're just not wired to the right place for the mobile client.
- **Real gap found: mobile env vars aren't `EXPO_PUBLIC_`-prefixed.** Expo only inlines env vars prefixed `EXPO_PUBLIC_` into the client bundle (confirmed against this repo's own existing pattern — `mobile/lib/supabase.ts` reads `process.env.EXPO_PUBLIC_SUPABASE_URL`/`EXPO_PUBLIC_SUPABASE_ANON_KEY`, and `mobile/.env.local` — checked for key names only, not values — has exactly `EXPO_PUBLIC_SUPABASE_URL`, `EXPO_PUBLIC_SUPABASE_ANON_KEY`, `EXPO_PUBLIC_BACKEND_URL`, nothing Sentry/PostHog-related). `SENTRY_DSN_MOBILE`/`POSTHOG_API_KEY` in the root `.env`/`.env.example` are the wrong shape for the mobile client to ever read them — the mobile app's own `mobile/.env.local` needs new, correctly-prefixed entries. `[trained-knowledge, not verified this session against current Expo docs — labeled per OPERATOR_RULEBOOK §E]` that `EXPO_PUBLIC_` prefixing is still the mechanism in the installed Expo SDK 56; Developer should spot-check this against `node_modules/expo-constants`/Expo's env docs if anything behaves unexpectedly.
- **No EAS project exists at all.** No `mobile/eas.json`, no `extra.eas.projectId` in `mobile/app.json`. This ticket can still write the correct config shape (see below) but cannot verify "source maps uploaded during EAS build" end-to-end — see Open Questions.
- `users.plan_tier` (enum `'free' | 'premium' | 'premium_annual'`, `supabase/migrations/001_initial.sql` line 16/35) already exists and is in `mobile/types/supabase.ts`'s generated types — no schema change needed for the "plan_tier in error context" AC.

## Files to create/modify

**Mobile — new:**
- `mobile/lib/sentry.ts` — `initSentry()` (idempotent, no-ops if `EXPO_PUBLIC_SENTRY_DSN` is unset), `setSentryUserContext(userId, planTier?)`, `clearSentryUserContext()`.
- `mobile/lib/analytics.ts` — `initAnalytics()` (constructs a singleton `PostHog` client, no-ops if `EXPO_PUBLIC_POSTHOG_API_KEY` is unset), `capture(event, properties?)` (always PII-checked, network-send skipped under `__DEV__`), `identifyAnalyticsUser(userId)`, `resetAnalyticsUser()`.
- `mobile/constants/analyticsEvents.ts` — `ANALYTICS_EVENTS` const object (13 typed event-name string constants) + `AnalyticsEventName` union + `AnalyticsEventProperties` per-event property map (see Concrete values). This is the first file in `mobile/constants/` — the folder doesn't exist yet, but CLAUDE.md's Anti-Patterns section already names `constants/api.ts` as the required home for a different concern (hardcoded URLs), establishing the convention; this ticket doesn't touch `api.ts` itself.
- `mobile/hooks/useAnalytics.ts` — `useAnalytics()` returning `{ track }`, a `useCallback`-memoized, type-safe wrapper over `lib/analytics.ts`'s `capture`.
- `mobile/eas.json` — build profiles (`development`/`preview`/`production`), each setting `EXPO_PUBLIC_APP_ENV` via `env`.

**Mobile — modify:**
- `mobile/app/_layout.tsx` — call `initSentry()` and `initAnalytics()` at module scope (top of file, before the component, mirroring `lib/supabase.ts`'s existing module-scope `createClient()` side effect — satisfies "both initialised before any user interaction code runs"); call `useAnalytics()` inside `RootLayout` and fire `track(ANALYTICS_EVENTS.APP_OPENED)` in a mount-only `useEffect`; wrap the default export with `Sentry.wrap(RootLayout)` (standard `@sentry/react-native` pattern for capturing React render-tree errors — `[trained-knowledge, not verified this session]`).
- `mobile/hooks/useAuth.ts` — after `setSession(session)` in both `seedInitialSession` and the `onAuthStateChange` callback, call a new local `syncMonitoringContext(session)` helper: on a real session, `setSentryUserContext(userId)` + `identifyAnalyticsUser(userId)` immediately, then `fetchUserPlanTier(userId)` and `setSentryUserContext(userId, planTier)` once it resolves (fire-and-forget, not awaited — matches the ticket's own "never `await` in UI code" note extended to monitoring context); on `session === null`, `clearSentryUserContext()` + `resetAnalyticsUser()`. This is the one place that covers *every* authenticated session (fresh OTP verify AND a returning user's persisted-session reopen), which `verify-otp.tsx` alone would not.
- `mobile/features/auth/auth.service.ts` — add `fetchUserPlanTier(userId: string): Promise<PlanTier | null>`, same try/catch-fail-safe-to-null shape as the existing `checkOnboardingCompleted`.
- `mobile/features/auth/auth.types.ts` — add `export type PlanTier = Database['public']['Enums']['plan_tier']` (import `Database` from `../../types/supabase`).
- `mobile/app/(auth)/verify-otp.tsx` — in `verifyOtpMutation`'s `onSuccess`, fire `track(ANALYTICS_EVENTS.REGISTER, { method: 'phone_otp' })` when `session.user.created_at === session.user.last_sign_in_at` (Supabase sets these identically on first sign-up — `[trained-knowledge, not verified this session]`, see Open Questions). This is the only one of the 12 named events with clean UI-flow ownership by an existing screen.
- `mobile/app.json` — add `"@sentry/react-native/expo"` to the `plugins` array with `{ organization, project, url }` config (values TODO — see Open Questions; ships as an obviously-labeled placeholder, not invented values, same precedent as BL-007/BL-022's placeholder tokens).
- `mobile/.env.local` — add `EXPO_PUBLIC_SENTRY_DSN=`, `EXPO_PUBLIC_POSTHOG_API_KEY=`, `EXPO_PUBLIC_POSTHOG_HOST=https://us.i.posthog.com`, `EXPO_PUBLIC_APP_ENV=development` — Developer copies the real values from the root `.env`'s existing `SENTRY_DSN_MOBILE`/`POSTHOG_API_KEY` (this file is gitignored; no secret ever touches a commit).
- `.env.example` (root) — add the correctly-prefixed placeholder names alongside the existing (now-superseded-for-mobile-purposes) `SENTRY_DSN_MOBILE`/`POSTHOG_API_KEY` entries: `EXPO_PUBLIC_SENTRY_DSN=`, `EXPO_PUBLIC_POSTHOG_API_KEY=`, `EXPO_PUBLIC_POSTHOG_HOST=`, `EXPO_PUBLIC_APP_ENV=`. Also add `ENVIRONMENT=` (backend) — pre-existing, undocumented gap in `.env.example` for a var `backend/main.py` already reads; cheap to fix while touching this file, not otherwise in scope.

**Backend — modify:**
- `backend/main.py` — add `release=f'stylesense-backend@{app.version}'` to the existing `sentry_sdk.init(...)` call (minor completeness improvement; not itself gating any AC, mirrors the mobile release field).

**Backend — new tests:**
- `backend/tests/test_sentry_integration.py` (see Test plan).

**Mobile — new/modified tests:** see Test plan.

**Explicitly not touched:** no DB schema/migration, no RLS, no payments code, no new FastAPI route, no changes to `routers/outfit_suggestions.py` or any AI port/adapter.

## Concrete values to use, not invent

Transcribed verbatim from `docs/tickets/raw/SS-009.md`:
- The 12 named events: `install`, `register`, `first_item_added`, `first_suggestion_viewed`, `first_outfit_saved`, `premium_paywall_viewed`, `subscription_started`, `item_uploaded`, `outfit_shared`, `affiliate_link_clicked`, `tryon_generated`, `category_filtered`.
- Plus `app_opened`, required by its own separate AC line ("PostHog records an `app_opened` event on launch") — **13 typed constants total**, not 12; the ticket's own Description list and AC list are slightly inconsistent (the description's "all key analytics events" enumeration omits `app_opened`, the AC requires it) and this design reconciles them rather than silently dropping one.
- Funnel: `onboarding → first item → first suggestion → premium`, mapped to real event names as `register → first_item_added → first_suggestion_viewed → premium_paywall_viewed` (see Open Questions — this is a PostHog dashboard configuration step, not code).
- Sentry free tier 5k errors/month, PostHog free tier 1M events/month (informational, no code depends on this).
- `tracesSampleRate: 0.1` — reused from the backend's existing value in `backend/main.py` for consistency across both SDKs (ticket doesn't pin a mobile-specific value; this is the Architect's own reasonable choice, flagged as such).

Reconciled with the existing schema/codebase:
- `users.plan_tier` enum values: `'free' | 'premium' | 'premium_annual'` (`supabase/migrations/001_initial.sql`).
- `EXPO_PUBLIC_` prefix requirement for any mobile env var (see Current repo state above) — `mobile/lib/supabase.ts`'s existing pattern is the precedent being followed, not invented.

Architect's own reasonable choices (not literal ticket spec, flagged as such):
- PII guard: `capture()` rejects any event-property key matching `phone`, `phone_number`, `name`, `full_name`, `email` (case-insensitive) — throws in `__DEV__`/test (fails loud during development) and strips + logs a Sentry warning-level message in production (fails safe — a telemetry bug should never crash the app).
- `AnalyticsEventProperties` per-event shape (none contain phone/name/email by construction):
  ```ts
  export const ANALYTICS_EVENTS = {
    APP_OPENED: 'app_opened',
    INSTALL: 'install',
    REGISTER: 'register',
    FIRST_ITEM_ADDED: 'first_item_added',
    FIRST_SUGGESTION_VIEWED: 'first_suggestion_viewed',
    FIRST_OUTFIT_SAVED: 'first_outfit_saved',
    PREMIUM_PAYWALL_VIEWED: 'premium_paywall_viewed',
    SUBSCRIPTION_STARTED: 'subscription_started',
    ITEM_UPLOADED: 'item_uploaded',
    OUTFIT_SHARED: 'outfit_shared',
    AFFILIATE_LINK_CLICKED: 'affiliate_link_clicked',
    TRYON_GENERATED: 'tryon_generated',
    CATEGORY_FILTERED: 'category_filtered',
  } as const;

  export type AnalyticsEventName = (typeof ANALYTICS_EVENTS)[keyof typeof ANALYTICS_EVENTS];

  export interface AnalyticsEventProperties {
    app_opened: Record<string, never>;
    install: Record<string, never>;
    register: { method: 'phone_otp' };
    first_item_added: { category?: string };
    first_suggestion_viewed: Record<string, never>;
    first_outfit_saved: Record<string, never>;
    premium_paywall_viewed: { source: string };
    subscription_started: { plan: 'monthly' | 'annual' };
    item_uploaded: { category?: string; source: 'camera' | 'gallery' };
    outfit_shared: { channel?: string };
    affiliate_link_clicked: { retailer?: string };
    tryon_generated: { outfit_id?: string };
    category_filtered: { category: string };
  }
  ```
- `register` new-vs-returning-user heuristic: `session.user.created_at === session.user.last_sign_in_at` (string equality on Supabase's ISO timestamps, which it sets identically at first sign-up). Reasonable, standard heuristic; not literally specified by the ticket.
- `eas.json` build profiles set `EXPO_PUBLIC_APP_ENV` to `development`/`preview`/`production` respectively, read by `lib/sentry.ts` as the Sentry `environment` tag (falls back to `__DEV__ ? 'development' : 'production'` when unset, e.g. local `npx expo start`).
- `EXPO_PUBLIC_POSTHOG_HOST` defaults to `https://us.i.posthog.com` (PostHog Cloud US) — **an assumption, not a confirmed account setting**, see Open Questions.
- Sentry `release` format: `` `stylesense@${Constants.expoConfig?.version ?? '0.0.0'}` `` on mobile (reads `mobile/app.json`'s `expo.version`, currently `1.0.0`), `` `stylesense-backend@${app.version}` `` on backend (reads the existing `FastAPI(version='0.1.0')`).

## Edge cases

Carried forward / newly surfaced:
- Offline analytics (from the raw ticket): `posthog-react-native`'s own SDK batches locally and flushes on reconnect — no app-level code needed; this design relies on the library's documented default behavior rather than reimplementing batching (`[trained-knowledge, not verified this session]`).
- Missing DSN/API key at runtime (e.g. a dev machine without `.env.local` filled in): `initSentry()`/`initAnalytics()` both no-op rather than throwing — the app must never fail to boot because monitoring credentials are absent.
- Double-init: both `init*()` functions guard against being called more than once (module-level flag / existing-client check), since `app/_layout.tsx` can theoretically remount in fast-refresh dev scenarios.
- Sign-out clears both Sentry user context and PostHog identity (`clearSentryUserContext()` + `resetAnalyticsUser()`) — an error thrown by a *different* logged-out user must never appear attributed to the previous user in the dashboard.
- `plan_tier` fetch failing (network blip, RLS edge case) must not crash the auth flow — `fetchUserPlanTier` fails safe to `null`, and `setSentryUserContext` simply skips the `plan_tier` tag rather than tagging a bad value.
- PII guard fires even on already-supposedly-safe internal call sites (defense in depth) — a future ticket accidentally passing `{ phone: ... }` into `track()` should fail loudly in dev/tests, not silently leak to PostHog in production.
- `__DEV__` capture-skip must not skip the PII assertion itself (see Concrete values) — otherwise a PII leak introduced during local dev would never be caught until it reached production.
- New edge case (not in the raw ticket): most of the 12 named events currently have **no real call site** — the owning features (wardrobe upload, styling-AI reward screen, save-outfit, premium paywall, social share, affiliate links, try-on, Discover category filter) don't exist yet in this repo. Shipping the typed constant now and wiring the call later (each owning ticket's job) is the deliberate design, not an oversight — see Open Questions and Backlog deltas.

## Test plan

**Backend — `backend/tests/test_sentry_integration.py`:**
1. `test_sentry_initializes_when_dsn_env_var_present` — monkeypatch `SENTRY_DSN_BACKEND` to a fake DSN, `importlib.reload(main)`, assert `sentry_sdk.Hub.current.client is not None` and its `dsn` matches; reset the Hub in teardown so this doesn't leak into other tests.
2. `test_sentry_skips_init_when_dsn_env_var_absent` — monkeypatch the var unset, reload, assert no client is configured (mirrors the CI environment, which has no real `.env`).
3. `test_unhandled_exception_captured_by_sentry_integration` — a small isolated `FastAPI()` app (not `main.app`) with `sentry_sdk.init(dsn=<fake>, transport=<capturing test transport>)` and one route that raises; call it via `TestClient(raise_server_exceptions=False)`; assert the capturing transport recorded at least one event. This is the actual proof behind the AC "Backend: Sentry initialised in FastAPI; unhandled exceptions captured" — not just eyeballing that `sentry_sdk.init()` was called.

**Mobile — new:**
- `mobile/__tests__/lib/sentry.test.ts`:
  1. `initSentry()` calls `Sentry.init` with `dsn`/`environment`/`release`/`tracesSampleRate` when `EXPO_PUBLIC_SENTRY_DSN` is set.
  2. `initSentry()` does not call `Sentry.init` when the DSN env var is unset.
  3. `initSentry()` calling `Sentry.init` only once across two calls (idempotency guard).
  4. `setSentryUserContext(id, tier)` calls `Sentry.setUser({ id })` and `Sentry.setTag('plan_tier', tier)`.
  5. `setSentryUserContext(id)` (no tier) calls `setUser` but not `setTag`.
  6. `clearSentryUserContext()` calls `Sentry.setUser(null)`.
- `mobile/__tests__/lib/analytics.test.ts`:
  1. `initAnalytics()` constructs the PostHog client with the configured API key/host when the env var is set; no-ops otherwise.
  2. `capture()` does not call the underlying PostHog client's `.capture()` when `__DEV__` is `true`.
  3. `capture()` calls the underlying client's `.capture(event, properties)` when `__DEV__` is `false`.
  4. `capture()` throws when `properties` contains a banned PII key (`phone`, `email`, `name`, `full_name`) under `__DEV__`/test conditions.
  5. `identifyAnalyticsUser(id)` calls the client's `.identify(id)`.
  6. `resetAnalyticsUser()` calls the client's `.reset()`.
- `mobile/__tests__/constants/analyticsEvents.test.ts`:
  1. `ANALYTICS_EVENTS` has exactly 13 entries, each a unique non-empty snake_case string, and includes `app_opened`.
- `mobile/__tests__/hooks/useAnalytics.test.ts`:
  1. `track()` calls `lib/analytics.ts`'s `capture` with the given event name and properties (mocked module).
  2. The returned `track` reference is stable across re-renders (asserts the `useCallback` anti-pattern rule from CLAUDE.md is actually honored).
- `mobile/__tests__/app/_layout.test.tsx` (new file — none exists today):
  1. `initSentry()` and `initAnalytics()` are each called exactly once when the module is first imported/rendered.
  2. `track(ANALYTICS_EVENTS.APP_OPENED)` fires exactly once on mount, not on every re-render.

**Mobile — modified:**
- `mobile/__tests__/hooks/useAuth.test.ts` — add:
  1. On a resolved non-null session, `setSentryUserContext`/`identifyAnalyticsUser` are called with the session's `user.id` (mock `lib/sentry.ts`/`lib/analytics.ts`).
  2. Once the mocked `fetchUserPlanTier` resolves, `setSentryUserContext` is called again including the tier.
  3. On a `SIGNED_OUT` event (session → null), `clearSentryUserContext`/`resetAnalyticsUser` are called.
- `mobile/__tests__/features/auth/auth.service.test.ts` — add:
  1. `fetchUserPlanTier` queries `users.plan_tier` filtered by `id` and returns the tier.
  2. `fetchUserPlanTier` fails safe to `null` on a thrown/Supabase error (same shape as the existing `checkOnboardingCompleted` test).
- `mobile/__tests__/app/(auth)/verify-otp.test.tsx` — add:
  1. On verify success where `created_at === last_sign_in_at`, `track(ANALYTICS_EVENTS.REGISTER, { method: 'phone_otp' })` fires once.
  2. On verify success where the timestamps differ (returning user), `track` is not called with `REGISTER`.

## Open questions / blockers

1. **No EAS project provisioned — blocks live verification of the source-maps AC.** No `eas.json` existed before this ticket (now added with build-profile config) and `mobile/app.json` has no `extra.eas.projectId`. Someone must run `eas init` (interactive, requires an Expo account) to get a real project ID, create a Sentry project to get the `organization`/`project` slugs for the `@sentry/react-native/expo` plugin config in `app.json`, and run `eas secret:create --name SENTRY_AUTH_TOKEN ...` before a real EAS build will actually upload source maps. This design ships correct config shape and code; "Sentry traces show TypeScript line numbers" cannot be verified until a real EAS build runs. Same class of gap as SS-010's R2-credentials blocker. Logged as `BL-047`.
2. **PostHog Cloud region (US vs EU host) unconfirmed.** `EXPO_PUBLIC_POSTHOG_HOST` defaults to `https://us.i.posthog.com` — if the actual PostHog account/project was provisioned on the EU instance, events will silently fail to appear in the dashboard (wrong host, not an error the SDK necessarily surfaces loudly). Needs a one-line confirmation from whoever created the PostHog account. Logged as `BL-048`.
3. **Most of the 12 named events have no real call site yet.** `install`, `first_item_added`, `first_suggestion_viewed`, `first_outfit_saved`, `premium_paywall_viewed`, `subscription_started`, `item_uploaded`, `outfit_shared`, `affiliate_link_clicked`, `tryon_generated`, `category_filtered` all belong to features that don't exist in this repo yet (wardrobe upload = SS-011/012/013, styling-AI reward screen = BL-034, premium/payments = unscheduled, social share/affiliate/try-on = Epics 4–6, Discover filtering = not yet built). This ticket ships the typed constants + hook infrastructure; each future feature ticket's Architect phase should wire the matching `track()` call as part of that feature's own scope, not retrofitted here. Logged as `BL-049` so it isn't forgotten piecemeal.
4. **PostHog funnel dashboard configuration is a manual step, not code.** "PostHog funnel: onboarding → first item → first suggestion → premium" requires creating a Funnel insight in the PostHog web UI with steps `register → first_item_added → first_suggestion_viewed → premium_paywall_viewed`. No agent in this pipeline has PostHog dashboard access — flagged as a manual step for the user post-merge, same pattern as SS-008's device-matrix testing (BL-010) and SS-010's live-bucket verification. The funnel can technically be configured now even with zero events flowing for the not-yet-built steps.
5. **"Sentry captures a test error visible in the dashboard within 30 seconds" is a manual verification step**, not something CI can prove (needs the real DSN + a live dashboard check). Recommend: after merge, trigger one real `Sentry.captureException` (mobile) and hit a route that raises (backend, locally with the real `.env`) and confirm both appear in the Sentry dashboard. Same class as SS-002/BL-005's "needs a live check" pattern.
6. **`register`'s new-vs-returning-user heuristic (`created_at === last_sign_in_at`) is unverified against live Supabase behavior this session** — reasonable and commonly used, but not confirmed against this project's actual Supabase Auth config. If it ever misfires (e.g. `register` firing on every login, or never firing), that's a signal this heuristic needs revisiting, not that the analytics pipe itself is broken.
7. **`app.json`'s `@sentry/react-native/expo` plugin config ships with placeholder `organization`/`project` values** — cannot be filled correctly without knowing the real Sentry org/project slugs (not reliably derivable from the DSN alone). Developer must fill these in from the Sentry dashboard, or from whoever provisioned the existing `SENTRY_DSN_MOBILE`/`SENTRY_DSN_BACKEND` values. Part of the same `BL-047` gap.

## Backlog deltas

Active-table resurfacing scan (tags `infra`/`ci`/`test`/`ai`, per this ticket's own pre-scan and the orchestrator's up-front scan): confirmed `BL-037` (no backend deployment) and `BL-038` (CI missing Snyk+deploy) are adjacent but not blockers — this ticket's source-map upload is an EAS-build-time concern, not a Railway-deployment concern, and neither row is resolved or worsened here. No other Active row (tag `infra`/`ci`/`test`/`ai`) intersects error-monitoring/analytics instrumentation specifically. None resolved by this ticket.

Added to `docs/BACKLOG.md`'s **Active** table:
- `BL-047` (infra) — No EAS project provisioned (`eas init` never run, no `extra.eas.projectId`, no Sentry org/project slugs, no `SENTRY_AUTH_TOKEN` EAS secret); blocks live verification of the source-maps-upload AC, config shipped but unverifiable end-to-end.
- `BL-048` (infra) — PostHog Cloud region (US vs EU host) unconfirmed; `EXPO_PUBLIC_POSTHOG_HOST` defaults to the US instance as an assumption.
- `BL-049` (infra) — 10 of the 12 named analytics events have no real call site yet (owning features don't exist); each future feature ticket must wire its own `track()` call.

## Risk: low

Justification: this ticket touches no DB schema/migration, no RLS, no payments code, and no new externally-reachable endpoint — it reads an existing DB column (`users.plan_tier`, already RLS-scoped to the caller by existing policy, unchanged here) and wires two already-installed, already-credentialed third-party SDKs that only send *outbound* telemetry (no new inbound attack surface). It's the literal "analytics hooks" example CLAUDE.md's own two-lane rubric names as a fast-lane case. Fast lane: Architect → Developer → QA auto-chain, human review consolidated at the PR.
