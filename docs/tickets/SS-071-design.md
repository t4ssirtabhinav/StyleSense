# SS-071 — Auth Foundation: Multi-Provider Entry Points, Sign-Out, Onboarding-Routing Hoist — Design

Ticket: `docs/tickets/raw/SS-071.md` · Branch: `feature/SS-071-auth-foundation` · Tier: standard (Est 6h)

## Scope restatement

Three structural fixes to `mobile/` auth, no backend and no schema change. (1) `app/(auth)/login.tsx` stops *being* the phone form and becomes a host that renders methods from a typed registry — with exactly one registered method it must render byte-for-byte the same UI it does today, and SS-003's existing login tests must pass unmodified as the proof. (2) The app gets a sign-out for the first time: a `signOut()` service call, a `useSignOutMutation`, and a confirmed Sign Out action on the Profile tab, which must clear the Supabase session, its persisted storage, the React Query cache, *every* user-scoped Zustand store, and the Sentry/PostHog identity — otherwise the next user on the device sees the previous user's data. (3) The `/onboarding`-vs-`/` decision, which today lives in a `useEffect` inside `verify-otp.tsx` and nowhere else, is hoisted into one shared mechanism that applies to any authenticated session however it was minted — including a cold app open that touches no auth screen at all.

The ticket exists because a `/new-feature` intake for a second sign-in method found the first one unfinished (`BL-167`, `BL-168`). It deliberately ships **no** second method (that is SS-072) and **no** account-linking UI (`BL-172`, settled policy, deferred owner).

## Ground-check — what I verified in the repo before designing

Every claim below was read out of the current working tree today (2026-08-15), not assumed.

**The `BL-168` routing gap, confirmed exactly as the live reproduction described.**

| Claim | Verified |
|---|---|
| `app/(tabs)/_layout.tsx` guards *away from* tabs on no-session only | Yes — `_layout.tsx:30-58`: reads `session`/`isSessionLoading` from `useAuthStore`, renders a `Loading…` Card while loading, `<Redirect href="/login" />` when `!session`. **No onboarding check of any kind.** |
| `app/(auth)/login.tsx` has zero session awareness | Yes — `login.tsx:23-86` imports only `useRouter`, `useSendOtpMutation`, `validateIndianMobile`, `CountryCodePicker`. It never reads `useAuthStore`, never renders `Redirect`. It renders the phone form unconditionally. |
| No `app/(auth)/_layout.tsx` exists | Yes — glob of `mobile/app/**/_layout.tsx` returns exactly two files: `app/_layout.tsx` and `app/(tabs)/_layout.tsx`. The `(auth)` group has no layout at all. |
| `verify-otp.tsx` is the only forward-routing site | Yes — `verify-otp.tsx:55-65`, a `useEffect` gated on `verifiedUserId && onboardingCompletedQuery.isSuccess` doing `router.replace(data ? '/' : '/onboarding')`. Grep confirms no other `replace('/onboarding')` anywhere. |
| The root layout's session bootstrap is fine | Yes — `app/_layout.tsx:39` calls `useAuth()` unconditionally above the `Stack`; `hooks/useAuth.ts:42-87` seeds via `getSession()` then subscribes to `onAuthStateChange`, writing both into `auth.store.ts`. This is why the live full-page-navigation workaround landed authenticated: the session *did* load; only `/login` never looked at it. |

**The provider-agnostic claims in the raw ticket hold.**

- `features/auth/auth.store.ts` stores `Session | null` + `isSessionLoading` and nothing provider-specific. `hooks/useAuth.ts` branches purely on session truthiness. Both are additive-safe. Confirmed.
- `features/auth/auth.types.ts`: `AuthErrorCode` is a 5-member union (`invalid_phone`, `network_error`, `rate_limited`, `invalid_or_expired_otp`, `unknown`); `AuthError` is `{ code, message }`. Additive extension is trivially possible.
- `supabase/migrations/001_initial.sql:26-27`: `email TEXT UNIQUE` and `phone TEXT UNIQUE` — **both nullable**. `002_onboarding_completed.sql:22-23`'s auto-provision trigger inserts `(NEW.id, NEW.phone, NEW.email)`, so an SS-070 admin-created email-only account already produces a `public.users` row with `phone IS NULL`. AC #8's fixture is real, not hypothetical, and no constraint blocks a future `linkIdentity()`.
- RLS across the 5 migrations that reference it is `auth.uid()`-based (21 occurrences), never phone- or provider-based. Nothing here is phone-coupled.
- Grep for `user.phone` / `session.user.email` across all of `mobile/` returns **no matches** — no screen or hook reads an identifier off the session today. AC #8's "no screen assumes `session.user.phone`" is already true; the job is to keep it true and prove it with a fixture, not to fix existing code. `app/(tabs)/profile.tsx:14-15` reads only `session?.user.id`.

**The four user-scoped Zustand stores (this is the exhaustive list AC #6 needs).** Glob of `mobile/features/**/*.store.ts` returns exactly four files, containing **six** `create<...>()` stores:

| File | Store | Holds user data? |
|---|---|---|
| `features/auth/auth.store.ts` | `useAuthStore` | Yes — the session itself |
| `features/onboarding/onboarding.store.ts` | `useOnboardingStore` | Yes — name, gender, city, style prefs. Has `reset()` |
| `features/wardrobe/wardrobe.store.ts` | `useWardrobeUploadStore` | Yes — in-flight upload tasks w/ local URIs. **No `reset()`** |
| `features/wardrobe/wardrobe.store.ts` | `useWardrobeBatchStore` | Yes — batch items + draft tags. Has `reset()` |
| `features/wardrobe/wardrobe.store.ts` | `useWardrobeFilterStore` | Yes (weakly) — filters/search text. Has `reset()` |
| `features/outfit-ai/outfit-ai.store.ts` | `useOutfitAiStore` | Yes — occasion, deck index, dismissed fingerprints, `sessionId`. Has `resetDeck()` but **no full reset** |

Note the raw ticket's Description names a "style-score" store — **there is none**; `features/style-score/` has no `.store.ts`. Its state is React Query only, so the cache clear covers it. Two of the six stores lack a full reset and need one added (see Files).

**`supabase.auth.signOut()` signature — `[VERIFIED 2026-08-15 against installed `@supabase/supabase-js@^2.108.2` → `node_modules/@supabase/auth-js/dist/module/GoTrueClient.d.ts:1960-2005`]`** (read from the installed SDK's own typings, per the raw ticket's `[TRAINED KNOWLEDGE — verify]` instruction and `docs/OPERATOR_RULEBOOK.md` §E):

- Signature is `signOut(options?: SignOut): Promise<{ error: AuthError | null }>` — it **resolves with an error field, it does not throw** on a server-side failure.
- **The default scope is `'global'`** — the SDK's own doc comment carries an explicit `**Warning:**` that this "signs the user out of **every device they are currently signed in on**, not just the current tab/session", and recommends passing `{ scope: 'local' }` explicitly for a Sign Out button "especially when users sign in from multiple devices and do not expect signing out of one to terminate the others". **This design takes that recommendation: `{ scope: 'local' }`.** Leaving the default would silently kill the user's other devices.
- Docs also confirm the browser-context behaviour we rely on: `signOut()` removes storage items and triggers a `SIGNED_OUT` event — which `hooks/useAuth.ts`'s existing `onAuthStateChange` subscription already handles by setting `session: null` and calling `clearSentryUserContext()` + `resetAnalyticsUser()`. **Sign-out therefore does not need to touch monitoring context by hand** — the existing listener does it, and doing it twice would be a second racing mechanism.

**`expo-router` surface used here exists** — `usePathname`, `useSegments`, `Redirect`, `Stack` are all exported from the installed `expo-router` (`node_modules/expo-router/build/exports.d.ts:2`, plus `Redirect`/`Stack` already in use in `(tabs)/_layout.tsx` and `(auth)/onboarding.tsx`).

## The routing decision — mechanism (b), one decision function, two enforcement points

The raw ticket's Technical Notes require an explicit pick between (a) a shared hook each entry point calls, and (b) a guard in the route layouts, and forbid shipping both racing. **Pick (b), with the decision logic factored into one pure-ish hook that the layouts consume.** The hook is not a second mechanism: it *computes* a target and never navigates. **Only layouts navigate.**

Why (b) and not (a):

1. **AC #4 (cold open, no auth screen involved) is unreachable by (a) by construction.** A user with a persisted session who opens the app directly at `/` passes through no auth entry point; only a layout is mounted. Verified: `app/_layout.tsx` mounts `useAuth()` and a `Stack`, and the only guard downstream is `(tabs)/_layout.tsx`, which checks session presence and nothing else.
2. **(a) placed in `login.tsx` would break AC #1, mechanically.** `__tests__/app/(auth)/login.test.tsx:5-7` mocks `expo-router` as `{ useRouter }` only (no `Redirect`) and `:19-24` mocks `features/auth/auth.queries` as `{ useSendOtpMutation }` only, and the file renders `<LoginScreen />` bare with **no `QueryClientProvider`**. Giving `login.tsx` session-awareness — a `<Redirect>`, or a `useOnboardingCompletedQuery` call — makes those mocks return `undefined` and the existing suite throws. AC #1 demands those tests pass *unmodified*. A guard in a **new `app/(auth)/_layout.tsx`**, which that test never renders, satisfies both.
3. It generalises for free to SS-072's email/password and the deferred Google SSO: a new entry point registered in the method registry inherits the forward guard by living in the `(auth)` group, with no per-screen routing code to copy. This is precisely the `BL-168` failure mode (a second entry point that forgets to copy the block) designed out rather than documented.

### Decision function

`features/auth/useAuthRouting.ts` exports `useAuthRouting(): AuthRoutingState`, a discriminated union:

```
type AuthRoutingState =
  | { status: 'loading' }          // session still resolving, or onboarding query not settled
  | { status: 'unauthenticated' }  // no session
  | { status: 'onboarding' }       // session, onboarding_completed === false
  | { status: 'app' };             // session, onboarding_completed === true
```

It reads `useAuthStore` (`session`, `isSessionLoading`) and `useOnboardingCompletedQuery(session?.user.id)`, and returns `'loading'` unless `isSessionLoading === false` **and** (no session, or `onboardingCompletedQuery.isSuccess`). That `isSuccess` gate is the same discipline `verify-otp.tsx:56` uses today and the ticket's "loading state, not a flash" note demands — preserved, just moved.

Fail-safe semantics are preserved unchanged: `checkOnboardingCompleted` (`auth.service.ts:134-150`) already catches and returns `false`, and additionally `?? false` on a null row. A failed check yields `'onboarding'`, never `'app'`. The hook adds no error branch that could invert this.

### Enforcement points, and the scope limit that prevents a redirect loop

**`app/(tabs)/_layout.tsx` (modified).** Replace the two-branch session check with the hook: `'loading'` → the existing `auth-guard-loading` Card (unchanged testID/copy); `'unauthenticated'` → `<Redirect href="/login" />` (unchanged); `'onboarding'` → **`<Redirect href="/onboarding" />` (new — this is AC #4)**; `'app'` → the `<Tabs>` tree, unchanged.

**`app/(auth)/_layout.tsx` (new).** Renders `<Stack screenOptions={{ headerShown: false }} />` (matching the root Stack's options, so adding this layout introduces no header). Above it, the forward guard — **scoped to credential-entry routes only**:

- Determine the active route via `usePathname()`. The guard applies **only** when the path is `/login` or `/verify-otp`.
- On those two routes: `'loading'` → render the same `Loading…` Card (new testID `auth-entry-loading`); `'app'` → `<Redirect href="/" />`; `'onboarding'` → `<Redirect href="/onboarding" />`; `'unauthenticated'` → render the `Stack` (normal login).
- On any other `(auth)` route — i.e. `/onboarding` — render the `Stack` unconditionally. **No redirect in either direction.**

**Why `/onboarding` is deliberately excluded from the `(auth)` guard.** Three reasons, all load-bearing:

1. **It is the only way to guarantee no ping-pong.** With `/onboarding` excluded, exactly one route group can ever redirect *toward* `/onboarding` (tabs) and exactly one can redirect *away from* login (auth-entry). No route is both a source and a target of a redirect, so a loop is structurally impossible rather than merely unlikely — even if the cached `onboarding_completed` value were momentarily stale.
2. **It preserves SS-016 exactly.** `app/(auth)/onboarding.tsx:104-134` deliberately handles a *completed* user who arrives by direct URL/deep link (the `!progressQuery.data?.onboardingCompleted` clause on `showResumePrompt`, plus the auto-hydrate effect added specifically for that case). A guard that bounced completed users off `/onboarding` would make that SS-016 code dead and regress its tests — which AC #11 forbids.
3. **`onboarding.tsx` already has its own session guard** (`:287-301`: loading Card, then `<Redirect href="/login" />` when `!session`), added as an SS-004 QA-blocker fix and asserted by its tests. Leaving it alone means no test rewrite and no duplicated redirect for the same route.

**`app/(auth)/verify-otp.tsx` (modified).** Delete the `useEffect` at `:55-65`, the `useOnboardingCompletedQuery` import and call, and the now-unused `verifiedUserId` state's routing role. `verifiedUserId` state itself is removed entirely: after a successful verify, `supabase.auth.onAuthStateChange` fires → `useAuth` writes the session → the `(auth)` layout guard (which wraps this screen) sees `'app'`/`'onboarding'` and redirects. **`verify-otp.tsx` performs no navigation at all after this ticket.** The `register` analytics `track()` in `onSuccess` (`:79-81`) stays exactly as-is.

The redirect-loop test the ticket's Technical Notes demand — complete onboarding, land in tabs, *stay* there — is in the Test plan below.

## The method registry

`features/auth/auth.methods.ts` holds a typed array; `login.tsx` holds no phone-specific code at all.

```
export type AuthMethodId = 'phone_otp';                 // SS-072 adds 'email_password'
export interface AuthMethodDescriptor {
  id: AuthMethodId;
  label: string;                                        // chooser button copy
  Component: ComponentType;                             // self-contained form
}
export const AUTH_METHODS: readonly AuthMethodDescriptor[] = [
  { id: 'phone_otp', label: 'Continue with mobile number', Component: PhoneLoginForm },
];
```

`login.tsx` becomes: if `AUTH_METHODS.length === 1`, render `AUTH_METHODS[0].Component` **and nothing else** — no wrapper, no chooser chrome, no "more options" affordance. Otherwise render `<AuthMethodChooser />`. The `Card testID="login-screen"` wrapper and every string/prop from today's `login.tsx:56-84` move **verbatim** into `PhoneLoginForm` so the single-method render tree is byte-identical to today's (`login-screen` is referenced nowhere else in the repo — grepped — but keeping it stable is free).

**AC #2's seam is a module mock, not a prop.** The AC-#2 test does `jest.mock('features/auth/auth.methods')` returning two descriptors and asserts both labels render and each is reachable. This keeps `login.tsx` prop-free and — critically — leaves the *existing* `login.test.tsx`, which does not mock `auth.methods`, resolving the real one-entry registry and therefore rendering exactly today's tree. That is how AC #1 is satisfied *unmodified* rather than by editing the old tests.

`AuthMethodChooser` (`features/auth/components/AuthMethodChooser.tsx`): a `Button` per descriptor `label`; pressing one sets local `selectedId` state and renders that descriptor's `Component` with a ghost "Back" button returning to the list. Local `useState`, not Zustand — nothing outside this screen needs it (same reasoning `auth.store.ts:11-15` already records for the phone/OTP fields).

## Sign-out

**`resetAllUserState()` via self-registration, not a hand-maintained list.** `features/auth/userStateReset.ts`:

```
type UserStateResetFn = () => void;
const resetFns = new Set<UserStateResetFn>();
export function registerUserStateReset(fn: UserStateResetFn): void;   // called at store module scope
export function resetAllUserState(): void;                            // each in its own try/catch
```

Each user-scoped store file calls `registerUserStateReset(() => useXStore.getState().reset())` at module scope, immediately after its `create()`. This inverts the failure mode exactly as the ticket's Technical Notes ask: forgetting to register is a *store-author* omission next to the store, not an invisible omission in a sign-out function someone else owns. The registry is safe against unimported modules by construction — a Zustand store that was never imported holds no state to leak.

`resetAllUserState()` wraps each call in `try/catch` so one throwing reset cannot abort the rest (a partial clear is the cross-user-bleed bug this AC exists to prevent).

**`useAuthStore` does NOT register.** The session is cleared by `supabase.auth.signOut()` → `SIGNED_OUT` → the existing `onAuthStateChange` listener in `hooks/useAuth.ts:77-80`, which also clears Sentry/PostHog identity. Clearing it from the reset registry too would create a second path to the same state with different ordering. (The mutation does set it defensively — see below — but that is one explicit line with a stated reason, not a registry entry.)

**`useSignOutMutation` ordering** (in `auth.queries.ts`, using `useQueryClient()`):

1. `await queryClient.cancelQueries()` — settles in-flight fetches before the session dies (edge case: mutation in flight).
2. `await signOut()` from `auth.service.ts` — never throws (see below).
3. `resetAllUserState()`.
4. `queryClient.clear()` — must be **after** cancel and after the service call, so a late-resolving query cannot repopulate the cache post-clear.
5. `track(ANALYTICS_EVENTS.SIGN_OUT)` and `router.replace('/(auth)/login')` in the caller (`profile.tsx`'s `onSuccess`), not in the mutation — navigation stays in the screen, consistent with `login.tsx`'s existing `onSuccess`-navigates pattern.

Steps 3 + 4 run in a `finally`, so **AC #7 holds by construction**: a failed network `signOut` still clears local state and still lands on login.

**`signOut()` in `auth.service.ts`:**

```
export async function signOut(): Promise<void> {
  try {
    const { error } = await supabase.auth.signOut({ scope: 'local' });
    if (error) { /* report, do not rethrow — local state is cleared regardless */ }
  } catch { /* network/unknown — same */ }
}
```

It resolves `void` and never rejects, so the mutation's success path always runs. `{ scope: 'local' }` is the SDK's own documented recommendation for a Sign Out button (see ground-check) — the default `'global'` would sign the user out on every other device.

> **Developer verification task (do not assume):** read `node_modules/@supabase/auth-js/dist/module/GoTrueClient.js`'s `_signOut`/`_removeSession` to confirm that a **failed** revoke call with `scope: 'local'` still removes the persisted session from the storage adapter and still emits `SIGNED_OUT`. If it does **not**, the mutation's `finally` must additionally call `useAuthStore.getState().setSession(null)` **and** remove the persisted key so AC #7's "persisted storage still cleared" is literally true rather than assumed. Record which branch you found in the worklog. (Design assumes the defensive `setSession(null)` line is present either way — it is idempotent with the listener and costs nothing.)

**Profile UI.** `profile.tsx` gains a `variant="secondary"` "Sign Out" `Button` below "Edit Preferences", behind a confirmation. **Verified: `components/ui/index.ts` exports no Dialog/Modal/Alert primitive** — the list is Avatar, Badge, AppBottomSheet, Button, Card, CircularProgress, EmptyState, IconButton, Input, ProgressBar, Skeleton, Text, tokens. So: use a **two-step inline confirm** (press "Sign Out" → local state swaps in "Sign out of StyleSense?" + "Sign Out" / "Cancel" buttons). Not `Alert.alert` (not web-friendly; this app is web-first) and **not** a new shared UI primitive — that would be scope creep into `components/ui/` and is logged as a backlog row instead.

Double-tap protection: the Button is `disabled` while `signOutMutation.isPending`, and the mutation is idempotent (every step tolerates already-cleared state).

## Files to create/modify

**Create**

| Path | What |
|---|---|
| `mobile/app/(auth)/_layout.tsx` | New auth-group layout: forward guard (login/verify-otp only) + `<Stack screenOptions={{ headerShown: false }} />` |
| `mobile/features/auth/useAuthRouting.ts` | `useAuthRouting()` — the single decision function returning `AuthRoutingState` |
| `mobile/features/auth/auth.methods.ts` | `AuthMethodId`, `AuthMethodDescriptor`, `AUTH_METHODS` (one entry) |
| `mobile/features/auth/userStateReset.ts` | `registerUserStateReset()` / `resetAllUserState()` |
| `mobile/features/auth/components/PhoneLoginForm.tsx` | Today's `login.tsx` body, moved verbatim |
| `mobile/features/auth/components/AuthMethodChooser.tsx` | Multi-method chooser (inert until a 2nd method registers) |

**Modify**

| Path | What |
|---|---|
| `mobile/app/(auth)/login.tsx` | Reduced to a registry host — no phone code, no session code |
| `mobile/app/(auth)/verify-otp.tsx` | Delete `:55-65` routing `useEffect`, its `useOnboardingCompletedQuery` import/call and `verifiedUserId` state. Keep the `register` `track()` |
| `mobile/app/(tabs)/_layout.tsx` | Guard reads `useAuthRouting()`; adds the `'onboarding'` → `<Redirect href="/onboarding" />` branch (AC #4) |
| `mobile/app/(tabs)/profile.tsx` | Sign Out button + inline confirm + `useSignOutMutation` + `track(SIGN_OUT)` + `router.replace('/login')` |
| `mobile/features/auth/auth.service.ts` | Add `signOut()` (never throws, `{ scope: 'local' }`) |
| `mobile/features/auth/auth.queries.ts` | Add `useSignOutMutation()` |
| `mobile/features/auth/auth.types.ts` | **Additive only** — add `AuthMethodId` usage-side types if needed; do not touch `AuthErrorCode`'s 5 members, `AuthError`'s shape, or any existing copy (AC #9) |
| `mobile/features/onboarding/onboarding.store.ts` | `registerUserStateReset(() => useOnboardingStore.getState().reset())` |
| `mobile/features/wardrobe/wardrobe.store.ts` | Add a `reset()` to `useWardrobeUploadStore` (**it has none today**); register all three wardrobe stores |
| `mobile/features/outfit-ai/outfit-ai.store.ts` | Add a full `reset()` (`resetDeck()` only clears `deckIndex` — `selectedOccasionKey`, `dismissedFingerprints`, `sessionId` survive it); register it |
| `mobile/constants/analyticsEvents.ts` | Add `SIGN_OUT: 'sign_out'` + its `sign_out: { method: AuthMethodId }` property shape (partially closes `BL-049`'s "events with no call site" by adding one that ships *with* its call site) |

**Test files** — see Test plan. Two existing test files need their mocks *extended* (never weakened): `__tests__/app/(tabs)/_layout.test.tsx` (its `expo-router` mock exports only `Redirect`; it will need `auth.queries`/`useAuthRouting` mocking or a `QueryClientProvider`) and `__tests__/app/(tabs)/profile.test.tsx` (its `expo-router` mock's `useRouter` returns `{ push }` only — sign-out needs `replace`). `__tests__/app/(auth)/login.test.tsx` and `verify-otp.test.tsx`: **login's must not be edited at all** (AC #1); verify-otp's will need its routing assertions removed *because the behaviour moved*, which is the one sanctioned deletion — replace them with equivalent assertions against the `(auth)` layout so net coverage does not drop.

**Explicitly not touched:** `mobile/lib/supabase.ts` (`detectSessionInUrl: false` stays — `BL-170`), `hooks/useAuth.ts` (already provider-neutral; its `SIGNED_OUT` handling is what sign-out relies on), `app/(auth)/onboarding.tsx` (SS-016 behaviour preserved), `supabase/migrations/*` (no schema change), all of `backend/`.

## Concrete values to use, not invent

- `AuthErrorCode` today: `'invalid_phone' | 'network_error' | 'rate_limited' | 'invalid_or_expired_otp' | 'unknown'`. Additive only. `AuthError = { code, message }` — shape frozen.
- Existing copy that must not change (AC #1): heading `Enter your mobile number`; CTA + `accessibilityLabel` `Send OTP`; validation messages `Please enter a valid 10-digit mobile number.` / `Please enter a mobile number, not a landline number.` / `Mobile numbers start with 6, 7, 8, or 9.`; `testID="login-screen"`; `Input variant="phone"` with `autoFocus`; `Card variant="flat" className="m-md flex-1 justify-center"`; the `sanitizePhoneInput` `/\D/g` + `slice(0, 10)` behaviour and its comment.
- Guard loading copy, reused verbatim from `(tabs)/_layout.tsx:44-54`: `Card variant="flat" className="m-md flex-1 items-center justify-center"` containing `<Text variant="body">Loading…</Text>` (that is U+2026, not three dots). Existing testID `auth-guard-loading` unchanged; new one for the auth group: `auth-entry-loading`.
- `signOut` scope: `{ scope: 'local' }` — verbatim, per the SDK's own recommendation.
- Analytics: `ANALYTICS_EVENTS.SIGN_OUT = 'sign_out'`, snake_case, matching all 14 existing entries. Property shape must contain **no PII** — `lib/analytics.ts`'s `capture()` enforces this at runtime (see `analyticsEvents.ts:46-50`), so `{ method: 'phone_otp' }`, never a phone/email.
- Onboarding query key: always via `onboardingCompletedQueryKey(userId)` from `auth.queries.ts:34` — never a duplicated literal.
- Route hrefs: `/login`, `/onboarding`, `/` — the strings already used by `(tabs)/_layout.tsx:57`, `verify-otp.tsx:59`, `onboarding.tsx:154/242/300`.

## Edge cases

Carried forward from the ticket, plus what the ground-check added.

1. **Sign-out with a mutation in flight** — `cancelQueries()` before the session dies; the cache `clear()` after, so a late resolve cannot repopulate. A late rejection must not navigate or toast: `profile.tsx` navigates only in the sign-out mutation's own `onSuccess`, and no other screen is mounted after `replace('/login')`.
2. **Double-tap sign-out / double-confirm** — button `disabled` while pending; every step idempotent; a second `router.replace('/login')` while already on login is a no-op.
3. **Sign-out mid-onboarding** (partial row, `onboarding_completed = false`) — allowed. `useOnboardingStore.reset()` runs, so the next sign-in re-hydrates from the DB via `useOnboardingProgressQuery` rather than inheriting the previous user's half-filled wizard. Signing back in routes to `/onboarding` (guard → `'onboarding'`).
4. **Web vs native persistence** — web `localStorage`, native `expo-secure-store` (`lib/supabase.ts:9-31`). Both go through the same storage adapter the SDK clears. **Native cannot be verified end-to-end** — no EAS build (`BL-047`), no hosted build (`BL-171`). QA must say so plainly rather than claim a native check.
5. **Deep link to an authenticated route while signed out** (`/wardrobe`, `/outfit/[id]`) — the `(tabs)` guard redirects to `/login`. **The intended destination is dropped**, not round-tripped; after login the user lands on `/` or `/onboarding`. Stated plainly, not papered over; logged as a backlog row rather than fixed here.
6. **Onboarding-completed check fails** — `auth.service.ts:144-149` catches → `false` → `'onboarding'`. Never `'app'`. A completed user briefly seeing onboarding is recoverable; a user locked out is not. Preserved exactly.
7. **Session expiry while the app is open** — `onAuthStateChange` fires with a null session → `auth.store` updates → `useAuthRouting()` recomputes → the tabs guard redirects to `/login` on the next render, no restart. Same code path as sign-out, which is why they share one mechanism.
8. **Redirect ping-pong** — structurally impossible: only the tabs guard redirects *toward* `/onboarding`, only the auth-entry guard redirects *away from* login/verify-otp, and `/onboarding` is guarded by neither. Still asserted by a test (Test plan #11).
9. **Onboarding completion → invalidation race** — `useCompleteOnboardingMutation` invalidates `onboardingCompletedQueryKey`; `onboarding.tsx:242` then `replace('/')`. While the refetch is in flight the tabs guard sees `'loading'` (isSuccess false during refetch of a *new* key state) and shows the loading Card, then `'app'`. It must never flash `'onboarding'` and bounce the user back — Test plan #11.
10. **Phone-less session** (SS-070 admin-created, email-only) — no code reads `session.user.phone` today (grepped: zero matches), and the auto-provision trigger already writes a `phone IS NULL` row. AC #8's fixture must mount profile *and* the tab layout with `{ user: { id, email, phone: null } }` and not crash. Any future identity display falls back email → neutral label; this ticket displays no identifier at all (`profile.tsx` shows `useUserGreetingQuery`'s `full_name` via `Avatar`).
11. **A store added later that forgets to register** — the self-registration pattern moves this failure next to the new store rather than into sign-out. Not eliminated; call it out in the code comment.
12. **`AUTH_METHODS` empty** (nobody should do this, but the type allows it) — `login.tsx` must render a neutral message rather than crash on `AUTH_METHODS[0]`. Cheap guard, one line.
13. **`usePathname()` returning a path with the group segment** — expo-router normally strips route-group segments, but the Developer must confirm the actual runtime value (`/login` vs `/(auth)/login`) and match on both defensively, or the forward guard silently never fires. This is exactly the class of bug `BL-168` already is.

## Test plan

All Jest + React Native Testing Library, `jest-expo` preset, mirroring the existing `mobile/__tests__/` layout.

**`mobile/__tests__/app/(auth)/login.test.tsx` — DO NOT EDIT.** Passing unmodified is AC #1's proof.

**`mobile/__tests__/features/auth/auth.methods.test.tsx`** (new)
1. `AUTH_METHODS` has exactly one entry today, `id: 'phone_otp'`, with a non-empty `label` and a defined `Component`.

**`mobile/__tests__/app/(auth)/login.registry.test.tsx`** (new — AC #2; separate file so `login.test.tsx` stays mock-free of `auth.methods`)
2. With `auth.methods` mocked to two descriptors, both labels render on the chooser.
3. Pressing the second method's label renders that method's component (reachability), and a Back affordance returns to the chooser.
4. With the real one-entry registry, **no** chooser affordance renders — asserts the absence of any "more options"/method-list element (guards the "must look exactly as today" half of AC #1 from the other side).

**`mobile/__tests__/features/auth/useAuthRouting.test.tsx`** (new — the decision function)
5. `isSessionLoading: true` → `'loading'`, regardless of query state.
6. Session null, not loading → `'unauthenticated'`.
7. Session present, onboarding query not yet `isSuccess` → `'loading'` (the no-flash discipline).
8. Session present, `data: false` → `'onboarding'`. `data: true` → `'app'`.
9. Session present, query errored/`checkOnboardingCompleted` resolved `false` → `'onboarding'`, never `'app'` (fail-safe).

**`mobile/__tests__/app/(auth)/_layout.test.tsx`** (new — AC #3, and the `BL-168` regression)
10. **The `BL-168` regression test, mirroring today's live reproduction:** pathname `/login`, a valid session, `onboarding_completed: true` → renders `<Redirect href="/" />` and **not** the login stack. This is the assertion that would have failed this morning.
11. Same but `onboarding_completed: false` → `<Redirect href="/onboarding" />`.
12. Pathname `/login`, no session → renders the `Stack` (children), no redirect.
13. Pathname `/login`, session loading → `auth-entry-loading` Card, no redirect (no flash).
14. Pathname `/verify-otp` with a fresh session behaves as #10/#11 — this is what replaces `verify-otp.tsx`'s deleted `useEffect`.
15. **Pathname `/onboarding` with a session and `onboarding_completed: true` → renders children, no redirect** (the SS-016 preservation + anti-loop guarantee, asserted explicitly).

**`mobile/__tests__/app/(tabs)/_layout.test.tsx`** (extend; keep all three existing cases)
16. Session + `onboarding_completed: false` → `<Redirect href="/onboarding" />` — **AC #4, the cold-open case**.
17. Session + `onboarding_completed: true` → `<Tabs>` renders (existing case, now with the query settled).
18. Session + onboarding query unsettled → `auth-guard-loading` Card, **not** tabs and **not** a redirect (no flash in either direction).

**`mobile/__tests__/app/(auth)/verify-otp.test.tsx`** (edit — remove the moved-behaviour assertions only)
19. A successful verify still fires `track('register', { method: 'phone_otp' })` for a first-ever verify and not for a returning user (unchanged assertions kept).
20. Assert `verify-otp.tsx` performs **no** navigation itself after success — `router.replace` is never called (locks in that the decision really did move, so the two mechanisms cannot both ship).

**`mobile/__tests__/features/auth/userStateReset.test.ts`** (new — AC #6's foundation)
21. `resetAllUserState()` invokes every registered fn exactly once.
22. A registered fn that throws does not prevent the others from running (partial-clear prevention).
23. **Coverage guard:** importing all four `*.store.ts` modules and calling `resetAllUserState()` leaves each of the six stores at its initial state — seed non-default values into `useOnboardingStore`, `useWardrobeUploadStore`, `useWardrobeBatchStore`, `useWardrobeFilterStore`, `useOutfitAiStore` first, then assert each is back to defaults. This is the test that catches a store whose `reset()` is incomplete (as `outfit-ai`'s `resetDeck()` is today).

**`mobile/__tests__/features/auth/signOut.test.tsx`** (new — AC #6, #7)
24. `signOut()` service calls `supabase.auth.signOut` with `{ scope: 'local' }` — asserts the argument literally, since the default would sign out other devices.
25. `signOut()` resolves (does not reject) when the SDK returns `{ error }`, and when it throws.
26. **AC #7:** with the SDK's `signOut` mocked to fail, the mutation still runs `resetAllUserState()` + `queryClient.clear()` and still reaches its success path (→ login).
27. **AC #6, the cross-user-bleed integration test:** seed the React Query cache with user A's data (e.g. `onboardingCompletedQueryKey('user-a')`, a wardrobe key) *and* non-default Zustand state; run sign-out; set a user-B session; mount an authenticated screen and assert **zero** of user A's values are present in the cache or any store.
28. Double-fire: calling the mutation twice does not throw and does not double-navigate.

**`mobile/__tests__/app/(tabs)/profile.test.tsx`** (extend; existing cases kept, `useRouter` mock gains `replace`)
29. A "Sign Out" button renders with an accessibility label.
30. Pressing it shows the confirm affordance and does **not** sign out yet; pressing Cancel returns to the default state with no mutation call.
31. Confirming fires the mutation, fires `track('sign_out', ...)`, and calls `router.replace('/login')`.
32. The button is disabled while `isPending` (double-tap).

**`mobile/__tests__/features/auth/phoneless-session.test.tsx`** (new — AC #8)
33. With a session fixture `{ user: { id: 'u1', email: 'a@b.com', phone: null } }`, `ProfileScreen` mounts and renders without throwing.
34. Same fixture: `TabsLayout` mounts and renders the guarded content without throwing.
35. Same with `{ user: { id: 'u1' } }` (neither phone nor email) — still no crash, no `undefined` rendered into a `Text`.

**Type/lint gate (AC #11):** `tsc --noEmit`, `biome check`, and the **full** jest suite green — no `any`, no test deleted except the two moved-behaviour assertions in #19/#20's file, which are replaced 1:1 by #10–#15.

## Forward-compatibility with `BL-172` account linking (AC #8's second half)

`BL-172`'s policy is settled and this ticket builds no linking UI. The question the ticket asks is whether the registry and the routing hook would need to *change* later to accommodate it — cheap now vs. expensive later.

**Answer: no change needed now, and the reason is structural.** Linking is a *while-already-authenticated* action (Supabase's `linkIdentity()` requires an existing session and fails if the candidate identity is already claimed). It therefore belongs on an authenticated surface — Profile — and never on the unauthenticated `(auth)` chooser. The two surfaces have disjoint preconditions, so the sign-in registry is not the linking registry and should not be pre-generalised into one.

What *is* worth getting right now, and this design does:

- **`AuthMethodId` is a shared exported union, not a per-screen string literal.** A future "Link a sign-in method" list on Profile reuses that union to name what it is linking. Had the method identity stayed inlined in `login.tsx`, the later linking work would have had to invent a second, drift-prone vocabulary. This is the one genuinely cheap-now / expensive-later item, and it is already in the design.
- **`AuthMethodDescriptor` is a plain 3-field interface**, so adding `linkable: boolean` or `LinkComponent` later is additive and touches one file. No forward field is added speculatively.
- **Nothing in this ticket writes to `public.users.phone`/`email`** or adds a constraint — verified: the only writer is `002_onboarding_completed.sql`'s trigger, and both columns are nullable `UNIQUE` (`001_initial.sql:26-27`). A later `linkIdentity()` attaching a second identifier is unobstructed.
- **The routing hook keys on session truthiness + `onboarding_completed` only** — never on *which* identity minted the session. Linking a second identity to an existing session changes neither input, so the guard is inert with respect to linking by construction.

## Open questions / blockers

1. **None of these blocks the Developer.** No external provisioning, no schema change, no third-party configuration is required — this is entirely local `mobile/` work. Development can start immediately.
2. **`usePathname()`'s runtime value must be confirmed, not assumed** (edge case #13). If it returns `/(auth)/login` rather than `/login`, a naive equality check makes the forward guard silently never fire — reintroducing `BL-168` while all the new tests pass against a mocked pathname. **The Developer must confirm the real value in a browser once**, not only in Jest. Match both forms defensively regardless.
3. **The `signOut` failure-path branch is an open verification, not an open design question** — see the boxed Developer verification task under Sign-out. Whichever branch the SDK actually takes, the mutation's `finally` makes AC #7 hold; the verification determines only whether the defensive `setSession(null)` is load-bearing or redundant. Record the finding in the worklog.
4. **AC #4 is an intentional user-visible behaviour change**, and it deserves one line of explicit acknowledgement at the PR: users who currently have a valid session with `onboarding_completed = false` and have been quietly using the tabs will now be routed to `/onboarding` on their next cold open. The raw ticket already flags this as intended. `Skip` on the onboarding screen (`onboarding.tsx:153-155`) does `router.replace('/')` **without** setting `onboarding_completed`, so such a user lands back on `/onboarding` at the *next* cold open too — a soft loop across sessions, not a hard one within a session. **This is pre-existing behaviour of Skip, not introduced here**, but AC #4 is what makes it reachable. Flagging rather than fixing: changing Skip's semantics is an onboarding-product decision (does Skip mean "done" or "later"?), not an auth decision, and the answer belongs to whoever owns onboarding. If the user's answer is "Skip means done", that is a one-line change in `onboarding.tsx` and should be added to this ticket explicitly rather than assumed.
5. **`verify-otp.test.tsx` is the one place where tests are deleted rather than added.** AC #11 forbids weakening the suite; the design's position is that assertions #10–#15 in the new `(auth)/_layout.test.tsx` cover strictly more than the deleted ones (they cover cold-open and `/login`-with-session, which the old ones never did). QA should check that specific claim rather than accept it.

**Backlog handled.** Per the rows handed to this pass:

- `BL-167` (no sign-out) and `BL-168` (routing gap) — **directly addressed by this design**, but deliberately **left Active**: the code is not written yet and the Architect resolving them here would put a false "done" in the cross-ticket memory. They should be moved to **Resolved** by the QA/DevOps phase once the ACs actually pass, referencing SS-071.
- `BL-172` (account-linking policy) — **not resolved by this ticket** and not re-litigated. Forward-compatibility addressed in its own section above; no design change needed now.
- `BL-052` (JWT stub on one backend route) — **genuinely unaffected**, confirmed rather than assumed: this ticket touches no file under `backend/`, and the mobile client's JWT handling is entirely inside `@supabase/supabase-js`, which this design does not reconfigure (`lib/supabase.ts` untouched). Sign-out revokes a refresh token; it does not change how any backend route validates an access token.
- `BL-001` (SMS/DLT provisioning), `BL-171` (no hosted build), `BL-037`, `BL-047` (no EAS build) — unaffected infra/distribution gaps. `BL-171`/`BL-047` do bear on QA: **the native persistence half of edge case #4 cannot be verified end-to-end**, and QA must say so plainly instead of claiming a native check.
- **New rows logged: `BL-178`** (auth redirects drop the intended destination — `auth`, Active), **`BL-179`** (no confirmation-dialog primitive in `components/ui/` — `tokens`, Active), **`BL-180`** (sign-out mid-upload abandons in-flight uploads without cancelling — `infra`, Active). The ID reservation notice was updated to start new rows at `BL-181`.

## Risk classification

`Risk: high` — **confirmed at the level the raw ticket set it, not raised and not lowered.**

This design rewires the session lifecycle and the routing guard standing in front of every authenticated screen in the app, and it adds the first code path that deletes user state. Both of the failure modes the raw ticket named are real and reachable in this design: an incomplete `resetAllUserState()` leaks one user's wardrobe/onboarding/suggestion state into the next session on the same device (`useWardrobeUploadStore` has no `reset()` at all today and `useOutfitAiStore`'s `resetDeck()` clears one of four fields — both are silent-leak sources this ticket must fix), and a mis-scoped guard can lock a user out of the app or trap them on a screen. It is external-facing auth surface under `docs/OPERATOR_RULEBOOK.md` §C2 regardless of there being no schema change and no migration. The `{ scope: 'local' }` finding is the concrete illustration: shipping the SDK default would have silently signed users out on every other device — a user-visible, irreversible-per-session effect from a one-word omission.

Nothing found during this pass argues for lowering it, and §C2's "on the fence → classify up" does not need to be invoked because this is not a close call.

**Verdict:** `Risk: high` (confirmed) — full lane, every human gate preserved.
