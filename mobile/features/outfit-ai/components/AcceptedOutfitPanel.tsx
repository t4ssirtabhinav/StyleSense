import { useState } from 'react';
import { Share, View } from 'react-native';
import { Button, Text } from '../../../components/ui';
import { ANALYTICS_EVENTS } from '../../../constants/analyticsEvents';
import { useAnalytics } from '../../../hooks/useAnalytics';
import { useAuthStore } from '../../auth/auth.store';
import {
  ACCEPT_CONFIRMATION_COPY,
  ALREADY_LOGGED_TODAY_COPY,
  ALREADY_SAVED_COPY,
  SHARE_CTA,
  WORE_THIS_TODAY_CTA,
} from '../outfit-ai.constants';
import { useRecordOutcomeMutation } from '../outfit-ai.queries';
import { exportOutfitCard } from '../share/outfitCardExport';

export interface AcceptedOutfitPanelProps {
  alreadySaved: boolean;
  sessionId: string;
  rank: number;
  occasionLabel: string;
  itemCategoryLabels: string[];
  testID?: string;
}

// Post-accept confirmation (AC #4's Share action + §6's optional "Wore this
// today" action). PNG export is DEFERRED (Open Question #2, signed off
// 2026-08-07) — Share always uses the text/deep-link fallback behind the
// outfitCardExport seam; `outfit_shared` analytics still fires.
export function AcceptedOutfitPanel({
  alreadySaved,
  sessionId,
  rank,
  occasionLabel,
  itemCategoryLabels,
  testID,
}: AcceptedOutfitPanelProps) {
  const jwt = useAuthStore((state) => state.session?.access_token);
  const { track } = useAnalytics();
  const recordOutcome = useRecordOutcomeMutation();
  const [wornState, setWornState] = useState<'idle' | 'done' | 'alreadyLogged'>(
    'idle',
  );

  const handleShare = async () => {
    const card = await exportOutfitCard({ occasionLabel, itemCategoryLabels });
    const body = card.kind === 'text' ? card.body : '';

    try {
      const result = await Share.share({ message: body });
      const channel =
        typeof result === 'object' &&
        result !== null &&
        'activityType' in result &&
        typeof (result as { activityType?: string }).activityType === 'string'
          ? (result as { activityType?: string }).activityType
          : undefined;
      track(ANALYTICS_EVENTS.OUTFIT_SHARED, { channel });
    } catch {
      // A cancelled/failed native share sheet is not an error the user
      // needs surfaced — the share action is optional and reversible.
    }

    if (!jwt) return;
    recordOutcome.mutate({
      request: { session_id: sessionId, rank, outcome_type: 'shared' },
      jwt,
    });
  };

  const handleMarkWorn = () => {
    if (!jwt) return;
    recordOutcome.mutate(
      { request: { session_id: sessionId, rank, outcome_type: 'worn' }, jwt },
      {
        onSuccess: (response) => {
          setWornState(response.already_saved ? 'alreadyLogged' : 'done');
        },
      },
    );
  };

  return (
    <View testID={testID ?? 'accepted-outfit-panel'} className="gap-sm p-md">
      <Text variant="heading">
        {alreadySaved ? ALREADY_SAVED_COPY : ACCEPT_CONFIRMATION_COPY}
      </Text>

      <View className="flex-row gap-sm">
        <Button
          variant="secondary"
          accessibilityLabel={SHARE_CTA}
          onPress={handleShare}
        >
          {SHARE_CTA}
        </Button>
        <Button
          variant="secondary"
          accessibilityLabel={WORE_THIS_TODAY_CTA}
          disabled={wornState !== 'idle'}
          onPress={handleMarkWorn}
        >
          {wornState === 'alreadyLogged'
            ? ALREADY_LOGGED_TODAY_COPY
            : wornState === 'done'
              ? 'Logged'
              : WORE_THIS_TODAY_CTA}
        </Button>
      </View>
    </View>
  );
}
