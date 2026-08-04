import { ActivityIndicator, View } from 'react-native';
import { Badge, Text } from '../../../components/ui';
import {
  WEAR_OCCASIONS_UNAVAILABLE_MESSAGE,
  WEAR_OCCASION_FIELD_LABEL,
  WEAR_OCCASION_NONE_LABEL,
} from '../wardrobe.constants';
import { useOccasionOptions } from '../wardrobe.queries';

export interface WearOccasionFieldProps {
  /** null = no occasion selected (the one-tap "Mark Worn" default). */
  value: string | null;
  onChange: (occasionKey: string | null) => void;
}

// SS-035 -- the optional occasion picker for the Add-a-wear / edit-a-wear
// cards (design §5.3). Built from useOccasionOptions().optionsIncluding()
// (the SS-025 union rule) so an unknown or deactivated slug already on an
// existing wear row stays visible and selected instead of being silently
// stripped on the next save. Selecting the already-selected chip clears it
// (toggle-off), same as the leading "No occasion" chip.
//
// Loading -> disabled-looking spinner state; error -> a friendly message,
// and the wear can STILL be logged without an occasion -- an occasion
// picker that fails must never block logging a wear (CLAUDE.md: every
// component handles loading/error/empty).
export function WearOccasionField({ value, onChange }: WearOccasionFieldProps) {
  const occasionTaxonomy = useOccasionOptions();

  if (occasionTaxonomy.isLoading) {
    return (
      <View
        testID="wear-occasion-field-loading"
        className="flex-row items-center gap-xs"
      >
        <ActivityIndicator testID="wear-occasion-field-spinner" />
        <Text variant="caption" color="secondary">
          {WEAR_OCCASION_FIELD_LABEL}
        </Text>
      </View>
    );
  }

  if (occasionTaxonomy.isError) {
    return (
      <Text
        testID="wear-occasion-field-error"
        variant="caption"
        color="secondary"
      >
        {WEAR_OCCASIONS_UNAVAILABLE_MESSAGE}
      </Text>
    );
  }

  const options = occasionTaxonomy.optionsIncluding(value ? [value] : []);

  const handleSelect = (key: string) => {
    onChange(value === key ? null : key);
  };

  return (
    <View testID="wear-occasion-field" className="gap-xs">
      <Text variant="caption" color="secondary">
        {WEAR_OCCASION_FIELD_LABEL}
      </Text>
      <View className="flex-row flex-wrap gap-xs">
        <Badge
          testID="wear-occasion-none"
          label={WEAR_OCCASION_NONE_LABEL}
          selected={value === null}
          onPress={() => onChange(null)}
        />
        {options.map((option) => (
          <Badge
            key={option.key}
            testID={`wear-occasion-${option.key}`}
            label={option.label}
            occasion={option.badgeColor}
            selected={value === option.key}
            onPress={() => handleSelect(option.key)}
          />
        ))}
      </View>
    </View>
  );
}
