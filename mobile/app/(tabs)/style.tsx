import { useLocalSearchParams } from 'expo-router';
import { EmptyState } from '../../components/ui';
import { OCCASION_PILLS } from '../../features/home/home.constants';

const GENERIC_HEADING = 'Nothing here yet';
const GENERIC_SUBTEXT = 'Outfit suggestions are on the way.';

// Reached (optionally) with a deep-linked `occasion` query param from the
// Home tab's OccasionPillRow. Real styling-AI functionality is SS-006/SS-007
// (out of this ticket's scope) — this is the minimum needed to satisfy the
// AC that the Style tab "navigates ... with that occasion pre-selected".
export default function StyleScreen() {
  const { occasion } = useLocalSearchParams<{ occasion?: string }>();

  const matchedPill = OCCASION_PILLS.find((pill) => pill.key === occasion);

  const heading = matchedPill
    ? `${matchedPill.label} looks — coming soon`
    : GENERIC_HEADING;

  return (
    <EmptyState
      testID="style-empty-state"
      icon="sparkles-outline"
      heading={heading}
      subtext={GENERIC_SUBTEXT}
    />
  );
}
