import { View } from 'react-native';
import { Skeleton } from '../../../components/ui';

export interface TaxonomyChipsSkeletonProps {
  count: number;
}

// Shared loading-state placeholder reused by Step2 (style keywords) and
// Step3 (occasions) — per docs/tickets/SS-004-design.md's "Files to
// create/modify" #13 (2026-07-13 revision). Step 4's colour-swatch loading
// state renders inline instead (12 Skeleton variant="circle" in a 4x3 grid)
// since circles, not pills, need a different shape.
export function TaxonomyChipsSkeleton({ count }: TaxonomyChipsSkeletonProps) {
  return (
    <View className="flex-row flex-wrap gap-2">
      {Array.from({ length: count }, (_, index) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: fixed-count placeholder pills, not a reorderable list
        <Skeleton key={index} variant="text" width={100} height={36} />
      ))}
    </View>
  );
}
