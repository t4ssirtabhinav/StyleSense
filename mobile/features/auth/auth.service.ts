import { type Session, isAuthWeakPasswordError } from '@supabase/supabase-js';
import * as Linking from 'expo-linking';
import { Platform } from 'react-native';
import { supabase } from '../../lib/supabase';
import type {
  AuthError,
  AuthErrorCode,
  EmailSignUpResult,
  FieldValidationResult,
  PhoneValidationResult,
  PlanTier,
} from './auth.types';

// The only place `supabase.auth.*` / `supabase.from('users')` is called from
// for this domain (besides the session-listener wiring in
// `hooks/useAuth.ts`), per CLAUDE.md's "no direct Supabase calls outside
// features/<domain>/*.queries.ts" rule extended to this service layer that
// backs `auth.queries.ts`.

const INDIA_COUNTRY_CODE = '+91';

const NETWORK_ERROR_MESSAGE =
  'No internet connection. Please check your network and try again.';
const RATE_LIMITED_MESSAGE =
  'Too many attempts. Please wait a moment before trying again.';
// Supabase does not distinguish "wrong OTP" from "expired OTP" in its error
// response (both surface as the same generic AuthApiError) — see
// docs/tickets/SS-003-design.md's Edge Cases. A single generic copy is used
// for both rather than inventing a client-side heuristic Supabase's API
// doesn't actually support.
const GENERIC_OTP_ERROR_MESSAGE =
  'Incorrect or expired OTP. Please try again or resend.';
const UNKNOWN_ERROR_MESSAGE = 'Something went wrong. Please try again.';

export function validateIndianMobile(digits: string): PhoneValidationResult {
  if (digits.length !== 10) {
    return {
      valid: false,
      message: 'Please enter a valid 10-digit mobile number.',
    };
  }
  if (digits[0] === '0' || digits[0] === '2') {
    return {
      valid: false,
      message: 'Please enter a mobile number, not a landline number.',
    };
  }
  if (!/^[6-9]\d{9}$/.test(digits)) {
    return {
      valid: false,
      message: 'Mobile numbers start with 6, 7, 8, or 9.',
    };
  }
  return { valid: true };
}

function isNetworkFailure(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return /network|fetch|internet|offline/i.test(message);
}

function isRateLimited(error: unknown): boolean {
  const status = (error as { status?: number } | null | undefined)?.status;
  const code = (error as { code?: string } | null | undefined)?.code;
  const message = error instanceof Error ? error.message : String(error);
  // SS-072: extended (not duplicated) to also match the two rate-limit
  // codes @supabase/auth-js's error-codes union carries for the email
  // signup/signin path — sendOtp/verifyOtp's existing status/message checks
  // above are untouched, so this is additive for every existing caller too.
  return (
    status === 429 ||
    code === 'over_request_rate_limit' ||
    code === 'over_email_send_rate_limit' ||
    /rate limit|too many/i.test(message)
  );
}

// Not confirmed against a live send (BL-001) — best-effort mapping of
// Supabase's documented error shapes to this domain's typed AuthError.
function toAuthError(error: unknown, fallbackCode: AuthErrorCode): AuthError {
  if (isNetworkFailure(error)) {
    return { code: 'network_error', message: NETWORK_ERROR_MESSAGE };
  }
  if (isRateLimited(error)) {
    return { code: 'rate_limited', message: RATE_LIMITED_MESSAGE };
  }
  if (fallbackCode === 'invalid_or_expired_otp') {
    return {
      code: 'invalid_or_expired_otp',
      message: GENERIC_OTP_ERROR_MESSAGE,
    };
  }
  return { code: fallbackCode, message: UNKNOWN_ERROR_MESSAGE };
}

export async function sendOtp(phoneDigits: string): Promise<void> {
  try {
    const { error } = await supabase.auth.signInWithOtp({
      phone: INDIA_COUNTRY_CODE + phoneDigits,
    });
    if (error) {
      throw error;
    }
  } catch (error) {
    throw toAuthError(error, 'unknown');
  }
}

export async function verifyOtp(
  phoneDigits: string,
  token: string,
): Promise<Session> {
  let session: Session | null;
  try {
    const { data, error } = await supabase.auth.verifyOtp({
      phone: INDIA_COUNTRY_CODE + phoneDigits,
      token,
      type: 'sms',
    });
    if (error) {
      throw error;
    }
    session = data.session;
  } catch (error) {
    throw toAuthError(error, 'invalid_or_expired_otp');
  }

  if (!session) {
    // A success response with a null session is treated as an `unknown`
    // AuthError, not a silent pass-through (docs/tickets/SS-003-design.md's
    // "Concrete values" section).
    throw toAuthError(
      new Error('verifyOtp resolved with a null session'),
      'unknown',
    );
  }

  return session;
}

// ---------------------------------------------------------------------
// SS-072 — Email/Password Sign-Up & Sign-In.
// docs/tickets/SS-072-design.md's "Service layer (auth.service.ts)" and
// "Error-code mapping table" sections — this block implements both
// verbatim; extend the table and this code together, never diverge them.
// ---------------------------------------------------------------------

const MIN_PASSWORD_LENGTH = 8;
const PASSWORD_TOO_SHORT_MESSAGE = `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
const INVALID_EMAIL_MESSAGE = 'Please enter a valid email address.';
const EMAIL_ALREADY_REGISTERED_MESSAGE =
  'This email is already registered — sign in instead.';
const INVALID_CREDENTIALS_MESSAGE = 'Incorrect email or password.';
const WEAK_PASSWORD_MESSAGE =
  'Please choose a stronger password (at least 8 characters).';
// SS-072 REVISION 2: this is no longer an error message shown to the user —
// signUpWithEmail's null-session branch is now a SUCCESS (see
// EmailSignUpResult in auth.types.ts). This constant survives only as the
// internal `message` on the `email_confirmation_required` AuthError that
// signInWithEmail's mapping still produces for AC #14 (signing in before
// confirming) — EmailAuthForm intercepts that code and renders
// CheckYourEmailNotice instead of ever displaying this string as a bare
// error. Never render this value directly.
const EMAIL_CONFIRMATION_REQUIRED_MESSAGE = 'Email not confirmed yet.';

const EMAIL_SHAPE_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Migration 021's deterministic token — see
// supabase/migrations/021_harden_handle_new_auth_user_email_conflict.sql.
const TRIGGER_CONFLICT_TOKEN_RE = /stylesense_email_conflict/i;
// [VERIFIED LIVE 2026-08-17 against the shared project — see
// docs/worklog/SS-072.md's Developer entry] A natural Postgres
// unique_violation raised from deep inside handle_new_auth_user (the exact
// SECURITY DEFINER AFTER INSERT trigger 021 rewrites) was observed to
// surface to the client only as a generic wrapped 500, worded "Database
// error CREATING new user" via the Admin API's create_user path — not
// "saving" as the raw ticket/BL-169 assumed. Matches both deliberately,
// since the wording may differ between the Admin API and the public
// /signup endpoint (unverified which the latter uses).
const GENERIC_TRIGGER_500_RE = /database error (saving|creating) new user/i;

export function normalizeEmail(raw: string): string {
  return raw.trim().toLowerCase();
}

export function validateEmail(email: string): FieldValidationResult {
  const normalized = normalizeEmail(email);
  if (!normalized || !EMAIL_SHAPE_RE.test(normalized)) {
    return { valid: false, message: INVALID_EMAIL_MESSAGE };
  }
  return { valid: true };
}

export function validatePassword(password: string): FieldValidationResult {
  // Passwords are never trimmed (docs/tickets/SS-072-design.md's Password
  // policy section) — a password of 8 spaces is a valid password.
  if (password.length < MIN_PASSWORD_LENGTH) {
    return { valid: false, message: PASSWORD_TOO_SHORT_MESSAGE };
  }
  return { valid: true };
}

function errorCode(error: unknown): string | undefined {
  return (error as { code?: string } | null | undefined)?.code;
}

function errorStatus(error: unknown): number | undefined {
  return (error as { status?: number } | null | undefined)?.status;
}

function errorMessageOf(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  // GoTrue's real errors are always Error instances (AuthApiError extends
  // Error), but this also reads a plain `{ message }` shape defensively —
  // deliberately more permissive than isNetworkFailure/isRateLimited above
  // (untouched, existing behaviour), since this helper's only job is
  // matching the 021 trigger's message content, not classifying an error.
  const message = (error as { message?: string } | null | undefined)?.message;
  return message ?? String(error);
}

// Branches on `error.code` per the installed SDK's own guidance
// (GoTrueClient.d.ts) — never on `error.message` — with exactly one
// documented exception: the generic-500 fallback below, which exists only
// because a trigger-raised failure has no other channel to identify itself
// through (see the design doc's "honest unknown about 021's client-visible
// error").
function toEmailAuthError(
  error: unknown,
  mode: 'signup' | 'signin',
): AuthError {
  if (isNetworkFailure(error)) {
    return { code: 'network_error', message: NETWORK_ERROR_MESSAGE };
  }
  if (isRateLimited(error)) {
    return { code: 'rate_limited', message: RATE_LIMITED_MESSAGE };
  }

  const code = errorCode(error);
  const status = errorStatus(error);
  const message = errorMessageOf(error);

  if (code === 'user_already_exists' || code === 'email_exists') {
    return {
      code: 'email_already_registered',
      message: EMAIL_ALREADY_REGISTERED_MESSAGE,
    };
  }

  if (
    mode === 'signup' &&
    (code === 'unexpected_failure' || status === 500) &&
    (TRIGGER_CONFLICT_TOKEN_RE.test(message) ||
      GENERIC_TRIGGER_500_RE.test(message))
  ) {
    return {
      code: 'email_already_registered',
      message: EMAIL_ALREADY_REGISTERED_MESSAGE,
    };
  }

  if (code === 'weak_password' || isAuthWeakPasswordError(error)) {
    return { code: 'weak_password', message: WEAK_PASSWORD_MESSAGE };
  }

  if (code === 'email_not_confirmed') {
    return {
      code: 'email_confirmation_required',
      message: EMAIL_CONFIRMATION_REQUIRED_MESSAGE,
    };
  }

  if (code === 'email_address_invalid' || code === 'validation_failed') {
    return { code: 'unknown', message: INVALID_EMAIL_MESSAGE };
  }

  if (mode === 'signin') {
    // AC #7 (no account enumeration): `invalid_credentials` and every
    // OTHER unmapped sign-in failure share this exact { code, message } —
    // a copy/code divergence between "unknown email" and "wrong password"
    // is not expressible because both fall through to this one branch.
    return {
      code: 'invalid_credentials',
      message: INVALID_CREDENTIALS_MESSAGE,
    };
  }

  return { code: 'unknown', message: UNKNOWN_ERROR_MESSAGE };
}

export async function signUpWithEmail(
  email: string,
  password: string,
): Promise<EmailSignUpResult> {
  const normalizedEmail = normalizeEmail(email);
  try {
    const { data, error } = await supabase.auth.signUp({
      email: normalizedEmail,
      password,
      // SS-073 — points the confirmation email's {{ .RedirectTo }} template
      // variable at this app's /confirm route (web origin or native
      // scheme). See getConfirmationRedirectUrl's own comment for why this
      // must also be on the Supabase Redirect URLs allow-list to take
      // effect, and BL-171 for why the web value is a dev-only localhost
      // origin today.
      options: { emailRedirectTo: getConfirmationRedirectUrl() },
    });
    if (error) {
      throw error;
    }

    if (!data.session) {
      // SS-072 REVISION 2: Confirm-email is ON, live-confirmed — this is
      // the PRIMARY path for 100% of signups today, not a defensive
      // fallback. A null session here means the account was created
      // successfully and a confirmation email is on its way; it is a
      // SUCCESS, never a throw. See docs/tickets/SS-072-design.md's
      // REVISION 2, "The revised flow". `normalizedEmail` (not the raw
      // typed string) is what was actually sent to GoTrue and is what
      // resendConfirmationEmail must be called with.
      return { status: 'confirmation_required', email: normalizedEmail };
    }

    // Kept but currently unreachable while Confirm-email stays ON — the
    // exact inverse of what shipped in the first pass. If Confirm-email is
    // ever turned off, this arm already works with no further edit.
    return { status: 'session', session: data.session };
  } catch (error) {
    throw toEmailAuthError(error, 'signup');
  }
}

// SS-072 REVISION 2 (AC #12) — backs CheckYourEmailNotice's Resend control.
// `type: 'signup'` is the correct member for a pending email confirmation
// (@supabase/auth-js's ResendParams restricts the email arm to
// Extract<EmailOtpType, 'signup' | 'email_change'>). Deliberately no
// `options.emailRedirectTo` — see docs/tickets/SS-072-design.md's REVISION
// 2, "Concrete values to use, not invent" for why (an out-of-allow-list
// redirect silently falls back to SITE_URL; that belongs with the
// split-out SS-073 work). Reuses toEmailAuthError('signup') so
// over_email_send_rate_limit/over_request_rate_limit map to the existing
// RATE_LIMITED_MESSAGE — no new copy for that case (AC #12).
export async function resendConfirmationEmail(email: string): Promise<void> {
  try {
    const { error } = await supabase.auth.resend({
      type: 'signup',
      email: normalizeEmail(email),
      // SS-073 — same reasoning as signUpWithEmail above; a resend must
      // point at /confirm too, not fall back to whatever SITE_URL is.
      options: { emailRedirectTo: getConfirmationRedirectUrl() },
    });
    if (error) throw error;
  } catch (error) {
    throw toEmailAuthError(error, 'signup');
  }
}

export async function signInWithEmail(
  email: string,
  password: string,
): Promise<Session> {
  const normalizedEmail = normalizeEmail(email);
  let session: Session | null;
  try {
    const { data, error } = await supabase.auth.signInWithPassword({
      email: normalizedEmail,
      password,
    });
    if (error) {
      throw error;
    }
    session = data.session;
  } catch (error) {
    throw toEmailAuthError(error, 'signin');
  }

  if (!session) {
    // No documented case produces this (unlike signUp's Confirm-email
    // branch above), but the same defensive-branch discipline applies —
    // never a silent pass-through of a falsy session.
    throw {
      code: 'unknown',
      message: UNKNOWN_ERROR_MESSAGE,
    } satisfies AuthError;
  }

  return session;
}

// SS-004 renames checkUserProfileExists -> checkOnboardingCompleted: once
// 002_onboarding_completed.sql's auto-provisioning trigger ships, a
// public.users row exists for every authenticated user immediately, which
// would make a row-existence check return true for every user, always —
// silently breaking the "first login vs. returning" distinction it was
// built for. Checking the actual onboarding_completed flag instead is what
// makes that distinction meaningful again.
export async function checkOnboardingCompleted(
  userId: string,
): Promise<boolean> {
  try {
    const { data } = await supabase
      .from('users')
      .select('onboarding_completed')
      .eq('id', userId)
      .maybeSingle();
    return data?.onboarding_completed ?? false;
  } catch {
    // A failed onboarding-completed check should not crash the
    // just-completed OTP verify flow — fail safe to "not completed" (routes
    // to /onboarding), the same outcome a genuinely first-time user gets.
    return false;
  }
}

// SS-009: feeds hooks/useAuth.ts's Sentry `plan_tier` error-context tagging.
// Same fail-safe-to-null shape as checkOnboardingCompleted above — a failed
// plan_tier lookup (network blip, RLS edge case) must not crash the auth
// flow; setSentryUserContext simply skips the plan_tier tag on a null.
export async function fetchUserPlanTier(
  userId: string,
): Promise<PlanTier | null> {
  try {
    const { data } = await supabase
      .from('users')
      .select('plan_tier')
      .eq('id', userId)
      .maybeSingle();
    return data?.plan_tier ?? null;
  } catch {
    return null;
  }
}

// SS-071 — `{ scope: 'local' }` is deliberate, not the SDK's default.
// [VERIFIED 2026-08-15 against installed @supabase/auth-js@2.108.2's own
// source, node_modules/@supabase/auth-js/dist/module/GoTrueClient.js:3316]
// `signOut()` defaults to `scope: 'global'`, which signs the user out of
// EVERY device they're currently signed in on — the SDK's own doc comment
// carries an explicit warning to that effect and recommends `'local'` for
// exactly this "Sign Out" button case. Leaving the default would silently
// kill the user's other devices on a single-device sign-out tap.
//
// Verified failure-path finding (read from the same file's `_signOut`,
// lines 3326-3352): if the network revoke call
// (`this.admin.signOut(accessToken, scope)`) fails with an error that is
// NOT a 404/401/403/session-missing (i.e. a genuine network failure or a
// 5xx, which the SDK wraps as AuthRetryableFetchError per
// node_modules/@supabase/auth-js/dist/module/lib/fetch.js:22-32/114), the
// SDK returns early WITHOUT calling `_removeSession()` — so on that branch
// specifically, the SDK's own call does NOT clear the persisted
// SecureStore/localStorage session and does NOT emit SIGNED_OUT. This
// function still resolves (never rejects) either way, per its own
// contract below; auth.queries.ts's useSignOutMutation additionally sets
// useAuthStore's session to null directly in its `finally`, defensively,
// specifically to cover this branch — see that file's comment. (A
// residual gap this ticket does not close: the persisted token itself can
// still be present in storage after a genuine network failure, until it
// next expires/refreshes — see docs/worklog/SS-071.md and the BL-181 entry
// this finding produced.)
export async function signOut(): Promise<void> {
  try {
    const { error } = await supabase.auth.signOut({ scope: 'local' });
    if (error) {
      // Do not rethrow — the mutation's local-state clear must proceed
      // regardless of whether the network revoke succeeded (AC #7).
    }
  } catch {
    // Network/unknown failure calling signOut() itself — same contract:
    // resolve, never reject.
  }
}

// ---------------------------------------------------------------------
// SS-073 — Email Confirmation-Link Landing Screen & Auto-Sign-In.
// docs/tickets/SS-073-design.md's "Concrete values to use, not invent"
// section — this block implements it verbatim.
// ---------------------------------------------------------------------

// [VERIFIED 2026-08-18 against Supabase's current Auth documentation —
// docs.supabase.com/docs/guides/auth/auth-email-templates (the {{
// .TokenHash }}/{{ .RedirectTo }} variable table) and
// docs.supabase.com/docs/guides/auth/passwords (a live worked example).
// The design doc flagged this string as trained-knowledge/unverified;
// checked here before use, per the design doc's Open Question #1.]
//
// Confirmed: `{{ .TokenHash }}` is documented as "useful for constructing
// your own email link", and `{{ .RedirectTo }}` is documented as "the
// redirect URL passed when signUp ... is called" (i.e.
// getConfirmationRedirectUrl()'s own output) — so
// `{{ .RedirectTo }}?token_hash={{ .TokenHash }}&type=email` is a correct
// use of both variables for this app's architecture, where /confirm itself
// (not a separate server route) performs the client-side verifyOtp
// exchange. Note for the record: the docs' own worked example for a
// Next.js app uses a different base pattern —
// `{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=email&next={{ .RedirectTo }}`
// — because that architecture's /auth/confirm is a fixed SERVER route
// that does its own subsequent redirect to `next`. This app has no such
// server route; `emailRedirectTo` (-> `{{ .RedirectTo }}`) already points
// directly at this app's /confirm screen, which handles both the exchange
// and (via the guard) the subsequent hand-off itself, so no separate
// `next` parameter is needed here. The exact template body applied is
// recorded verbatim in docs/worklog/SS-073.md per AC #9.
//
// Template body actually applied in the Supabase dashboard:
//   {{ .RedirectTo }}?token_hash={{ .TokenHash }}&type=email

// SS-073 — distinct name is load-bearing: `verifyOtp` (above) already
// exists for the SMS path (`type: 'sms'`); this is the email-confirmation
// path (`type: 'email'`), a different call shape and a different error
// mapping (toConfirmationLinkError, not toAuthError/toEmailAuthError).
export async function confirmEmailToken(tokenHash: string): Promise<Session> {
  let session: Session | null;
  try {
    const { data, error } = await supabase.auth.verifyOtp({
      token_hash: tokenHash,
      // NOT 'signup' — deprecated per the installed SDK's own doc comment
      // (SS-072's Architect pass already verified this; carried forward,
      // not re-verified independently this pass).
      type: 'email',
    });
    if (error) throw error;
    session = data.session;
  } catch (error) {
    throw toConfirmationLinkError(error);
  }
  if (!session) {
    // Defensive-branch discipline, matching the existing SMS verifyOtp's
    // null-session handling above.
    throw toConfirmationLinkError(
      new Error('verifyOtp resolved with a null session'),
    );
  }
  return session;
}

// Web-only fallback for Supabase's DEFAULT confirmation template (implicit
// tokens delivered in the URL fragment rather than a token_hash query
// param) — inert (resolves null, never throws) on native, so confirm.tsx
// can call it unconditionally behind a Platform.OS check without a second
// code path. Never calls the SDK's private _getSessionFromURL (confirmed
// unusable outside a browser by SS-072's Architect pass — throws 'No
// browser detected.' per GoTrueClient.js:3164-3211).
export async function adoptSessionFromUrlFragment(): Promise<Session | null> {
  if (Platform.OS !== 'web' || typeof window === 'undefined') {
    return null;
  }
  const hash = new URLSearchParams(window.location.hash.replace(/^#/, ''));
  const access_token = hash.get('access_token');
  const refresh_token = hash.get('refresh_token');
  if (!access_token || !refresh_token) {
    return null;
  }
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
// e.g. weak_password or email_already_registered codes that don't apply
// here.
function toConfirmationLinkError(error: unknown): AuthError {
  if (isNetworkFailure(error)) {
    return { code: 'network_error', message: NETWORK_ERROR_MESSAGE };
  }
  return {
    code: 'invalid_or_expired_confirmation_link',
    message:
      'This link may have expired or already been used. Your account may already be confirmed — try signing in.',
  };
}

// Feeds `emailRedirectTo` on both signUpWithEmail's and
// resendConfirmationEmail's call sites above, so a confirmation email's
// {{ .RedirectTo }} template variable points at this app's own /confirm
// route rather than falling back to SITE_URL (which is not owned by
// /confirm — see docs/tickets/SS-073-design.md's "Redirect URL not
// configured" edge case).
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
