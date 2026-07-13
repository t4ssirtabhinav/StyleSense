import {
  checkUserProfileExists,
  sendOtp,
  validateIndianMobile,
  verifyOtp,
} from '../../../features/auth/auth.service';

const mockSignInWithOtp = jest.fn();
const mockVerifyOtp = jest.fn();
const mockMaybeSingle = jest.fn();
const mockEq = jest.fn();
const mockSelect = jest.fn();
const mockFrom = jest.fn();

mockEq.mockReturnValue({ maybeSingle: mockMaybeSingle });
mockSelect.mockReturnValue({ eq: mockEq });
mockFrom.mockReturnValue({ select: mockSelect });

// Wrapper functions (rather than referencing the mocks directly as property
// values) defer access to `mockSignInWithOtp`/`mockVerifyOtp`/`mockFrom`
// until call time — jest.mock() factories are hoisted above this file's own
// top-level `const` declarations, so a direct reference would race against
// those declarations. Jest's "mock"-prefix hoisting exception only permits
// the *identifier reference* here, not an execution-order guarantee.
jest.mock('../../../lib/supabase', () => ({
  supabase: {
    auth: {
      signInWithOtp: (arg: unknown) => mockSignInWithOtp(arg),
      verifyOtp: (arg: unknown) => mockVerifyOtp(arg),
    },
    from: (arg: unknown) => mockFrom(arg),
  },
}));

describe('validateIndianMobile', () => {
  it('accepts a valid 10-digit number starting with 6-9', () => {
    expect(validateIndianMobile('9876543210')).toEqual({ valid: true });
  });

  it('rejects the wrong length', () => {
    const result = validateIndianMobile('98765');
    expect(result).toEqual({
      valid: false,
      message: 'Please enter a valid 10-digit mobile number.',
    });
  });

  it('rejects a 0-prefixed landline-looking number with landline copy', () => {
    const result = validateIndianMobile('0123456789');
    expect(result).toEqual({
      valid: false,
      message: 'Please enter a mobile number, not a landline number.',
    });
  });

  it('rejects a 2-prefixed landline-looking number with landline copy', () => {
    const result = validateIndianMobile('2123456789');
    expect(result).toEqual({
      valid: false,
      message: 'Please enter a mobile number, not a landline number.',
    });
  });

  it('rejects a 1-prefixed number with the generic starts-with copy', () => {
    const result = validateIndianMobile('1345678901');
    expect(result).toEqual({
      valid: false,
      message: 'Mobile numbers start with 6, 7, 8, or 9.',
    });
  });
});

describe('sendOtp', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('prepends +91 exactly once', async () => {
    mockSignInWithOtp.mockResolvedValue({ error: null });
    await sendOtp('9876543210');
    expect(mockSignInWithOtp).toHaveBeenCalledWith({ phone: '+919876543210' });
  });

  it('re-throws a rejected call as a typed AuthError, not the raw error', async () => {
    mockSignInWithOtp.mockRejectedValue(new Error('Network request failed'));

    await expect(sendOtp('9876543210')).rejects.toEqual(
      expect.objectContaining({ code: 'network_error' }),
    );
  });
});

describe('verifyOtp', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('calls verifyOtp with phone, token, and type: sms', async () => {
    const session = { user: { id: 'user-1' } };
    mockVerifyOtp.mockResolvedValue({ data: { session }, error: null });

    await verifyOtp('9876543210', '123456');

    expect(mockVerifyOtp).toHaveBeenCalledWith({
      phone: '+919876543210',
      token: '123456',
      type: 'sms',
    });
  });

  it('returns the session on a successful response', async () => {
    const session = { user: { id: 'user-1' } };
    mockVerifyOtp.mockResolvedValue({ data: { session }, error: null });

    await expect(verifyOtp('9876543210', '123456')).resolves.toBe(session);
  });

  it('throws AuthError({ code: "unknown" }) when session is null on success', async () => {
    mockVerifyOtp.mockResolvedValue({ data: { session: null }, error: null });

    await expect(verifyOtp('9876543210', '123456')).rejects.toEqual(
      expect.objectContaining({ code: 'unknown' }),
    );
  });

  it('throws AuthError({ code: "invalid_or_expired_otp" }) on a rejected/error response', async () => {
    mockVerifyOtp.mockResolvedValue({
      data: { session: null },
      error: new Error('Token has expired or is invalid'),
    });

    await expect(verifyOtp('9876543210', '000000')).rejects.toEqual(
      expect.objectContaining({ code: 'invalid_or_expired_otp' }),
    );
  });
});

describe('checkUserProfileExists', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('returns true when a row is present', async () => {
    mockMaybeSingle.mockResolvedValue({ data: { id: 'user-1' }, error: null });

    await expect(checkUserProfileExists('user-1')).resolves.toBe(true);
    expect(mockFrom).toHaveBeenCalledWith('users');
    expect(mockSelect).toHaveBeenCalledWith('id');
    expect(mockEq).toHaveBeenCalledWith('id', 'user-1');
  });

  it('returns false when no row is present', async () => {
    mockMaybeSingle.mockResolvedValue({ data: null, error: null });

    await expect(checkUserProfileExists('user-2')).resolves.toBe(false);
  });

  it('returns false (fail-safe) when the query throws', async () => {
    mockMaybeSingle.mockRejectedValue(new Error('Network request failed'));

    await expect(checkUserProfileExists('user-3')).resolves.toBe(false);
  });
});
