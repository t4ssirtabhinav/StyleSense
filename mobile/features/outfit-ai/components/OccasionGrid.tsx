import { View } from 'react-native';
import { Badge, Text } from '../../../components/ui';
import { useOccasionTaxonomy } from '../../onboarding/onboarding.queries';

export interface OccasionGridProps {
  selectedKey: string | null;
  onSelect: (occasionKey: string) => void;
  testID?: string;
}

// Dynamic grid over the SS-025 occasions registry
// (`useOccasionTaxonomy().topLevelOccasions`) — deliberately NOT
// `home.constants.ts`'s hardcoded `OCCASION_PILLS` (a curated Home-tab
// subset with emoji that aren't registry columns). The Style tab shows the
// full active registry, so adding an occasion is an INSERT with no code
// change (design §5).
//
// Labels render `occasion.label` (English) with no i18n lookup — `BL-090`,
// `labels_i18n` ships `'{}'` for every row, so a lookup helper would be
// dead code that silently returns English anyway (design §5, stated
// explicitly rather than pretended away).
export function OccasionGrid({
  selectedKey,
  onSelect,
  testID,
}: OccasionGridProps) {
  const { topLevelOccasions, badgeColor, isLoading, isError, isStale } =
    useOccasionTaxonomy();

  if (isLoading) {
    return (
      <View testID="occasion-grid-loading" className="p-md">
        <Text variant="caption" color="secondary">
          Loading occasions…
        </Text>
      </View>
    );
  }

  if (isError) {
    return (
      <View testID="occasion-grid-error" className="p-md">
        <Text variant="caption" color="secondary">
          Couldn't load occasions. Try again in a moment.
        </Text>
      </View>
    );
  }

  return (
    <View testID={testID ?? 'occasion-grid'} className="gap-sm p-md">
      {isStale ? (
        <Text
          testID="occasion-grid-stale-notice"
          variant="caption"
          color="secondary"
        >
          Showing your last-known occasions — reconnect to refresh.
        </Text>
      ) : null}
      <View className="flex-row flex-wrap gap-sm">
        {topLevelOccasions.map((occasion) => (
          <Badge
            key={occasion.key}
            testID={`occasion-tile-${occasion.key}`}
            label={occasion.label}
            occasion={badgeColor(occasion.key)}
            selected={selectedKey === occasion.key}
            onPress={() => onSelect(occasion.key)}
          />
        ))}
      </View>
    </View>
  );
}
