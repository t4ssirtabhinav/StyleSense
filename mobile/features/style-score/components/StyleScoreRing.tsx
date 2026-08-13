import { CircularProgress, Text } from '../../../components/ui';

export interface StyleScoreRingProps {
  total: number;
  size?: number;
  caption?: string;
  testID?: string;
}

// SS-021 — design §5.6. Single fill colour (accent.marigold, CircularProgress's
// own default) at every value — no red/amber/green banding, since no
// semantic status colours exist in the token set (BL-007) and inventing
// them here is exactly what that row forbids.
export function StyleScoreRing({
  total,
  size,
  caption = '/100',
  testID,
}: StyleScoreRingProps) {
  return (
    <CircularProgress
      progress={total}
      size={size}
      testID={testID ?? 'style-score-ring'}
    >
      <Text variant="display" weight="bold">
        {total}
      </Text>
      <Text variant="caption" color="muted">
        {caption}
      </Text>
    </CircularProgress>
  );
}
