import { View } from 'react-native';
import { Badge, Button, Text } from '../../../components/ui';
import { useOccasionTaxonomy } from '../onboarding.queries';
import { useOnboardingStore } from '../onboarding.store';
import { TaxonomyChipsSkeleton } from './TaxonomyChipsSkeleton';

const OCCASION_TYPES_COUNT = 12;
const MAX_OCCASIONS = 3;

// (SS-025) Sources the 12 TOP-LEVEL active occasions from the `occasions`
// registry (was the retired 9-row `occasion_types` table). `parent_key IS
// NULL` is what keeps the wizard from flooding as the registry grows —
// inserting `ganesh_chaturthi` under `festival` reaches wardrobe tagging,
// filters and the AI vocabulary, and correctly does NOT appear here.
//
// Each chip now carries its registry `badge_color`. BL-008 (4 of 12
// occasions coloured, the rest neutral) is resolved structurally: the
// column is NOT NULL with a CHECK against Badge's four occasion tokens, so
// a colourless occasion is unrepresentable.
export function Step3OccasionPriorities() {
  const { topLevelOccasions, badgeColor, isLoading, isError, refetch } =
    useOccasionTaxonomy();

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

      {!isLoading && !isError && topLevelOccasions.length === 0 ? (
        <Text variant="body" color="secondary">
          No options available right now.
        </Text>
      ) : null}

      {!isLoading && !isError && topLevelOccasions.length > 0 ? (
        <View className="flex-row flex-wrap gap-2">
          {topLevelOccasions.map((option) => (
            <Badge
              key={option.key}
              testID={`occasion-priority-${option.key}`}
              label={option.label}
              occasion={badgeColor(option.key)}
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
