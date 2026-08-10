import { useState } from 'react';
import { View } from 'react-native';
import { Button, Text } from '../../../components/ui';
import { useAuthStore } from '../../auth/auth.store';
import { useOccasionTaxonomy } from '../../onboarding/onboarding.queries';
import {
  EXHAUSTED_AFTER_REGENERATE_COPY,
  OUTFIT_SAVE_DEGRADED_COPY,
  REGENERATE_CTA,
} from '../outfit-ai.constants';
import { useRecordOutcomeMutation } from '../outfit-ai.queries';
import { useOutfitAiStore } from '../outfit-ai.store';
import type { PortfolioItemResponse } from '../outfit-ai.types';
import { AcceptedOutfitPanel } from './AcceptedOutfitPanel';
import { OutfitCard } from './OutfitCard';

export interface OutfitCardDeckProps {
  portfolio: PortfolioItemResponse[];
  occasionKey: string;
  sessionId: string | null;
  limitedOptions: boolean;
  onRegenerate: () => void;
  onFirstAccept?: () => void;
  testID?: string;
}

type CardOutcome =
  | { status: 'idle' }
  | { status: 'accepted'; outfitId: string | null; alreadySaved: boolean }
  | { status: 'degraded' };

// The swipe/gesture deck state machine (design §"Files to create/modify").
// Swipe right = 'saved', swipe left = 'dismissed' (Accept/Reject
// IconButtons on OutfitCard — the accessible-button fallback that
// guarantees AC #2 is satisfiable even on a platform where the gesture
// layer degrades, per the design's web-first mitigation). Exhausting the
// deck renders the regenerate CTA; `limitedOptions` distinguishes an
// honest "that's everything we can build" from a normal end-of-deck.
export function OutfitCardDeck({
  portfolio,
  occasionKey,
  sessionId,
  limitedOptions,
  onRegenerate,
  onFirstAccept,
  testID,
}: OutfitCardDeckProps) {
  const jwt = useAuthStore((state) => state.session?.access_token);
  const { label: occasionLabel } = useOccasionTaxonomy();
  const deckIndex = useOutfitAiStore((state) => state.deckIndex);
  const advanceDeck = useOutfitAiStore((state) => state.advanceDeck);
  const recordOutcome = useRecordOutcomeMutation();
  const [outcome, setOutcome] = useState<CardOutcome>({ status: 'idle' });

  const currentItem = portfolio[deckIndex];

  const handleAccept = () => {
    if (!sessionId || !currentItem) {
      setOutcome({ status: 'degraded' });
      return;
    }
    recordOutcome.mutate(
      {
        request: {
          session_id: sessionId,
          rank: currentItem.rank,
          outcome_type: 'saved',
        },
        jwt: jwt as string,
      },
      {
        onSuccess: (response) => {
          setOutcome({
            status: 'accepted',
            outfitId: response.outfit_id,
            alreadySaved: response.already_saved,
          });
          onFirstAccept?.();
        },
        onError: () => setOutcome({ status: 'degraded' }),
      },
    );
  };

  const handleReject = () => {
    if (sessionId && currentItem) {
      recordOutcome.mutate({
        request: {
          session_id: sessionId,
          rank: currentItem.rank,
          outcome_type: 'dismissed',
        },
        jwt: jwt as string,
      });
    }
    // No toast on reject -- a swipe left is self-evident (design §5).
    advanceDeck();
    setOutcome({ status: 'idle' });
  };

  const handleContinue = () => {
    advanceDeck();
    setOutcome({ status: 'idle' });
  };

  if (!currentItem) {
    return (
      <View
        testID={testID ?? 'outfit-card-deck-exhausted'}
        className="items-center gap-md p-lg"
      >
        {limitedOptions ? (
          <Text variant="body" color="secondary" className="text-center">
            {EXHAUSTED_AFTER_REGENERATE_COPY}
          </Text>
        ) : null}
        <Button
          variant="secondary"
          accessibilityLabel={REGENERATE_CTA}
          onPress={onRegenerate}
        >
          {REGENERATE_CTA}
        </Button>
      </View>
    );
  }

  if (outcome.status === 'accepted') {
    return (
      <View testID={testID ?? 'outfit-card-deck'} className="gap-md">
        <AcceptedOutfitPanel
          alreadySaved={outcome.alreadySaved}
          sessionId={sessionId as string}
          rank={currentItem.rank}
          occasionLabel={occasionLabel(occasionKey)}
          itemCategoryLabels={Object.values(currentItem.category_labels)}
        />
        <Button
          variant="primary"
          accessibilityLabel="Continue to the next outfit"
          onPress={handleContinue}
        >
          Continue
        </Button>
      </View>
    );
  }

  return (
    <View testID={testID ?? 'outfit-card-deck'} className="gap-sm">
      {outcome.status === 'degraded' ? (
        <Text
          testID="outfit-card-deck-degraded-notice"
          variant="caption"
          color="secondary"
        >
          {OUTFIT_SAVE_DEGRADED_COPY}
        </Text>
      ) : null}
      <OutfitCard
        item={currentItem}
        occasionKey={occasionKey}
        onAccept={handleAccept}
        onReject={handleReject}
      />
      <Button
        variant="ghost"
        accessibilityLabel={REGENERATE_CTA}
        onPress={onRegenerate}
      >
        {REGENERATE_CTA}
      </Button>
    </View>
  );
}
