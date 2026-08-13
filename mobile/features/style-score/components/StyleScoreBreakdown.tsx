import { useEffect } from 'react';
import { View } from 'react-native';
import { Button, ProgressBar, Text } from '../../../components/ui';
import { ANALYTICS_EVENTS } from '../../../constants/analyticsEvents';
import { useAnalytics } from '../../../hooks/useAnalytics';
import { STYLE_SCORE_LOCKED_COPY } from '../style-score.constants';
import type { StyleScoreDimensionResult } from '../style-score.types';

export interface StyleScoreBreakdownProps {
  breakdown: StyleScoreDimensionResult[];
  isPremium: boolean;
  testID?: string;
  /** Free-tier "Upgrade" CTA — kept as a prop rather than a hardcoded
   * navigation call so this presentational component has no router
   * dependency of its own. No premium/paywall screen exists in this repo
   * yet, so the caller's handler is a visual affordance only (same
   * "coming soon" posture as app/(tabs)/profile.tsx's own placeholder). */
  onUpgrade: () => void;
}

// SS-021 — design §5.6. Premium: one row per dimension (label, score or
// '—', a ProgressBar, and a tip beneath when present). Free: the locked
// upsell copy + an Upgrade button, and fires PREMIUM_PAYWALL_VIEWED with
// { source: 'style_score' } exactly once per mount — an already-defined
// event (BL-049) gaining a real call site here. Sub-scores must never
// render in any form when !isPremium.
export function StyleScoreBreakdown({
  breakdown,
  isPremium,
  testID,
  onUpgrade,
}: StyleScoreBreakdownProps) {
  const { track } = useAnalytics();

  // Fire once per mount of the free-tier view — isPremium doesn't change
  // without a remount (a plan-tier change invalidates/refetches the whole
  // query, which remounts this component via StyleScoreCard's tree), and
  // `track` is stable (useAnalytics memoizes it over an empty dep array).
  // biome-ignore lint/correctness/useExhaustiveDependencies: intentional mount-only effect, see comment above.
  useEffect(() => {
    if (!isPremium) {
      track(ANALYTICS_EVENTS.PREMIUM_PAYWALL_VIEWED, { source: 'style_score' });
    }
  }, []);

  if (!isPremium) {
    return (
      <View testID={testID ?? 'style-score-breakdown'} className="mt-md gap-sm">
        <Text variant="body" color="secondary">
          {STYLE_SCORE_LOCKED_COPY}
        </Text>
        <Button
          variant="secondary"
          accessibilityLabel="Upgrade"
          onPress={onUpgrade}
        >
          Upgrade
        </Button>
      </View>
    );
  }

  return (
    <View testID={testID ?? 'style-score-breakdown'} className="mt-md gap-md">
      {breakdown.map((entry) => (
        <View key={entry.dimension} className="gap-xs">
          <View className="flex-row items-center justify-between">
            <Text variant="body">{entry.label}</Text>
            <Text variant="body" color="secondary">
              {entry.score === null ? '—' : entry.score}
            </Text>
          </View>
          <ProgressBar
            progress={entry.score ?? 0}
            testID={`style-score-progress-${entry.dimension}`}
          />
          {entry.tip ? (
            <Text variant="caption" color="muted">
              {entry.tip}
            </Text>
          ) : null}
        </View>
      ))}
    </View>
  );
}
