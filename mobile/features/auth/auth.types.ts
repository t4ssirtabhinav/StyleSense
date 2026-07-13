// Domain types for SS-003 (Phone OTP Authentication Flow). Per
// docs/tickets/SS-003-design.md's "Files to create/modify" #1.

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
