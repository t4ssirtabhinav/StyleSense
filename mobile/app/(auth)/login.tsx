import { Card, Text } from '../../components/ui';
import { AUTH_METHODS } from '../../features/auth/auth.methods';
import { AuthMethodChooser } from '../../features/auth/components/AuthMethodChooser';

// SS-071: reduced to a registry host. No phone-specific code, no session
// code — session-awareness lives in app/(auth)/_layout.tsx (see
// useAuthRouting.ts's own comment for why: login.test.tsx renders this
// screen bare, with no QueryClientProvider, and AC #1 requires that suite
// to pass unmodified).
//
// With exactly one registered method (today), this renders that method's
// Component directly — no wrapper, no chooser chrome, no "more options"
// affordance — so the render tree is byte-identical to the pre-SS-071
// phone-only screen. Registering a second method is what makes
// AuthMethodChooser appear.
export default function LoginScreen() {
  if (AUTH_METHODS.length === 0) {
    // Cheap guard against a misconfigured empty registry (design doc edge
    // case #12) — should never happen, but AUTH_METHODS[0] below would
    // otherwise crash.
    return (
      <Card
        testID="login-screen"
        variant="flat"
        className="m-md flex-1 items-center justify-center"
      >
        <Text variant="body">No sign-in method is available right now.</Text>
      </Card>
    );
  }

  if (AUTH_METHODS.length === 1) {
    const OnlyMethod = AUTH_METHODS[0].Component;
    return <OnlyMethod />;
  }

  return <AuthMethodChooser methods={AUTH_METHODS} />;
}
