import { cleanup, fireEvent, render } from '@testing-library/react-native';
import { EmailAuthForm } from '../../../../features/auth/components/EmailAuthForm';

// EmailAuthForm imports validateEmail/validatePassword directly from
// auth.service.ts (pure functions), which still top-level-imports
// lib/supabase.ts — constructs the real Supabase client at module-load
// time and throws without env vars under Jest. Same mocking approach as
// login.test.tsx / auth.methods.test.tsx.
jest.mock('../../../../lib/supabase', () => ({ supabase: {} }));

const mockSignUpMutate = jest.fn();
const mockSignInMutate = jest.fn();
const mockSignUpReset = jest.fn();
const mockSignInReset = jest.fn();
const mockResendMutate = jest.fn();
let mockSignUpIsPending = false;
let mockSignInIsPending = false;

jest.mock('../../../../features/auth/auth.queries', () => ({
  useSignUpWithEmailMutation: () => ({
    mutate: mockSignUpMutate,
    isPending: mockSignUpIsPending,
    reset: mockSignUpReset,
  }),
  useSignInWithEmailMutation: () => ({
    mutate: mockSignInMutate,
    isPending: mockSignInIsPending,
    reset: mockSignInReset,
  }),
  // CheckYourEmailNotice (rendered by EmailAuthForm once
  // pendingConfirmationEmail is set) also pulls from this module.
  useResendConfirmationEmailMutation: () => ({
    mutate: mockResendMutate,
    isPending: false,
  }),
}));

const mockTrack = jest.fn();
jest.mock('../../../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({ track: mockTrack }),
}));

// expo-router is not imported by EmailAuthForm at all — AC #2/#6 assert
// that fact by checking these mocks are never called (design doc's "no
// navigation of its own"). Mocked anyway so a future accidental import
// fails loudly via a call assertion rather than a module-resolution error.
const mockPush = jest.fn();
const mockReplace = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
}));

describe('EmailAuthForm', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSignUpIsPending = false;
    mockSignInIsPending = false;
  });

  afterEach(async () => {
    await cleanup();
  });

  // Test plan #19.
  it('renders in signin mode by default with an email field, a password field, and a mode-switch control; both fields have distinct accessibility labels', async () => {
    const { getByLabelText, getByText } = await render(<EmailAuthForm />);

    expect(getByLabelText('Email address')).toBeOnTheScreen();
    expect(getByLabelText('Password')).toBeOnTheScreen();
    expect(getByText('Sign in with email')).toBeOnTheScreen();
    expect(getByText('Create account')).toBeOnTheScreen();
  });

  // Test plan #20 (AC #1 + edge case 7).
  it('switching signup <-> signin preserves the typed email and clears the password', async () => {
    const { getByLabelText, getByText } = await render(<EmailAuthForm />);

    await fireEvent.changeText(
      getByLabelText('Email address'),
      'user@example.com',
    );
    await fireEvent.changeText(getByLabelText('Password'), 'password123');

    await fireEvent.press(getByText('Create account'));

    expect(getByLabelText('Email address').props.value).toBe(
      'user@example.com',
    );
    expect(getByLabelText('Password').props.value).toBe('');
  });

  // Test plan #21 (AC #8).
  it('an invalid email shows an inline error and the mutation is not called', async () => {
    const { getByLabelText, getByText, findByText } = await render(
      <EmailAuthForm />,
    );

    await fireEvent.changeText(getByLabelText('Email address'), 'not-an-email');
    await fireEvent.changeText(getByLabelText('Password'), 'password123');
    await fireEvent.press(getByText('Sign in'));

    expect(
      await findByText('Please enter a valid email address.'),
    ).toBeOnTheScreen();
    expect(mockSignInMutate).not.toHaveBeenCalled();
  });

  // Test plan #22.
  it('a password under the minimum shows an inline error and the mutation is not called', async () => {
    const { getByLabelText, getByText, findByText } = await render(
      <EmailAuthForm />,
    );

    await fireEvent.changeText(
      getByLabelText('Email address'),
      'user@example.com',
    );
    await fireEvent.changeText(getByLabelText('Password'), 'short');
    await fireEvent.press(getByText('Sign in'));

    expect(
      await findByText('Password must be at least 8 characters.'),
    ).toBeOnTheScreen();
    expect(mockSignInMutate).not.toHaveBeenCalled();
  });

  // R7 (REVISION 2, replaces Test plan #23, AC #2) — a successful signup
  // now resolves { status: 'confirmation_required', email }, not a
  // session. This must render the Check-your-email state, not a bare
  // success, and must not render the form's password field.
  it('R7: a successful signup renders the Check-your-email state (heading + the exact submitted address), does not render the password field, and navigates nowhere', async () => {
    mockSignUpMutate.mockImplementation(
      (
        _vars: unknown,
        {
          onSuccess,
        }: { onSuccess: (result: { status: string; email: string }) => void },
      ) => {
        onSuccess({
          status: 'confirmation_required',
          email: 'user@example.com',
        });
      },
    );
    const { getByLabelText, getByText, queryByLabelText } = await render(
      <EmailAuthForm />,
    );

    await fireEvent.press(getByText('Create account'));
    await fireEvent.changeText(
      getByLabelText('Email address'),
      'user@example.com',
    );
    await fireEvent.changeText(getByLabelText('Password'), 'password123');
    await fireEvent.press(getByText('Create account'));

    expect(mockSignUpMutate).toHaveBeenCalledWith(
      { email: 'user@example.com', password: 'password123' },
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    );
    expect(getByText('Check your email')).toBeOnTheScreen();
    expect(
      getByText(
        "We've sent a confirmation link to user@example.com. Open it to activate your account.",
      ),
    ).toBeOnTheScreen();
    expect(queryByLabelText('Password')).toBeNull();
    expect(mockPush).not.toHaveBeenCalled();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  // R8.
  it('R8: register still fires exactly once on signup success, with { method: email_password }', async () => {
    mockSignUpMutate.mockImplementation(
      (
        _vars: unknown,
        {
          onSuccess,
        }: { onSuccess: (result: { status: string; email: string }) => void },
      ) => {
        onSuccess({
          status: 'confirmation_required',
          email: 'user@example.com',
        });
      },
    );
    const { getByLabelText, getByText } = await render(<EmailAuthForm />);

    await fireEvent.press(getByText('Create account'));
    await fireEvent.changeText(
      getByLabelText('Email address'),
      'user@example.com',
    );
    await fireEvent.changeText(getByLabelText('Password'), 'password123');
    await fireEvent.press(getByText('Create account'));

    expect(mockTrack).toHaveBeenCalledTimes(1);
    expect(mockTrack).toHaveBeenCalledWith('register', {
      method: 'email_password',
    });
  });

  // R9 (AC #14).
  it('R9: a sign-in failing with email_confirmation_required renders the Check-your-email state, not "Incorrect email or password."', async () => {
    mockSignInMutate.mockImplementation(
      (_vars: unknown, { onError }: { onError: (e: unknown) => void }) => {
        onError({
          code: 'email_confirmation_required',
          message: 'Email not confirmed yet.',
        });
      },
    );
    const { getByLabelText, getByText, findByText, queryByText } = await render(
      <EmailAuthForm />,
    );

    await fireEvent.changeText(
      getByLabelText('Email address'),
      'user@example.com',
    );
    await fireEvent.changeText(getByLabelText('Password'), 'password123');
    await fireEvent.press(getByText('Sign in'));

    expect(await findByText('Check your email')).toBeOnTheScreen();
    expect(queryByText('Incorrect email or password.')).toBeNull();
  });

  // R10 (REVISION 2, amends Test plan #24, AC #6) — a successful sign-in
  // fires no register event, navigates nowhere, and does NOT render the
  // notice (that path is signup-only / the email_confirmation_required
  // sign-in error, never a bare sign-in success).
  it('R10: a successful sign-in fires no register event, navigates nowhere, and does not render the Check-your-email notice', async () => {
    mockSignInMutate.mockImplementation(
      (
        _vars: unknown,
        { onSuccess }: { onSuccess: (session: unknown) => void },
      ) => {
        onSuccess({ user: { id: 'u1' } });
      },
    );
    const { getByLabelText, getByText, queryByText } = await render(
      <EmailAuthForm />,
    );

    await fireEvent.changeText(
      getByLabelText('Email address'),
      'user@example.com',
    );
    await fireEvent.changeText(getByLabelText('Password'), 'password123');
    await fireEvent.press(getByText('Sign in'));

    expect(mockSignInMutate).toHaveBeenCalledWith(
      { email: 'user@example.com', password: 'password123' },
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    );
    expect(mockTrack).not.toHaveBeenCalled();
    expect(mockPush).not.toHaveBeenCalled();
    expect(mockReplace).not.toHaveBeenCalled();
    expect(queryByText('Check your email')).toBeNull();
  });

  // Test plan #25 (AC #3).
  it('an email_already_registered error renders the exact copy and a "Sign in instead" control that switches to signin with the email prefilled', async () => {
    mockSignUpMutate.mockImplementation(
      (_vars: unknown, { onError }: { onError: (e: unknown) => void }) => {
        onError({
          code: 'email_already_registered',
          message: 'This email is already registered — sign in instead.',
        });
      },
    );
    const { getByLabelText, getByText, findByText } = await render(
      <EmailAuthForm />,
    );

    await fireEvent.press(getByText('Create account'));
    await fireEvent.changeText(
      getByLabelText('Email address'),
      'taken@example.com',
    );
    await fireEvent.changeText(getByLabelText('Password'), 'password123');
    await fireEvent.press(getByText('Create account'));

    expect(
      await findByText('This email is already registered — sign in instead.'),
    ).toBeOnTheScreen();

    await fireEvent.press(getByText('Sign in instead'));

    expect(getByText('Sign in with email')).toBeOnTheScreen();
    expect(getByLabelText('Email address').props.value).toBe(
      'taken@example.com',
    );
    expect(getByLabelText('Password').props.value).toBe('');
  });

  // R11 (REVISION 2, extends Test plan #26, AC #10) — must still hold in
  // all THREE states: signin, signup, and the Check-your-email notice.
  // "Resend" is worded deliberately so it never trips this assertion.
  it('R11: never renders a "Forgot password?" affordance in signin, signup, or the Check-your-email state', async () => {
    mockSignUpMutate.mockImplementation(
      (
        _vars: unknown,
        {
          onSuccess,
        }: { onSuccess: (result: { status: string; email: string }) => void },
      ) => {
        onSuccess({
          status: 'confirmation_required',
          email: 'user@example.com',
        });
      },
    );
    const { queryByText, getByLabelText, getByText } = await render(
      <EmailAuthForm />,
    );

    expect(queryByText(/forgot|reset/i)).toBeNull();

    await fireEvent.press(getByText('Create account'));
    expect(queryByText(/forgot|reset/i)).toBeNull();

    await fireEvent.changeText(
      getByLabelText('Email address'),
      'user@example.com',
    );
    await fireEvent.changeText(getByLabelText('Password'), 'password123');
    await fireEvent.press(getByText('Create account'));

    expect(getByText('Check your email')).toBeOnTheScreen();
    expect(queryByText(/forgot|reset/i)).toBeNull();
  });

  // Test plan #27.
  it('shows the loading state on submit and cannot be re-pressed while pending', async () => {
    mockSignInIsPending = true;
    const { getByTestId, getByLabelText, getByText } = await render(
      <EmailAuthForm />,
    );

    expect(getByTestId('button-spinner')).toBeOnTheScreen();

    await fireEvent.changeText(
      getByLabelText('Email address'),
      'user@example.com',
    );
    await fireEvent.changeText(getByLabelText('Password'), 'password123');
    await fireEvent.press(getByText('Sign in'));

    expect(mockSignInMutate).not.toHaveBeenCalled();
  });

  // Test plan #28.
  it('a network_error renders the existing network copy', async () => {
    mockSignInMutate.mockImplementation(
      (_vars: unknown, { onError }: { onError: (e: unknown) => void }) => {
        onError({
          code: 'network_error',
          message:
            'No internet connection. Please check your network and try again.',
        });
      },
    );
    const { getByLabelText, getByText, findByText } = await render(
      <EmailAuthForm />,
    );

    await fireEvent.changeText(
      getByLabelText('Email address'),
      'user@example.com',
    );
    await fireEvent.changeText(getByLabelText('Password'), 'password123');
    await fireEvent.press(getByText('Sign in'));

    expect(
      await findByText(
        'No internet connection. Please check your network and try again.',
      ),
    ).toBeOnTheScreen();
  });

  it('a rate_limited error renders the existing rate-limit copy', async () => {
    mockSignInMutate.mockImplementation(
      (_vars: unknown, { onError }: { onError: (e: unknown) => void }) => {
        onError({
          code: 'rate_limited',
          message:
            'Too many attempts. Please wait a moment before trying again.',
        });
      },
    );
    const { getByLabelText, getByText, findByText } = await render(
      <EmailAuthForm />,
    );

    await fireEvent.changeText(
      getByLabelText('Email address'),
      'user@example.com',
    );
    await fireEvent.changeText(getByLabelText('Password'), 'password123');
    await fireEvent.press(getByText('Sign in'));

    expect(
      await findByText(
        'Too many attempts. Please wait a moment before trying again.',
      ),
    ).toBeOnTheScreen();
  });
});
