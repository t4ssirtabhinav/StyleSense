import { useRouter } from 'expo-router';
import { Button, Card, Text } from '../../../components/ui';
import type { BatchItemState } from '../wardrobe.types';

export interface BatchSummaryToastProps {
  items: BatchItemState[];
  onAddAnother: () => void;
  /** SS-019: set by the parent screen when the batch stopped early because
   * of a wardrobe_limit_reached 403 -- surfaces the free-tier-cap
   * explanation instead of the generic counts-only summary. Absent/null
   * leaves existing counts-only behavior unchanged. */
  limitReachedMessage?: string | null;
}

// End-of-batch summary (success/failure counts) with "Add another"/"View
// wardrobe" actions, per docs/tickets/SS-013-design.md's
// BatchSummaryToast spec.
export function BatchSummaryToast({
  items,
  onAddAnother,
  limitReachedMessage,
}: BatchSummaryToastProps) {
  const router = useRouter();
  const successCount = items.filter((item) => item.status === 'saved').length;
  const failureCount = items.filter((item) => item.status === 'failed').length;

  const handleViewWardrobe = () => {
    router.push('/(tabs)/wardrobe');
  };

  return (
    <Card testID="batch-summary-toast">
      <Text variant="body" testID="batch-summary-counts">
        {`${successCount} added, ${failureCount} failed`}
      </Text>
      {limitReachedMessage ? (
        <Text variant="caption" testID="limit-reached-message">
          {limitReachedMessage}
        </Text>
      ) : null}
      <Button
        variant="primary"
        accessibilityLabel="Add another"
        onPress={onAddAnother}
      >
        Add another
      </Button>
      <Button
        variant="secondary"
        accessibilityLabel="View wardrobe"
        onPress={handleViewWardrobe}
      >
        View wardrobe
      </Button>
    </Card>
  );
}
