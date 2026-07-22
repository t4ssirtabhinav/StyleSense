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
const mockUseOnboardingCompletedQuery = jest.fn((userId: string | undefined) =>
  userId
    ? { isSuccess: true, data: false }
    : { isSuccess: false, data: undefined },
);

jest.mock('../../../features/auth/auth.queries', () => ({
  useSendOtpMutation: () => ({ mutate: mockSendOtpMutate, isPending: false }),
  useVerifyOtpMutation: () => ({
    mutate: mockVerifyOtpMutate,
    isPending: false,
  }),
  useOnboardingCompletedQuery: (userId: string | undefined) =>
    mockUseOnboardingCompletedQuery(userId),
}));

describe('VerifyOtpScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseOnboardingCompletedQuery.mockImplementation((userId) =>
      userId
        ? { isSuccess: true, data: false }
        : { isSuccess: false, data: undefined },
    );
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

  it('calls router.replace("/onboarding") when the profile-exists query resolves false', async () => {
    mockVerifyOtpMutate.mockImplementation(
      (
        _vars: unknown,
        { onSuccess }: { onSuccess: (session: unknown) => void },
      ) => {
        onSuccess({ user: { id: 'user-1' } });
      },
    );
    mockUseOnboardingCompletedQuery.mockImplementation((userId) =>
      userId
        ? { isSuccess: true, data: false }
        : { isSuccess: false, data: undefined },
    );
    const { getByTestId } = await render(<VerifyOtpScreen />);

    await fireEvent.changeText(getByTestId('otp-hidden-input'), '123456');

    await waitFor(() =>
      expect(mockReplace).toHaveBeenCalledWith('/onboarding'),
    );
  });

  it('calls router.replace("/") when the profile-exists query resolves true', async () => {
    mockVerifyOtpMutate.mockImplementation(
      (
        _vars: unknown,
        { onSuccess }: { onSuccess: (session: unknown) => void },
      ) => {
        onSuccess({ user: { id: 'user-1' } });
      },
    );
    mockUseOnboardingCompletedQuery.mockImplementation((userId) =>
      userId
        ? { isSuccess: true, data: true }
        : { isSuccess: false, data: undefined },
    );
    const { getByTestId } = await render(<VerifyOtpScreen />);

    await fireEvent.changeText(getByTestId('otp-hidden-input'), '123456');

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/'));
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
});
