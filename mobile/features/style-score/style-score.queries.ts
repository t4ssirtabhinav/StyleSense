// SS-021 — the only file components import from for style-score data
// (design §5.3). Composes: the app's single occasion-taxonomy fetcher +
// fetchUserPlanTier + fetchStyleScoreInputs + the pure computeStyleScore.
//
// Imports useOccasionTaxonomy directly from features/onboarding/
// onboarding.queries.ts (the fetcher itself) rather than through
// features/wardrobe/wardrobe.queries.ts's useOccasionOptions re-export —
// still the SAME single taxonomy fetcher (BL-089: do NOT add a second
// occasions fetcher; this isn't one), just imported at its source. Going
// through the wardrobe re-export here would create a wardrobe.queries.ts
// <-> style-score.queries.ts import cycle, since wardrobe.queries.ts also
// needs styleScoreQueryKey (below) to invalidate the score after a
// wardrobe mutation.
import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import { fetchUserPlanTier } from '../auth/auth.service';
import { useOccasionTaxonomy } from '../onboarding/onboarding.queries';
import { computeStyleScore } from './style-score.compute';
import { STYLE_SCORE_STALE_TIME_MS } from './style-score.constants';
import { fetchStyleScoreInputs } from './style-score.service';
import type { StyleScoreSummary } from './style-score.types';

const PREMIUM_TIERS = ['premium', 'premium_annual'];

export function styleScoreQueryKey(userId: string | undefined) {
  return ['style-score', 'summary', userId] as const;
}

export function useStyleScoreQuery(userId: string | undefined) {
  const taxonomy = useOccasionTaxonomy();
  // undefined while the taxonomy hasn't resolved yet (loading), an array
  // (possibly empty — edge case #6) once it has — distinct from "always an
  // array" so `enabled` can gate on resolution, not on non-emptiness.
  const activeOccasionKeys = useMemo(
    () =>
      taxonomy.isLoading
        ? undefined
        : taxonomy.occasions.map((occasion) => occasion.key),
    [taxonomy.isLoading, taxonomy.occasions],
  );

  return useQuery<StyleScoreSummary>({
    queryKey: styleScoreQueryKey(userId),
    queryFn: async () => {
      const now = new Date();
      const [inputs, planTier] = await Promise.all([
        fetchStyleScoreInputs(
          userId as string,
          now,
          activeOccasionKeys as string[],
        ),
        fetchUserPlanTier(userId as string),
      ]);
      const result = computeStyleScore(inputs);
      const isPremium = Boolean(planTier && PREMIUM_TIERS.includes(planTier));
      return { ...result, isPremium };
    },
    enabled: Boolean(userId) && Boolean(activeOccasionKeys),
    staleTime: STYLE_SCORE_STALE_TIME_MS,
  });
}
