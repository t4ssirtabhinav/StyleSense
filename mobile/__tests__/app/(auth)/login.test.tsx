import { cleanup, fireEvent, render } from '@testing-library/react-native';
import LoginScreen from '../../../app/(auth)/login';

const mockPush = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush, replace: jest.fn() }),
}));

// login.tsx also imports validateIndianMobile (a pure function) directly
// from features/auth/auth.service.ts — that module's top-level import of
// lib/supabase.ts constructs the real Supabase client at module-load time,
// which throws ("supabaseUrl is required") without env vars set in the test
// environment. Mocked here (rather than only mocking auth.queries.ts) so
// the real, unmocked auth.service.ts module can load safely in this file.
jest.mock('../../../lib/supabase', () => ({ supabase: {} }));

const mockMutate = jest.fn();
let mockIsPending = false;
jest.mock('../../../features/auth/auth.queries', () => ({
  useSendOtpMutation: () => ({
    mutate: mockMutate,
    isPending: mockIsPending,
  }),
}));

// SS-072 — this file resolves the REAL features/auth/auth.methods registry
// (by design, per SS-071's AC #1 — see that file's own comment), which now
// registers EmailAuthForm as its second entry. EmailAuthForm transitively
// imports hooks/useAnalytics -> lib/analytics -> posthog-react-native /
// @sentry/react-native, an ESM dependency Jest can't parse without a
// transform, which this file has never needed until now. Confirmed live
// (docs/worklog/SS-072.md): without this mock, the whole suite fails to
// load with "SyntaxError: Unexpected token 'export'" before a single test
// runs. This is the ONLY sanctioned change to this file — no assertion
// below is touched, matching __tests__/app/(auth)/verify-otp.test.tsx's own
// existing mock of the same module.
jest.mock('../../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({ track: jest.fn() }),
}));

// Same mocking approach as components/ui/__tests__/BottomSheet.test.tsx —
// login.tsx renders CountryCodePicker (which wraps AppBottomSheet), and this
// screen's own tests don't exercise the country picker's UI, so it's fully
// replaced rather than requiring a BottomSheetModalProvider ancestor.
jest.mock('@gorhom/bottom-sheet', () => {
  const actual = jest.requireActual('@gorhom/bottom-sheet');
  const react = jest.requireActual('react');
  const reactNative = jest.requireActual('react-native');

  const MockBottomSheetModal = react.forwardRef(
    (_props: Record<string, unknown>, ref: React.Ref<unknown>) => {
      react.useImperativeHandle(ref, () => ({
        present: jest.fn(),
        dismiss: jest.fn(),
      }));
      return null;
    },
  );
  MockBottomSheetModal.displayName = 'MockBottomSheetModal';

  return {
    ...actual,
    BottomSheetModal: MockBottomSheetModal,
    BottomSheetView: reactNative.View,
  };
});

describe('LoginScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockIsPending = false;
  });

  afterEach(async () => {
    await cleanup();
  });

  it('renders the +91 prefix by default', async () => {
    const { getByText } = await render(<LoginScreen />);
    expect(getByText('+91')).toBeOnTheScreen();
  });

  it('typing a valid number and pressing Send OTP calls mutate and navigates to /verify-otp on success', async () => {
    mockMutate.mockImplementation(
      (_phone: string, { onSuccess }: { onSuccess: () => void }) => {
        onSuccess();
      },
    );
    const { getByLabelText, getByText } = await render(<LoginScreen />);

    await fireEvent.changeText(getByLabelText('Phone number'), '9876543210');
    await fireEvent.press(getByText('Send OTP'));

    expect(mockMutate).toHaveBeenCalledWith(
      '9876543210',
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    );
    expect(mockPush).toHaveBeenCalledWith({
      pathname: '/verify-otp',
      params: { phone: '9876543210' },
    });
  });

  it('shows the landline-specific error and does not call the mutation for a 0-prefixed number', async () => {
    const { getByLabelText, getByText, findByText } = await render(
      <LoginScreen />,
    );

    await fireEvent.changeText(getByLabelText('Phone number'), '0123456789');
    await fireEvent.press(getByText('Send OTP'));

    expect(
      await findByText('Please enter a mobile number, not a landline number.'),
    ).toBeOnTheScreen();
    expect(mockMutate).not.toHaveBeenCalled();
  });

  it('shows the loading state while the mutation is pending and cannot be pressed again', async () => {
    mockIsPending = true;
    const { getByTestId, getByLabelText, getByText } = await render(
      <LoginScreen />,
    );

    expect(getByTestId('button-spinner')).toBeOnTheScreen();

    await fireEvent.changeText(getByLabelText('Phone number'), '9876543210');
    await fireEvent.press(getByText('Send OTP'));
    expect(mockMutate).not.toHaveBeenCalled();
  });

  it('renders a "No internet connection" message on a network-error-shaped AuthError', async () => {
    mockMutate.mockImplementation(
      (_phone: string, { onError }: { onError: (e: unknown) => void }) => {
        onError({
          code: 'network_error',
          message:
            'No internet connection. Please check your network and try again.',
        });
      },
    );
    const { getByLabelText, getByText, findByText } = await render(
      <LoginScreen />,
    );

    await fireEvent.changeText(getByLabelText('Phone number'), '9876543210');
    await fireEvent.press(getByText('Send OTP'));

    expect(
      await findByText(
        'No internet connection. Please check your network and try again.',
      ),
    ).toBeOnTheScreen();
  });

  it('renders a rate-limit-specific message on a rate_limited AuthError', async () => {
    mockMutate.mockImplementation(
      (_phone: string, { onError }: { onError: (e: unknown) => void }) => {
        onError({
          code: 'rate_limited',
          message:
            'Too many attempts. Please wait a moment before trying again.',
        });
      },
    );
    const { getByLabelText, getByText, findByText } = await render(
      <LoginScreen />,
    );

    await fireEvent.changeText(getByLabelText('Phone number'), '9876543210');
    await fireEvent.press(getByText('Send OTP'));

    expect(
      await findByText(
        'Too many attempts. Please wait a moment before trying again.',
      ),
    ).toBeOnTheScreen();
  });
});
