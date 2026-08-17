import { useState } from 'react';
import { View } from 'react-native';
import { Button, Card, Input, Text, colors } from '../../../components/ui';
import { ANALYTICS_EVENTS } from '../../../constants/analyticsEvents';
import { useAnalytics } from '../../../hooks/useAnalytics';
import {
  useSignInWithEmailMutation,
  useSignUpWithEmailMutation,
} from '../auth.queries';
import {
  normalizeEmail,
  validateEmail,
  validatePassword,
} from '../auth.service';
import type { AuthError } from '../auth.types';
import { CheckYourEmailNotice } from './CheckYourEmailNotice';

type Mode = 'signin' | 'signup';

interface ModeCopy {
  heading: string;
  submitLabel: string;
  switchPrompt: string;
  switchActionLabel: string;
}

const COPY: Record<Mode, ModeCopy> = {
  signin: {
    heading: 'Sign in with email',
    submitLabel: 'Sign in',
    switchPrompt: "Don't have an account?",
    switchActionLabel: 'Create account',
  },
  signup: {
    heading: 'Create your account',
    submitLabel: 'Create account',
    switchPrompt: 'Already have an account?',
    switchActionLabel: 'Sign in',
  },
};

// SS-072 — the registry's second Component (../auth.methods.ts), rendered
// under /login (Deviation 1, docs/tickets/SS-072-design.md) — already
// inside app/(auth)/_layout.tsx's GUARDED_ROUTES set. This component
// therefore performs NO navigation of its own: a successful signup/sign-in
// writes a session via supabase.auth.onAuthStateChange -> hooks/useAuth.ts,
// and the layout guard redirects to /onboarding or / on its own next
// render, exactly as it already does for PhoneLoginForm/verify-otp.tsx.
//
// Local useState only — same reasoning as AuthMethodChooser.tsx /
// auth.store.ts's own comments: nothing outside this screen needs this
// state.
export function EmailAuthForm() {
  const [mode, setMode] = useState<Mode>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [emailError, setEmailError] = useState<string | undefined>(undefined);
  const [passwordError, setPasswordError] = useState<string | undefined>(
    undefined,
  );
  const [formError, setFormError] = useState<AuthError | undefined>(undefined);
  // SS-072 REVISION 2 — set once signup returns `confirmation_required` OR
  // sign-in fails with `email_confirmation_required` (AC #14). When set,
  // this replaces the whole form with CheckYourEmailNotice — see this
  // component's render below.
  const [pendingConfirmationEmail, setPendingConfirmationEmail] = useState<
    string | undefined
  >(undefined);

  const signUpMutation = useSignUpWithEmailMutation();
  const signInMutation = useSignInWithEmailMutation();
  const { track } = useAnalytics();

  const isPending =
    mode === 'signup' ? signUpMutation.isPending : signInMutation.isPending;

  const clearFieldErrors = () => {
    setEmailError(undefined);
    setPasswordError(undefined);
    setFormError(undefined);
  };

  // Mode switching must not strand stale credentials (design doc edge case
  // #7 / raw ticket's own edge case): the typed email survives, the
  // password does not, and every error slot clears so a stale error from
  // the previous mode never lingers under the new one.
  const switchMode = (nextMode: Mode) => {
    setMode(nextMode);
    setPassword('');
    clearFieldErrors();
  };

  const handleChangeEmail = (text: string) => {
    setEmail(text);
    if (emailError) setEmailError(undefined);
    if (formError) setFormError(undefined);
  };

  const handleChangePassword = (text: string) => {
    setPassword(text);
    if (passwordError) setPasswordError(undefined);
    if (formError) setFormError(undefined);
  };

  const handleSubmit = () => {
    // AC #8: client-side validation before any network call. Handlers read
    // the current state values at call time — no cached snapshot (design
    // doc edge case #7's other half, the web-autofill case).
    const emailResult = validateEmail(email);
    const passwordResult = validatePassword(password);

    setEmailError(emailResult.valid ? undefined : emailResult.message);
    setPasswordError(passwordResult.valid ? undefined : passwordResult.message);
    setFormError(undefined);

    if (!emailResult.valid || !passwordResult.valid) {
      return;
    }

    if (mode === 'signup') {
      signUpMutation.mutate(
        { email, password },
        {
          onSuccess: (result) => {
            // AC #9 — `register` still fires unconditionally on a
            // successful signup call, regardless of `.status`. Decision
            // recorded in docs/tickets/SS-072-design.md's REVISION 2
            // ("Analytics" section): signUp IS the registration act; the
            // alternative (firing on first post-confirmation sign-in) has
            // no state to carry that intent across a session boundary.
            track(ANALYTICS_EVENTS.REGISTER, { method: 'email_password' });
            if (result.status === 'confirmation_required') {
              // AC #2 — the primary path today: no session yet, no
              // navigation, render the Check-your-email state instead.
              setPendingConfirmationEmail(result.email);
            }
            // `status === 'session'` (currently unreachable while
            // Confirm-email stays ON): a session was written directly by
            // supabase.auth.onAuthStateChange -> hooks/useAuth.ts; the
            // layout guard redirects on its own next render, same as
            // every other auth path in this app. No navigation call here.
          },
          onError: (authError) => {
            setFormError(authError);
          },
        },
      );
      return;
    }

    signInMutation.mutate(
      { email, password },
      {
        onSuccess: () => {
          // No navigation call here by design — see this component's own
          // top comment.
        },
        onError: (authError) => {
          if (authError.code === 'email_confirmation_required') {
            // AC #14 — signing in before confirming routes into the same
            // Check-your-email state with Resend, not the generic
            // "Incorrect email or password." (AC #7's deliberate,
            // re-accepted exception — see the design doc's clarified
            // AC #7.)
            setPendingConfirmationEmail(normalizeEmail(email));
          } else {
            setFormError(authError);
          }
        },
      },
    );
  };

  // "Wrong email? Start over" (AC #13) — returns to the signup form with
  // the email field cleared and focused, and resets both mutations so no
  // stale error/data from the abandoned attempt can resurface on the next
  // one (boundary sweep: "must not leave any stale mutation/query state
  // behind").
  const handleStartOver = () => {
    setPendingConfirmationEmail(undefined);
    setMode('signup');
    setEmail('');
    setPassword('');
    clearFieldErrors();
    signUpMutation.reset();
    signInMutation.reset();
  };

  // "Sign in instead" (AC #3's hard half) — switches to signin mode with
  // the email prefilled and the password empty; same stale-state reset as
  // Start over.
  const handleSignInInstead = (confirmedEmail: string) => {
    setPendingConfirmationEmail(undefined);
    setMode('signin');
    setEmail(confirmedEmail);
    setPassword('');
    clearFieldErrors();
    signUpMutation.reset();
    signInMutation.reset();
  };

  if (pendingConfirmationEmail) {
    return (
      <CheckYourEmailNotice
        email={pendingConfirmationEmail}
        onStartOver={handleStartOver}
        onSignInInstead={handleSignInInstead}
      />
    );
  }

  const copy = COPY[mode];

  return (
    <Card
      testID="email-auth-form"
      variant="flat"
      className="m-md flex-1 justify-center"
    >
      <Text variant="heading" className="mb-md">
        {copy.heading}
      </Text>

      <Input
        variant="email"
        label="Email"
        value={email}
        onChangeText={handleChangeEmail}
        error={emailError}
        accessibilityLabel="Email address"
        disabled={isPending}
        autoFocus
      />

      <View className="mt-sm">
        <Input
          variant="password"
          label="Password"
          value={password}
          onChangeText={handleChangePassword}
          error={passwordError}
          accessibilityLabel="Password"
          passwordMode={mode === 'signup' ? 'new' : 'current'}
          disabled={isPending}
        />
      </View>

      {formError ? (
        <View className="mt-sm">
          <Text
            variant="caption"
            style={{ color: colors.accent.errorPlaceholder }}
          >
            {formError.message}
          </Text>
          {formError.code === 'email_already_registered' ? (
            <View className="mt-xs items-start">
              <Button
                variant="ghost"
                onPress={() => switchMode('signin')}
                disabled={isPending}
                accessibilityLabel="Sign in instead"
              >
                Sign in instead
              </Button>
            </View>
          ) : null}
        </View>
      ) : null}

      <View className="mt-md">
        <Button
          onPress={handleSubmit}
          loading={isPending}
          fullWidth
          accessibilityLabel={copy.submitLabel}
        >
          {copy.submitLabel}
        </Button>
      </View>

      {/* AC #10: deliberately no "Forgot password?" text/link anywhere in
       * this component — see docs/tickets/SS-072-design.md / BL-173. */}
      <View className="mt-md flex-row items-center justify-center gap-xs">
        <Text variant="caption" color="secondary">
          {copy.switchPrompt}
        </Text>
        <Button
          variant="ghost"
          onPress={() => switchMode(mode === 'signup' ? 'signin' : 'signup')}
          disabled={isPending}
          accessibilityLabel={copy.switchActionLabel}
        >
          {copy.switchActionLabel}
        </Button>
      </View>
    </Card>
  );
}
