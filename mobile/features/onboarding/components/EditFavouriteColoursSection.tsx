import { useState } from 'react';
import { View } from 'react-native';
import { Button, Skeleton, Text } from '../../../components/ui';
import { useUpdateFavouriteColoursMutation } from '../onboarding.queries';
import type { OnboardingTaxonomies } from '../onboarding.types';
import { ColourSwatch } from './Step4BudgetColours';

const COLOUR_PALETTE_COUNT = 12;
const MAX_COLOURS = 5;

// (SS-007) Edit Preferences — favourite colours section. Multi-select,
// capped at 5, reusing ColourSwatch's exact 64px-square/corner-checkmark
// presentation exported from Step4BudgetColours.tsx (design doc's Open
// Questions #1 — export chosen over duplicating, see that file's header
// comment). Per docs/tickets/SS-007-design.md's "Files to create/modify" #6.
// Cap-hint copy and no-op-past-cap-unless-deselecting toggle logic
// transcribed verbatim from onboarding.store.ts's toggleColour. Local
// component state — see EditStyleKeywordsSection.tsx's header comment for
// why.
export interface EditFavouriteColoursSectionProps {
  userId: string;
  initialColours: string[];
  taxonomies: OnboardingTaxonomies | undefined;
  isTaxonomiesLoading: boolean;
  isTaxonomiesError: boolean;
  onRetryTaxonomies: () => void;
}

export function EditFavouriteColoursSection({
  userId,
  initialColours,
  taxonomies,
  isTaxonomiesLoading,
  isTaxonomiesError,
  onRetryTaxonomies,
}: EditFavouriteColoursSectionProps) {
  const [colours, setColours] = useState<string[]>(initialColours);
  const mutation = useUpdateFavouriteColoursMutation();

  const atCap = colours.length >= MAX_COLOURS;

  const toggleColour = (hex: string) => {
    setColours((current) => {
      if (current.includes(hex)) {
        return current.filter((existing) => existing !== hex);
      }
      if (current.length >= MAX_COLOURS) {
        return current;
      }
      return [...current, hex];
    });
  };

  const handleSave = () => {
    mutation.mutate({ userId, colours });
  };

  const hasTaxonomiesData = !isTaxonomiesLoading && !isTaxonomiesError;

  return (
    <View className="p-md" testID="edit-favourite-colours-section">
      <Text variant="heading">Favourite colours (up to 5)</Text>

      {isTaxonomiesLoading ? (
        <View className="flex-row flex-wrap">
          {Array.from({ length: COLOUR_PALETTE_COUNT }, (_, index) => (
            <View
              // biome-ignore lint/suspicious/noArrayIndexKey: fixed-count placeholder circles, not a reorderable list
              key={index}
              className="w-1/4 items-center justify-center py-xs"
            >
              <Skeleton variant="circle" />
            </View>
          ))}
        </View>
      ) : null}

      {isTaxonomiesError ? (
        <View className="items-start">
          <Text variant="body" color="secondary">
            Couldn't load colour options.
          </Text>
          <Button variant="ghost" onPress={onRetryTaxonomies}>
            Retry
          </Button>
        </View>
      ) : null}

      {hasTaxonomiesData &&
      taxonomies &&
      taxonomies.colourPalette.length === 0 ? (
        <Text variant="body" color="secondary">
          No options available right now.
        </Text>
      ) : null}

      {hasTaxonomiesData &&
      taxonomies &&
      taxonomies.colourPalette.length > 0 ? (
        <View className="flex-row flex-wrap" testID="edit-colour-palette-grid">
          {taxonomies.colourPalette.map((option) => {
            const selected = colours.includes(option.hex);
            return (
              <ColourSwatch
                key={option.key}
                hex={option.hex}
                label={option.label}
                selected={selected}
                onPress={() => toggleColour(option.hex)}
              />
            );
          })}
        </View>
      ) : null}

      {atCap ? (
        <Text variant="caption" color="secondary" className="mt-sm">
          You can select up to 5 colours.
        </Text>
      ) : null}

      {mutation.isError ? (
        <View className="mb-sm mt-sm items-start">
          <Text variant="body" color="secondary">
            Couldn't save favourite colours.
          </Text>
          <Button variant="ghost" onPress={handleSave}>
            Try again
          </Button>
        </View>
      ) : null}

      <View className="mt-md">
        <Button
          onPress={handleSave}
          loading={mutation.isPending}
          accessibilityLabel="Save favourite colours"
        >
          Save
        </Button>
      </View>
    </View>
  );
}
