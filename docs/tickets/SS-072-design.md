# SS-072 — Email/Password Sign-Up & Sign-In — Design

Ticket: `docs/tickets/raw/SS-072.md` · Branch: `feature/SS-072-email-password-auth` · Tier: standard (Est 8h) · Depends on: SS-071 (merged)

## Scope restatement

Add email/password as the **second** entry in SS-071's auth-method registry, and harden the DB trigger that every signup path runs through. On the client: one self-contained form component with two modes (Create account / Sign in) sharing an email field, reached from `/login`, built out of SS-003's existing vocabulary — typed `AuthErrorCode` values, `Input` inline error states, `useMutation` hooks in `auth.queries.ts` over service functions in `auth.service.ts`. It performs **no navigation of its own**: a successful signup or sign-in writes a session, and SS-071's `(auth)` layout guard redirects to `/onboarding` or `/` exactly as it already does for phone OTP. On the database: migration `021` rewrites `handle_new_auth_user` so a signup carrying an already-registered email aborts its whole transaction with a recognizable error instead of an opaque `500 Database error saving new user` (`BL-169`), while leaving the phone-only (NULL email) path byte-for-byte unchanged.

Three things are settled and are implemented as written, not re-litigated: email confirmation stays **off** (`BL-174`, with a defensive `session === null` branch anyway), duplicate email is **rejected outright, never merged** (`BL-169`), and there is **no password-reset flow and no "Forgot password?" affordance at all** (`BL-173`). No backend change, no account-linking UI (`BL-172`).

## Ground-check — what I verified in the repo before designing

Everything below was read out of the current working tree today (2026-08-16). Four of these findings changed the design; two of them contradict the raw ticket.

### SS-071's shipped surface (the four things this ticket must build on)

| Claim | Verified |
|---|---|
| `features/auth/useAuthRouting.ts` is the single routing decision function, consumed only by layouts | Yes — `useAuthRouting.ts:18-49` returns the 4-state union; it computes and never navigates. Its only consumers are `app/(auth)/_layout.tsx:37` and `app/(tabs)/_layout.tsx`. |
| `app/(auth)/_layout.tsx` guards `/login` and `/verify-otp` away from an authenticated session, excluding `/onboarding` | Yes — `_layout.tsx:28-33`'s `GUARDED_ROUTES` set is exactly `{/login, /(auth)/login, /verify-otp, /(auth)/verify-otp}`; `/onboarding` deliberately absent. |
| `auth.methods.ts` + `AuthMethodChooser.tsx` accommodate a second method without touching `login.tsx` | **Partly — see "Deviation 2" below.** The registry accommodates it; the *chooser's render shape* does not satisfy AC #1's "phone remains visually primary/default", and adding a second entry breaks a shipped test. `login.tsx` itself still needs no edit. |
| Email/password sign-in reuses the same session bootstrap, so `userStateReset.ts` fires identically | Yes, and it is automatic. `hooks/useAuth.ts` subscribes to `supabase.auth.onAuthStateChange` and branches purely on session truthiness — it never inspects which provider minted the session. `signInWithPassword`/`signUp` emit `SIGNED_IN` through the same listener that `verifyOtp` does. `useSignOutMutation` (`auth.queries.ts:89-103`) calls `resetAllUserState()` unconditionally in a `finally`. **No change needed to `userStateReset.ts`, `auth.store.ts`, or `hooks/useAuth.ts`.** |

### The raw ticket's characterization of SS-003's patterns — holds

- `auth.types.ts:10-15` — `AuthErrorCode` is still the 5-member union SS-071 left it at (`invalid_phone`, `network_error`, `rate_limited`, `invalid_or_expired_otp`, `unknown`); `AuthError = { code, message }` (`:17-20`). Additive extension is trivial.
- `auth.service.ts` still owns all `supabase.auth.*` calls for this domain, with `isNetworkFailure` (`:53-56`), `isRateLimited` (`:58-62`) and `toAuthError` (`:66-80`) as the mapping helpers to reuse. `verifyOtp:114-122` establishes the exact precedent for the null-session branch this ticket needs.
- `auth.queries.ts:27-31` — `useMutation<Session, AuthError, {...}>` is the established mutation shape.
- `Input`'s inline error pattern is real: `error?: string` (`Input.tsx:23`) renders via `ErrorText` (`:59-66`) in the accent-error colour. `PhoneLoginForm.tsx:33,50-59` is the canonical "validate locally, then map the mutation's `onError` into the same `error` slot" flow to copy.

### Migration numbering — `021` confirmed

`supabase/migrations/` contains `001`–`020` with no gaps; `020_outfits_first_writer.sql` is the highest. **`021` is correct**, matching the ticket's reservation under `BL-110`'s serialization rule.

### `handle_new_auth_user`'s exact current shape — read, not recalled

`002_onboarding_completed.sql:15-31`, verbatim:

```sql
CREATE OR REPLACE FUNCTION public.handle_new_auth_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
BEGIN
  INSERT INTO public.users (id, phone, email)
  VALUES (NEW.id, NEW.phone, NEW.email)
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END; $$;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION public.handle_new_auth_user();
```

`001_initial.sql:24-41`: `users.email TEXT UNIQUE` and `users.phone TEXT UNIQUE`, **both nullable**, and `id UUID PRIMARY KEY DEFAULT gen_random_uuid()` — **with no `REFERENCES auth.users(id)` and no `ON DELETE CASCADE`.** Grep across all 20 migrations confirms nothing later adds that FK, adds `NOT NULL`, changes `email` to `citext`, or adds a functional index on it. Two consequences the ticket did not anticipate, both load-bearing:

1. `ON CONFLICT (id) DO NOTHING` guards `id` only, so the `email UNIQUE` constraint fires from *inside* the `SECURITY DEFINER` body — exactly `BL-169` as described. Confirmed.
2. **`public.users` rows outlive their `auth.users` rows.** Deleting an auth user (dashboard, or SS-070's script) leaves an orphan `public.users` row still holding that email, which then permanently blocks re-signup with it. Migration `021` converts that from an opaque 500 into a clean error, but does **not** unblock it. Logged as `BL-184`.

Note also `004_backfill_missing_user_rows.sql` inserts `(id, phone, email)` straight from `auth.users` — it is a one-shot historical backfill and is unaffected by `021` (it does not call the function).

### `@supabase/supabase-js` — verified against the installed SDK, not asserted

`[VERIFIED 2026-08-16 against `mobile/node_modules/@supabase/auth-js/dist/module/`]` — this is the check the ticket's `[TRAINED KNOWLEDGE — verify before writing code]` note demanded, and it resolves the ticket's own open worry about anti-enumeration obfuscation:

- `GoTrueClient.d.ts:443` — `signUp(credentials: SignUpWithPasswordCredentials): Promise<AuthResponse>`. `:566` — `signInWithPassword(credentials): Promise<AuthTokenResponsePassword>`. Both shapes are as the ticket assumed.
- **Confirm-email semantics, from the SDK's own doc comment (`:279-283`):** "If **Confirm email** is enabled, a `user` is returned but `session` is null. If **Confirm email** is disabled, both a `user` and a `session` are returned." Confirms the design's premise *and* the necessity of the defensive `session === null` branch.
- **The duplicate-signup obfuscation question is answered (`:284-286`):** an obfuscated/fake user object is returned **only when both Confirm email *and* Confirm phone are enabled**. "When either **Confirm email** or **Confirm phone** is disabled, the error message, `User already registered` is returned." Since this project runs with Confirm email **off**, `signUp` on a duplicate returns a **real, mappable error** — so **AC #3's specific copy is achievable and does not need reconciling downward.** This was the ticket's single largest unknown; it is closed.
- **Errors carry a stable machine-readable `code`** (`errors.d.ts:20`: `code: ErrorCode | (string & {}) | undefined`) — branch on `error.code`, never on `error.message`. The SDK's own guidance says exactly this (`GoTrueClient.d.ts:562`). Relevant members of the `ErrorCode` union (`error-codes.d.ts:6`, read in full): `user_already_exists`, `email_exists`, `invalid_credentials`, `weak_password`, `email_not_confirmed`, `email_address_invalid`, `validation_failed`, `signup_disabled`, `over_request_rate_limit`, `over_email_send_rate_limit`, `unexpected_failure`.
- `isAuthWeakPasswordError` + `AuthWeakPasswordError.reasons: WeakPasswordReasons[]` exist (`errors.d.ts:254-268`) and `AuthResponse` carries `weak_password?: WeakPassword | null` (`types.d.ts:187`) — a real weak-password signal, not a message heuristic.

### `components/ui/Input.tsx` cannot render a password field today

`Input.tsx:13` — `InputVariant = 'text' | 'phone' | 'search' | 'otp'`. `TextVariantInput` (`:261-291`) forwards only `value/onChangeText/placeholder/editable/autoFocus/multiline/maxLength`. It passes **no `secureTextEntry`, no `keyboardType`, no `autoCapitalize`, no `autoComplete`/`textContentType`**, and hardcodes `accessibilityLabel={placeholder ?? 'Text input'}` (`:286`) — so two unlabelled fields on one screen would share the label `Text input`.

This is not a nice-to-have: **a password field without `secureTextEntry` is unshippable**, and an email field defaulting to `autoCapitalize="sentences"` actively creates the `User@x.com` case-variance the ticket lists as an edge case. So this ticket must extend `components/ui/` — see "Deviation 3". (`BL-179`'s missing confirm-dialog primitive is a *different* gap and is **not** needed here — nothing in signup/sign-in is destructive enough to confirm.)

### Analytics

`constants/analyticsEvents.ts:59` — `register: { method: 'phone_otp' }` is a hardcoded literal, so AC #9 requires widening it. `lib/analytics.ts:26,55-57` — the PII guard scans **key names** only (`BANNED_PII_KEYS` includes `email`), so a *value* of `'email_password'` under the key `method` passes cleanly. Verified, because "method: email_password" would otherwise have thrown in dev.

Separately: `profile.tsx:45` fires `track(ANALYTICS_EVENTS.SIGN_OUT, { method: 'phone_otp' })` **hardcoded**. Once this ticket makes an email session possible, that event misreports. Out of scope (fixing it needs `session.user.app_metadata.provider` mapping + tests); logged as `BL-182`.

## Three deviations from the raw ticket, each with its reason

The raw ticket was written by the `/new-feature` intake **before SS-071 shipped**. Its Description therefore describes a shape that the shipped registry has since made worse rather than better. None of these deviations conflicts with an Acceptance Criterion — the ACs are satisfied in every case; only the Description's implementation sketch changes.

### Deviation 1 — no new route. `EmailAuthForm` is a registry `Component`, rendered under `/login`

The ticket says "One route, `app/(auth)/email-auth.tsx`". **Do not create it.** Register the form as `AUTH_METHODS[1].Component` and let it render inside `/login`, exactly as `PhoneLoginForm` does.

Why this is not a preference:

1. **It is the `BL-168` failure mode, designed out instead of re-created.** A new `/email-auth` route is *not* in `app/(auth)/_layout.tsx:28-33`'s `GUARDED_ROUTES` set. Adding one and forgetting to extend that set gives a screen where a successful signup mints a session and **nothing redirects** — the user sits on the form. That is precisely the bug SS-071 just fixed, reintroduced by the very next ticket. Rendering under `/login`, which *is* guarded, makes AC #2 and AC #6 hold **by construction, with zero new guard code**.
2. It is what SS-071's registry was built for — `auth.methods.ts:4-7` states it outright: "adding a second entry (SS-072's email/password …) is an addition here plus one new form component, never an edit to `login.tsx`."
3. **No AC requires a route.** AC #1 requires only that "selecting email *reaches a screen* supporting both Create account and Sign in" — an inline render satisfies it, with the chooser's Back affordance for free.

If a reviewer nonetheless wants a deep-linkable `/email-auth` route, the **mandatory** condition is that `/email-auth` and `/(auth)/email-auth` are both added to `GUARDED_ROUTES` in the same commit, with a test asserting an authenticated session on that path redirects. That is strictly more work for strictly more risk; the design recommends against it.

### Deviation 2 — the chooser renders the primary method's form inline; it is not a two-button menu

**This is the finding with real teeth.** `AuthMethodChooser.tsx:39-59` currently renders a *list of buttons* when 2+ methods are registered, and `login.tsx:32-37` switches from "render the only method directly" to "render the chooser" the moment a second entry appears. Adding email/password therefore silently changes what `/login` renders — with two consequences:

- **AC #1 fails.** "Phone remains the visually primary/default path" is not true of a two-equal-buttons menu with no default.
- **`__tests__/app/(auth)/login.test.tsx` breaks.** Verified: that file (SS-003's original 6-case suite) does **not** mock `features/auth/auth.methods` — it resolves the real registry — and asserts `getByText('+91')`, `getByLabelText('Phone number')`, `getByText('Send OTP')` on a bare `<LoginScreen />`. Under a menu, none of those render until a button is pressed. SS-071 went to deliberate lengths (its AC #1, its whole "seam is a module mock, not a prop" argument) to keep this file unmodified; a two-button menu throws that away one ticket later.

**New chooser shape:** `AUTH_METHODS[0]` is the primary method — by array order, no new descriptor field. Then:

- `selectedId === undefined` (default) → render `AUTH_METHODS[0].Component` inline, and below it one `Button variant="secondary"` per **non-primary** method carrying its `label`.
- `selectedId === <a non-primary id>` → render that descriptor's `Component` plus the existing ghost **Back** button, which returns to the default state (i.e. back to the primary form).

`login.tsx` is **not modified** — its `length === 1` / `length === 0` branches and the `auth-method-chooser` testID are all untouched, so `login.registry.single.test.tsx` and `login.registry.empty.test.tsx` keep passing as-is.

This satisfies AC #1 literally ("phone visually primary *and* default"), and keeps `login.test.tsx` passing because `PhoneLoginForm` still renders on a bare mount. The cost is rewriting **`login.registry.test.tsx`** (SS-071's own 2-case file, one ticket old) to assert the new shape — strictly better than restructuring SS-003's 6-case suite, and it is equivalent coverage, not reduced coverage (see Test plan).

> **Developer verification task (do not assume).** `login.test.tsx` mocks `lib/supabase` and `features/auth/auth.queries` (with `useSendOtpMutation` only) but **does not mock `hooks/useAnalytics`** — and every other suite in the repo that transitively reaches it does (`verify-otp.test.tsx:29`, `wardrobe.queries.test.tsx:27`, `app/_layout.test.tsx:27`). Once `auth.methods.ts` imports `EmailAuthForm`, `login.test.tsx` transitively imports `useAnalytics` → `lib/analytics` → `posthog-react-native` at module load. **Run `login.test.tsx` immediately after registering the second method, before writing anything else.** If it throws at import time, the single sanctioned repair is adding one `jest.mock('../../../hooks/useAnalytics', …)` line — a mock addition, never an assertion change. Record which happened in the worklog.

### Deviation 3 — `components/ui/Input.tsx` gains `email` and `password` variants

Unavoidable per the ground-check: there is no way to mask a password with today's `Input`. Extend `InputVariant` **additively** to `'text' | 'phone' | 'search' | 'otp' | 'email' | 'password'`; the four existing variants and their render paths are untouched.

Chosen over the alternative of adding raw pass-through props (`secureTextEntry`, `keyboardType`, `autoCapitalize`, …) to the `text` variant, because that turns `Input` into a thin `TextInput` wrapper and lets any future caller bypass the design system's decisions. A variant per use case is the pattern the file already establishes four times over.

- **`email` variant** — `keyboardType="email-address"`, `autoCapitalize="none"`, `autoCorrect={false}`, `autoComplete="email"`, `textContentType="emailAddress"`. `autoCapitalize="none"` is load-bearing, not cosmetic: the default would upper-case the first character on mobile and manufacture the `User@x.com` duplicate this ticket exists to reject.
- **`password` variant** — `secureTextEntry` (toggleable), `autoCapitalize="none"`, `autoCorrect={false}`, plus a show/hide eye toggle built from the same `Pressable` + `Ionicons` pattern `SearchInput` already uses for its clear button (`Input.tsx:243-256`), with `accessibilityLabel` `Show password` / `Hide password`. Takes a `passwordMode?: 'current' | 'new'` prop driving `autoComplete` (`'password'` vs `'new-password'`) and `textContentType` (`'password'` vs `'newPassword'`) so a password manager offers "save new password" on signup and "fill" on sign-in.
- **`accessibilityLabel?: string` is added to `InputProps`** and honoured by the two new variants (required, not optional, in practice — the form has two fields and the existing `placeholder ?? 'Text input'` fallback would give both the same name). Existing variants' labelling is unchanged.

> **Developer verification task:** react-native-web's mapping of RN's `autoComplete="password" | "new-password"` onto the DOM `autocomplete` attribute (`current-password` / `new-password`) is **not verified here** — check what actually lands in the DOM on web and adjust, since web is this app's primary target and password-manager behaviour is the ticket's own stated edge case.

## Migration `021` — hardening `handle_new_auth_user`

File: `supabase/migrations/021_harden_handle_new_auth_user_email_conflict.sql`. It **replaces a function and nothing else** — no `ALTER TABLE`, no new constraint, no new index, no trigger re-creation (the trigger binds by name, so `CREATE OR REPLACE FUNCTION` alone is sufficient and the `AFTER INSERT` timing is preserved).

### Defence is three layers, and only one of them is new

Stating this explicitly because it is what makes the race in the ticket's edge-case list actually safe:

| Layer | Mechanism | Guarantees | Atomic? |
|---|---|---|---|
| 1 — UX | Client maps Supabase's own `user_already_exists` / `email_exists` error to AC #3's copy | A fast, specific message on the common path | n/a |
| 2 — **new in `021`** | Trigger's `lower(email)` pre-check → `RAISE EXCEPTION` | A *clean, identifiable* failure instead of an opaque unique violation from inside `SECURITY DEFINER`; catches case-variants the constraint misses | **No** |
| 3 — correctness backstop | `public.users.email UNIQUE` from `001_initial.sql:26` (already exists) | No duplicate row can ever be committed, even under a perfectly-timed race | **Yes** |

Layer 2 is a **message** layer, not the correctness layer. Two exactly-concurrent duplicate signups can both pass the trigger's `SELECT` and both reach the `INSERT`; layer 3 then rejects the loser. The outcome is still "rejected outright, never merged" — the ticket's actual requirement — just with a less pretty message on that one path. **Say this plainly rather than claiming `021` closes the race**, because layer 3 already made the race safe and `021` was never able to close it.

### Function body

```sql
CREATE OR REPLACE FUNCTION public.handle_new_auth_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  -- SS-072 (BL-169): reject a signup whose email is already owned by a
  -- DIFFERENT public.users row, with a recognizable error, instead of
  -- letting users.email's UNIQUE constraint fire from inside this
  -- SECURITY DEFINER body as an opaque "Database error saving new user".
  -- Case-insensitive: auth.users normalises email case, public.users'
  -- UNIQUE constraint does not, so lower() is what makes the two agree.
  IF NEW.email IS NOT NULL AND EXISTS (
    SELECT 1 FROM public.users u
    WHERE u.id <> NEW.id AND lower(u.email) = lower(NEW.email)
  ) THEN
    RAISE EXCEPTION 'stylesense_email_conflict'
      USING ERRCODE = 'P0001',
            DETAIL  = 'email already registered to a different account',
            HINT    = 'sign in instead, or link the identity while authenticated';
  END IF;

  -- Unchanged from 002_onboarding_completed.sql. ON CONFLICT (id) DO
  -- NOTHING preserves re-entrancy for the id case.
  INSERT INTO public.users (id, phone, email)
  VALUES (NEW.id, NEW.phone, NEW.email)
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$;
```

Concrete values that are **not** to be restyled: the exception message token is exactly `stylesense_email_conflict` (the client greps for it); `ERRCODE = 'P0001'` is plpgsql's default `raise_exception` — deliberately **not** `23505`, so a genuine unique violation stays distinguishable from this deliberate rejection.

### Why the phone path is untouched (AC #5)

The `IF` is gated on `NEW.email IS NOT NULL`. A phone-only signup carries `email = NULL`, short-circuits the guard on its first term, and falls through to the *identical* `INSERT … ON CONFLICT (id) DO NOTHING` that `002` has today. The insert statement is copied verbatim. **AC #5 is nonetheless a live verification, not an inspection** — see Test plan.

### Deliberately not in `021`

- **No case-insensitive functional unique index on `email`.** The trigger's `lower()` comparison already covers the semantics, and the ticket itself makes the index conditional on first proving zero pre-existing case-variant duplicates. Adding it buys atomicity only for the case-variant race — which is unreachable from GoTrue (it normalises email case, so two case-variant auth users cannot both exist) and reachable only via a direct admin insert. Not worth a migration that can fail mid-flight on live rows. Deferred to `BL-185`.
- **No symmetric `phone` conflict check.** `public.users.phone` carries the identical landmine, but adding a second branch changes the phone path's behaviour in the exact ticket whose AC #5 demands that path be *provably* unaffected. That trade is not worth it, especially since the phone path cannot be exercised end-to-end today (`BL-001`, no SMS). Deferred to `BL-185`.
- **No FK from `public.users.id` to `auth.users.id`.** Adding one now would be a genuinely irreversible schema change on live data and is well outside this ticket. Logged as `BL-184`.
- **No `types/supabase.ts` regeneration.** `021` changes a function, not a table or a type surface — no generated-type delta. (`BL-143` tracks that file being stale; do not fold it in here.)

### Rollback

One statement, copy-paste, no reconstruction: re-run `002_onboarding_completed.sql:15-27` verbatim (the `CREATE OR REPLACE FUNCTION public.handle_new_auth_user()` block quoted in the ground-check above). The trigger binding, the table, and every row are untouched by `021`, so reverting the function is a complete revert.

### The honest unknown about `021`'s client-visible error

**`[UNVERIFIED — the Developer must confirm live, and the design does not depend on the answer.]`** Whether GoTrue propagates a trigger's `RAISE EXCEPTION` message to the HTTP client, or swallows it and returns a generic `500 unexpected_failure / "Database error saving new user"`, could not be established from this repo. Both are plausible across GoTrue versions.

The design is therefore built so that **either answer satisfies AC #3 and AC #4**:

- If the token *does* reach the client, `auth.service.ts` matches `/stylesense_email_conflict/i` and maps to `email_already_registered` — deterministic, as the ticket wants.
- If it does **not**, the same mapping additionally treats a **signup-path** `unexpected_failure` (or status 500) whose message matches `/database error saving new user/i` as `email_already_registered`. This is a superset heuristic and is labelled as such in the code comment: on the signup path a trigger-raised 500 is overwhelmingly this case, and AC #3's hard requirement is the **negative** one — the raw string `Database error saving new user` and a bare `500` must never reach the user. That holds unconditionally, because the fallback branch never passes `error.message` through.

AC #4's substantive requirements — transaction rolls back, no orphaned `auth.users` row, no merged or overwritten `public.users` row — are properties of the `RAISE EXCEPTION` inside an `AFTER INSERT` trigger and are independent of what the client sees. They are verified live, per AC #4's own wording.

## Client design

### `EmailAuthForm` — one component, two modes, no navigation

Local `useState` only (no Zustand — nothing outside this screen needs it, the same reasoning `auth.store.ts` and `AuthMethodChooser.tsx:10-15` already record):

`mode: 'signin' | 'signup'` · `email: string` · `password: string` · `emailError?: string` · `passwordError?: string` · `formError?: AuthError`

- **Mode switch preserves the typed email (AC #1), clears the password, and clears all three error slots.** Clearing the password is deliberate: it is the ticket's "mode switching must not strand stale credentials" edge case, and it makes the password manager re-offer the correct `autoComplete` for the new mode.
- **Submit validates before any network call (AC #8):** `normalizeEmail` → `validateEmail` → `validatePassword`, each surfaced into the matching `Input`'s `error` prop. Only on all-valid does it call the mutation. Handlers read the current state values at call time — no cached snapshot.
- **On success it navigates nowhere.** Identical to `verify-otp.tsx` post-SS-071 (`verify-otp.tsx:47-53`): the session lands via `onAuthStateChange` → `hooks/useAuth.ts` → `auth.store`, and `app/(auth)/_layout.tsx`'s guard — which wraps `/login`, where this component renders — redirects to `/onboarding` or `/`. This is AC #2 and AC #6, and it is why Deviation 1 matters. Asserted by a test that `router.replace`/`router.push` are never called.
- **Analytics (AC #9):** on **signup** success only, `track(ANALYTICS_EVENTS.REGISTER, { method: 'email_password' })`, fired unconditionally. Deliberately **not** reusing `verify-otp.tsx:65`'s `created_at === last_sign_in_at` heuristic — that heuristic exists because `verifyOtp` cannot distinguish signup from sign-in, whereas `signUp` *is* the registration call. Sign-in never fires `register`.
- **AC #3's recovery control:** when `formError.code === 'email_already_registered'`, render the message plus a `Button` reading `Sign in instead` which sets `mode = 'signin'` and leaves `email` populated. This is the AC's required "control that switches to sign-in mode with the email prefilled".
- **AC #10:** there is **no** "Forgot password?" text, link, or button anywhere in this component. Asserted negatively by a test (`queryByText(/forgot|reset/i)` is null) so a later well-meaning addition of a dead link fails CI.
- Loading/error/empty (CLAUDE.md): submit `Button` takes `loading={mutation.isPending}`; the mode-switch and "Sign in instead" controls are `disabled` while pending. There is no empty state — a form has no collection.

### Service layer (`auth.service.ts`)

All additive; nothing existing is edited.

```
normalizeEmail(raw: string): string                       // raw.trim().toLowerCase()
validateEmail(email: string): FieldValidationResult
validatePassword(password: string): FieldValidationResult
signUpWithEmail(email: string, password: string): Promise<Session>
signInWithEmail(email: string, password: string): Promise<Session>
```

- Both call `normalizeEmail` **inside** the service, not only in the component, so every future caller gets the normalization (the ticket's case/whitespace edge case).
- Both throw the typed `AuthError` and never a raw error, matching `sendOtp`/`verifyOtp`'s contract exactly (`auth.service.ts:82-125`).
- **Null-session branches**, following `verifyOtp:114-122`'s precedent verbatim in spirit: `signUp` resolving `{ session: null, error: null }` throws `email_confirmation_required` (this is the Confirm-email-turned-back-on defence — a real branch, not dead code); `signInWithPassword` resolving with a null session and no error throws `unknown`.
- Mapping helper `toEmailAuthError(error, mode)` reuses the existing `isNetworkFailure` (`:53`) and `isRateLimited` (`:58`), extending the latter's check to also match `error.code ∈ {over_request_rate_limit, over_email_send_rate_limit}`. It branches on **`error.code`**, never `error.message` (per the SDK's own guidance) — the one exception being the `stylesense_email_conflict` / `database error saving new user` message match documented above, which exists only because the trigger has no other channel.

### Error-code mapping table — use these, do not invent

| Condition | `AuthErrorCode` | User-facing copy |
|---|---|---|
| `code` is `user_already_exists` or `email_exists` (signup) | `email_already_registered` | `This email is already registered — sign in instead.` |
| Signup 500 / `unexpected_failure` matching `stylesense_email_conflict` or `database error saving new user` | `email_already_registered` | same string as above |
| `code` is `invalid_credentials` (sign-in), **and** any unmapped sign-in failure | `invalid_credentials` | `Incorrect email or password.` |
| `code` is `weak_password`, or `isAuthWeakPasswordError(error)` | `weak_password` | `Please choose a stronger password (at least 8 characters).` |
| `signUp` resolves `session: null` with no error; or `code` is `email_not_confirmed` | `email_confirmation_required` | `This account needs email confirmation, which isn't set up yet. Contact support to get in.` |
| `code` is `email_address_invalid` / `validation_failed` | `unknown` (surfaced on the email field) | `Please enter a valid email address.` |
| network-shaped | `network_error` | existing `NETWORK_ERROR_MESSAGE` — reused verbatim, no new string |
| 429 / `over_request_rate_limit` / `over_email_send_rate_limit` | `rate_limited` | existing `RATE_LIMITED_MESSAGE` — reused verbatim |
| anything else | `unknown` | existing `UNKNOWN_ERROR_MESSAGE` — reused verbatim |

**AC #7 (no enumeration on sign-in)** falls out of row 3: `invalid_credentials` is the mapping for both an unknown email and a wrong password *and* for every unmapped sign-in failure, and the copy is a single module-level constant, so a copy divergence is not expressible. The **timing** half of AC #7 is a GoTrue server property this client neither controls nor can measure from the repo — QA must assert the copy identity and state plainly that timing was not measured rather than claim it.

**`email_confirmation_required` leaks account existence on sign-in** (it only appears for an account that exists). Accepted and stated: it is reachable only on the defensive branch where someone has re-enabled Confirm-email, and the alternative — showing `Incorrect email or password.` — would strand a real user with no explanation of a state they cannot fix. AC #7's asymmetry allowance covers the signup side; this is the same trade, made explicitly.

### Password policy

Client-side minimum: **8 characters**, non-empty after no trimming (passwords are never trimmed). One rule, one constant, one message.

`[UNVERIFIED — cannot be checked from this repo.]` The live project's Auth password policy (minimum length; whether the HaveIBeenPwned leaked-password check is available on this project's plan) is a dashboard setting, and this Architect pass has no Bash and no Supabase MCP access to read it. The intake's original flag therefore stands unresolved. Design consequence: **8 characters client-side is the baseline regardless**, and Supabase's own `weak_password` rejection is mapped (row 4 above) so a stricter *server* policy surfaces as a clear message rather than a generic failure. The Developer must read the live setting, raise the client constant if the project minimum is higher (never lower it below the project setting), and record both values in the worklog. Logged as `BL-183`.

## Files to create/modify

**Create**

| Path | What |
|---|---|
| `mobile/features/auth/components/EmailAuthForm.tsx` | The two-mode form; the registry's second `Component`. Navigates nowhere. |
| `supabase/migrations/021_harden_handle_new_auth_user_email_conflict.sql` | `CREATE OR REPLACE FUNCTION public.handle_new_auth_user()` per the body above. Nothing else. |

**Modify**

| Path | What |
|---|---|
| `mobile/features/auth/auth.methods.ts` | `AuthMethodId` gains `'email_password'`; second descriptor appended **after** phone (array order = primacy). |
| `mobile/features/auth/components/AuthMethodChooser.tsx` | New shape per Deviation 2: primary form inline by default + secondary buttons; Back returns to primary. `testID="auth-method-chooser"` retained. |
| `mobile/features/auth/auth.types.ts` | **Additive only** — `AuthErrorCode` gains `email_already_registered`, `invalid_credentials`, `weak_password`, `email_confirmation_required`. Add `FieldValidationResult`, and alias `PhoneValidationResult = FieldValidationResult` so the existing name and every existing caller keep working. `AuthError`'s shape frozen. |
| `mobile/features/auth/auth.service.ts` | Add the five functions + `toEmailAuthError`; extend `isRateLimited` with the two `over_*_rate_limit` codes. Existing functions untouched. |
| `mobile/features/auth/auth.queries.ts` | Add `useSignUpWithEmailMutation` / `useSignInWithEmailMutation`, both `useMutation<Session, AuthError, { email: string; password: string }>`. |
| `mobile/components/ui/Input.tsx` | Additive `email` + `password` variants, `accessibilityLabel?`, `passwordMode?`. Four existing variants untouched. |
| `mobile/constants/analyticsEvents.ts` | Widen `register` to `{ method: 'phone_otp' \| 'email_password' }`. **Do not** touch `sign_out` (that is `BL-182`). |

**Explicitly NOT touched** — each confirmed unnecessary by the ground-check, not assumed:

`app/(auth)/login.tsx` (its branching already handles this) · `app/(auth)/_layout.tsx` (no new route ⇒ no `GUARDED_ROUTES` change) · `features/auth/useAuthRouting.ts` (keys on session truthiness + `onboarding_completed`, never on provider) · `features/auth/userStateReset.ts` and all six store files (sign-out is method-agnostic) · `hooks/useAuth.ts` and `features/auth/auth.store.ts` (already provider-neutral) · `app/(auth)/verify-otp.tsx` and `features/auth/components/PhoneLoginForm.tsx` · `lib/supabase.ts` (`detectSessionInUrl: false` stays — `BL-170`) · `types/supabase.ts` (`BL-143`) · all of `backend/` (`get_current_user_id` is provider-agnostic; every RLS policy keys on `auth.uid()`; `BL-052` stays out of scope).

## Edge cases

Every case from the ticket is carried forward, plus what the ground-check added (11–15).

1. **Email differing only in case or with surrounding whitespace.** `normalizeEmail` (trim + lowercase) runs inside the service, so every path normalises; the trigger's check is `lower()`-based. Both land on AC #3's message, never on a second account.
2. **A phone-first user signs up with an email.** Creates a **second, separate account** with its own empty wardrobe (`BL-172`). Not merged, not warned about speculatively. **No auto-link is reachable from this code path** — checked explicitly, per the brief: this ticket calls only `signUp` / `signInWithPassword` and never `linkIdentity`, and the trigger only ever inserts a row keyed on `NEW.id` (never `UPDATE`s an existing row's email onto a different id). The one construct that could have merged accounts — an `ON CONFLICT (email) DO UPDATE` — is exactly what `021` refuses to do.
3. **Confirm-email is ON in the live project.** `signUp` resolves `session: null, error: null` → service throws `email_confirmation_required` → explicit honest message. Never a blank screen, never an infinite spinner. This is the defensive branch the intake mandated; it has a unit test.
4. **Signup/sign-in rate limiting.** Mapped to the existing `rate_limited` code and SS-003's existing copy — no new string.
5. **Offline / network failure at either call.** Existing `network_error` mapping and copy; no crash; no partially-navigated state (the form navigates nowhere by design, so there is no partial navigation to be in).
6. **A duplicate that races the client pre-check.** Covered for correctness by layer 3 (`email UNIQUE`), for message quality by layer 2 (`021`) on all non-simultaneous cases. The perfectly-simultaneous case yields the generic-500 fallback mapping, which still shows AC #3's copy. Documented above rather than papered over.
7. **Web password-manager autofill** filling both fields, or filling the sign-in form while in signup mode. Mode switch clears the password and re-declares `passwordMode`; the submit handler reads current state values, not a snapshot.
8. **A user who forgets their password** has no recovery path in this ticket at all (AC #10, `BL-173`). Operational mitigation for the beta is SS-070's admin script. Stated, not hidden.
9. **`BL-169`'s landmine is reachable from SS-070's seed script too.** After `021`, the script's failure there becomes the clean `stylesense_email_conflict` instead of an opaque 500; SS-070's own pre-check remains the better-message layer. No change to SS-070 in this ticket.
10. **Migration rollback** — one copy-paste of `002`'s function body (see Rollback above).
11. **(new) An orphan `public.users` row permanently blocks its email.** Because there is no FK/cascade to `auth.users`, deleting an auth user leaves the email claimed forever; `021` makes that a clean rejection rather than a fix. Reachable today via the Supabase dashboard's "delete user". `BL-184`.
12. **(new) Two `Input`s with no distinct accessibility label.** Today's `TextVariantInput` labels every field `Text input`; two such fields on one screen are indistinguishable to a screen reader *and* to `getByLabelText` in tests. Fixed by the `accessibilityLabel` prop in Deviation 3.
13. **(new) `autoCapitalize` default manufactures duplicates.** Without `autoCapitalize="none"` the mobile keyboard upper-cases the first character, producing exactly the `User@x.com` case the ticket's first edge case is about. The `email` variant sets it.
14. **(new) Adding the second registry entry silently changes `/login`'s render tree** and breaks `login.test.tsx` (Deviation 2). The chooser reshape prevents it; the `useAnalytics` import-time risk is a named Developer verification task.
15. **(new) `sign_out` analytics misreports for email sessions** — `profile.tsx:45` hardcodes `method: 'phone_otp'`. Not fixed here; `BL-182`.
16. **Deep link to an authenticated route while signed out** still drops the intended destination (`BL-178`). **Checked: the email path is affected identically, and adds no new instance** — because it renders under `/login`, it inherits exactly the same guard and the same gap, rather than creating a second one. Not fixed here; a separate `/email-auth` route (Deviation 1, rejected) would have added a second instance.

## Test plan

Jest + React Native Testing Library, `jest-expo` preset, mirroring `mobile/__tests__/`'s existing layout.

**`mobile/__tests__/app/(auth)/login.test.tsx` — DO NOT EDIT assertions.** It must still pass with two methods registered; that is Deviation 2's proof. The only sanctioned change is adding a `hooks/useAnalytics` module mock if the transitive import fails at load (see the verification task).

**`mobile/__tests__/app/(auth)/login.registry.test.tsx`** (rewrite to the new chooser shape — equivalent coverage, not reduced)
1. With a 2-entry mocked registry, the **primary** method's component renders on a bare mount, and the secondary's `label` renders as a button (AC #1 — phone is primary *and* default).
2. Pressing the secondary label renders the secondary component and hides the primary's.
3. Pressing `Back` returns to the primary component with the secondary button visible again.

**`mobile/__tests__/features/auth/auth.methods.test.tsx`** (extend the existing file)
4. `AUTH_METHODS` has exactly two entries; `[0].id === 'phone_otp'` and `[1].id === 'email_password'` — pins primacy-by-array-order, which the chooser depends on.

**`mobile/__tests__/features/auth/emailValidation.test.ts`** (new — AC #8)
5. `normalizeEmail` trims surrounding whitespace and lowercases (`'  User@X.com '` → `'user@x.com'`).
6. `validateEmail` rejects empty, no-`@`, no-domain-dot; accepts a normal address. Asserts the exact message string.
7. `validatePassword` rejects `<8` chars with the exact message; accepts 8; does **not** trim (a password of 8 spaces is accepted, proving no trimming).

**`mobile/__tests__/features/auth/emailAuth.service.test.ts`** (new — the mapping table, one test per row)
8. `signUpWithEmail` calls `supabase.auth.signUp` with the **normalized** email and the raw password.
9. `signInWithEmail` calls `supabase.auth.signInWithPassword` with the normalized email.
10. `code: 'user_already_exists'` → throws `{ code: 'email_already_registered' }` with the exact AC #3 copy. Same for `'email_exists'`.
11. **The `021` server path:** an error with `code: 'unexpected_failure'`, status 500, message `'Database error saving new user'` → throws `email_already_registered`, **and the thrown `message` does not contain the substring `Database error saving new user`** (AC #3's hard negative — assert the absence explicitly, not just the presence of the right copy).
12. Same for a message containing `stylesense_email_conflict`.
13. `code: 'invalid_credentials'` on sign-in → `invalid_credentials` with the generic copy.
14. **AC #7:** an unknown-email failure and a wrong-password failure produce a byte-identical `{ code, message }` — assert the two thrown objects deep-equal each other.
15. `isAuthWeakPasswordError`-shaped error, and `code: 'weak_password'` → `weak_password`.
16. **The Confirm-email defence:** `signUp` resolving `{ data: { user, session: null }, error: null }` → throws `email_confirmation_required` with its explicit message (never resolves, never returns undefined).
17. Network-shaped and 429/`over_request_rate_limit` errors reuse SS-003's existing `network_error` / `rate_limited` codes and copy verbatim.
18. A completely unrecognised error → `unknown` with `UNKNOWN_ERROR_MESSAGE`, and the raw message is **not** passed through.

**`mobile/__tests__/features/auth/components/EmailAuthForm.test.tsx`** (new — the AC-facing behaviour)
19. Renders in `signin` mode by default with an email field, a password field, and a mode-switch control; both fields are findable by distinct accessibility labels (proves edge case 12 is fixed).
20. Switching signup ↔ signin **preserves the typed email and clears the password** (AC #1 + edge case 7).
21. Invalid email → inline `Input` error, and the mutation is **not** called (AC #8).
22. Password under the minimum → inline error, mutation not called.
23. **AC #2:** a successful signup fires `track('register', { method: 'email_password' })` and calls **neither** `router.push` nor `router.replace` — navigation is the layout guard's job.
24. **AC #6:** a successful sign-in fires **no** `register` event and likewise never navigates.
25. **AC #3:** an `email_already_registered` error renders the exact copy **and** a `Sign in instead` control; pressing it switches to signin mode with the email still populated.
26. **AC #10:** `queryByText(/forgot|reset/i)` is null in both modes — the negative assertion that keeps a dead link out.
27. The submit button shows its loading state and cannot be re-pressed while `isPending` (double-submit).
28. A `network_error` and a `rate_limited` error each render SS-003's existing copy.

**`mobile/__tests__/components/ui/Input.test.tsx`** (extend the existing file)
29. `variant="password"` renders a masked field (`secureTextEntry` true) and the show/hide toggle flips it, with the accessibility label changing `Show password` ↔ `Hide password`.
30. `variant="email"` sets `autoCapitalize="none"` and `keyboardType="email-address"` — asserted on the props, since these are the duplicate-prevention mechanism, not styling.
31. Both new variants render the inline `error` string, and the four existing variants' snapshots/behaviour are unchanged.

**Migration — live verification, not a Jest test.** These are the ACs that cannot be faked; they run against local/dev Supabase and their observed output goes in the worklog:

32. **AC #5, the regression this migration risks.** Apply `021`, then create a **phone-only** auth user (NULL email) and confirm a `public.users` row is auto-provisioned with `phone` set and `email NULL`, exactly as before. Run this **before and after** applying `021` and compare. This is a live check because `021` rewrites the trigger every signup path — phone included — runs through.
33. **AC #4.** With an email already present in `public.users`, attempt an `auth.users` insert carrying it; confirm (a) the insert fails, (b) **no** `auth.users` row remains (transaction rolled back), (c) the existing `public.users` row's `email`/`id` are unchanged, (d) no second `public.users` row exists, and (e) the error carries the `stylesense_email_conflict` token server-side.
34. **Record what the *client* actually receives** on a duplicate `signUp` against the live project — the token, or a generic 500 — and confirm the shipped mapping covers whichever it is (the honest unknown above). Adjust the mapping if reality differs; do not leave the assumption unstated.
35. Confirm the live Confirm-email setting's value **before** changing it, set it to off, and record both values (the ticket's explicit instruction — a dashboard setting, not code).
36. Confirm and record the live project's password minimum and whether HIBP leaked-password checking is available (`BL-183`); raise the client constant if the project minimum exceeds 8.
37. Re-run a phone-only signup **after** all of the above to confirm nothing in the sequence regressed it.

**Gates (AC #11):** `tsc --noEmit`, `biome check`, and the **full** jest suite green — no `any`, no test deleted. `login.registry.test.tsx` is rewritten, not weakened; `login.test.tsx`'s assertions are untouched.

## Open questions / blockers

1. **Nothing blocks the Developer from starting.** No external provisioning, no vendor, no DLT. The client work and `021` can both begin immediately. The items below are verifications and one decision, not blockers.
2. **Two deviations from the raw ticket's Description need a reviewer's nod at the PR, not before coding** (both leave every AC satisfied): no `app/(auth)/email-auth.tsx` route (Deviation 1), and the chooser renders phone inline rather than as a menu (Deviation 2). If either is rejected, the fallbacks are stated in-place — and for Deviation 1 the fallback carries a **mandatory** `GUARDED_ROUTES` addition, without which AC #2/#6 silently fail.
3. **The live dashboard values are unread by this pass** — no Bash, no Supabase MCP access here. Three of them must be read and recorded by the Developer: current Confirm-email setting (then set off), password minimum, HIBP availability. Test-plan items 35–36. `BL-183`.
4. **Whether GoTrue propagates the trigger's exception message to the client is unverified** and must be observed live (test-plan 34). The design is deliberately correct under either answer, so this is a verification, not a design fork.
5. **`login.test.tsx`'s transitive `useAnalytics` import** (Deviation 2's boxed task) — must be run first, before other work, because the answer determines whether SS-071's "SS-003's suite passes unmodified" property survives this ticket intact or with one added mock line.
6. **No conflict found between the ACs and CLAUDE.md or the codebase.** The one place they brush against each other is CLAUDE.md's `components/ui/` being a shared design system while SS-071 deliberately avoided touching it (`BL-179`) — resolved in Deviation 3 on the grounds that a masked password field is not optional. That is an additive variant, not a redesign.
7. **AC #7's timing half is unverifiable from this repo** and QA must say so rather than claim it (see the mapping-table note).

## Backlog

Acting only on the rows handed to this pass; no re-scan performed.

- **`BL-169`** (duplicate-email trigger landmine) — **this design resolves it**, via migration `021` plus the client mapping. Deliberately **left Active** until the code exists and the live checks pass: per the SS-071 precedent, the Architect marking it resolved would put a false "done" in cross-ticket memory. QA/DevOps moves it to **Resolved**, referencing SS-072, once test-plan items 33–34 have actually been observed.
- **`BL-173`** (no password reset) — acknowledged, **not resolved**. AC #10 ships the gap knowingly with no dead link; SS-070's admin script is the stated beta mitigation.
- **`BL-174`** (email confirmation off) — acknowledged, **not resolved**. Confirmation stays off; the tradeoff is the ticket's, and this design adds the defensive `session === null` branch it asked for.
- **`BL-172`** (account-linking policy) — forward-compat only, no UI. Explicitly checked for accidental auto-linking (edge case 2): none is reachable, because the trigger only ever inserts keyed on `NEW.id` and this ticket never calls `linkIdentity`. `021` also preserves linkability: no `NOT NULL`, no row merge, `AFTER INSERT` only, so a later authenticated "add an email" `UPDATE` is unobstructed.
- **`BL-178`** (auth redirects drop deep-link destination) — **checked, not fixed.** The email path inherits the identical gap and adds no new instance, precisely because it renders under `/login` (edge case 16).
- **`BL-179`** (no confirm-dialog primitive) — **checked, not needed.** Nothing in signup/sign-in is destructive. This ticket does extend `components/ui/Input.tsx`, which is a different primitive and a different gap.
- **`BL-181`** (sign-out residual persisted-token gap) — unaffected, different code path, confirmed rather than assumed: this ticket touches no sign-out code and `useSignOutMutation` is method-agnostic.
- **`BL-052`, `BL-001`, `BL-171`, `BL-037`, `BL-047`** — unaffected. No `backend/` file is touched (`BL-052`); no SMS is sent (`BL-001`) — indeed email/password exists *because* of `BL-001`; native end-to-end remains unverifiable without an EAS/hosted build (`BL-047`, `BL-171`), so QA must state plainly that the web path was verified and the native path was not.

**New rows logged (starting at `BL-182`):**

| ID | Tag | Row |
|---|---|---|
| `BL-182` | `auth` | `sign_out` analytics hardcodes `method: 'phone_otp'` (`profile.tsx:45`, `analyticsEvents.ts:73`); misreports once email sessions exist. Fix needs `session.user.app_metadata.provider` mapping. Active. |
| `BL-183` | `auth` | Live Supabase password policy (minimum length; HIBP leaked-password availability on this plan) unverified; client ships an 8-char baseline. Active. |
| `BL-184` | `schema` | `public.users.id` has no FK/cascade to `auth.users.id`, so deleting an auth user orphans the row and permanently blocks re-signup with that email/phone. Active. |
| `BL-185` | `schema` | `021` hardens the **email** path only — phone-side symmetry and a case-insensitive functional unique index on `public.users.email` deliberately deferred (AC #5 wanted the phone path provably untouched; the index can fail mid-migration on live rows). Active. |

## Risk classification

`Risk: high` — **confirmed at the level the raw ticket set it. Not lowered, and nothing found argues for lowering it.**

Three independent one-way doors under `docs/OPERATOR_RULEBOOK.md` §C2, any one of which alone would justify the classification:

1. **It is an authentication method that stores credentials.** First password storage in this product, first email-bearing signup path, and a live account-enumeration surface (AC #7) whose failure mode is silent — a copy or code divergence between "unknown email" and "wrong password" leaks account existence without anything breaking visibly.
2. **Migration `021` rewrites a `SECURITY DEFINER` trigger on `auth.users` inserts** — a function that can abort the signup transaction of *every* auth method. The ground-check makes this concrete rather than theoretical: the phone path shares the exact same function body, which is why AC #5 demands a live before/after check rather than an inspection, and why the phone-symmetry hardening is deliberately deferred rather than bundled.
3. **It is external-facing and irreversible in effect.** Accounts created under Confirm-email-off cannot be retroactively verified, and with no password reset (`BL-173`) and no FK cascade (`BL-184`), a mistyped address produces an account whose email is claimed permanently and recoverable only by an operator with the admin script.

The ground-check also surfaced two failure modes the ticket did not anticipate — a second entry point silently escaping SS-071's route guard (Deviation 1) and a shipped test breaking the moment a second method registers (Deviation 2) — which is itself evidence that this ticket's blast radius reaches further than its own diff.

**Verdict:** `Risk: high` (confirmed) — full lane, every human gate preserved.
