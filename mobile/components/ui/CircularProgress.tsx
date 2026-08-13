import type { ReactNode } from 'react';
import { View } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import { colors } from './tokens';

// SS-021 — new design-system primitive: components/ui/ has ProgressBar
// (linear) but nothing circular. Follows ProgressBar.tsx's conventions
// verbatim: token-driven colours, NativeWind for anything static, the same
// NaN-clamp behaviour. No StyleSheet.create.
//
// react-native-svg is this repo's first production use of the package
// (BL-146) — verified under jest-expo (jest.config.js's
// transformIgnorePatterns needed a small addition, see that file) and it is
// expected to render under react-native-web since @react-native-svg ships a
// web implementation. If either verification had failed, this file would
// instead render the existing ProgressBar beneath the centred content —
// that fallback was NOT needed; the ring renders in both environments.

export interface CircularProgressProps {
  /** 0-100. NaN -> 0; out-of-range clamped, exactly like ProgressBar.tsx. */
  progress: number;
  size?: number;
  strokeWidth?: number;
  trackColor?: string;
  fillColor?: string;
  children?: ReactNode;
  testID?: string;
}

const DEFAULT_SIZE = 120;
const DEFAULT_STROKE_WIDTH = 10;

function clampProgress(value: number): number {
  if (Number.isNaN(value)) {
    return 0;
  }
  return Math.min(100, Math.max(0, value));
}

export function CircularProgress({
  progress,
  size = DEFAULT_SIZE,
  strokeWidth = DEFAULT_STROKE_WIDTH,
  trackColor = colors.bg.secondary,
  fillColor = colors.accent.marigold,
  children,
  testID,
}: CircularProgressProps) {
  const clamped = clampProgress(progress);
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - clamped / 100);
  const center = size / 2;

  return (
    <View
      testID={testID ?? 'circular-progress'}
      accessibilityRole="progressbar"
      accessibilityValue={{ min: 0, max: 100, now: clamped }}
      style={{ width: size, height: size }}
      className="items-center justify-center"
    >
      <Svg width={size} height={size} style={{ position: 'absolute' }}>
        <Circle
          cx={center}
          cy={center}
          r={radius}
          stroke={trackColor}
          strokeWidth={strokeWidth}
          fill="none"
        />
        <Circle
          testID="circular-progress-fill"
          cx={center}
          cy={center}
          r={radius}
          stroke={fillColor}
          strokeWidth={strokeWidth}
          fill="none"
          strokeDasharray={`${circumference} ${circumference}`}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
          rotation={-90}
          originX={center}
          originY={center}
        />
      </Svg>
      <View className="items-center justify-center">{children}</View>
    </View>
  );
}
