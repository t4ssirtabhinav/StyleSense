import { useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Platform, View } from 'react-native';
import { Button, Card, Text, colors } from '../../components/ui';
import {
  useAdoptSessionFromUrlFragmentMutation,
  useConfirmEmailTokenMutation,
} from '../../features/auth/auth.queries';
import type { AuthError } from '../../features/auth/auth.types';

// SS-073 — the confirmation-link landing screen. Per
// docs/tickets/SS-073-design.md's "confirm.tsx — state shape" section:
// exactly three explicit states, never a fourth (blank/indefinite-spinner)
// one. This screen performs NO navigation of its own (AC #6, no open
// redirect) — a successful exchange writes a session via
// supabase.auth.onAuthStateChange -> hooks/useAuth.ts, and
// app/(auth)/_layout.tsx's forward guard (extended in this ticket) redirects
// toward /onboarding or / on its own next render, exactly like every other
// auth entry point in this app.

type ConfirmState =
  | { status: 'working' }
  | { status: 'success' }
  | { status: 'failed'; error: AuthError };

const NO_TOKEN_ERROR: AuthError = {
  code: 'invalid_or_expired_confirmation_link',
  message:
    'This link may have expired or already been used. Your account may already be confirmed — try signing in.',
};

const HEADING_BY_STATUS: Record<ConfirmState['status'], string> = {
  working: 'Confirming your account…',
  success: "You're confirmed",
  failed: "This link didn't work",
};

export default function ConfirmScreen() {
  const { token_hash: tokenHashParam } = useLocalSearchParams<{
    token_hash?: string;
  }>();
  const router = useRouter();
  const confirmEmailTokenMutation = useConfirmEmailTokenMutation();
  const adoptSessionFromUrlFragmentMutation =
    useAdoptSessionFromUrlFragmentMutation();

  const [state, setState] = useState<ConfirmState>({ status: 'working' });
  // React 18 Strict Mode double-effect / a re-render before the mutation
  // settles must not fire verifyOtp/setSession twice with the same token —
  // a ref (not state) survives re-renders without itself triggering one.
  const hasAttemptedRef = useRef(false);
  // Captured once, at the first attempt — a retry after a failure reuses
  // this captured token rather than re-reading the (possibly since-
  // stripped) URL, per the design doc's network-failure edge case.
  const capturedTokenHashRef = useRef<string | undefined>(undefined);

  // Refs, kept in sync with the latest mutation objects every render
  // (a plain synchronous assignment during render, not a useEffect — the
  // established pattern for "read the latest callback without making it a
  // reactive dependency"). This is what lets `attempt` below have a
  // genuinely exhaustive, stable dependency list: it never reads
  // confirmEmailTokenMutation/adoptSessionFromUrlFragmentMutation directly,
  // only these refs, so a fresh mutation-object identity every render (as
  // useMutation always produces) never needs to be a dependency.
  const confirmEmailTokenMutationRef = useRef(confirmEmailTokenMutation);
  confirmEmailTokenMutationRef.current = confirmEmailTokenMutation;
  const adoptSessionFromUrlFragmentMutationRef = useRef(
    adoptSessionFromUrlFragmentMutation,
  );
  adoptSessionFromUrlFragmentMutationRef.current =
    adoptSessionFromUrlFragmentMutation;

  const attempt = useCallback(() => {
    const tokenHash = capturedTokenHashRef.current ?? tokenHashParam;
    capturedTokenHashRef.current = tokenHash;

    if (tokenHash) {
      confirmEmailTokenMutationRef.current.mutate(tokenHash, {
        onSuccess: () => {
          if (Platform.OS === 'web' && typeof window !== 'undefined') {
            window.history.replaceState(null, '', window.location.pathname);
          }
          setState({ status: 'success' });
        },
        onError: (error) => setState({ status: 'failed', error }),
      });
      return;
    }

    // No token_hash param — try the web fragment fallback (a no-op,
    // resolving null, on native). Never races the token_hash attempt above
    // since this branch only runs when tokenHash is absent (design doc's
    // "token_hash present but the fragment also present" edge case).
    if (Platform.OS !== 'web') {
      setState({ status: 'failed', error: NO_TOKEN_ERROR });
      return;
    }

    adoptSessionFromUrlFragmentMutationRef.current.mutate(undefined, {
      onSuccess: (session) => {
        if (!session) {
          setState({ status: 'failed', error: NO_TOKEN_ERROR });
          return;
        }
        if (typeof window !== 'undefined') {
          window.history.replaceState(null, '', window.location.pathname);
        }
        setState({ status: 'success' });
      },
      onError: (error) => setState({ status: 'failed', error }),
    });
  }, [tokenHashParam]);

  // A legitimate one-time side effect (a network call), the same
  // discipline verify-otp.tsx's resend-cooldown timer already uses in this
  // app — not "derived state" in the sense CLAUDE.md's anti-pattern rule
  // guards against. hasAttemptedRef (not React state, and not this
  // effect's dependency list) is what actually guards the double-invoke:
  // React 18 Strict Mode's double-effect in dev, or a re-render before the
  // mutation settles, must not fire confirmEmailToken/
  // adoptSessionFromUrlFragment twice with the same token (design doc Test
  // plan #14). `attempt` IS included below (it is stable across renders
  // for a fixed tokenHashParam per the exhaustive deps above), so this
  // satisfies the lint rule while still only ever running its body once —
  // every subsequent re-run is a no-op via the ref guard.
  useEffect(() => {
    if (!hasAttemptedRef.current) {
      hasAttemptedRef.current = true;
      attempt();
    }
  }, [attempt]);

  const handleRetry = useCallback(() => {
    setState({ status: 'working' });
    attempt();
  }, [attempt]);

  return (
    <Card
      testID="confirm-screen"
      variant="flat"
      className="m-md flex-1 items-center justify-center"
    >
      <Text variant="heading" className="mb-md">
        {HEADING_BY_STATUS[state.status]}
      </Text>

      {state.status === 'working' ? (
        <Text testID="confirm-working" variant="body">
          One moment while we confirm your account…
        </Text>
      ) : null}

      {state.status === 'success' ? (
        <Text testID="confirm-success" variant="body">
          Taking you into the app…
        </Text>
      ) : null}

      {state.status === 'failed' ? (
        <View testID="confirm-failed" className="items-center">
          <Text
            variant="body"
            className="mb-md text-center"
            style={{ color: colors.accent.errorPlaceholder }}
          >
            {state.error.message}
          </Text>
          {state.error.code === 'network_error' ? (
            <Button
              variant="secondary"
              onPress={handleRetry}
              accessibilityLabel="Retry"
              fullWidth
            >
              Retry
            </Button>
          ) : null}
          <View className="mt-sm">
            <Button
              variant="primary"
              onPress={() => router.push('/login')}
              accessibilityLabel="Sign in"
            >
              Sign in
            </Button>
          </View>
        </View>
      ) : null}
    </Card>
  );
}
