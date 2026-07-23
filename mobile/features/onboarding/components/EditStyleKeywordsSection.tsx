import { useState } from 'react';
import { View } from 'react-native';
import { Badge, Button, Text } from '../../../components/ui';
import { useUpdateStyleKeywordsMutation } from '../onboarding.queries';
import type {
  OnboardingTaxonomies,
  StyleKeywordKey,
} from '../onboarding.types';
import { TaxonomyChipsSkeleton } from './TaxonomyChipsSkeleton';

const STYLE_KEYWORDS_COUNT = 9;

// (SS-007) Edit Preferences — style keywords section. Multi-select, no cap
// (per docs/tickets/SS-007-design.md's "Files to create/modify" #2). Local
// component state, not onboarding.store.ts — see design doc's "Why plain
// component state" section: this section is independently editable and
// independently saved, with no cross-section shared state to justify a
// store, and reusing the wizard's store risks a wizard-in-progress and an
// open Edit Preferences draft clobbering each other.
export interface EditStyleKeywordsSectionProps {
  userId: string;
  initialStyles: StyleKeywordKey[];
  taxonomies: OnboardingTaxonomies | undefined;
  isTaxonomiesLoading: boolean;
  isTaxonomiesError: boolean;
  onRetryTaxonomies: () => void;
}

export function EditStyleKeywordsSection({
  userId,
  initialStyles,
  taxonomies,
  isTaxonomiesLoading,
  isTaxonomiesError,
  onRetryTaxonomies,
}: EditStyleKeywordsSectionProps) {
  const [styles, setStyles] = useState<StyleKeywordKey[]>(initialStyles);
  const mutation = useUpdateStyleKeywordsMutation();

  const toggleStyle = (key: StyleKeywordKey) => {
    setStyles((current) =>
      current.includes(key)
        ? current.filter((existing) => existing !== key)
        : [...current, key],
    );
  };

  // react-query's mutate() is fire-and-forget (errors surface via
  // mutation.isError/mutation.error, not a thrown exception) — same
  // no-try/catch convention already used by (auth)/onboarding.tsx's
  // handleNext/handleGetStarted for the identical reason.
  const handleSave = () => {
    mutation.mutate({ userId, styles });
  };

  const hasTaxonomiesData = !isTaxonomiesLoading && !isTaxonomiesError;

  return (
    <View className="p-md" testID="edit-style-keywords-section">
      <Text variant="heading">Style keywords</Text>

      {isTaxonomiesLoading ? (
        <TaxonomyChipsSkeleton count={STYLE_KEYWORDS_COUNT} />
      ) : null}

      {isTaxonomiesError ? (
        <View className="items-start">
          <Text variant="body" color="secondary">
            Couldn't load style options.
          </Text>
          <Button variant="ghost" onPress={onRetryTaxonomies}>
            Retry
          </Button>
        </View>
      ) : null}

      {hasTaxonomiesData &&
      taxonomies &&
      taxonomies.styleKeywords.length === 0 ? (
        <Text variant="body" color="secondary">
          No style options available right now.
        </Text>
      ) : null}

      {hasTaxonomiesData &&
      taxonomies &&
      taxonomies.styleKeywords.length > 0 ? (
        <View className="mb-md flex-row flex-wrap gap-2">
          {taxonomies.styleKeywords.map((option) => (
            <Badge
              key={option.key}
              label={option.label}
              selected={styles.includes(option.key)}
              onPress={() => toggleStyle(option.key)}
            />
          ))}
        </View>
      ) : null}

      {mutation.isError ? (
        <View className="mb-sm items-start">
          <Text variant="body" color="secondary">
            Couldn't save style keywords.
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
          accessibilityLabel="Save style keywords"
        >
          Save
        </Button>
      </View>
    </View>
  );
}
