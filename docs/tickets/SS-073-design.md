# SS-073 — Email Confirmation-Link Landing Screen & Auto-Sign-In — Design

Ticket: `docs/tickets/raw/SS-073.md` · Tier: standard (Est 5h) · Depends on: SS-072 (merged, `develop`) · Risk: high (see raw ticket's own §Risk classification — reasoned there, re-confirmed below, not re-derived)

## Scope restatement

Add one new route, `app/(auth)/confirm.tsx`, that is the landing target for a signup confirmation email's link. It reads a `token_hash` query param, exchanges it for a session via `supabase.auth.verifyOtp({ token_hash, type: 'email' })` (a distinctly-named service function, `confirmEmailToken`, to avoid colliding with the existing SMS-path `verifyOtp` export), and renders exactly three explicit states — working, success, failed — never a blank screen or an indefinite spinner. It performs no navigation of its own: like every other auth entry point in this app, a successful exchange writes a session via `supabase.auth.onAuthStateChange` → `hooks/useAuth.ts`, and `app/(auth)/_layout.tsx`'s existing forward guard (extended in this ticket to also guard `/confirm`) redirects to `/onboarding` or `/` on its own next render. A web-only fallback additionally adopts implicit-flow tokens from `window.location.hash` via the public `setSession()` API, covering any confirmation email still using Supabase's default template. Two out-of-repo configuration changes — the confirmation email template body, and the Auth Redirect-URLs allow-list — ship alongside the code and are recorded verbatim in the worklog, not just performed. Live, end-to-end verification (a real email, opened same-device and cross-device) is attempted but is explicitly allowed to close as **blocked** rather than **passed** if `BL-188`'s outbound-email gap (partially mitigated 2026-08-18 via Resend, but only for the developer's own registered address until a domain is verified) still prevents a real send reaching the test inbox.

## Ground-check — 2026-08-18

Read out of the current working tree today; no Bash, no WebSearch, no Supabase MCP this pass. Everything below is either a direct file citation or explicitly labelled per `docs/OPERATOR_RULEBOOK.md` §E.

| Claim | Status |
|---|---|
| `mobile/features/auth/auth.service.ts:107` already exports `verifyOtp(phoneDigits, token)` for the SMS path (`type: 'sms'`) | **Verified** — the new function must be named differently; used `confirmEmailToken` below. |
| `mobile/features/auth/auth.types.ts:11-22`'s `AuthErrorCode` union does **not** yet contain a code for a bad confirmation link; `email_confirmation_required` is already taken by SS-072's sign-in-side mapping | **Verified** — added `invalid_or_expired_confirmation_link` below, additive only. |
| `app/(auth)/_layout.tsx:28-33`'s `GUARDED_ROUTES` is exactly `{'/login', '/(auth)/login', '/verify-otp', '/(auth)/verify-otp'}`; `usePathname()` strips route-group segments (still true, same `expo-router@56.2.11` install as SS-071/SS-072 verified against) | **Verified** — `/confirm` is not in the set today, so it is unauthenticated-reachable with zero edit; this design adds it deliberately (see "The guard decision" below), not as a default. |
| `mobile/lib/supabase.ts:33-40` — `detectSessionInUrl: false`, `storage` platform-branches SecureStore/localStorage, no `flowType` override (stays `implicit`) | **Verified, and this file is NOT touched by this ticket** — carries forward SS-072's revision block and `BL-170`'s standing decision unchanged. |
| `hooks/useAuth.ts:75-80` — `onAuthStateChange` is the single place any session (however minted) is written to `useAuthStore` and synced to Sentry/analytics; no service function needs to touch the store directly | **Verified** — `confirmEmailToken`/`adoptSessionFromUrlFragment` follow `auth.service.ts`'s existing `verifyOtp`/`signInWithEmail` shape: call the SDK, return/resolve, let the listener do the rest. |
| `mobile/app.json:7` — native scheme `stylesense` is configured; no `expo-linking`-specific plugin config beyond the scheme itself | **Verified** — `stylesense://confirm?token_hash=...&type=email` resolves through Expo Router's linking config to `app/(auth)/confirm.tsx` the same way any other deep link does; no new native wiring needed. |
| `@supabase/auth-js@2.108.2`'s `verifyOtp({ token_hash, type: 'email' })` and public `setSession({ access_token, refresh_token })` shapes | **Verified by SS-072's Architect pass** (`GoTrueClient.d.ts:1096-1102`, `types.d.ts:686-693`, `setSession` in the same `.d.ts`) — reused here, not re-verified independently this pass since the installed SDK version is unchanged. |
| The exact confirmation-email template variable (`{{ .RedirectTo }}` + `{{ .TokenHash }}`) needed to point Supabase's confirmation link at `/confirm?token_hash=...&type=email` | `[TRAINED KNOWLEDGE — NOT VERIFIED, no WebSearch this pass]` — this is the standard Supabase custom-template pattern for a token-hash-based confirmation flow, but it must be checked against Supabase's current Auth → Email Templates documentation before being applied live. Flagged as an Open question below; do not apply the template in the dashboard without that check. |
| Whether `SITE_URL` is currently a Supabase default or already set to something sane | `[UNKNOWN — not readable from this repo]` — same class of unknown as `BL-171` (no hosted origin exists yet); recorded as a live-verification item, not asserted. |

## Files to create/modify

**Create**

| Path | What |
|---|---|
| `mobile/app/(auth)/confirm.tsx` | The new route. Reads `token_hash`/`type` from `useLocalSearchParams` (works identically for a web query-string navigation and a native deep link — Expo Router parses both into the same params object, per the ground-check above). Renders three states — `working` / `success` / `failed` — via local `useState`, never a fourth (blank/indefinite-spinner) state. Calls `useConfirmEmailTokenMutation()`; on web, if no `token_hash` param is present, falls back to `adoptSessionFromUrlFragment()` (`Platform.OS === 'web'` guarded) before giving up and rendering `failed`. On success, calls `window.history.replaceState` (web only) to strip the token from the address bar, then renders a brief "success" state — no navigation call; `app/(auth)/_layout.tsx`'s guard (see below) redirects on its own next render once the session lands in the store. On failure, renders the non-technical copy plus a `Button` linking to `/login` (hardcoded, never URL-derived — AC #6). |
| `mobile/__tests__/app/(auth)/confirm.test.tsx` | New suite — see Test plan. |

**Modify**

| Path | What |
|---|---|
| `mobile/app/(auth)/_layout.tsx` | Add `/confirm` and `/(auth)/confirm` to `GUARDED_ROUTES` (see "The guard decision" below — this is the deliberate part of AC #2, not an oversight). No other change to this file; the existing `loading`/`app`/`onboarding`/fall-through branches are reused exactly as they already are for `/login`/`/verify-otp`. |
| `mobile/features/auth/auth.service.ts` | Add `confirmEmailToken(tokenHash: string): Promise<Session>` (the `verifyOtp({ token_hash, type: 'email' })` wrapper — distinctly named per the ground-check) and `adoptSessionFromUrlFragment(): Promise<Session \| null>` (the web fragment fallback, reading `window.location.hash` and calling `supabase.auth.setSession(...)`). Both follow the existing `toEmailAuthError`/`toAuthError`-mapping discipline: catch, map, throw a typed `AuthError`, never a raw SDK error. Modify `signUpWithEmail`'s `supabase.auth.signUp` call and `resendConfirmationEmail`'s `supabase.auth.resend` call to pass `options: { emailRedirectTo: getConfirmationRedirectUrl() }` (a new small helper, also added here — see "Concrete values" below). No other function in this file changes. |
| `mobile/features/auth/auth.types.ts` | Add `'invalid_or_expired_confirmation_link'` to `AuthErrorCode` — additive only, `AuthError`'s `{ code, message }` shape is unchanged. |
| `mobile/features/auth/auth.queries.ts` | Add `useConfirmEmailTokenMutation()` (`useMutation<Session, AuthError, string>`, wraps `confirmEmailToken`) and `useAdoptSessionFromUrlFragmentMutation()` (`useMutation<Session \| null, AuthError, void>`, wraps `adoptSessionFromUrlFragment`) — same `TError = AuthError` pattern every existing mutation in this file already uses. |

**Explicitly NOT touched, and why:** `mobile/lib/supabase.ts` (`detectSessionInUrl` stays `false`, `flowType` stays `implicit` — `BL-170` untouched, per the ticket's own Technical Notes and re-confirmed by the ground-check); `mobile/app.json` (no new deep-link config needed — the existing `stylesense` scheme already covers it); `backend/` (no backend change, no migration — a session minted via `verifyOtp`/`setSession` is indistinguishable downstream from any other, per `hooks/useAuth.ts`'s provider-agnostic listener); `mobile/features/auth/components/EmailAuthForm.tsx` and `CheckYourEmailNotice.tsx` (SS-072's flow keeps working unchanged, per AC #10 — this ticket adds a fast path, it does not touch the existing one).

## The guard decision (AC #2 — resolved deliberately, not by omission)

**`/confirm` is added to `GUARDED_ROUTES`.** This means: the instant a session exists (any session — the one this exact click is about to mint, or an unrelated one already live), `_layout.tsx`'s existing guard redirects away to `/` or `/onboarding` **before `confirm.tsx` ever renders or calls `verifyOtp`**. This single decision resolves three of the ticket's edge cases at once, with zero new guard code beyond two set-literal entries:

- **Same user's session already live** (edge case: "harmless, but must not loop or double-navigate"): the guard redirects away immediately — the token is never even read. No loop is possible by the same structural argument SS-071's design doc already established (`_layout.tsx`'s guard is the only redirect *away from* this route group; `(tabs)/_layout.tsx`'s guard is the only redirect *toward* `/onboarding`; no route is both a source and a target).
- **A *different* user's session live** (edge case, explicitly flagged as needing a deliberate decision): the guard redirects away without ever calling `verifyOtp` or `setSession` — so the active session can never be silently swapped underneath the browser's current user. This is the safer of the two options AC #2 names ("a guard redirect away, or an explicit 'you're signed in as X' state") and costs nothing extra to implement, since it's the same mechanism as the first bullet. The account the link was for is still confirmed server-side regardless (GoTrue does that before the redirect even fires) — nothing is lost, the user just doesn't get auto-signed-in on this particular click; SS-072's manual "come back and sign in" path remains available to them under their own session after signing out, unchanged.
- **Cold, fully unauthenticated open** (the normal, cross-device case the whole ticket exists for): the guard's `unauthenticated` branch falls through to the `Stack` exactly as it does for `/login`/`/verify-otp` today — `confirm.tsx` renders, reads the token, exchanges it, and the *next* render (once the store updates via `onAuthStateChange`) picks up the new session and redirects. No navigation call inside `confirm.tsx` itself, matching every other auth screen in this app.

The alternative considered and rejected: leaving `/confirm` unguarded and having the screen itself branch on session state via `useAuthRouting()`. Rejected because it duplicates guard logic that already exists, tests worse (two independent places asserting the same three-way branch instead of one), and reopens exactly the `BL-168` failure class SS-071 was built to close — a route that can render while authenticated with no guarantee anything redirects it away.

## Concrete values to use, not invent

### `confirmEmailToken` and `adoptSessionFromUrlFragment`

```ts
// auth.service.ts — additive, alongside the existing SMS-path verifyOtp.
// Distinct name is load-bearing — see this doc's Ground-check table.
export async function confirmEmailToken(tokenHash: string): Promise<Session> {
  let session: Session | null;
  try {
    const { data, error } = await supabase.auth.verifyOtp({
      token_hash: tokenHash,
      type: 'email', // NOT 'signup' — deprecated per the installed SDK's own doc comment (SS-072's Architect pass already verified this).
    });
    if (error) throw error;
    session = data.session;
  } catch (error) {
    throw toConfirmationLinkError(error);
  }
  if (!session) {
    throw toConfirmationLinkError(
      new Error('verifyOtp resolved with a null session'),
    );
  }
  return session;
}

// Web-only fallback for Supabase's DEFAULT template (implicit tokens in the
// URL fragment) — inert (resolves null, never throws) on native, so
// confirm.tsx can call it unconditionally behind a Platform.OS check without
// a second code path. Never calls the SDK's private _getSessionFromURL
// (confirmed unusable outside a browser by SS-072's Architect pass).
export async function adoptSessionFromUrlFragment(): Promise<Session | null> {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return null;
  const hash = new URLSearchParams(window.location.hash.replace(/^#/, ''));
  const access_token = hash.get('access_token');
  const refresh_token = hash.get('refresh_token');
  if (!access_token || !refresh_token) return null;
  try {
    const { data, error } = await supabase.auth.setSession({
      access_token,
      refresh_token,
    });
    if (error) throw error;
    return data.session;
  } catch (error) {
    throw toConfirmationLinkError(error);
  }
}

// New, narrow mapping — deliberately NOT toEmailAuthError('signup'|'signin'),
// which has no branch for a stale/malformed link and would wrongly report
// e.g. weak_password or email_already_registered codes it doesn't apply to.
function toConfirmationLinkError(error: unknown): AuthError {
  if (isNetworkFailure(error)) {
    return { code: 'network_error', message: NETWORK_ERROR_MESSAGE }; // reused verbatim, SS-003's constant
  }
  return {
    code: 'invalid_or_expired_confirmation_link',
    message:
      'This link may have expired or already been used. Your account may already be confirmed — try signing in.',
  };
}
```

### `getConfirmationRedirectUrl()` — feeds `emailRedirectTo` on both SS-072 call sites

```ts
// auth.service.ts
function getConfirmationRedirectUrl(): string {
  if (Platform.OS === 'web') {
    // BL-171: no hosted origin exists yet — this resolves to whatever
    // origin the app is actually being served from today (localhost:8081
    // in dev), which is exactly what needs to be on the Redirect URLs
    // allow-list. Re-derives correctly with zero code change once a real
    // origin exists.
    return `${window.location.origin}/confirm`;
  }
  return Linking.createURL('confirm'); // resolves to stylesense://confirm
}
```

`signUpWithEmail` and `resendConfirmationEmail` both add `options: { emailRedirectTo: getConfirmationRedirectUrl() }` to their existing `supabase.auth.signUp(...)`/`supabase.auth.resend(...)` calls — no other change to either function's body or return contract.

### Confirmation email template — the exact string to configure, and its verification gate

`[TRAINED KNOWLEDGE — NOT VERIFIED, no WebSearch this pass — the Developer must check this against Supabase's current Auth → Email Templates documentation before applying it live, and record what was actually applied in the worklog per AC #9]`. The recommended "Confirm signup" template body:

```
{{ .RedirectTo }}?token_hash={{ .TokenHash }}&type=email
```

`{{ .RedirectTo }}` resolves to whatever `emailRedirectTo` was passed at `signUp()`/`resend()` time (i.e. `getConfirmationRedirectUrl()`'s output), **provided that exact origin is on the Redirect URLs allow-list** — otherwise GoTrue silently substitutes `SITE_URL` instead, which is precisely the "link lands on a page StyleSense doesn't own" edge case. This is why the redirect-URL allow-list entry and the template edit are described in the raw ticket as "equally load-bearing" — one without the other produces a link to a route that doesn't parse the token.

### Redirect URLs allow-list — entries to add, recorded exactly

- `http://localhost:8081/confirm` (current dev web origin — `BL-171`, no hosted origin exists yet; re-add the real production origin the moment one exists)
- `stylesense://confirm` (native scheme, `mobile/app.json:7`)

### `SITE_URL`

Set to `http://localhost:8081` for now (the only real origin that exists today, per `BL-171`), recording whatever the previous value was before changing it (live-verification item — see Open questions). This is the fallback target when `emailRedirectTo` isn't allow-listed; setting it to something real (rather than a Supabase default placeholder) is what keeps a misconfigured allow-list entry from landing the user on a broken page rather than merely an unbranded one.

### `AuthErrorCode` — the one new member

```ts
// auth.types.ts — additive only
export type AuthErrorCode =
  | 'invalid_phone'
  | 'network_error'
  | 'rate_limited'
  | 'invalid_or_expired_otp'
  | 'unknown'
  | 'email_already_registered'
  | 'invalid_credentials'
  | 'weak_password'
  | 'email_confirmation_required'
  | 'invalid_or_expired_confirmation_link'; // SS-073 — new
```

### `confirm.tsx` — state shape

```ts
type ConfirmState =
  | { status: 'working' }
  | { status: 'success' }
  | { status: 'failed'; error: AuthError };
```

No fourth state; the component never returns `null`/blank. `working` is the initial state and covers both the token-hash exchange and the fragment-fallback attempt (sequential: try `token_hash` first, then the fragment fallback if absent — never both, since both mutate global auth state and racing them is undesirable). A `hasAttempted` ref guards against a double-invoke (React 18 Strict Mode's double-effect in dev, or a re-render before the mutation settles) firing `verifyOtp`/`setSession` twice with the same token.

## Edge cases

Carried forward verbatim from the raw ticket's own list (all of them — see `docs/tickets/raw/SS-073.md`'s Edge Cases & Failure Modes) plus the resolutions recorded above:

- Cross-device open with no prior app state — the primary case; `confirm.tsx` renders cold with no dependency on the originating device (`verifyOtp({ token_hash })`'s whole reason for existing over PKCE).
- Expired/already-used token — `toConfirmationLinkError`'s single non-network branch, worded to say the account may already be confirmed, with a `Sign in` route.
- Redirect URL not configured in the dashboard — silent-and-recoverable by construction: the account is still confirmed server-side (GoTrue does that before any redirect), and SS-072's manual "check your email → come back and sign in" path still works regardless of whether `/confirm` was ever reached.
- Different user's live session — resolved via the guard decision above (redirect away, no swap, no consumption attempt).
- Same user's live session — resolved the same way (redirect away, no loop).
- Mail-client pre-fetch consuming the token before the human clicks — same failure copy as expired/used; explicitly not treated as an attack, per the raw ticket.
- Native deep link vs. web navigation — `useLocalSearchParams` covers both for `token_hash`; the fragment fallback is `Platform.OS === 'web'`-guarded and is a plain no-op (resolves `null`) on native, never a crash.
- Token left in browser history — `window.history.replaceState` on success, web-only (native has no address bar to leak from).
- No token at all (direct open, or a mail client stripping the query string) — `working` transitions straight to `failed` once both the `token_hash` read and the fragment-fallback attempt come back empty, with the same `Sign in` route.
- Network failure mid-exchange — `network_error` code/copy (SS-003's existing constant, reused by identity not by copied literal), with a retry that re-uses the **captured** token from component state, not a re-read of the URL (the URL is only stripped on success, so a failed attempt's token is never lost — see "Concrete values" above).
- `BL-188` blocks live verification — AC #8 is recorded as **blocked**, not passed, if the developer's own Resend-sandbox test address (the only address Resend's unverified sandbox sender can currently reach, per `BL-188`'s 2026-08-18 update) still doesn't receive the email at Developer-verification time.

New edge case this design surfaces, not in the raw ticket:

- **A `token_hash` present but the fragment also present** (unlikely, but possible if a link is manually edited/shared) — `confirm.tsx` tries `token_hash` first and never falls through to the fragment path if a `token_hash` attempt was made, successful or not, so the two mechanisms never race each other.

## Test plan

Jest + RNTL, following the existing `_layout.test.tsx`/`emailAuth.service.test.ts` mocking conventions (mock `expo-router`'s `useLocalSearchParams`, mock `lib/supabase`, do not mock `features/auth/auth.methods` unless a suite transitively needs it per SS-071's "run login.test.tsx first" lesson).

**`mobile/__tests__/features/auth/emailAuth.service.test.ts`** (extend)
1. `confirmEmailToken` calls `supabase.auth.verifyOtp` with exactly `{ token_hash, type: 'email' }` — pins the exact call shape (AC #3).
2. `confirmEmailToken` resolving `{ data: { session: null }, error: null }` throws `invalid_or_expired_confirmation_link` (defensive-branch discipline, matching the existing SMS `verifyOtp`'s null-session handling).
3. `confirmEmailToken` rejecting with an unmapped/expired-token-shaped error throws `{ code: 'invalid_or_expired_confirmation_link' }` with the non-technical copy — never the raw SDK message (AC #5).
4. `confirmEmailToken` rejecting with a network-failure-shaped error throws `{ code: 'network_error' }` (SS-003's existing message, asserted by identity).
5. `adoptSessionFromUrlFragment` on a non-web `Platform.OS` resolves `null` without calling `supabase.auth.setSession` at all.
6. `adoptSessionFromUrlFragment` on web with no `access_token`/`refresh_token` in `window.location.hash` resolves `null` without calling `setSession`.
7. `adoptSessionFromUrlFragment` on web with both tokens present in the hash calls `supabase.auth.setSession({ access_token, refresh_token })` exactly once and resolves the returned session.
8. `signUpWithEmail` and `resendConfirmationEmail` both call the SDK with `options.emailRedirectTo` equal to `getConfirmationRedirectUrl()`'s output — regression guard so a future edit can't silently drop it.

**`mobile/__tests__/app/(auth)/confirm.test.tsx`** (new)
9. `token_hash` param present and the mutation resolves a session → renders the `success` state; asserts `router.push`/`router.replace` are **never** called (routing is the guard's job, not this screen's).
10. `token_hash` param present and the mutation rejects with `invalid_or_expired_confirmation_link` → renders the failure copy plus a working `Sign in` link to `/login`; never renders the raw error message.
11. No `token_hash` param, web platform, hash carries `access_token`/`refresh_token` → falls back to `adoptSessionFromUrlFragment`, renders `success` on resolution.
12. No `token_hash` param, no hash tokens either (any platform) → renders `failed` with the "no token" copy, not an indefinite spinner.
13. No `token_hash` param, **native** platform → does not attempt the fragment fallback (asserts `adoptSessionFromUrlFragment`'s mock — if mocked at the service layer — is never called, or equivalently that no crash occurs referencing `window`), renders `failed`.
14. A double-render/double-effect (simulate via a rerender before the mutation resolves) calls the underlying exchange function exactly once — pins the `hasAttempted` guard.
15. On success, `window.history.replaceState` is called (web) — spy on it, assert it fires once and only on the success path, not on `working` or `failed`.
16. Loading state renders a distinct `working` UI (not blank) while the mutation is pending.

**`mobile/__tests__/app/(auth)/_layout.test.tsx`** (extend — AC #2's "pinned by tests on both sides")
17. `pathname /confirm`, `useAuthRouting()` returns `{ status: 'app' }` → redirects to `/`, mirroring the existing `/login`+`app` case (same-user-already-signed-in / different-user-signed-in, both resolved identically by the guard — no code distinguishes them, so one test covers both).
18. `pathname /confirm`, `useAuthRouting()` returns `{ status: 'onboarding' }` → redirects to `/onboarding`.
19. `pathname /confirm`, `useAuthRouting()` returns `{ status: 'unauthenticated' }` → renders the `Stack` (falls through to `confirm.tsx`), no redirect — the cold-open case this whole ticket exists for.
20. `pathname /(auth)/confirm` (route-group-prefixed form) behaves identically to `/confirm` for at least one of the above — pins the defensive dual-form matching the existing entries already use.

**Unchanged gates:** `tsc --noEmit`, `biome check` on this ticket's files, full jest suite green — including SS-072's existing suites, which must show **zero weakened assertions** (AC #10).

## Open questions / blockers

1. **The confirmation-email template string is `[TRAINED KNOWLEDGE — NOT VERIFIED]`.** Before applying it in the Supabase dashboard, the Developer must check `{{ .RedirectTo }}` + `{{ .TokenHash }}` against Supabase's current Auth → Email Templates documentation (this pass had no WebSearch tool). If the actual supported syntax differs, record the real one used in the worklog per AC #9 — do not silently apply the guessed string without checking.
2. **`AC #8` (live end-to-end verification) is gated on `BL-188`, which is only *partially* resolved as of 2026-08-18.** Resend is wired in `supabase/config.toml` but not yet pushed live (`supabase config push` deliberately deferred — see `BL-188`'s 2026-08-18 note, pending `BL-183`'s still-unread live password policy). Even once applied via the Dashboard's manual SMTP fields (the safer path `BL-188` recommends), Resend's sandbox sender only reaches the developer's own registered address until a domain is verified — so AC #8's *same-device* half is plausibly closeable, but its *cross-device* half (a different device/browser than the one that signed up) still needs that same address reachable from a second device, which is achievable (the developer can open their own inbox on a phone) and does not require the domain-verification step. Recorded here so QA doesn't read a "blocked" AC #8 as a Developer failure if the domain step genuinely isn't done yet.
3. **`SITE_URL`'s current live value is unread** (`[UNKNOWN — not readable from this repo]`). The Developer must read it from the dashboard before changing it, and record both the old and new values in the worklog per the raw ticket's Technical Notes ("record the previous value").
4. **This ticket does not touch `BL-183`** (live password policy / HIBP, still open) or `BL-173` (no password reset) — both remain open and unrelated to this ticket's scope; noted so a reviewer doesn't expect either to move.
5. **No conflict found between this design and CLAUDE.md.** `confirm.tsx` is a route under `app/(auth)/`, its data access goes through `features/auth/auth.service.ts`/`auth.queries.ts` exactly like every other screen in this domain, no `StyleSheet.create`, no direct Supabase call from the component, loading/error/success states all explicit, no inline styles beyond the one pre-existing `errorPlaceholder` color pattern SS-003/SS-072 already established.

## Backlog delta

No new `BL-XXX` row needed — this ticket is itself the resolution SS-072's `BL-187` row already points at (see `docs/BACKLOG.md`'s Resolved table: `BL-187` "Resolved by: SS-073 (ticketed, not fixed) / Architect, 2026-08-17"). This design doc is the code-level follow-through on that resolution; `BL-187`'s row does not need editing again until the Developer/QA phases actually ship it (at which point QA or DevOps should update its note to reflect real shipped status, not this Architect pass). `BL-188` and `BL-183` (both `auth`/`infra`-tagged, both Active) are directly relevant and were re-scanned above — `BL-188` is referenced throughout as this ticket's live-verification gate (not resolved by this design, only its scope narrowed by the 2026-08-18 Resend update already recorded there); `BL-183` is unaffected and not touched.

## Risk classification

`Risk: high` — confirmed, not re-derived. This design changes nothing about the three independent factors the raw ticket's own §Risk classification already established (credential-consuming public route; live Auth configuration changes affecting every signup; a new guard entry on the exact file SS-071 shipped to fix `BL-168`) — it implements them as scoped. Full lane, every human gate preserved.

**Model-triage note for the orchestrator:** this pass ran on the default (Sonnet) model per the orchestrator's mechanical keyword/path scan, but the ticket's own header already carries `Risk: high` and its Source note names the auth/session/guard/config surface explicitly — so the triage scan did not miss anything here; the risk was already visible before this pass started, and nothing found during this pass changes that classification or argues for re-running on Opus. Flagging per this role's own standing instruction to say so explicitly when the question is live, even though the answer here is "no re-run needed."
