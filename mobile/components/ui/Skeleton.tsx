import { useEffect } from 'react';
import type { DimensionValue } from 'react-native';
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';
import { colors, radii } from './tokens';

export type SkeletonVariant = 'card' | 'listItem' | 'circle' | 'text';

export interface SkeletonProps {
  variant?: SkeletonVariant;
  width?: DimensionValue;
  height?: DimensionValue;
}

// Default shapes per variant (Architect's decision — the ticket doesn't
// specify exact dimensions, only that the shimmer must "match card and list
// item shapes").
const DEFAULT_DIMENSIONS: Record<
  SkeletonVariant,
  { width: DimensionValue; height: DimensionValue }
> = {
  card: { width: '100%', height: 160 },
  listItem: { width: '100%', height: 64 },
  circle: { width: 48, height: 48 },
  text: { width: '80%', height: 16 },
};

const VARIANT_RADIUS: Record<SkeletonVariant, number> = {
  card: radii.lg,
  listItem: radii.md,
  circle: radii.pill,
  text: radii.sm,
};

export function Skeleton({ variant = 'text', width, height }: SkeletonProps) {
  const opacity = useSharedValue(0.4);

  useEffect(() => {
    opacity.value = withRepeat(
      withTiming(1, { duration: 800, easing: Easing.inOut(Easing.ease) }),
      -1,
      true,
    );
  }, [opacity]);

  const animatedStyle = useAnimatedStyle(() => ({ opacity: opacity.value }));
  const dimensions = DEFAULT_DIMENSIONS[variant];

  return (
    // NativeWind's className interop doesn't cover reanimated's
    // Animated.View (see Input.tsx's OTP row for the same issue), so
    // background/radius are set via inline style instead of className.
    <Animated.View
      testID="skeleton"
      style={[
        {
          width: width ?? dimensions.width,
          height: height ?? dimensions.height,
          backgroundColor: colors.bg.secondary,
          borderRadius: VARIANT_RADIUS[variant],
        },
        animatedStyle,
      ]}
    />
  );
}
