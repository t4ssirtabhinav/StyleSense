import { useState } from 'react';
import { View } from 'react-native';
import { Badge, Button, Text } from '../../../components/ui';
import { occasionBadgeColor, topLevelOccasions } from '../onboarding.occasions';
import { useUpdateOccasionPrioritiesMutation } from '../onboarding.queries';
import type {
  OccasionPriorityKey,
  OnboardingTaxonomies,
} from '../onboarding.types';
import { TaxonomyChipsSkeleton } from './TaxonomyChipsSkeleton';

const OCCASION_TYPES_COUNT = 12;
const MAX_OCCASIONS = 3;

// (SS-007) Edit Preferences — occasion priorities section. Multi-select,
// capped at 3 (per docs/tickets/SS-007-design.md's "Files to create/modify"
// #4). Cap-hint copy and no-op-past-cap-unless-deselecting toggle logic
// transcribed verbatim from onboarding.store.ts's toggleOccasion /
// Step3OccasionPriorities.tsx — see design doc's "Concrete values to use,
// not invent". Local component state — see EditStyleKeywordsSection.tsx's
// header comment for why.
export interface EditOccasionPrioritiesSectionProps {
  userId: string;
  initialOccasions: OccasionPriorityKey[];
  taxonomies: OnboardingTaxonomies | undefined;
  isTaxonomiesLoading: boolean;
  isTaxonomiesError: boolean;
  onRetryTaxonomies: () => void;
}

export function EditOccasionPrioritiesSection({
  userId,
  initialOccasions,
  taxonomies,
  isTaxonomiesLoading,
  isTaxonomiesError,
  onRetryTaxonomies,
}: EditOccasionPrioritiesSectionProps) {
  const [occasions, setOccasions] =
    useState<OccasionPriorityKey[]>(initialOccasions);
  const mutation = useUpdateOccasionPrioritiesMutation();

  const atCap = occasions.length >= MAX_OCCASIONS;

  const toggleOccasion = (key: OccasionPriorityKey) => {
    setOccasions((current) => {
      if (current.includes(key)) {
        return current.filter((existing) => existing !== key);
      }
      if (current.length >= MAX_OCCASIONS) {
        return current;
      }
      return [...current, key];
    });
  };

  const handleSave = () => {
    mutation.mutate({ userId, occasions });
  };

  const hasTaxonomiesData = !isTaxonomiesLoading && !isTaxonomiesError;
  // (SS-025) Same top-level-only + registry-colour sourcing as onboarding
  // Step 3 — derived during render from the snapshot the parent already
  // fetched, not a second query.
  const occasionOptions = topLevelOccasions(taxonomies);

  return (
    <View className="p-md" testID="edit-occasion-priorities-section">
      <Text variant="heading">Occasion priorities</Text>

      {isTaxonomiesLoading ? (
        <TaxonomyChipsSkeleton count={OCCASION_TYPES_COUNT} />
      ) : null}

      {isTaxonomiesError ? (
        <View className="items-start">
          <Text variant="body" color="secondary">
            Couldn't load occasion options.
          </Text>
          <Button variant="ghost" onPress={onRetryTaxonomies}>
            Retry
          </Button>
        </View>
      ) : null}

      {hasTaxonomiesData && taxonomies && occasionOptions.length === 0 ? (
        <Text variant="body" color="secondary">
          No options available right now.
        </Text>
      ) : null}

      {hasTaxonomiesData && taxonomies && occasionOptions.length > 0 ? (
        <View className="flex-row flex-wrap gap-2">
          {occasionOptions.map((option) => (
            <Badge
              key={option.key}
              testID={`edit-occasion-priority-${option.key}`}
              label={option.label}
              occasion={occasionBadgeColor(option.key, taxonomies)}
              selected={occasions.includes(option.key)}
              onPress={() => toggleOccasion(option.key)}
            />
          ))}
        </View>
      ) : null}

      {atCap ? (
        <Text variant="caption" color="secondary" className="mt-sm">
          You can select up to 3 occasions.
        </Text>
      ) : null}

      {mutation.isError ? (
        <View className="mb-sm mt-sm items-start">
          <Text variant="body" color="secondary">
            Couldn't save occasion priorities.
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
          accessibilityLabel="Save occasion priorities"
        >
          Save
        </Button>
      </View>
    </View>
  );
}
