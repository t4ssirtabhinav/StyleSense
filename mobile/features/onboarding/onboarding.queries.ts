import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { onboardingCompletedQueryKey } from '../auth/auth.queries';
import { useAuthStore } from '../auth/auth.store';
import {
  type OnboardingProgress,
  type Step1ProfileInput,
  completeOnboarding,
  fetchOnboardingProgress,
  saveStep1Profile,
} from './onboarding.service';
import { fetchOnboardingTaxonomies } from './onboarding.taxonomies.service';
import type { StylePreferences } from './onboarding.types';

// The only place these React Query hooks are called from is components (per
// CLAUDE.md's anti-pattern rule extended to this domain: no direct Supabase
// calls in components — only through features/<domain>/*.queries.ts).

export function useSaveStep1Mutation() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, { userId: string; input: Step1ProfileInput }>(
    {
      mutationFn: ({ userId, input }) => saveStep1Profile(userId, input),
      onSuccess: (_data, { userId }) => {
        queryClient.invalidateQueries({
          queryKey: ['onboarding', 'progress', userId],
        });
      },
    },
  );
}

export function useCompleteOnboardingMutation() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, { userId: string; data: StylePreferences }>({
    mutationFn: ({ userId, data }) => completeOnboarding(userId, data),
    onSuccess: (_data, { userId }) => {
      queryClient.invalidateQueries({
        queryKey: ['onboarding', 'progress', userId],
      });
      // (fix pass 2, 2026-07-22 — SS-004 CRITICAL bug) Also invalidate the
      // auth domain's completion-status query, which verify-otp.tsx routes
      // on. Without this, a stale cached `false` from earlier in the same
      // app session (e.g. this same phone's first, incomplete OTP verify)
      // survives completion and re-routes a re-verifying user back into the
      // wizard, discarding their already-saved selections. Uses the shared
      // key helper (not a duplicated literal) so this can't silently drift
      // from features/auth/auth.queries.ts, which owns the key.
      queryClient.invalidateQueries({
        queryKey: onboardingCompletedQueryKey(userId),
      });
    },
  });
}

export function useOnboardingProgressQuery(userId: string | undefined) {
  return useQuery<OnboardingProgress | null>({
    queryKey: ['onboarding', 'progress', userId],
    queryFn: () => fetchOnboardingProgress(userId as string),
    enabled: Boolean(userId),
  });
}

// (2026-07-13 revision) staleTime/gcTime here are an Architect judgment call,
// not a value fixed elsewhere in the repo — flagged in
// docs/tickets/SS-004-design.md's Open Questions #8.
//
// (QA-blocker fix pass, 2026-07-22 — see docs/worklog/SS-004.md) `enabled:
// Boolean(session)` is load-bearing, not cosmetic: these three reference
// tables (style_keywords/occasion_types/colour_palette) are RLS-protected
// and an anonymous/unauthenticated read resolves *successfully* with empty
// arrays rather than erroring. Combined with the 24h staleTime/Infinity
// gcTime above, a single pre-auth fire of this query permanently poisons
// the ['onboarding', 'taxonomies'] cache entry with an empty-but-"successful"
// result for the rest of the app session, even after the user later
// authenticates — this is exactly what produced the "no options available"
// bug. Gating on session presence means the query cannot fire (and
// therefore cannot cache a false-empty result) until RLS will actually let
// the read through.
export function useOnboardingTaxonomiesQuery() {
  const session = useAuthStore((state) => state.session);
  return useQuery({
    queryKey: ['onboarding', 'taxonomies'],
    queryFn: fetchOnboardingTaxonomies,
    staleTime: 24 * 60 * 60 * 1000, // 24h — reference data changes rarely
    gcTime: Number.POSITIVE_INFINITY, // keep cached for the app session lifetime
    enabled: Boolean(session),
  });
}
