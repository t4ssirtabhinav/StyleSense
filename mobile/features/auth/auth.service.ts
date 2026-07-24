import type { Session } from '@supabase/supabase-js';
import { supabase } from '../../lib/supabase';
import type {
  AuthError,
  AuthErrorCode,
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
  const message = error instanceof Error ? error.message : String(error);
  return status === 429 || /rate limit|too many/i.test(message);
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
