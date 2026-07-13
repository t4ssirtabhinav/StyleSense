# SS-003 — Design: Phone OTP Authentication Flow (India-First)

## Scope restatement

Build the app's phone-first login flow end-to-end on the client: a Phone Input screen that validates a 10-digit Indian mobile number and calls `supabase.auth.signInWithOtp`, an OTP Verification screen (6 boxes, auto-advance, paste-fill, auto-submit, 30s resend cooldown, shake-on-wrong-OTP) that calls `supabase.auth.verifyOtp`, and an Auth Guard that wraps the `(tabs)` route group so an unauthenticated user is redirected to login and a returning user with a valid session skips it. All screens are composed entirely from `components/ui`'s existing `Input` (`phone`/`otp` variants), `Button`, `Text`, `Card` — SS-008 already built the visual chrome and shake/paste/auto-focus mechanics; this ticket owns validation logic, the actual Supabase auth calls, session persistence/propagation, the resend timer, the post-auth onboarding-vs-home routing decision, and (best-effort, largely untestable) Android SMS auto-read. Per the ticket's own Status note, MSG91/Twilio is not configured (tracked as BL-001), so this design targets Supabase's Phone Auth abstraction generically — the actual OTP-delivery AC cannot be exercised end-to-end yet, only everything upstream/downstream of that one network call.

## Current codebase state (verified, not assumed)

- `mobile/lib/supabase.ts` exports `supabase`, already constructed with a correct `secureStoreAdapter` (`getItem`/`setItem`/`removeItem` wrapping `expo-secure-store`'s `*Async` methods — this was BL-014, already fixed and committed), `persistSession: true`, `autoRefreshToken: true`, `detectSessionInUrl: false`. Nothing further needed here.
- `mobile/components/ui/Input.tsx` (confirmed by direct read): `variant='phone'` renders a static `+91` prefix `Pressable` (`onCountryCodePress` callback, `countryCode` prop defaults to `'+91'`) plus a `TextInput` with `keyboardType="phone-pad"` and **`maxLength={10}` already enforced** — but it does **not** filter non-digit characters, and provides zero validation. `variant='otp'`: single hidden `TextInput` (`testID="otp-hidden-input"`), `onChangeText` already strips non-digits and slices to `length` (default 6) internally, calls `onComplete(digitsOnly)` the instant `digitsOnly.length === length` — auto-submit-on-6th-digit and paste-fill are **already free**, SS-003 does not need to reimplement either. The shake animation is driven by a `useEffect` watching `error` transition falsy→truthy (via `prevHadErrorRef`) — SS-003 only needs to set/clear the `error` string; it does not control the animation directly.
- `mobile/app/_layout.tsx`: bare `<Stack>` wrapped in `GestureHandlerRootView`/`BottomSheetModalProvider`, `useFonts` not gating render. No auth wiring of any kind yet.
- `mobile/app/index.tsx`: SS-008's disposable `Card`+`Text` smoke-test screen, still living at the **top-level** route (`/`), not inside any route group. **No `app/(auth)/` or `app/(tabs)/` directories exist yet** — this ticket is the first to create them.
- `mobile/features/` does not exist yet — this is the first `features/<domain>/` folder in the repo.
- `mobile/hooks/` does not exist yet, despite being named in CLAUDE.md's folder structure (`useAuth`, `useCamera`, `useLocation`).
- No SMS-retrieval package (`expo-sms-retriever` or equivalent) is present in `package.json`/`node_modules` — confirmed via read of `mobile/package.json`. The ticket's own Technical Note names it tentatively ("`expo-sms-retriever` or similar"); no such package is chosen or resolvable from the codebase today.
- `supabase/migrations/001_initial.sql`'s `users` table (verified by direct read) has **no `onboarding_completed` boolean and no trigger that auto-creates a `public.users` row on Supabase Auth signup** — `auth.users` (Supabase-managed) and `public.users` (the app's own table, RLS'd on `auth.uid() = id`) are separate, and nothing currently bridges them. This directly affects the AC "redirect to onboarding (first login) or home (returning user)" — see "Concrete values" and "Open questions" below.

## Files to create/modify

### New — `features/auth/` (per CLAUDE.md's domain-folder convention)

1. **`mobile/features/auth/auth.types.ts`** — `AuthErrorCode = 'invalid_phone' | 'network_error' | 'rate_limited' | 'invalid_or_expired_otp' | 'unknown'`; `AuthError { code: AuthErrorCode; message: string }`; `PhoneValidationResult = { valid: true } | { valid: false; message: string }`.
2. **`mobile/features/auth/auth.service.ts`** — raw calls, the only file that touches `supabase.auth.*` for this domain besides `hooks/useAuth.ts`:
   - `validateIndianMobile(digits: string): PhoneValidationResult` — pure function, no I/O (see exact rules below).
   - `sendOtp(phoneDigits: string): Promise<void>` — calls `supabase.auth.signInWithOtp({ phone: '+91' + phoneDigits })`, wrapped in `try/catch`, throws a typed `AuthError`.
   - `verifyOtp(phoneDigits: string, token: string): Promise<Session>` — calls `supabase.auth.verifyOtp({ phone: '+91' + phoneDigits, token, type: 'sms' })`, wrapped in `try/catch`, throws a typed `AuthError`, returns `data.session` (never null on success — throw `unknown` if it is).
   - `checkUserProfileExists(userId: string): Promise<boolean>` — `supabase.from('users').select('id').eq('id', userId).maybeSingle()`, returns `Boolean(data)`.
3. **`mobile/features/auth/auth.queries.ts`** — React Query hooks, the **only** place these are called from components (per CLAUDE.md's anti-pattern rule, extended to this domain's queries file):
   - `useSendOtpMutation()` → `useMutation({ mutationFn: sendOtp })`.
   - `useVerifyOtpMutation()` → `useMutation({ mutationFn: ({ phone, token }) => verifyOtp(phone, token) })`.
   - `useUserProfileExistsQuery(userId: string | undefined)` → `useQuery({ queryKey: ['auth', 'profile-exists', userId], queryFn: () => checkUserProfileExists(userId!), enabled: Boolean(userId) })`.
4. **`mobile/features/auth/auth.store.ts`** — Zustand store, typed selectors only: `{ session: Session | null; isSessionLoading: boolean; setSession: (s: Session | null) => void; setSessionLoading: (b: boolean) => void }`. This is the one piece of session state shared across the Auth Guard and (indirectly) every screen — everything else in this ticket (phone number in progress, OTP value, resend countdown) is local screen `useState`, not global store state, since nothing outside the two auth screens needs it (avoids over-using Zustand for state with a single consumer).
5. **`mobile/features/auth/components/CountryCodePicker.tsx`** — thin wrapper around `components/ui`'s `AppBottomSheet`, opened via `onCountryCodePress`. MVP scope: renders a single selectable row, "🇮🇳 India +91" (see Open Questions — no other country is specified anywhere in the ticket, schema, or backlog; do not invent a country list).

### New — `hooks/`

6. **`mobile/hooks/useAuth.ts`** — device/platform-capability-style hook (same category as CLAUDE.md's named `useCamera`/`useLocation` examples), called exactly once, from root `_layout.tsx`. On mount: calls `supabase.auth.getSession()` to seed initial state, then subscribes via `supabase.auth.onAuthStateChange((event, session) => setSession(session))`; unsubscribes (`subscription.unsubscribe()`) on unmount. Writes into `features/auth/auth.store.ts`, does not return session itself (consumers read the store directly via a typed selector) — this hook's only job is wiring the listener, once.
7. **`mobile/hooks/useSmsAutoRead.ts`** — see "SMS auto-read" section below; a documented no-op stub on this pass, not a real integration.

### New — `app/(auth)/`

8. **`mobile/app/(auth)/login.tsx`** — Phone Input screen.
9. **`mobile/app/(auth)/verify-otp.tsx`** — OTP Verification screen.
10. **`mobile/app/(auth)/onboarding.tsx`** — **thin disposable placeholder**, same pattern SS-008's Architect used for `app/index.tsx` (a screen has to exist at this route or the post-auth "new user" redirect 404s; full onboarding logic is SS-004's job entirely). Renders `Card`+`Text` ("Welcome to StyleSense — onboarding coming soon") + a `Button` that calls `router.replace('/')`. **Do not add real onboarding logic here** — flag this file explicitly to whoever reviews the PR as disposable, exactly as SS-008's design doc did for the old `app/index.tsx`.

### New — `app/(tabs)/`

11. **`mobile/app/(tabs)/_layout.tsx`** — the Auth Guard. Reads `session`/`isSessionLoading` from `auth.store.ts` via a typed selector. While `isSessionLoading` is true: render a centered `Card`+`Text` ("Loading…") — never a blank screen. Once resolved: no session → `<Redirect href="/login" />`; valid session → `<Slot />` (deliberately **not** Expo Router's `<Tabs>` yet — there is no tab-bar UI to render until SS-005 lands; using `Slot` here means SS-005's Architect pass can drop `<Tabs>` in around/inside this same guard without having to redesign the guard logic itself. Flagging this explicitly for SS-005's Architect to reconcile, not silently deciding it's "done").
12. **`mobile/app/(tabs)/index.tsx`** — **moved** from `mobile/app/index.tsx` (identical content — the disposable `Card`+`Text` smoke test SS-008 built). This is a file **move**, not a rewrite: Expo Router resolves both a top-level `app/index.tsx` and a grouped `app/(tabs)/index.tsx` to the same `/` path, so the old top-level file must be deleted as part of this move, not left in place (a duplicate route would be ambiguous). `mobile/__tests__/app/index.test.tsx` must move to `mobile/__tests__/app/(tabs)/index.test.tsx` alongside it (same test content, updated import path).

### Modified

13. **`mobile/app/_layout.tsx`** — add a single `useAuth()` call at the top of `RootLayout`, before the `<Stack>` render, so the session listener is registered before any screen mounts. No other changes.
14. **`mobile/package.json`** — no new dependency is being added in this pass for SMS auto-read (see Open Questions #3); if the Developer finds a concrete Expo-SDK-56-compatible package during implementation, that is a same-ticket install, not an invented one — but the library choice itself is flagged as unresolved by this design doc, not decided here.

### New test files

15. `mobile/__tests__/features/auth/auth.service.test.ts`
16. `mobile/__tests__/features/auth/auth.queries.test.tsx`
17. `mobile/__tests__/features/auth/auth.store.test.ts`
18. `mobile/__tests__/features/auth/components/CountryCodePicker.test.tsx`
19. `mobile/__tests__/hooks/useAuth.test.ts`
20. `mobile/__tests__/hooks/useSmsAutoRead.test.ts`
21. `mobile/__tests__/app/(auth)/login.test.tsx`
22. `mobile/__tests__/app/(auth)/verify-otp.test.tsx`
23. `mobile/__tests__/app/(auth)/onboarding.test.tsx`
24. `mobile/__tests__/app/(tabs)/_layout.test.tsx`
25. `mobile/__tests__/app/(tabs)/index.test.tsx` (moved, see #12)

No `backend/` files are implicated — this ticket is entirely client-side; Supabase Auth is called directly from the mobile app per the ticket's Technical Notes, there is no FastAPI route in this flow.

## Concrete values to use, not invent

### Supabase Auth API calls (exact signatures — do not invent alternate call shapes)

```ts
// Send OTP — always prepend +91, per ticket's Technical Note
await supabase.auth.signInWithOtp({ phone: '+91' + phoneDigits });

// Verify OTP
const { data, error } = await supabase.auth.verifyOtp({
  phone: '+91' + phoneDigits,
  token,       // the 6-digit string
  type: 'sms',
});
// data.session: Session | null — on success this is populated; treat a
// success response with a null session as an `unknown` AuthError, not a
// silent pass-through.

// Session listener — registered once, in hooks/useAuth.ts
const { data: { session } } = await supabase.auth.getSession(); // initial seed
const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
  // event: 'SIGNED_IN' | 'SIGNED_OUT' | 'TOKEN_REFRESHED' | 'USER_UPDATED' | ...
  setSession(session);
});
// cleanup: subscription.unsubscribe()
```

`autoRefreshToken: true` (already set in `lib/supabase.ts`) means ordinary token expiry is handled invisibly by supabase-js; the app only needs to react to an eventual `SIGNED_OUT` event (refresh failure, e.g. after a very long time offline) by redirecting to login via the guard — no separate expiry-polling logic needed.

### Phone validation — exact rules (India-only, 10 digits, starts 6/7/8/9)

```ts
export function validateIndianMobile(digits: string): PhoneValidationResult {
  if (digits.length !== 10) {
    return { valid: false, message: 'Please enter a valid 10-digit mobile number.' };
  }
  if (digits[0] === '0' || digits[0] === '2') {
    return { valid: false, message: 'Please enter a mobile number, not a landline number.' };
  }
  if (!/^[6-9]\d{9}$/.test(digits)) {
    return { valid: false, message: 'Mobile numbers start with 6, 7, 8, or 9.' };
  }
  return { valid: true };
}
```
Sanitize input **before** validating — strip everything but digits and cap at 10 in `login.tsx`'s `onChangeText` handler (`text.replace(/\D/g, '').slice(0, 10)`) before calling `setPhone`, since `Input`'s `phone` variant does not filter non-digit characters itself (confirmed by reading `Input.tsx` — it only enforces `maxLength={10}` at the RN `TextInput` level, which still admits non-digit characters on web/paste).

### `Input` props this ticket must wire exactly (from `components/ui/Input.tsx`, do not restyle)

- `variant="phone"`: `value`, `onChangeText`, `error` (validation message string or `undefined`), `countryCode="+91"` (default, no need to pass explicitly), `onCountryCodePress={() => countryPickerRef.current?.present()}`, `autoFocus`.
- `variant="otp"`: `value`, `onChangeText`, `error` (set only on failed verify, cleared on new attempt), `length={6}` (default, no need to pass), `onComplete={handleVerify}` — this is the auto-submit hook, already wired by SS-008; do not add a separate "Verify" button as the primary submit path (a manual fallback button is fine for accessibility, but auto-submit via `onComplete` is the ticket's stated primary UX).

### Occasion/error colour — reuse, do not invent

`Input`'s `error` prop already renders using `colors.accent.errorPlaceholder` (`#D32F2F`, BL-007, parked) via its internal `ERROR_COLOR` constant. SS-003's screens must **only** pass a string to `error` — never style error text with a different colour or introduce a second error-colour source. BL-007 remains open/parked; this ticket consumes the existing placeholder, it does not resolve BL-007.

### Resend cooldown — 30 seconds, local screen state (not global store)

`verify-otp.tsx` owns a local `useState<number>(30)` that decrements every second via a single `setInterval` in a `useEffect` (this is a legitimate timer *side effect*, not "derived state" in the sense CLAUDE.md's anti-pattern rule is guarding against — there is no prop/state this value could instead be computed from during render; it requires a real-time subscription). Starts at 30 the moment the screen mounts (an OTP was just sent by `login.tsx`) and restarts at 30 whenever the user presses "Resend" (which re-calls `useSendOtpMutation`). The `Button` for "Resend" is `disabled` while the counter is `> 0`, and its label interpolates the remaining seconds (e.g. `` `Resend OTP (${seconds}s)` ``).

### Route/navigation contract

- `/login` — phone input (`app/(auth)/login.tsx`). On successful `sendOtp`, navigate with `router.push({ pathname: '/verify-otp', params: { phone: phoneDigits } })` (the 10 raw digits, no `+91` prefix — `verify-otp.tsx` re-applies the prefix when calling `verifyOtp`).
- `/verify-otp` — reads `phone` via `useLocalSearchParams<{ phone: string }>()`.
- `/` — `app/(tabs)/index.tsx`, guarded by `app/(tabs)/_layout.tsx`.
- `/onboarding` — placeholder screen (see Files above).
- On successful `verifyOtp`: call `useUserProfileExistsQuery(session.user.id)`; if it resolves `false` → `router.replace('/onboarding')`; if `true` → `router.replace('/')`. Use `replace`, not `push`, in both cases so the OTP screen isn't reachable via back-navigation post-auth.

## Edge cases

Carried forward verbatim from the ticket:
- SMS not received after 30s → "Resend" becomes enabled; copy should note "Check if DND is active on your number" (static copy, can ship regardless of j91 status).
- Airplane mode / no network → `sendOtp`/`verifyOtp` must catch the network failure and surface a "No internet connection. Please check your network and try again." message via the same `AuthError`/`error` prop path — never let the raw exception propagate to a crash. Both `auth.service.ts` functions wrap every call in `try/catch` per CLAUDE.md's async-ops rule.
- Keyboard covers OTP input on small screens → wrap `verify-otp.tsx`'s screen content in RN's `KeyboardAvoidingView` (`behavior={Platform.OS === 'ios' ? 'padding' : 'height'}`). This is not a `View`/`Text` primitive covered by CLAUDE.md's "never use raw View/Text" rule (that rule targets the two specific primitives that `components/ui` replaces); `KeyboardAvoidingView` has no `components/ui` equivalent and must be used directly from `react-native`.
- Paste 6 digits at once → already handled entirely inside `Input`'s `otp` variant (single underlying `TextInput` receiving the full pasted string as one `onChangeText` call) — SS-003 wires nothing extra for this.
- Landline number (starts with 0 or 2) → distinct copy per `validateIndianMobile` above ("Please enter a mobile number, not a landline number.").

New edge cases found from the current codebase state:
- **Supabase does not distinguish "wrong OTP" from "expired OTP" in its error response** — both surface as the same generic `AuthApiError` (commonly "Token has expired or is invalid"). The ticket's AC treats these as two distinct UX cases ("wrong OTP shows inline error + shake" vs. "expired OTP prompts resend"), but there is no reliable signal in Supabase's response to tell them apart. Design decision: show one generic error ("Incorrect or expired OTP. Please try again or resend.") for both, and always leave "Resend" available (bounded only by the 30s cooldown) so the user's remediation path is the same either way. Flagging this as an API-shape limitation, not something this ticket can resolve by inventing a distinction Supabase doesn't expose.
- **No `public.users` row is ever created automatically on phone signup**, and no `onboarding_completed` flag exists (verified by reading `001_initial.sql`). This ticket uses **row existence** (`checkUserProfileExists`) as the first-login/returning-user heuristic. This means every user will be routed to `/onboarding` on every login until SS-004's (not-yet-built) onboarding flow actually inserts the row — that is expected and acceptable for this ticket alone, but it means SS-003's AC "redirected to onboarding (first login) or home (returning user)" is only *half* closable without SS-004 also shipping the row-creation step. Flagged below and in the backlog.
- **`app/(tabs)/_layout.tsx`'s guard has a first-render race**: `useAuth()`'s initial `getSession()` call is asynchronous, so `isSessionLoading` must default to `true` (not `false`) to avoid a one-frame flash-redirect to `/login` for users who actually do have a valid persisted session. This must be tested explicitly (see Test plan).
- **Web platform has no SMS Retriever/User Consent API at all** — `useSmsAutoRead` must be a guaranteed no-op outside Android (checked via `Platform.OS === 'android'`), never attempted on web/iOS, so it can't throw on unsupported platforms.

## SMS auto-read — explicitly scoped as best-effort, not a full implementation

The ticket's Technical Note names `expo-sms-retriever` "or similar," but no such package exists in `package.json`/`node_modules`, and none is chosen by this design doc (see Open Questions #3). `mobile/hooks/useSmsAutoRead.ts` is specified as:

```ts
export function useSmsAutoRead(onCodeReceived: (code: string) => void): void {
  useEffect(() => {
    if (Platform.OS !== 'android') return; // no-op on web/iOS — no SMS Retriever API exists there
    // TODO(SS-003 follow-up): wire a real SMS Retriever / SMS User Consent
    // integration once a concrete Expo-SDK-56-compatible package is chosen
    // (see docs/BACKLOG.md). Deliberately not implemented here — no package
    // is installed, and it could not be device-tested even if it were
    // (BL-013: dev server unreachable from a phone on the same WiFi).
  }, [onCodeReceived]);
}
```
`verify-otp.tsx` calls this hook unconditionally (`useSmsAutoRead(setOtpValue)`), so wiring a real implementation later is additive — no screen-level changes needed once a package is chosen. Manual typing, paste-fill, and auto-submit all work today without this hook doing anything.

## Test plan

`mobile/__tests__/features/auth/auth.service.test.ts`
- `validateIndianMobile`: asserts `valid: true` for `9876543210`; asserts specific error messages for wrong length, `0`/`2`-prefixed (landline copy), and `1345`-prefixed (generic "starts with 6,7,8,9" copy).
- `sendOtp`: mocks `supabase.auth.signInWithOtp`, asserts it's called with `{ phone: '+91XXXXXXXXXX' }` (prefix prepended exactly once); asserts a rejected promise is caught and re-thrown as a typed `AuthError`, not the raw Supabase error.
- `verifyOtp`: mocks `supabase.auth.verifyOtp`, asserts call args (`phone`, `token`, `type: 'sms'`); asserts a successful response with `data.session` returns that session; asserts a successful response with a null `session` throws `AuthError({ code: 'unknown' })`; asserts a rejected/error response throws `AuthError({ code: 'invalid_or_expired_otp' })`.
- `checkUserProfileExists`: mocks `supabase.from('users').select().eq().maybeSingle()`, asserts `true`/`false` for row-present/absent.

`mobile/__tests__/features/auth/auth.queries.test.tsx`
- `useSendOtpMutation`/`useVerifyOtpMutation`: mocks `auth.service.ts`, asserts the mutation's `mutate`/`mutateAsync` calls through and exposes `isPending`/`isError`/`isSuccess` correctly.
- `useUserProfileExistsQuery`: asserts `enabled: false` (no query fired) when `userId` is `undefined`.

`mobile/__tests__/features/auth/auth.store.test.ts`
- `setSession`/`setSessionLoading` update state; a typed selector (`useAuthStore((s) => s.session)`) returns the updated value.

`mobile/__tests__/features/auth/components/CountryCodePicker.test.tsx`
- renders and asserts the single `+91 India` row is present; pressing it calls `onSelect`/closes the sheet (exact callback shape decided by Developer, assert whatever contract is implemented, no gesture gesture-level assertions per SS-008's own precedent for `BottomSheet`).

`mobile/__tests__/hooks/useAuth.test.ts`
- mocks `supabase.auth.getSession` and `onAuthStateChange`; asserts `setSessionLoading(true)` initially, then `setSessionLoading(false)` + `setSession(...)` after the initial `getSession()` resolves.
- asserts a `SIGNED_OUT` event later fired through the mocked subscription updates the store to `session: null`.
- asserts `subscription.unsubscribe()` is called on unmount.

`mobile/__tests__/hooks/useSmsAutoRead.test.ts`
- mocks `Platform.OS = 'ios'`/`'web'`, asserts the effect body never attempts anything (no throw, no calls to `onCodeReceived`).
- mocks `Platform.OS = 'android'`, asserts it still doesn't throw (stub only) and documents (via a comment in the test) that this is intentionally a no-op pending a package decision.

`mobile/__tests__/app/(auth)/login.test.tsx`
- renders with the `+91` prefix visible by default.
- typing `9876543210` and pressing "Send OTP" calls `useSendOtpMutation`'s mutate with the sanitized 10-digit string and navigates to `/verify-otp` with `{ phone: '9876543210' }` on success.
- typing a landline-looking number (`0123456789`) shows the landline-specific error and does **not** call the mutation.
- while the mutation is pending, the "Send OTP" button shows `Button`'s `loading` state and cannot be pressed again.
- simulates a rejected mutation with a network-error-shaped `AuthError` and asserts the "No internet connection" message renders, not a crash/unhandled rejection.
- simulates a `rate_limited` `AuthError` and asserts a rate-limit-specific message renders.

`mobile/__tests__/app/(auth)/verify-otp.test.tsx`
- reads `phone` from the mocked `useLocalSearchParams` and renders it in the "OTP sent to +91 XXXXXXXXXX" copy.
- typing all 6 digits (via the hidden `TextInput`, matching `Input`'s own test pattern from SS-008) triggers `onComplete` → auto-calls `useVerifyOtpMutation` without a separate button press.
- a rejected verify mutation sets `Input`'s `error` prop to a non-empty string (asserting the shake-triggering falsy→truthy transition happens) and does not crash.
- a resolved verify mutation with `useUserProfileExistsQuery` resolving `false` calls `router.replace('/onboarding')`; resolving `true` calls `router.replace('/')`.
- "Resend" button is disabled immediately on mount with `30` seconds showing; after the countdown mock-advances to 0, the button becomes enabled; pressing it calls `useSendOtpMutation` again and resets the countdown to 30.

`mobile/__tests__/app/(auth)/onboarding.test.tsx`
- smoke test: renders without crashing, contains the placeholder copy, `router.replace('/')` fires on button press.

`mobile/__tests__/app/(tabs)/_layout.test.tsx`
- `isSessionLoading: true` → renders the loading `Card`/`Text`, does **not** render `<Redirect>` yet (guards the first-render race called out in Edge Cases).
- `isSessionLoading: false, session: null` → renders `<Redirect href="/login" />`.
- `isSessionLoading: false, session: <valid Session>` → renders the guarded child content (`<Slot />`), no redirect.

`mobile/__tests__/app/(tabs)/index.test.tsx` (moved)
- identical assertions to the pre-move `mobile/__tests__/app/index.test.tsx`, updated import path to `'../../../app/(tabs)/index'`.

Manual/device verification (cannot be covered by any of the above, must be tracked separately — see Open Questions):
- Actual OTP SMS delivery timing/content (blocked on BL-001).
- Android SMS auto-read behaviour (blocked on both the missing package, BL-001's lack of a real SMS to auto-read, and BL-013's device-connectivity gap).
- Real keyboard-covering-input visual behaviour on a small physical/emulated screen.

## Open questions / blockers

1. **BL-001 (Phone Auth/MSG91 not configured) — confirmed still open, central blocker for end-to-end testing.** Everything in this design doc up to and including the actual `supabase.auth.signInWithOtp`/`verifyOtp` network calls can be built and unit-tested with mocks. What **cannot** be tested until MSG91 (or Twilio) is actually configured: real OTP SMS delivery/timing, real wrong-vs-expired-OTP error payload shape (the generic-message edge case above is a best guess based on Supabase's documented behavior, not confirmed against a live send in this repo), and the entire SMS auto-read AC (there's no real SMS to auto-read without a live provider). This is not a code defect — it's the same acknowledged gap SS-002's Architect/Developer/QA all carried forward. Recommend the worklog record the OTP-delivery and SMS-auto-read ACs as "built against mocks, not verified end-to-end" rather than "done," mirroring SS-002's framing.
2. **No `public.users` auto-provisioning trigger and no `onboarding_completed` flag** (new gap, not previously flagged by SS-002's Architect). This ticket's design uses row-existence as a stand-in heuristic, but nothing in the current schema ever creates that row — SS-004 (Onboarding Wizard) must be the one to actually insert it once it collects profile data, or every login will route to `/onboarding` indefinitely. Flagging for SS-004's Architect pass to close this loop explicitly, and logging to the backlog since it's a schema-adjacent gap outside this ticket's authority to fix (would mean either a DB trigger — SS-002/infra scope — or an application-level insert in SS-004's onboarding-completion step).
3. **No SMS-retrieval package is chosen.** The ticket names `expo-sms-retriever` tentatively; no such package (or an equivalent) is installed, and this design doc deliberately does not pick one, since (a) it may require a custom Expo dev client / config plugin rather than working in managed Expo Go, and (b) BL-013 (dev server unreachable from a phone on the same WiFi) means even a correctly-chosen package couldn't be verified on a real Android device in this environment today. `useSmsAutoRead` ships as a documented no-op; this AC is not closeable in this pass. Logging to backlog as a product/technical decision needed (which library, and whether a dev-client rebuild is acceptable for this ticket's scope).
4. **BL-013 (Expo dev server unreachable from phone on same WiFi) directly blocks device-level verification of this ticket's most device-specific ACs** — SMS auto-read and real on-screen keyboard-avoidance behaviour on a small Android screen. Same status as flagged for BL-010 in SS-008: parked, browser/emulator-based or mocked verification is what's available until BL-013 is resolved.
5. **Supabase's generic "Token has expired or is invalid" error message does not distinguish wrong-OTP from expired-OTP** (see Edge Cases) — the ticket's AC implies two distinguishable UX states that the underlying API doesn't actually support distinguishing. Recommend accepting the single generic-message design in this doc rather than inventing a client-side heuristic (e.g., guessing based on elapsed time since send) that could easily be wrong.
6. **Country code picker scope**: this design builds the minimal India-only picker (per Files to create #5) since neither the ticket nor any schema/backlog item specifies additional countries. If Product wants other country codes supported (e.g., for the Indian diaspora), that's a scope addition outside this ticket — flagging rather than guessing at a country list.

## Backlog logging

Appended to `docs/BACKLOG.md`'s Open table (new rows, this ticket's Architect phase):
- **BL-018**: no `public.users` auto-provisioning / `onboarding_completed` flag — blocks a clean close of SS-003's onboarding-vs-home AC until SS-004 ships; needs either a DB trigger or an application-level insert decision.
- **BL-019**: no SMS auto-read package chosen, and even a correctly-chosen one can't be device-verified today (compounds with BL-013). Needs a product/technical decision on which library and whether a custom dev client is acceptable.

No existing Open backlog row is resolved by this ticket. BL-007 (error colour) and BL-013 (dev server/WiFi) are consumed/referenced as-is, not resolved — this ticket reuses `Input`'s existing error-colour placeholder rather than inventing a new one, and inherits BL-013 as a blocker for device-level SMS/keyboard testing rather than fixing it (out of scope here).
