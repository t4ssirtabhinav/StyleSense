import { View } from 'react-native';
import { Badge, Button, Text } from '../../../components/ui';
import { WARDROBE_TYPES } from '../onboarding.constants';
import { useOnboardingTaxonomiesQuery } from '../onboarding.queries';
import { useOnboardingStore } from '../onboarding.store';
import { TaxonomyChipsSkeleton } from './TaxonomyChipsSkeleton';

const STYLE_KEYWORDS_COUNT = 9;

// (2026-07-13 revision) calls useOnboardingTaxonomiesQuery() itself — see
// docs/tickets/SS-004-design.md's "Loading/error/empty state pattern"
// section for why each step owns this call rather than the wizard shell
// hoisting one call and prop-drilling it down. Per "Files to
// create/modify" #15.
export function Step2StyleWardrobe() {
  const { data, isLoading, isError, isSuccess, refetch } =
    useOnboardingTaxonomiesQuery();

  const styles = useOnboardingStore((state) => state.styles);
  const toggleStyle = useOnboardingStore((state) => state.toggleStyle);
  const wardrobeType = useOnboardingStore((state) => state.wardrobeType);
  const setWardrobeType = useOnboardingStore((state) => state.setWardrobeType);

  // Fix pass 4, 2026-07-22 (SS-004 Fix 2): same pager-height cause as
  // Step1BasicProfile — heading + 2 chip groups (9 style keywords + 5
  // wardrobe types) is still visibly shorter than the pager's full height,
  // leaving the same top-glued/void-below symptom. `justify-center`
  // applied for consistency with Step1/Step3; unlike Step4's 12-swatch
  // grid, this step's content doesn't already fill the available height,
  // so centering doesn't introduce an awkward gap on both sides.
  return (
    <View className="flex-1 justify-center p-md">
      <Text variant="heading">What's your style?</Text>
      <Text variant="caption" color="secondary" className="mb-xs mt-md">
        Style keywords
      </Text>

      {isLoading ? (
        <TaxonomyChipsSkeleton count={STYLE_KEYWORDS_COUNT} />
      ) : null}

      {isError ? (
        <View className="items-start">
          <Text variant="body" color="secondary">
            Couldn't load style options.
          </Text>
          <Button variant="ghost" onPress={() => refetch()}>
            Retry
          </Button>
        </View>
      ) : null}

      {isSuccess && data.styleKeywords.length === 0 ? (
        <Text variant="body" color="secondary">
          No style options available right now.
        </Text>
      ) : null}

      {isSuccess && data.styleKeywords.length > 0 ? (
        <View className="flex-row flex-wrap gap-2">
          {data.styleKeywords.map((option) => (
            <Badge
              key={option.key}
              label={option.label}
              selected={styles.includes(option.key)}
              onPress={() => toggleStyle(option.key)}
            />
          ))}
        </View>
      ) : null}

      <Text variant="caption" color="secondary" className="mb-xs mt-md">
        Wardrobe type
      </Text>
      <View className="flex-row flex-wrap gap-2">
        {WARDROBE_TYPES.map((option) => (
          <Badge
            key={option.key}
            label={option.label}
            selected={wardrobeType === option.key}
            onPress={() => setWardrobeType(option.key)}
          />
        ))}
      </View>
    </View>
  );
}
