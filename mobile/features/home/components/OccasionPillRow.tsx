import { useRouter } from 'expo-router';
import { ScrollView } from 'react-native';
import { Badge } from '../../../components/ui';
import { OCCASION_PILLS } from '../home.constants';

// Horizontal ScrollView, not FlashList — 6 fixed items is not a "large list"
// per CLAUDE.md's FlashList rule. No loading/error state needed: the pill
// row itself has no network call (see home.constants.ts for why the list is
// hardcoded, not DB-fetched).
export function OccasionPillRow() {
  const router = useRouter();

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
          onPress={() => handlePress(pill.key)}
        />
      ))}
    </ScrollView>
  );
}
