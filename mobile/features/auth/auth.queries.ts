import type { Session } from '@supabase/supabase-js';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  checkOnboardingCompleted,
  fetchUserPlanTier,
  sendOtp,
  verifyOtp,
} from './auth.service';
import type { AuthError } from './auth.types';

// The only place these React Query hooks are called from is components (per
// CLAUDE.md's anti-pattern rule extended to this domain: no direct Supabase
// calls in components — only through features/<domain>/*.queries.ts).
//
// Both mutations are typed with AuthError as the TError generic (rather than
// react-query's default Error) since auth.service.ts's sendOtp/verifyOtp
// always throw the typed AuthError, never a raw Error — this lets
// consumers' onError handlers read `.code`/`.message` without an unsafe cast.

export function useSendOtpMutation() {
  return useMutation<void, AuthError, string>({ mutationFn: sendOtp });
}

export function useVerifyOtpMutation() {
  return useMutation<Session, AuthError, { phone: string; token: string }>({
    mutationFn: ({ phone, token }) => verifyOtp(phone, token),
  });
}

// Exported so other domains that need to invalidate this query (e.g.
// onboarding.queries.ts's useCompleteOnboardingMutation, on completion) use
// the exact same key instead of duplicating the literal and risking drift.
// This query key is OWNED by this file — always build it via this helper.
export function onboardingCompletedQueryKey(userId: string | undefined) {
  return ['auth', 'onboarding-completed', userId] as const;
}

export function useOnboardingCompletedQuery(userId: string | undefined) {
  return useQuery({
    queryKey: onboardingCompletedQueryKey(userId),
    queryFn: () => checkOnboardingCompleted(userId as string),
    enabled: Boolean(userId),
  });
}

// SS-014: feeds the free-tier banner and the floating add-button's gating
// logic (design doc's Files section) -- same file-layering precedent as
// useOnboardingCompletedQuery above, wrapping the existing (SS-009)
// fetchUserPlanTier service function in a useQuery for the first time.
export function planTierQueryKey(userId: string | undefined) {
  return ['auth', 'plan-tier', userId] as const;
}

export function usePlanTierQuery(userId: string | undefined) {
  return useQuery({
    queryKey: planTierQueryKey(userId),
    queryFn: () => fetchUserPlanTier(userId as string),
    enabled: Boolean(userId),
  });
}
