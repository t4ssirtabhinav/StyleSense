// Domain types for SS-003 (Phone OTP Authentication Flow). Per
// docs/tickets/SS-003-design.md's "Files to create/modify" #1.

import type { Session } from '@supabase/supabase-js';
import type { Database } from '../../types/supabase';

// SS-009: reused for Sentry error-context tagging (setSentryUserContext)
// after auth — sourced from the generated enum, never hand-typed.
export type PlanTier = Database['public']['Enums']['plan_tier'];

export type AuthErrorCode =
  | 'invalid_phone'
  | 'network_error'
  | 'rate_limited'
  | 'invalid_or_expired_otp'
  | 'unknown'
  // SS-072 — additive only, per docs/tickets/SS-072-design.md's "Files to
  // create/modify" (AuthError's shape itself is frozen: { code, message }).
  | 'email_already_registered'
  | 'invalid_credentials'
  | 'weak_password'
  | 'email_confirmation_required'
  // SS-073 — additive only. Deliberately distinct from
  // 'email_confirmation_required' (already taken by SS-072's sign-in-side
  // mapping for "you haven't confirmed yet") — this one covers a
  // confirmation LINK itself being expired/already-used/malformed, a
  // different failure than "you tried to sign in before confirming".
  | 'invalid_or_expired_confirmation_link';

export interface AuthError {
  code: AuthErrorCode;
  message: string;
}

// SS-072: renamed generic name for the same shape SS-003's
// validateIndianMobile already returns — `PhoneValidationResult` is kept as
// an alias so every existing caller/import of that name keeps working
// unmodified, while validateEmail/validatePassword share the vocabulary
// instead of inventing a second, drift-prone result shape.
export type FieldValidationResult =
  | { valid: true }
  | { valid: false; message: string };

export type PhoneValidationResult = FieldValidationResult;

// SS-072 REVISION 2 — signUpWithEmail's return contract. A `session: null`
// response from supabase.auth.signUp() is a SUCCESS with Confirm-email ON
// (the primary path for every signup today, not a defensive fallback) — see
// docs/tickets/SS-072-design.md's REVISION 2, "The revised flow". The
// `'session'` arm is kept, currently unreachable, so a future Confirm-email
// flip needs no code change here. signInWithEmail is unaffected — it still
// returns Promise<Session> and still throws on a null session.
export type EmailSignUpResult =
  | { status: 'session'; session: Session }
  | { status: 'confirmation_required'; email: string };
