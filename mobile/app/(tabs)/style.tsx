import { useLocalSearchParams } from 'expo-router';
import { EmptyState } from '../../components/ui';
import { OCCASION_PILLS } from '../../features/home/home.constants';
import { useOccasionTaxonomy } from '../../features/onboarding/onboarding.queries';

const GENERIC_HEADING = 'Nothing here yet';
const GENERIC_SUBTEXT = 'Outfit suggestions are on the way.';

// Reached (optionally) with a deep-linked `occasion` query param from the
// Home tab's OccasionPillRow. Real styling-AI functionality is SS-006/SS-007
// (out of this ticket's scope) — this is the minimum needed to satisfy the
// AC that the Style tab "navigates ... with that occasion pre-selected".
//
// (SS-025) The incoming param is run through the registry's alias map
// before matching OCCASION_PILLS, so a LEGACY deep link carrying the old
// `?occasion=wedding` / `?occasion=date` keys (shipped by SS-005, and
// possibly bookmarked or sitting in a notification) still resolves to the
// Wedding/Date pill now that the pill keys are `wedding_guest`/`date_night`.
// If the taxonomy has not resolved yet, `resolveOccasion` normalises shape
// only and the raw param still matches any pill whose key it already
// equals — never a crash, never a blank heading.
export default function StyleScreen() {
  const { occasion } = useLocalSearchParams<{ occasion?: string }>();
  const { resolveOccasion } = useOccasionTaxonomy();

  const resolved = occasion ? resolveOccasion(occasion) : undefined;
  const matchedPill = OCCASION_PILLS.find(
    (pill) => pill.key === resolved || pill.key === occasion,
  );

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
