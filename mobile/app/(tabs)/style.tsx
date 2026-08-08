import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { View } from 'react-native';
import { Button, EmptyState, Text } from '../../components/ui';
import { ANALYTICS_EVENTS } from '../../constants/analyticsEvents';
import { useAuthStore } from '../../features/auth/auth.store';
import { useOccasionTaxonomy } from '../../features/onboarding/onboarding.queries';
import { OccasionGrid } from '../../features/outfit-ai/components/OccasionGrid';
import { OutfitCardDeck } from '../../features/outfit-ai/components/OutfitCardDeck';
import { SuggestionSkeletonDeck } from '../../features/outfit-ai/components/SuggestionSkeletonDeck';
import {
  BACKEND_UNREACHABLE_COPY,
  GET_SUGGESTIONS_CTA,
  OCCASION_SCREEN_HEADING,
  RETRY_CTA,
  ZERO_WARDROBE_CTA,
  ZERO_WARDROBE_HEADING,
  ZERO_WARDROBE_SUBTEXT,
} from '../../features/outfit-ai/outfit-ai.constants';
import {
  useGenerateSuggestionsMutation,
  useWardrobeItemCountQuery,
} from '../../features/outfit-ai/outfit-ai.queries';
import { useOutfitAiStore } from '../../features/outfit-ai/outfit-ai.store';
import type { GeneratePortfolioResponse } from '../../features/outfit-ai/outfit-ai.types';
import { useAnalytics } from '../../hooks/useAnalytics';
import { hasFiredOnceEvent, markOnceEventFired } from '../../lib/storage';

// Turns the Style tab from an EmptyState placeholder (SS-005/SS-013) into
// the product's primary AI surface (SS-023). Keeps the existing `?occasion=`
// deep-link handling and its resolveOccasion alias pass verbatim in
// behaviour (design §"Files to modify") — it is load-bearing for legacy
// SS-005 deep links — now pre-selecting a grid tile (and auto-firing the
// request, zero-tap) instead of changing a heading.
export default function StyleScreen() {
  const router = useRouter();
  const { occasion } = useLocalSearchParams<{ occasion?: string }>();
  const { resolveOccasion } = useOccasionTaxonomy();
  const { track } = useAnalytics();

  const userId = useAuthStore((state) => state.session?.user.id);
  const jwt = useAuthStore((state) => state.session?.access_token);

  const countQuery = useWardrobeItemCountQuery(userId);
  const generateMutation = useGenerateSuggestionsMutation();

  const selectedOccasionKey = useOutfitAiStore(
    (state) => state.selectedOccasionKey,
  );
  const dismissedFingerprints = useOutfitAiStore(
    (state) => state.dismissedFingerprints,
  );
  const sessionId = useOutfitAiStore((state) => state.sessionId);
  const selectOccasion = useOutfitAiStore((state) => state.selectOccasion);
  const setSessionId = useOutfitAiStore((state) => state.setSessionId);
  const addShownFingerprints = useOutfitAiStore(
    (state) => state.addShownFingerprints,
  );
  const resetDeck = useOutfitAiStore((state) => state.resetDeck);

  const [result, setResult] = useState<GeneratePortfolioResponse | null>(null);

  const deepLinkResolved = occasion ? resolveOccasion(occasion) : undefined;

  const fetchSuggestions = (
    occasionKey: string,
    excludeFingerprints: string[],
  ) => {
    if (!jwt) return;
    selectOccasion(occasionKey);
    generateMutation.mutate(
      {
        request: {
          occasion: occasionKey,
          exclude_fingerprints: excludeFingerprints,
        },
        jwt,
      },
      {
        onSuccess: (data) => {
          setResult(data);
          setSessionId(data.session_id);
          addShownFingerprints(
            data.portfolio.map((item) => item.outfit_fingerprint),
          );
          resetDeck();
          if (data.portfolio.length > 0 && userId) {
            void hasFiredOnceEvent(userId, 'first_suggestion_viewed').then(
              (fired) => {
                if (!fired) {
                  track(ANALYTICS_EVENTS.FIRST_SUGGESTION_VIEWED);
                  void markOnceEventFired(userId, 'first_suggestion_viewed');
                }
              },
            );
          }
        },
      },
    );
  };

  const handleSelectOccasion = (occasionKey: string) => {
    const exclude =
      selectedOccasionKey === occasionKey ? dismissedFingerprints : [];
    fetchSuggestions(occasionKey, exclude);
  };

  const handleGetSuggestions = () => {
    if (!selectedOccasionKey) return;
    fetchSuggestions(selectedOccasionKey, dismissedFingerprints);
  };

  const handleRegenerate = () => {
    if (!selectedOccasionKey) return;
    fetchSuggestions(selectedOccasionKey, dismissedFingerprints);
  };

  const handleFirstAccept = () => {
    if (!userId) return;
    void hasFiredOnceEvent(userId, 'first_outfit_saved').then((fired) => {
      if (!fired) {
        track(ANALYTICS_EVENTS.FIRST_OUTFIT_SAVED);
        void markOnceEventFired(userId, 'first_outfit_saved');
      }
    });
  };

  // Zero-tap deep link: pre-select AND auto-fire, once per incoming param
  // (never re-fires on an unrelated re-render). Preserves style.tsx's
  // existing "never crash, never blank" behaviour when the taxonomy hasn't
  // resolved yet (resolveOccasion normalises shape only in that case).
  // biome-ignore lint/correctness/useExhaustiveDependencies: intentionally scoped to [deepLinkResolved, jwt] only -- selectedOccasionKey/fetchSuggestions are read for their CURRENT value at fire time, not to be watched (including them would re-fire the deep link on every selection change, defeating "once per incoming param").
  useEffect(() => {
    if (deepLinkResolved && deepLinkResolved !== selectedOccasionKey && jwt) {
      fetchSuggestions(deepLinkResolved, []);
    }
  }, [deepLinkResolved, jwt]);

  if (countQuery.isLoading) {
    return (
      <View
        testID="style-loading"
        className="flex-1 items-center justify-center"
      >
        <Text variant="caption" color="secondary">
          Loading…
        </Text>
      </View>
    );
  }

  if (countQuery.data === 0) {
    return (
      <EmptyState
        testID="style-zero-wardrobe-state"
        icon="shirt-outline"
        heading={ZERO_WARDROBE_HEADING}
        subtext={ZERO_WARDROBE_SUBTEXT}
      >
        <Button
          variant="primary"
          accessibilityLabel={ZERO_WARDROBE_CTA}
          onPress={() => router.push('/wardrobe/upload')}
        >
          {ZERO_WARDROBE_CTA}
        </Button>
      </EmptyState>
    );
  }

  if (generateMutation.isPending) {
    return <SuggestionSkeletonDeck />;
  }

  if (generateMutation.isError) {
    return (
      <EmptyState
        testID="style-error-state"
        icon="alert-circle-outline"
        heading={BACKEND_UNREACHABLE_COPY}
        subtext=""
      >
        <Button
          variant="primary"
          accessibilityLabel={RETRY_CTA}
          onPress={handleGetSuggestions}
        >
          {RETRY_CTA}
        </Button>
      </EmptyState>
    );
  }

  if (result && selectedOccasionKey) {
    return (
      <View testID="style-deck-screen" className="flex-1">
        <OutfitCardDeck
          portfolio={result.portfolio}
          occasionKey={result.occasion_key}
          sessionId={sessionId}
          limitedOptions={result.limited_options}
          onRegenerate={handleRegenerate}
          onFirstAccept={handleFirstAccept}
        />
      </View>
    );
  }

  return (
    <View testID="style-occasion-screen" className="flex-1">
      <Text variant="heading" className="px-md pt-md">
        {OCCASION_SCREEN_HEADING}
      </Text>
      <OccasionGrid
        selectedKey={selectedOccasionKey}
        onSelect={handleSelectOccasion}
      />
      <View className="px-md">
        <Button
          variant="primary"
          fullWidth
          disabled={!selectedOccasionKey}
          accessibilityLabel={GET_SUGGESTIONS_CTA}
          onPress={handleGetSuggestions}
        >
          {GET_SUGGESTIONS_CTA}
        </Button>
      </View>
    </View>
  );
}
