import { useEffect } from 'react';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import { Text, colors } from '../../../components/ui';
import { WEAR_TOAST_DURATION_MS } from '../wardrobe.constants';

// SS-015: no Toast exists in components/ui and this design deliberately
// doesn't add one (SS-014's "no new components/ui primitives" precedent --
// a portal-based global toast interacting with an open bottom sheet is
// exactly what BL-010 says can't be verified on device). An in-sheet Card
// banner instead, local to this domain.

export interface WearLoggedToastProps {
  message: string;
  onDismiss: () => void;
  /** Overridable for tests; defaults to the shared constant. */
  durationMs?: number;
}

export function WearLoggedToast({
  message,
  onDismiss,
  durationMs = WEAR_TOAST_DURATION_MS,
}: WearLoggedToastProps) {
  const opacity = useSharedValue(0);

  useEffect(() => {
    opacity.value = withTiming(1, { duration: 200 });
    const timer = setTimeout(() => {
      opacity.value = withTiming(0, { duration: 200 });
      onDismiss();
    }, durationMs);
    return () => clearTimeout(timer);
  }, [durationMs, onDismiss, opacity]);

  const animatedStyle = useAnimatedStyle(() => ({ opacity: opacity.value }));

  return (
    // Animated.View, not Card -- NativeWind's className interop doesn't
    // cover reanimated's Animated.View (same reason Input.tsx's OTP row and
    // Skeleton.tsx use inline style instead), and Card's own contract
    // reserves className for additive spacing only, not bg overrides.
    <Animated.View
      testID="wear-logged-toast"
      style={[
        {
          marginBottom: 12,
          borderRadius: 8,
          padding: 12,
          backgroundColor: colors.accent.emerald,
        },
        animatedStyle,
      ]}
    >
      <Text variant="body" weight="bold" className="text-white">
        {message}
      </Text>
    </Animated.View>
  );
}
