import { View } from 'react-native';

export interface StepIndicatorDotsProps {
  currentIndex: number;
  total: number;
}

// Purely presentational — 4 dots, active dot marigold (bg-brand), inactive
// bg-textMuted. Per docs/tickets/SS-004-design.md's "Files to
// create/modify" #10.
export function StepIndicatorDots({
  currentIndex,
  total,
}: StepIndicatorDotsProps) {
  return (
    <View className="flex-row items-center justify-center gap-2">
      {Array.from({ length: total }, (_, index) => (
        <View
          // biome-ignore lint/suspicious/noArrayIndexKey: fixed-length step positions, not a reorderable list
          key={index}
          testID={`step-dot-${index}`}
          className={`h-2 w-2 rounded-pill ${
            index === currentIndex ? 'bg-brand' : 'bg-textMuted'
          }`}
        />
      ))}
    </View>
  );
}
