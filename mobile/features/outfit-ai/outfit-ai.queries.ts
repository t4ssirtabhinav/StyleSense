// SS-023 — React Query hooks. The only place outfit-ai.service.ts is
// called from (CLAUDE.md: "No direct Supabase calls in components — only
// through features/<domain>/*.queries.ts" — extended here to the backend
// fetch calls, mirroring wardrobe.queries.ts's own established split).

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../auth/auth.store';
import { styleScoreQueryKey } from '../style-score/style-score.queries';
import {
  generateSuggestionsPortfolio,
  recordOutfitOutcome,
} from './outfit-ai.service';
import type {
  GeneratePortfolioRequest,
  GeneratePortfolioResponse,
  RecordOutcomeRequest,
  RecordOutcomeResponse,
} from './outfit-ai.types';

// Re-exported so screens under features/outfit-ai/ never need to import
// from features/wardrobe/ directly for the one thing they need from it
// (design §"Files to create/modify": "re-exported/reused from
// wardrobe.queries.ts if one already exists — check fetchWardrobeItemCount
// before adding a second"). fetchWardrobeItemCount/useWardrobeItemCountQuery
// already exist (SS-014) — no second implementation added.
export { useWardrobeItemCountQuery } from '../wardrobe/wardrobe.queries';

export function useGenerateSuggestionsMutation() {
  return useMutation<
    GeneratePortfolioResponse,
    Error,
    { request: GeneratePortfolioRequest; jwt: string }
  >({
    mutationFn: ({ request, jwt }) =>
      generateSuggestionsPortfolio(request, jwt),
  });
}

// SS-021: onSuccess invalidates the style score's query key -- the "score
// updates after each outfit saved" half of AC #1 (design §4). Outfit
// outcomes ('accepted'/'worn') are the only writes to outfits /
// wardrobe_item_wears this domain owns.
export function useRecordOutcomeMutation() {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.session?.user.id);

  return useMutation<
    RecordOutcomeResponse,
    Error,
    { request: RecordOutcomeRequest; jwt: string }
  >({
    mutationFn: ({ request, jwt }) => recordOutfitOutcome(request, jwt),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: styleScoreQueryKey(userId) });
    },
  });
}
