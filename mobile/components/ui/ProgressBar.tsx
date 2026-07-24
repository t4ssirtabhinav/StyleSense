import { useEffect } from 'react';
import { View } from 'react-native';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import { colors, radii } from './tokens';

// SS-010 — needed because this ticket's own upload-progress AC requires the
// percentage to be "visible" and no such primitive existed yet. Follows
// Skeleton.tsx's conventions: tokens-driven colours, Reanimated `withTiming`
// for the fill's transition, NativeWind for anything static (track height).

export interface ProgressBarProps {
  /** 0-100. Out-of-range values (negative, >100, NaN) are clamped rather
   * than rendered as an invalid width. */
  progress: number;
  testID?: string;
}

function clampProgress(value: number): number {
  if (Number.isNaN(value)) {
    return 0;
  }
  return Math.min(100, Math.max(0, value));
}

export function ProgressBar({ progress, testID }: ProgressBarProps) {
  const clamped = clampProgress(progress);
  // Re-seeded to the current (already-clamped) value on every render — the
  // withTiming transition below is purely cosmetic smoothing for a real
  // device, not what tests assert against.
  const width = useSharedValue(clamped);

  useEffect(() => {
    width.value = withTiming(clamped, { duration: 200 });
  }, [clamped, width]);

  const animatedStyle = useAnimatedStyle(() => ({
    width: `${width.value}%`,
  }));

  return (
    <View
      testID={testID ?? 'progress-bar'}
      className="h-2 w-full overflow-hidden"
      style={{
        backgroundColor: colors.bg.secondary,
        borderRadius: radii.pill,
      }}
    >
      <Animated.View
        testID="progress-bar-fill"
        style={[
          {
            height: '100%',
            backgroundColor: colors.accent.marigold,
            borderRadius: radii.pill,
          },
          animatedStyle,
        ]}
      />
    </View>
  );
}
