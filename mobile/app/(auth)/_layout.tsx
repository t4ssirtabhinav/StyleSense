import { Redirect, Stack, usePathname } from 'expo-router';
import { Card, Text } from '../../components/ui';
import { useAuthRouting } from '../../features/auth/useAuthRouting';

// SS-071 — the (auth) route group's forward guard: an authenticated
// session on /login or /verify-otp is redirected away, toward /onboarding
// or / as useAuthRouting() decides. This is the BL-168 fix's second half
// (the first half is app/(tabs)/_layout.tsx's guard toward /onboarding).
//
// /onboarding is DELIBERATELY excluded from this guard — see
// docs/tickets/SS-071-design.md's "Why /onboarding is deliberately
// excluded" section for the full reasoning. In short: with /onboarding
// excluded, exactly one route group redirects TOWARD it (tabs) and exactly
// one redirects AWAY from login/verify-otp (this one) — no route is both a
// source and a target, so a redirect loop is structurally impossible. It
// also preserves SS-016's own direct-entry handling on /onboarding and
// that screen's own session guard, both of which a blanket (auth)-group
// guard would regress.
//
// usePathname() strips route-group segments — confirmed against the
// installed expo-router@56.2.11's own source
// (node_modules/expo-router/build/global-state/getRouteInfoFromState.js:93-95
// filters any segment matching /^\(.*\)$/ before joining the pathname), so
// the real runtime value is "/login", never "/(auth)/login". Matched
// against both forms anyway (design doc edge case #13) as a defensive
// belt-and-braces measure against a future expo-router version changing
// that behaviour silently.
// SS-073 (AC #2) — `/confirm` is deliberately added here, not left
// unguarded. The instant any session exists (this exact click's own new
// session, or an unrelated one already live), this guard redirects away
// BEFORE confirm.tsx ever renders or calls confirmEmailToken/
// adoptSessionFromUrlFragment — so a confirm link opened in a browser
// with a *different* user's session live can never silently swap the
// active session underneath them, and the *same* user's already-live
// session can't loop or double-navigate either. See
// docs/tickets/SS-073-design.md's "The guard decision" section for the
// full reasoning; this is the same mechanism as /login and /verify-otp
// above, not new guard logic.
const GUARDED_ROUTES = new Set([
  '/login',
  '/(auth)/login',
  '/verify-otp',
  '/(auth)/verify-otp',
  '/confirm',
  '/(auth)/confirm',
]);

export default function AuthLayout() {
  const pathname = usePathname();
  const routing = useAuthRouting();
  const isGuardedRoute = GUARDED_ROUTES.has(pathname);

  if (isGuardedRoute) {
    if (routing.status === 'loading') {
      return (
        <Card
          testID="auth-entry-loading"
          variant="flat"
          className="m-md flex-1 items-center justify-center"
        >
          <Text variant="body">Loading…</Text>
        </Card>
      );
    }

    if (routing.status === 'app') {
      return <Redirect href="/" />;
    }

    if (routing.status === 'onboarding') {
      return <Redirect href="/onboarding" />;
    }

    // 'unauthenticated' — fall through to the normal (auth) Stack below.
  }

  return <Stack screenOptions={{ headerShown: false }} />;
}
