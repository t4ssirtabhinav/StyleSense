import { act, cleanup, fireEvent, render } from '@testing-library/react-native';
import { CheckYourEmailNotice } from '../../../../features/auth/components/CheckYourEmailNotice';

// Same reasoning as EmailAuthForm.test.tsx: this component's mutation hook
// (auth.queries.ts) transitively imports lib/supabase.ts, which constructs
// the real client at module-load time and throws without env vars under
// Jest.
jest.mock('../../../../lib/supabase', () => ({ supabase: {} }));

const mockResendMutate = jest.fn();
let mockResendIsPending = false;

jest.mock('../../../../features/auth/auth.queries', () => ({
  useResendConfirmationEmailMutation: () => ({
    mutate: mockResendMutate,
    isPending: mockResendIsPending,
  }),
}));

describe('CheckYourEmailNotice', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockResendIsPending = false;
  });

  afterEach(async () => {
    await cleanup();
    jest.useRealTimers();
  });

  // R12.
  it('renders the exact address passed to it, the heading, and the browser-expectation line', async () => {
    const { getByText } = await render(
      <CheckYourEmailNotice
        email="user@example.com"
        onStartOver={jest.fn()}
        onSignInInstead={jest.fn()}
      />,
    );

    expect(getByText('Check your email')).toBeOnTheScreen();
    expect(
      getByText(
        "We've sent a confirmation link to user@example.com. Open it to activate your account.",
      ),
    ).toBeOnTheScreen();
    expect(
      getByText(
        'The link opens a confirmation page in your browser — you can close it and come back here to sign in.',
      ),
    ).toBeOnTheScreen();
  });

  // R13.
  it('Resend email calls the resend mutation once; the button is disabled during the 60s cooldown and counts down; no state update after unmount', async () => {
    jest.useFakeTimers();
    const { getByText, queryByText } = await render(
      <CheckYourEmailNotice
        email="user@example.com"
        onStartOver={jest.fn()}
        onSignInInstead={jest.fn()}
      />,
    );

    await act(async () => {
      fireEvent.press(getByText('Resend email'));
    });

    expect(mockResendMutate).toHaveBeenCalledTimes(1);
    expect(mockResendMutate).toHaveBeenCalledWith(
      'user@example.com',
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    );
    expect(getByText('Resend in 60s')).toBeOnTheScreen();

    // A second press mid-cooldown must not call the mutation again
    // (boundary sweep: blocked client-side, never reaches the network).
    await act(async () => {
      fireEvent.press(getByText('Resend in 60s'));
    });
    expect(mockResendMutate).toHaveBeenCalledTimes(1);

    await act(async () => {
      jest.advanceTimersByTime(5000);
    });
    expect(getByText('Resend in 55s')).toBeOnTheScreen();

    await act(async () => {
      jest.advanceTimersByTime(55000);
    });
    expect(getByText('Resend email')).toBeOnTheScreen();
    expect(queryByText(/Resend in \d+s/)).toBeNull();

    // Unmounting mid-cooldown must not throw / warn about a state update
    // after unmount — the timer is cleared.
    await act(async () => {
      fireEvent.press(getByText('Resend email'));
    });
    await cleanup();
    await act(async () => {
      jest.advanceTimersByTime(60000);
    });
  });

  // R14.
  it('a rate-limited resend renders the existing rate_limited copy, not a new string', async () => {
    mockResendMutate.mockImplementation(
      (_email: string, { onError }: { onError: (e: unknown) => void }) => {
        onError({
          code: 'rate_limited',
          message:
            'Too many attempts. Please wait a moment before trying again.',
        });
      },
    );
    const { getByText, findByText } = await render(
      <CheckYourEmailNotice
        email="user@example.com"
        onStartOver={jest.fn()}
        onSignInInstead={jest.fn()}
      />,
    );

    fireEvent.press(getByText('Resend email'));

    expect(
      await findByText(
        'Too many attempts. Please wait a moment before trying again.',
      ),
    ).toBeOnTheScreen();
  });

  // R15.
  it('Wrong email? Start over calls onStartOver', async () => {
    const onStartOver = jest.fn();
    const { getByText } = await render(
      <CheckYourEmailNotice
        email="typo@example.com"
        onStartOver={onStartOver}
        onSignInInstead={jest.fn()}
      />,
    );

    fireEvent.press(getByText('Wrong email? Start over'));

    expect(onStartOver).toHaveBeenCalledTimes(1);
  });

  // R16.
  it('Sign in instead calls onSignInInstead with the exact email (AC #3 hard half)', async () => {
    const onSignInInstead = jest.fn();
    const { getByText } = await render(
      <CheckYourEmailNotice
        email="user@example.com"
        onStartOver={jest.fn()}
        onSignInInstead={onSignInInstead}
      />,
    );

    fireEvent.press(getByText('Sign in instead'));

    expect(onSignInInstead).toHaveBeenCalledWith('user@example.com');
  });

  // R17.
  it('renders content in the loading state and the error state alike — there is no empty state', async () => {
    mockResendIsPending = true;
    const { getByText, getByTestId } = await render(
      <CheckYourEmailNotice
        email="user@example.com"
        onStartOver={jest.fn()}
        onSignInInstead={jest.fn()}
      />,
    );

    expect(getByText('Check your email')).toBeOnTheScreen();
    expect(getByTestId('button-spinner')).toBeOnTheScreen();

    mockResendIsPending = false;
    mockResendMutate.mockImplementation(
      (_email: string, { onError }: { onError: (e: unknown) => void }) => {
        onError({ code: 'unknown', message: 'Something went wrong.' });
      },
    );
    const { getByText: getByTextRerendered, findByText } = await render(
      <CheckYourEmailNotice
        email="user@example.com"
        onStartOver={jest.fn()}
        onSignInInstead={jest.fn()}
      />,
    );
    fireEvent.press(getByTextRerendered('Resend email'));

    expect(getByTextRerendered('Check your email')).toBeOnTheScreen();
    expect(await findByText('Something went wrong.')).toBeOnTheScreen();
  });
});
