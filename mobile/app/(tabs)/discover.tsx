import { EmptyState } from '../../components/ui';

// Styled empty state for this ticket (SS-005) — the real Discover feed is a
// future epic, unscheduled.
export default function DiscoverScreen() {
  return (
    <EmptyState
      testID="discover-empty-state"
      icon="compass-outline"
      heading="Nothing here yet"
      subtext="Outfit suggestions are on the way."
    />
  );
}
