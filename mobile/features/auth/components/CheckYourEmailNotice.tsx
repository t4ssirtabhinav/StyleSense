import { useEffect, useState } from 'react';
import { View } from 'react-native';
import { Button, Card, Text, colors } from '../../../components/ui';
import { useResendConfirmationEmailMutation } from '../auth.queries';
import type { AuthError } from '../auth.types';

// SS-072 REVISION 2 — the "Check your email" state. Per
// docs/tickets/SS-072-design.md's REVISION 2, this is a STATE of
// EmailAuthForm, not a route (Deviation 1 re-confirmed) — it performs no
// navigation of its own. Two entrances, both driven by the parent:
// signup returning `{ status: 'confirmation_required' }`, and sign-in
// failing with `email_confirmation_required` (AC #14). All three controls
// below call back into the parent, which owns the actual form state —
// this component only owns its own resend-cooldown UI state.

const RESEND_COOLDOWN_SECONDS = 60;

const HEADING = 'Check your email';
const BROWSER_EXPECTATION_LINE =
  'The link opens a confirmation page in your browser — you can close it and come back here to sign in.';
const RESEND_SUCCESS_MESSAGE = 'Confirmation email sent again.';

function bodyMessage(email: string): string {
  return `We've sent a confirmation link to ${email}. Open it to activate your account.`;
}

function resendLabel(cooldownSeconds: number): string {
  return cooldownSeconds > 0 ? `Resend in ${cooldownSeconds}s` : 'Resend email';
}

export interface CheckYourEmailNoticeProps {
  /** The normalized address the confirmation link was sent to — never the
   * raw typed string (see signUpWithEmail's EmailSignUpResult). */
  email: string;
  /** "Wrong email? Start over" — the parent clears the form and returns to
   * signup mode; this component carries no form state of its own. */
  onStartOver: () => void;
  /** "Sign in instead" — the parent switches to signin mode with this
   * email prefilled (AC #3's hard half: a control off every
   * duplicate-reachable state). */
  onSignInInstead: (email: string) => void;
}

export function CheckYourEmailNotice({
  email,
  onStartOver,
  onSignInInstead,
}: CheckYourEmailNoticeProps) {
  const [cooldown, setCooldown] = useState(0);
  const [resendMessage, setResendMessage] = useState<string | undefined>(
    undefined,
  );
  const [resendError, setResendError] = useState<AuthError | undefined>(
    undefined,
  );
  const resendMutation = useResendConfirmationEmailMutation();

  // Ticks the client-side cooldown down once per second. Deliberately
  // depends on `cooldown > 0` (a boolean), not `cooldown` itself — one
  // interval is created for the whole 60s run and decrements via a
  // functional update, rather than a new timer being scheduled on every
  // single tick. Cleared on the 0-transition and on unmount, so there is
  // never a leaked timer or a setState-after-unmount (design doc edge case
  // 5 / the boundary sweep's "Wrong email? Start over must not leave stale
  // state behind" note — this timer specifically must not outlive this
  // component).
  // biome-ignore lint/correctness/useExhaustiveDependencies: intentionally depends on the boolean transition (cooldown > 0), not the raw value — see the comment above.
  useEffect(() => {
    if (cooldown <= 0) {
      return undefined;
    }
    const interval = setInterval(() => {
      setCooldown((current) => Math.max(0, current - 1));
    }, 1000);
    return () => clearInterval(interval);
  }, [cooldown > 0]);

  const handleResend = () => {
    // Boundary sweep: a press before the 60s cooldown expires is blocked
    // client-side here and never reaches supabase.auth.resend() at all. A
    // press after the cooldown expires always attempts the network call —
    // if the server's OWN rate limit is still active, that surfaces via
    // toEmailAuthError's existing rate_limited mapping below, not a new
    // client-side guess at the server's real limit.
    if (cooldown > 0 || resendMutation.isPending) {
      return;
    }
    setResendMessage(undefined);
    setResendError(undefined);
    setCooldown(RESEND_COOLDOWN_SECONDS);
    resendMutation.mutate(email, {
      onSuccess: () => setResendMessage(RESEND_SUCCESS_MESSAGE),
      onError: (error) => setResendError(error),
    });
  };

  return (
    <Card
      testID="check-your-email-notice"
      variant="flat"
      className="m-md flex-1 justify-center"
    >
      <Text variant="heading" className="mb-md">
        {HEADING}
      </Text>
      <Text variant="body">{bodyMessage(email)}</Text>
      <Text variant="caption" color="secondary" className="mt-sm">
        {BROWSER_EXPECTATION_LINE}
      </Text>

      {resendMessage ? (
        <Text variant="caption" color="secondary" className="mt-sm">
          {resendMessage}
        </Text>
      ) : null}
      {resendError ? (
        <Text
          variant="caption"
          className="mt-sm"
          style={{ color: colors.accent.errorPlaceholder }}
        >
          {resendError.message}
        </Text>
      ) : null}

      <View className="mt-md">
        <Button
          variant="secondary"
          onPress={handleResend}
          loading={resendMutation.isPending}
          disabled={cooldown > 0}
          fullWidth
          accessibilityLabel={resendLabel(cooldown)}
        >
          {resendLabel(cooldown)}
        </Button>
      </View>

      <View className="mt-md flex-row items-center justify-center gap-xs">
        <Button
          variant="ghost"
          onPress={onStartOver}
          accessibilityLabel="Wrong email? Start over"
        >
          Wrong email? Start over
        </Button>
        <Button
          variant="ghost"
          onPress={() => onSignInInstead(email)}
          accessibilityLabel="Sign in instead"
        >
          Sign in instead
        </Button>
      </View>
    </Card>
  );
}
