import {
  act,
  cleanup,
  fireEvent,
  render,
  waitFor,
} from '@testing-library/react-native';
import VerifyOtpScreen from '../../../app/(auth)/verify-otp';

const mockReplace = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({ replace: mockReplace, push: jest.fn() }),
  useLocalSearchParams: () => ({ phone: '9876543210' }),
}));

const mockSendOtpMutate = jest.fn();
const mockVerifyOtpMutate = jest.fn();

jest.mock('../../../features/auth/auth.queries', () => ({
  useSendOtpMutation: () => ({ mutate: mockSendOtpMutate, isPending: false }),
  useVerifyOtpMutation: () => ({
    mutate: mockVerifyOtpMutate,
    isPending: false,
  }),
}));

// SS-009: track() is asserted on directly for the REGISTER-event tests below.
const mockTrack = jest.fn();
jest.mock('../../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({ track: mockTrack }),
}));

describe('VerifyOtpScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  afterEach(async () => {
    // Unmount the previous test's render before the next one mounts — back
    // to back render() calls in the same file without this can leave a
    // stale renderer/overlapping act() scope (observed as later tests being
    // unable to find elements that clearly render in isolation).
    await cleanup();
  });

  it('renders the phone from useLocalSearchParams in the "OTP sent to" copy', async () => {
    const { getByText } = await render(<VerifyOtpScreen />);
    expect(getByText('OTP sent to +91 9876543210')).toBeOnTheScreen();
  });

  it('typing all 6 digits triggers onComplete and auto-calls verifyOtp without a button press', async () => {
    const { getByTestId } = await render(<VerifyOtpScreen />);
    await fireEvent.changeText(getByTestId('otp-hidden-input'), '123456');

    expect(mockVerifyOtpMutate).toHaveBeenCalledWith(
      { phone: '9876543210', token: '123456' },
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    );
  });

  it('sets an inline error on a rejected verify mutation without crashing', async () => {
    mockVerifyOtpMutate.mockImplementation(
      (_vars: unknown, { onError }: { onError: (e: unknown) => void }) => {
        onError({
          code: 'invalid_or_expired_otp',
          message: 'Incorrect or expired OTP. Please try again or resend.',
        });
      },
    );
    const { getByTestId, findByText } = await render(<VerifyOtpScreen />);

    await fireEvent.changeText(getByTestId('otp-hidden-input'), '000000');

    expect(
      await findByText('Incorrect or expired OTP. Please try again or resend.'),
    ).toBeOnTheScreen();
  });

  // SS-071: the /onboarding-vs-/ decision moved to
  // app/(auth)/_layout.tsx's forward guard (see
  // __tests__/app/(auth)/_layout.test.tsx tests #10-#15, which cover both
  // the cold-open case these two deleted tests never did and the
  // /login-with-session case). This screen no longer performs that
  // decision or any navigation of its own — the assertion below is the
  // replacement: it locks in that the routing logic really did move, so
  // the two mechanisms (a per-screen useEffect and the layout guard)
  // cannot both ship at once.
  it('performs no navigation itself after a successful verify — router.replace is never called', async () => {
    mockVerifyOtpMutate.mockImplementation(
      (
        _vars: unknown,
        { onSuccess }: { onSuccess: (session: unknown) => void },
      ) => {
        onSuccess({
          user: {
            id: 'user-1',
            created_at: '2026-07-24T00:00:00.000Z',
            last_sign_in_at: '2026-07-24T00:00:00.000Z',
          },
        });
      },
    );
    const { getByTestId } = await render(<VerifyOtpScreen />);

    await fireEvent.changeText(getByTestId('otp-hidden-input'), '123456');

    await waitFor(() =>
      expect(mockTrack).toHaveBeenCalledWith('register', {
        method: 'phone_otp',
      }),
    );
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it('Resend is disabled at mount showing 30s, becomes enabled after the countdown, and resets on press', async () => {
    jest.useFakeTimers();
    try {
      const { getByText, getByLabelText } = await render(<VerifyOtpScreen />);

      expect(getByText('Resend OTP (30s)')).toBeOnTheScreen();
      expect(getByLabelText('Resend OTP')).toBeDisabled();

      await act(async () => {
        jest.advanceTimersByTime(30000);
      });

      expect(getByText('Resend OTP')).toBeOnTheScreen();
      expect(getByLabelText('Resend OTP')).toBeEnabled();

      await act(async () => {
        fireEvent.press(getByLabelText('Resend OTP'));
      });

      expect(mockSendOtpMutate).toHaveBeenCalledWith('9876543210');
      expect(getByText('Resend OTP (30s)')).toBeOnTheScreen();
    } finally {
      jest.useRealTimers();
    }
  });

  it('tracks REGISTER on verify success when created_at === last_sign_in_at (new sign-up)', async () => {
    mockVerifyOtpMutate.mockImplementation(
      (
        _vars: unknown,
        { onSuccess }: { onSuccess: (session: unknown) => void },
      ) => {
        onSuccess({
          user: {
            id: 'user-1',
            created_at: '2026-07-24T00:00:00.000Z',
            last_sign_in_at: '2026-07-24T00:00:00.000Z',
          },
        });
      },
    );
    const { getByTestId } = await render(<VerifyOtpScreen />);

    await fireEvent.changeText(getByTestId('otp-hidden-input'), '123456');

    expect(mockTrack).toHaveBeenCalledWith('register', {
      method: 'phone_otp',
    });
  });

  it('does not track REGISTER on verify success when the timestamps differ (returning user)', async () => {
    mockVerifyOtpMutate.mockImplementation(
      (
        _vars: unknown,
        { onSuccess }: { onSuccess: (session: unknown) => void },
      ) => {
        onSuccess({
          user: {
            id: 'user-1',
            created_at: '2026-01-01T00:00:00.000Z',
            last_sign_in_at: '2026-07-24T00:00:00.000Z',
          },
        });
      },
    );
    const { getByTestId } = await render(<VerifyOtpScreen />);

    await fireEvent.changeText(getByTestId('otp-hidden-input'), '123456');

    expect(mockTrack).not.toHaveBeenCalledWith('register', expect.anything());
  });
});
