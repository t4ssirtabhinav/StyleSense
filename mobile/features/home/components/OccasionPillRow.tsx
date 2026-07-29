import { useRouter } from 'expo-router';
import { ScrollView } from 'react-native';
import { Badge } from '../../../components/ui';
import { useOccasionTaxonomy } from '../../onboarding/onboarding.queries';
import { OCCASION_PILLS } from '../home.constants';

// Horizontal ScrollView, not FlashList — 6 fixed items is not a "large list"
// per CLAUDE.md's FlashList rule. The pill LIST itself is still hardcoded
// (see home.constants.ts for why), so this component has no loading or
// error state of its own.
//
// (SS-025) The pills gain their colour from the occasion registry —
// previously all 6 rendered neutral as BL-008's workaround. The taxonomy
// query is read for colour ONLY: while it is loading, erroring or empty,
// `badgeColor()` returns undefined and every pill renders neutral, exactly
// as it did before this ticket. The home screen must never block, flash
// empty, or show an error because of an occasion-colour lookup.
export function OccasionPillRow() {
  const router = useRouter();
  const { badgeColor } = useOccasionTaxonomy();

  const handlePress = (occasionKey: string) => {
    router.push({ pathname: '/style', params: { occasion: occasionKey } });
  };

  return (
    <ScrollView
      testID="occasion-pill-row"
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerClassName="gap-sm px-md"
    >
      {OCCASION_PILLS.map((pill) => (
        <Badge
          key={pill.key}
          testID={`occasion-pill-${pill.key}`}
          label={pill.label}
          icon={pill.icon}
          occasion={badgeColor(pill.key)}
          onPress={() => handlePress(pill.key)}
        />
      ))}
    </ScrollView>
  );
}
