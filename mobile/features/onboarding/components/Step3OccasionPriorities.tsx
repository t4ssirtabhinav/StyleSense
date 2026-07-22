import { View } from 'react-native';
import { Badge, Button, Text } from '../../../components/ui';
import { useOnboardingTaxonomiesQuery } from '../onboarding.queries';
import { useOnboardingStore } from '../onboarding.store';
import { TaxonomyChipsSkeleton } from './TaxonomyChipsSkeleton';

const OCCASION_TYPES_COUNT = 9;
const MAX_OCCASIONS = 3;

// All 9 chips render with Badge's neutral style (no `occasion` prop) rather
// than inventing the 5 colours BL-008 still needs a product decision for —
// see docs/tickets/SS-004-design.md's "Concrete values" section. Per "Files
// to create/modify" #16.
export function Step3OccasionPriorities() {
  const { data, isLoading, isError, isSuccess, refetch } =
    useOnboardingTaxonomiesQuery();

  const occasionsPriority = useOnboardingStore(
    (state) => state.occasionsPriority,
  );
  const toggleOccasion = useOnboardingStore((state) => state.toggleOccasion);

  const atCap = occasionsPriority.length >= MAX_OCCASIONS;

  // Fix pass 4, 2026-07-22 (SS-004 Fix 2): same pager-height cause as
  // Step1BasicProfile — this step (heading + a single 9-chip grid) is one
  // of the two steps the reported "floating cluster with a void beneath"
  // complaint named directly, being the sparsest alongside Step1.
  // `justify-center` distributes the empty space evenly above/below
  // instead of leaving it all glued beneath the content.
  return (
    <View className="flex-1 justify-center p-md">
      <Text variant="heading">When do you dress up most?</Text>
      <Text variant="caption" color="secondary" className="mb-xs mt-md">
        Pick up to 3 occasions
      </Text>

      {isLoading ? (
        <TaxonomyChipsSkeleton count={OCCASION_TYPES_COUNT} />
      ) : null}

      {isError ? (
        <View className="items-start">
          <Text variant="body" color="secondary">
            Couldn't load occasion options.
          </Text>
          <Button variant="ghost" onPress={() => refetch()}>
            Retry
          </Button>
        </View>
      ) : null}

      {isSuccess && data.occasionTypes.length === 0 ? (
        <Text variant="body" color="secondary">
          No options available right now.
        </Text>
      ) : null}

      {isSuccess && data.occasionTypes.length > 0 ? (
        <View className="flex-row flex-wrap gap-2">
          {data.occasionTypes.map((option) => (
            <Badge
              key={option.key}
              label={option.label}
              selected={occasionsPriority.includes(option.key)}
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
    </View>
  );
}
