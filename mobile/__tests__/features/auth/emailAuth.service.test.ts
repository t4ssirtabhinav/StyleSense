import { AuthWeakPasswordError } from '@supabase/supabase-js';
import { Platform } from 'react-native';
import {
  adoptSessionFromUrlFragment,
  confirmEmailToken,
  resendConfirmationEmail,
  signInWithEmail,
  signUpWithEmail,
} from '../../../features/auth/auth.service';
import type { AuthError } from '../../../features/auth/auth.types';

const mockSignUp = jest.fn();
const mockSignInWithPassword = jest.fn();
const mockResend = jest.fn();
const mockVerifyOtp = jest.fn();
const mockSetSession = jest.fn();

// Same deferred-wrapper reasoning as auth.service.test.ts: jest.mock()
// factories are hoisted above this file's own top-level const
// declarations.
jest.mock('../../../lib/supabase', () => ({
  supabase: {
    auth: {
      signUp: (arg: unknown) => mockSignUp(arg),
      signInWithPassword: (arg: unknown) => mockSignInWithPassword(arg),
      resend: (arg: unknown) => mockResend(arg),
      verifyOtp: (arg: unknown) => mockVerifyOtp(arg),
      setSession: (arg: unknown) => mockSetSession(arg),
    },
  },
}));

// SS-073 — deterministic native-scheme output, independent of app.json's
// real scheme resolution (which under jest depends on expo-constants'
// mocked config and isn't this test's concern).
jest.mock('expo-linking', () => ({
  createURL: (path: string) => `stylesense://${path}`,
}));

const FAKE_SESSION = { access_token: 'tok', user: { id: 'u1' } } as never;
const ORIGINAL_PLATFORM_OS = Platform.OS;

beforeEach(() => {
  jest.clearAllMocks();
  Platform.OS = ORIGINAL_PLATFORM_OS;
  // test-only global, reset between tests.
  (global as { window?: unknown }).window = undefined;
});

afterEach(() => {
  Platform.OS = ORIGINAL_PLATFORM_OS;
  (global as { window?: unknown }).window = undefined;
});

// docs/tickets/SS-072-design.md's Test plan #8-18 (the mapping table, one
// test per row) + the two service-level call-shape assertions.

describe('signUpWithEmail', () => {
  it('calls supabase.auth.signUp with the normalized email and the raw password', async () => {
    mockSignUp.mockResolvedValue({
      data: { user: { id: 'u1' }, session: FAKE_SESSION },
      error: null,
    });

    await signUpWithEmail('  User@X.com ', 'raw-Password-Not-Trimmed ');

    expect(mockSignUp).toHaveBeenCalledWith({
      email: 'user@x.com',
      password: 'raw-Password-Not-Trimmed ',
      options: { emailRedirectTo: 'stylesense://confirm' },
    });
  });

  // SS-073 Test plan #8 — regression guard so a future edit can't silently
  // drop emailRedirectTo from either SS-072 call site.
  it("SS-073: calls supabase.auth.signUp with options.emailRedirectTo equal to getConfirmationRedirectUrl()'s output", async () => {
    mockSignUp.mockResolvedValue({
      data: { user: { id: 'u1' }, session: null },
      error: null,
    });

    await signUpWithEmail('user@x.com', 'password123');

    const call = mockSignUp.mock.calls[0][0] as {
      options?: { emailRedirectTo?: string };
    };
    expect(call.options?.emailRedirectTo).toBe('stylesense://confirm');
  });

  // R2 — kept but currently unreachable while Confirm-email stays ON; the
  // exact inverse of what shipped before this revision.
  it('R2: resolves { status: "session", session } when signUp returns a real session', async () => {
    mockSignUp.mockResolvedValue({
      data: { user: { id: 'u1' }, session: FAKE_SESSION },
      error: null,
    });

    await expect(signUpWithEmail('user@x.com', 'password123')).resolves.toEqual(
      { status: 'session', session: FAKE_SESSION },
    );
  });

  it('code "user_already_exists" -> email_already_registered with the exact AC #3 copy', async () => {
    mockSignUp.mockRejectedValue({
      code: 'user_already_exists',
      status: 422,
      message: 'User already registered',
    });

    await expect(signUpWithEmail('user@x.com', 'password123')).rejects.toEqual({
      code: 'email_already_registered',
      message: 'This email is already registered — sign in instead.',
    });
  });

  it('code "email_exists" -> email_already_registered with the exact AC #3 copy', async () => {
    mockSignUp.mockRejectedValue({
      code: 'email_exists',
      status: 422,
      message: 'Email address already registered',
    });

    await expect(signUpWithEmail('user@x.com', 'password123')).rejects.toEqual({
      code: 'email_already_registered',
      message: 'This email is already registered — sign in instead.',
    });
  });

  it('the 021 server path (generic "Database error saving new user" 500) -> email_already_registered, and the raw string never reaches the thrown message', async () => {
    mockSignUp.mockRejectedValue({
      code: 'unexpected_failure',
      status: 500,
      message: 'Database error saving new user',
    });

    let thrown: unknown;
    try {
      await signUpWithEmail('user@x.com', 'password123');
    } catch (error) {
      thrown = error;
    }

    expect(thrown).toEqual({
      code: 'email_already_registered',
      message: 'This email is already registered — sign in instead.',
    });
    expect((thrown as { message: string }).message).not.toContain(
      'Database error saving new user',
    );
  });

  it('the generic 500 fallback also matches "Database error creating new user" (the live-verified wording)', async () => {
    mockSignUp.mockRejectedValue({
      code: 'unexpected_failure',
      status: 500,
      message: 'Database error creating new user',
    });

    await expect(signUpWithEmail('user@x.com', 'password123')).rejects.toEqual({
      code: 'email_already_registered',
      message: 'This email is already registered — sign in instead.',
    });
  });

  it('a message containing the stylesense_email_conflict token -> email_already_registered', async () => {
    mockSignUp.mockRejectedValue({
      code: 'unexpected_failure',
      status: 500,
      message: 'stylesense_email_conflict',
    });

    await expect(signUpWithEmail('user@x.com', 'password123')).rejects.toEqual({
      code: 'email_already_registered',
      message: 'This email is already registered — sign in instead.',
    });
  });

  it('code "weak_password" -> weak_password with the exact copy', async () => {
    mockSignUp.mockRejectedValue({
      code: 'weak_password',
      status: 422,
      message: 'Password is too weak',
    });

    await expect(signUpWithEmail('user@x.com', 'short')).rejects.toEqual({
      code: 'weak_password',
      message: 'Please choose a stronger password (at least 8 characters).',
    });
  });

  it('an isAuthWeakPasswordError-shaped error -> weak_password with the exact copy', async () => {
    mockSignUp.mockRejectedValue(
      new AuthWeakPasswordError('Password too weak', 422, ['length']),
    );

    await expect(signUpWithEmail('user@x.com', 'short')).rejects.toEqual({
      code: 'weak_password',
      message: 'Please choose a stronger password (at least 8 characters).',
    });
  });

  // R1 (REVISION 2, replaces the pre-revision "Confirm-email defence"
  // test above) — a null session is now the PRIMARY path for every
  // signup, and it is a SUCCESS, not a throw.
  it('R1: signUp resolving { session: null, error: null } resolves { status: "confirmation_required", email } — does NOT throw', async () => {
    mockSignUp.mockResolvedValue({
      data: { user: { id: 'u1' }, session: null },
      error: null,
    });

    await expect(signUpWithEmail('user@x.com', 'password123')).resolves.toEqual(
      {
        status: 'confirmation_required',
        email: 'user@x.com',
      },
    );
  });

  it('R1: the confirmation_required email is normalized even when the input had mixed case and surrounding whitespace', async () => {
    mockSignUp.mockResolvedValue({
      data: { user: { id: 'u1' }, session: null },
      error: null,
    });

    await expect(
      signUpWithEmail('  User@X.com ', 'password123'),
    ).resolves.toEqual({
      status: 'confirmation_required',
      email: 'user@x.com',
    });
  });

  it('network-shaped error reuses the existing network_error code and copy verbatim', async () => {
    mockSignUp.mockRejectedValue(new Error('Network request failed'));

    await expect(signUpWithEmail('user@x.com', 'password123')).rejects.toEqual({
      code: 'network_error',
      message:
        'No internet connection. Please check your network and try again.',
    });
  });

  it('a 429 / over_request_rate_limit error reuses the existing rate_limited code and copy verbatim', async () => {
    mockSignUp.mockRejectedValue({
      code: 'over_request_rate_limit',
      status: 429,
      message: 'Too many requests',
    });

    await expect(signUpWithEmail('user@x.com', 'password123')).rejects.toEqual({
      code: 'rate_limited',
      message: 'Too many attempts. Please wait a moment before trying again.',
    });
  });

  it('a completely unrecognised error on signup -> unknown, and the raw message is not passed through', async () => {
    mockSignUp.mockRejectedValue({
      code: 'some_new_unmapped_code',
      status: 400,
      message: 'a very specific internal detail nobody should see',
    });

    let thrown: unknown;
    try {
      await signUpWithEmail('user@x.com', 'password123');
    } catch (error) {
      thrown = error;
    }

    expect(thrown).toEqual({
      code: 'unknown',
      message: 'Something went wrong. Please try again.',
    });
    expect((thrown as { message: string }).message).not.toContain(
      'a very specific internal detail nobody should see',
    );
  });
});

describe('resendConfirmationEmail', () => {
  // R3 — SS-073 REVISION: resend now DOES carry options.emailRedirectTo
  // (added by this ticket, see auth.service.ts's SS-073 block below); the
  // pre-SS-073 "no options" assertion is intentionally replaced, not
  // weakened — the type/email shape it pinned is still asserted exactly.
  it('R3 (SS-073 revision): calls supabase.auth.resend with { type: "signup", email: <normalized>, options: { emailRedirectTo } }', async () => {
    mockResend.mockResolvedValue({ error: null });

    await resendConfirmationEmail('  User@X.com ');

    expect(mockResend).toHaveBeenCalledWith({
      type: 'signup',
      email: 'user@x.com',
      options: { emailRedirectTo: 'stylesense://confirm' },
    });
    expect(mockResend).toHaveBeenCalledTimes(1);
  });

  // R4 — asserted by identity with the OTP/signup rate-limited path's
  // message, not by a copied literal: both paths go through the same
  // toEmailAuthError('signup') mapping, so their thrown messages must be
  // the exact same string reference-equal value, not two independently
  // typed-out copies that could silently drift apart.
  it("R4: a resend rejected with over_email_send_rate_limit throws rate_limited, with the message identical to the signup path's rate-limited message", async () => {
    mockSignUp.mockRejectedValueOnce({
      code: 'over_request_rate_limit',
      status: 429,
      message: 'Too many requests',
    });
    let signUpRateLimited: AuthError | undefined;
    try {
      await signUpWithEmail('user@x.com', 'password123');
    } catch (error) {
      signUpRateLimited = error as AuthError;
    }

    mockResend.mockRejectedValueOnce({
      code: 'over_email_send_rate_limit',
      status: 429,
      message: 'Email rate limit exceeded',
    });
    let resendRateLimited: AuthError | undefined;
    try {
      await resendConfirmationEmail('user@x.com');
    } catch (error) {
      resendRateLimited = error as AuthError;
    }

    expect(resendRateLimited).toEqual({
      code: 'rate_limited',
      message: signUpRateLimited?.message,
    });
    expect(resendRateLimited?.message).toBe(signUpRateLimited?.message);
  });

  it('a network-shaped resend failure reuses the existing network_error code and copy verbatim', async () => {
    mockResend.mockRejectedValue(new Error('Network request failed'));

    await expect(resendConfirmationEmail('user@x.com')).rejects.toEqual({
      code: 'network_error',
      message:
        'No internet connection. Please check your network and try again.',
    });
  });
});

describe('signInWithEmail', () => {
  it('calls supabase.auth.signInWithPassword with the normalized email', async () => {
    mockSignInWithPassword.mockResolvedValue({
      data: { user: { id: 'u1' }, session: FAKE_SESSION },
      error: null,
    });

    await signInWithEmail('  User@X.com ', 'password123');

    expect(mockSignInWithPassword).toHaveBeenCalledWith({
      email: 'user@x.com',
      password: 'password123',
    });
  });

  it('code "invalid_credentials" -> invalid_credentials with the generic copy', async () => {
    mockSignInWithPassword.mockRejectedValue({
      code: 'invalid_credentials',
      status: 400,
      message: 'Invalid login credentials',
    });

    await expect(
      signInWithEmail('user@x.com', 'wrong-password'),
    ).rejects.toEqual({
      code: 'invalid_credentials',
      message: 'Incorrect email or password.',
    });
  });

  // R5 — mapping unchanged from before this revision; pins that AC #14's
  // entrance still exists at the service layer (EmailAuthForm intercepts
  // this code and renders CheckYourEmailNotice instead of a bare error).
  it('R5: code "email_not_confirmed" -> email_confirmation_required (AC #14 entrance)', async () => {
    mockSignInWithPassword.mockRejectedValue({
      code: 'email_not_confirmed',
      status: 400,
      message: 'Email not confirmed',
    });

    await expect(signInWithEmail('user@x.com', 'password123')).rejects.toEqual({
      code: 'email_confirmation_required',
      message: 'Email not confirmed yet.',
    });
  });

  it('AC #7: an unknown-email failure and a wrong-password failure produce a byte-identical { code, message }', async () => {
    mockSignInWithPassword.mockRejectedValueOnce({
      code: 'invalid_credentials',
      status: 400,
      message: 'Invalid login credentials',
    });
    let unknownEmailError: unknown;
    try {
      await signInWithEmail('nobody@x.com', 'whatever123');
    } catch (error) {
      unknownEmailError = error;
    }

    mockSignInWithPassword.mockRejectedValueOnce({
      code: 'invalid_credentials',
      status: 400,
      message: 'Invalid login credentials',
    });
    let wrongPasswordError: unknown;
    try {
      await signInWithEmail('user@x.com', 'wrong-password');
    } catch (error) {
      wrongPasswordError = error;
    }

    expect(unknownEmailError).toEqual(wrongPasswordError);
  });

  it('a completely unrecognised sign-in failure also lands on invalid_credentials (AC #7 by construction)', async () => {
    mockSignInWithPassword.mockRejectedValue({
      code: 'some_unrecognised_code',
      status: 400,
      message: 'anything',
    });

    await expect(
      signInWithEmail('user@x.com', 'wrong-password'),
    ).rejects.toEqual({
      code: 'invalid_credentials',
      message: 'Incorrect email or password.',
    });
  });

  it('a 429 error reuses the existing rate_limited code and copy verbatim', async () => {
    mockSignInWithPassword.mockRejectedValue({
      status: 429,
      message: 'Too many requests',
    });

    await expect(signInWithEmail('user@x.com', 'password123')).rejects.toEqual({
      code: 'rate_limited',
      message: 'Too many attempts. Please wait a moment before trying again.',
    });
  });

  it('a null session with no error throws unknown, never a silent pass-through', async () => {
    mockSignInWithPassword.mockResolvedValue({
      data: { user: { id: 'u1' }, session: null },
      error: null,
    });

    await expect(signInWithEmail('user@x.com', 'password123')).rejects.toEqual({
      code: 'unknown',
      message: 'Something went wrong. Please try again.',
    });
  });
});

// docs/tickets/SS-073-design.md's Test plan #1-8 (the confirmEmailToken /
// adoptSessionFromUrlFragment block).

describe('confirmEmailToken', () => {
  it('calls supabase.auth.verifyOtp with exactly { token_hash, type: "email" } (AC #3)', async () => {
    mockVerifyOtp.mockResolvedValue({
      data: { session: FAKE_SESSION },
      error: null,
    });

    await confirmEmailToken('the-token-hash');

    expect(mockVerifyOtp).toHaveBeenCalledWith({
      token_hash: 'the-token-hash',
      type: 'email',
    });
    expect(mockVerifyOtp).toHaveBeenCalledTimes(1);
  });

  it('resolves the session on success', async () => {
    mockVerifyOtp.mockResolvedValue({
      data: { session: FAKE_SESSION },
      error: null,
    });

    await expect(confirmEmailToken('the-token-hash')).resolves.toEqual(
      FAKE_SESSION,
    );
  });

  it('a { data: { session: null }, error: null } response throws invalid_or_expired_confirmation_link (defensive-branch discipline)', async () => {
    mockVerifyOtp.mockResolvedValue({
      data: { session: null },
      error: null,
    });

    await expect(confirmEmailToken('the-token-hash')).rejects.toEqual({
      code: 'invalid_or_expired_confirmation_link',
      message:
        'This link may have expired or already been used. Your account may already be confirmed — try signing in.',
    });
  });

  it('an unmapped/expired-token-shaped rejection throws invalid_or_expired_confirmation_link with the non-technical copy, never the raw SDK message (AC #5)', async () => {
    mockVerifyOtp.mockRejectedValue({
      code: 'otp_expired',
      status: 403,
      message: 'Token has expired or is invalid',
    });

    let thrown: unknown;
    try {
      await confirmEmailToken('the-token-hash');
    } catch (error) {
      thrown = error;
    }

    expect(thrown).toEqual({
      code: 'invalid_or_expired_confirmation_link',
      message:
        'This link may have expired or already been used. Your account may already be confirmed — try signing in.',
    });
    expect((thrown as { message: string }).message).not.toContain(
      'Token has expired or is invalid',
    );
  });

  it("a network-failure-shaped rejection throws network_error (SS-003's existing message, by identity)", async () => {
    mockVerifyOtp.mockRejectedValue(new Error('Network request failed'));

    await expect(confirmEmailToken('the-token-hash')).rejects.toEqual({
      code: 'network_error',
      message:
        'No internet connection. Please check your network and try again.',
    });
  });
});

describe('adoptSessionFromUrlFragment', () => {
  it('on a non-web Platform.OS resolves null without calling supabase.auth.setSession at all', async () => {
    Platform.OS = 'ios';

    await expect(adoptSessionFromUrlFragment()).resolves.toBeNull();
    expect(mockSetSession).not.toHaveBeenCalled();
  });

  it('on web with no access_token/refresh_token in window.location.hash resolves null without calling setSession', async () => {
    Platform.OS = 'web';
    global.window = { location: { hash: '' } } as never;

    await expect(adoptSessionFromUrlFragment()).resolves.toBeNull();
    expect(mockSetSession).not.toHaveBeenCalled();
  });

  it('on web with both tokens present in the hash calls setSession exactly once and resolves the returned session', async () => {
    Platform.OS = 'web';
    global.window = {
      location: { hash: '#access_token=at1&refresh_token=rt1' },
    } as never;
    mockSetSession.mockResolvedValue({
      data: { session: FAKE_SESSION },
      error: null,
    });

    await expect(adoptSessionFromUrlFragment()).resolves.toEqual(FAKE_SESSION);
    expect(mockSetSession).toHaveBeenCalledWith({
      access_token: 'at1',
      refresh_token: 'rt1',
    });
    expect(mockSetSession).toHaveBeenCalledTimes(1);
  });

  it('a setSession rejection on web with both tokens present maps through toConfirmationLinkError', async () => {
    Platform.OS = 'web';
    global.window = {
      location: { hash: '#access_token=at1&refresh_token=rt1' },
    } as never;
    mockSetSession.mockRejectedValue({
      code: 'otp_expired',
      status: 403,
      message: 'Token has expired or is invalid',
    });

    await expect(adoptSessionFromUrlFragment()).rejects.toEqual({
      code: 'invalid_or_expired_confirmation_link',
      message:
        'This link may have expired or already been used. Your account may already be confirmed — try signing in.',
    });
  });
});
