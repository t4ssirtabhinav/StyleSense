import { useRouter } from 'expo-router';
import { useCallback } from 'react';
import { Share, View } from 'react-native';
import { Button, Card, Skeleton, Text } from '../../../components/ui';
import { ANALYTICS_EVENTS } from '../../../constants/analyticsEvents';
import { useAnalytics } from '../../../hooks/useAnalytics';
import { useAuthStore } from '../../auth/auth.store';
import { exportStyleScoreCard } from '../share/styleScoreCardExport';
import {
  STYLE_SCORE_EMPTY_COPY,
  STYLE_SCORE_ERROR_COPY,
  STYLE_SCORE_SHARE_CTA,
  STYLE_SCORE_TITLE,
} from '../style-score.constants';
import { useStyleScoreQuery } from '../style-score.queries';
import { StyleScoreBreakdown } from './StyleScoreBreakdown';
import { StyleScoreRing } from './StyleScoreRing';

export interface StyleScoreCardProps {
  variant: 'compact' | 'full';
  testID?: string;
}

// SS-021 — the one composed entry point (design §5.6). Owns
// useStyleScoreQuery; handles loading/error/empty/ok. `compact` (Home)
// renders ring + total only — no breakdown, no share, no upsell (Home is
// not a paywall surface). `full` (Profile) additionally renders the
// breakdown and the Share button.
export function StyleScoreCard({ variant, testID }: StyleScoreCardProps) {
  const router = useRouter();
  const { track } = useAnalytics();
  const session = useAuthStore((state) => state.session);
  const userId = session?.user.id;
  const query = useStyleScoreQuery(userId);

  const handleAddItems = useCallback(() => {
    router.push('/wardrobe');
  }, [router]);

  const handleUpgrade = useCallback(() => {
    // No premium/paywall screen exists in this repo yet (design §5.6) — the
    // paywall-viewed analytics event (fired by StyleScoreBreakdown itself)
    // is the real signal here; this press has nothing to navigate to.
  }, []);

  const handleShare = useCallback(async () => {
    if (!query.data) return;
    const card = await exportStyleScoreCard({ total: query.data.total });
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
      track(ANALYTICS_EVENTS.STYLE_SCORE_SHARED, { channel });
    } catch {
      // A cancelled/failed native share sheet is not an error the user
      // needs surfaced — the share action is optional and reversible.
    }
  }, [query.data, track]);

  if (!session) {
    return null;
  }

  if (query.isLoading) {
    return (
      <Card
        testID={testID ?? 'style-score-card'}
        variant="elevated"
        className="m-md"
      >
        <Text variant="heading">{STYLE_SCORE_TITLE}</Text>
        <View className="mt-sm items-center">
          <Skeleton variant="circle" width={120} height={120} />
        </View>
      </Card>
    );
  }

  if (query.isError) {
    return (
      <Card
        testID={testID ?? 'style-score-card'}
        variant="elevated"
        className="m-md"
      >
        <Text variant="heading">{STYLE_SCORE_TITLE}</Text>
        <Text variant="body" color="secondary" className="mt-sm">
          {STYLE_SCORE_ERROR_COPY}
        </Text>
        <View className="mt-sm">
          <Button
            variant="secondary"
            accessibilityLabel="Retry"
            onPress={() => query.refetch()}
          >
            Retry
          </Button>
        </View>
      </Card>
    );
  }

  const summary = query.data;
  if (!summary) {
    return null;
  }

  if (summary.state === 'empty_wardrobe') {
    return (
      <Card
        testID={testID ?? 'style-score-card'}
        variant="elevated"
        className="m-md"
      >
        <Text variant="heading">{STYLE_SCORE_TITLE}</Text>
        <View className="mt-sm items-center">
          <StyleScoreRing total={0} />
        </View>
        <Text variant="body" color="secondary" className="mt-sm text-center">
          {STYLE_SCORE_EMPTY_COPY}
        </Text>
        <View className="mt-sm">
          <Button
            variant="primary"
            accessibilityLabel="Add your first item"
            onPress={handleAddItems}
          >
            Add your first item
          </Button>
        </View>
      </Card>
    );
  }

  return (
    <Card
      testID={testID ?? 'style-score-card'}
      variant="elevated"
      className="m-md"
    >
      <Text variant="heading">{STYLE_SCORE_TITLE}</Text>
      <View className="mt-sm items-center">
        <StyleScoreRing total={summary.total} />
      </View>
      {variant === 'full' ? (
        <>
          <StyleScoreBreakdown
            breakdown={summary.breakdown}
            isPremium={summary.isPremium}
            onUpgrade={handleUpgrade}
          />
          <View className="mt-md">
            <Button
              variant="secondary"
              accessibilityLabel={STYLE_SCORE_SHARE_CTA}
              onPress={handleShare}
            >
              {STYLE_SCORE_SHARE_CTA}
            </Button>
          </View>
        </>
      ) : null}
    </Card>
  );
}
