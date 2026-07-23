import { EmptyState } from '../../components/ui';

// Styled empty state for this ticket (SS-005) — the real wardrobe list/
// upload feature is Epic 2, unscheduled.
export default function WardrobeScreen() {
  return (
    <EmptyState
      testID="wardrobe-empty-state"
      icon="shirt-outline"
      heading="Your wardrobe is empty"
      subtext="Add your first item to get outfit suggestions."
    />
  );
}
