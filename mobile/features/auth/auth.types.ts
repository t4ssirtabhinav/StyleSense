// Domain types for SS-003 (Phone OTP Authentication Flow). Per
// docs/tickets/SS-003-design.md's "Files to create/modify" #1.

import type { Database } from '../../types/supabase';

// SS-009: reused for Sentry error-context tagging (setSentryUserContext)
// after auth — sourced from the generated enum, never hand-typed.
export type PlanTier = Database['public']['Enums']['plan_tier'];

export type AuthErrorCode =
  | 'invalid_phone'
  | 'network_error'
  | 'rate_limited'
  | 'invalid_or_expired_otp'
  | 'unknown';

export interface AuthError {
  code: AuthErrorCode;
  message: string;
}

export type PhoneValidationResult =
  | { valid: true }
  | { valid: false; message: string };
