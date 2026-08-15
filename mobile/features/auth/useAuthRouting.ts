import { useOnboardingCompletedQuery } from './auth.queries';
import { useAuthStore } from './auth.store';

// SS-071 — the single shared post-auth routing decision. Consumed ONLY by
// route layouts (app/(auth)/_layout.tsx, app/(tabs)/_layout.tsx) — never by
// individual screens. This hook computes a target; it never navigates
// itself. See docs/tickets/SS-071-design.md's "The routing decision"
// section for why (b) route-layout guards was picked over (a) a
// per-entry-point hook, and why /onboarding is deliberately excluded from
// the (auth) guard that also consumes this hook's output.

export type AuthRoutingState =
  | { status: 'loading' }
  | { status: 'unauthenticated' }
  | { status: 'onboarding' }
  | { status: 'app' };

export function useAuthRouting(): AuthRoutingState {
  const session = useAuthStore((state) => state.session);
  const isSessionLoading = useAuthStore((state) => state.isSessionLoading);
  const onboardingCompletedQuery = useOnboardingCompletedQuery(
    session?.user.id,
  );

  if (isSessionLoading) {
    return { status: 'loading' };
  }

  if (!session) {
    return { status: 'unauthenticated' };
  }

  // Same discipline verify-otp.tsx's deleted useEffect used: gate on
  // isSuccess, not on `data` alone, so a still-in-flight/refetching query
  // renders a loading state instead of a one-frame flash toward the wrong
  // destination (design doc's "no flash" note; also what makes edge case #9
  // — the onboarding-completion invalidation race — safe).
  if (!onboardingCompletedQuery.isSuccess) {
    return { status: 'loading' };
  }

  // checkOnboardingCompleted (auth.service.ts) already fails safe to
  // `false` on a network/RLS error, and this `?? false` is a second,
  // cheap layer of the same fail-safe discipline — a failed/undefined read
  // must never resolve to 'app'.
  return (onboardingCompletedQuery.data ?? false)
    ? { status: 'app' }
    : { status: 'onboarding' };
}
