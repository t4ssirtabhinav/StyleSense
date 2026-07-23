import { Redirect } from 'expo-router';
import { ScrollView, View } from 'react-native';
import { Button, Card, Text } from '../components/ui';
import { useAuthStore } from '../features/auth/auth.store';
import { EditBudgetRangeSection } from '../features/onboarding/components/EditBudgetRangeSection';
import { EditFavouriteColoursSection } from '../features/onboarding/components/EditFavouriteColoursSection';
import { EditOccasionPrioritiesSection } from '../features/onboarding/components/EditOccasionPrioritiesSection';
import { EditStyleKeywordsSection } from '../features/onboarding/components/EditStyleKeywordsSection';
import { EditWardrobeTypeSection } from '../features/onboarding/components/EditWardrobeTypeSection';
import {
  useOnboardingProgressQuery,
  useOnboardingTaxonomiesQuery,
} from '../features/onboarding/onboarding.queries';

// (SS-007) Granular Preferences Editor. Per docs/tickets/SS-007-design.md's
// "Route placement" section: a deliberate top-level route (not
// app/(tabs)/profile/edit-preferences.tsx), following the same precedent as
// CLAUDE.md's documented outfit/[id].tsx / tryon/[outfitId].tsx — a
// full-screen destination reached *from* a tab but not itself a tab. Since
// this sits outside app/(tabs)/_layout.tsx's Auth Guard, it self-guards
// session exactly like (auth)/onboarding.tsx does.
export default function EditPreferencesScreen() {
  const session = useAuthStore((state) => state.session);
  const isSessionLoading = useAuthStore((state) => state.isSessionLoading);
  const userId = session?.user.id;

  const progressQuery = useOnboardingProgressQuery(userId);
  // Fetched once here and passed down to the 3 sections that need DB-backed
  // options (style keywords, occasion priorities, colours) rather than each
  // section re-calling the hook independently — this screen mounts all 5
  // sections simultaneously (unlike the wizard's pager, whose steps mount
  // one at a time), so one shared call avoids 3 redundant network requests.
  // See design doc's "Files to create/modify" #1.
  const taxonomiesQuery = useOnboardingTaxonomiesQuery();

  if (isSessionLoading) {
    return (
      <Card
        testID="edit-preferences-session-loading"
        variant="flat"
        className="m-md flex-1 items-center justify-center"
      >
        <Text variant="body">Loading…</Text>
      </Card>
    );
  }

  if (!session || !userId) {
    return <Redirect href="/login" />;
  }

  // Gate the 5 sections' mount on the progress fetch settling, rather than
  // syncing progressQuery.data into already-mounted sections via a
  // useEffect (CLAUDE.md bans useEffect for derived state) — each section
  // initializes its own local state once, at mount, from its slice of
  // stylePreferences, so it must not mount before that data has actually
  // arrived (or definitively failed to).
  if (progressQuery.isLoading) {
    return (
      <Card
        testID="edit-preferences-progress-loading"
        variant="flat"
        className="m-md flex-1 items-center justify-center"
      >
        <Text variant="body">Loading…</Text>
      </Card>
    );
  }

  const stylePreferences = progressQuery.data?.stylePreferences ?? null;
  // Edge case (design doc): a user who has never completed onboarding (or
  // reaches this screen some other way) is allowed in — every section below
  // remains editable, this banner is informational only, never a gate.
  const showIncompleteBanner =
    progressQuery.data?.onboardingCompleted === false;

  return (
    <ScrollView testID="edit-preferences-screen" className="flex-1">
      <View className="p-md">
        <Text variant="heading">Edit Preferences</Text>
      </View>

      {progressQuery.isError ? (
        <Card
          testID="edit-preferences-progress-error"
          variant="flat"
          className="mx-md mb-md"
        >
          <Text variant="body" color="secondary">
            Couldn't load your saved preferences. You can still edit and save
            below.
          </Text>
          <Button variant="ghost" onPress={() => progressQuery.refetch()}>
            Retry
          </Button>
        </Card>
      ) : null}

      {showIncompleteBanner ? (
        <Card
          testID="edit-preferences-incomplete-banner"
          variant="flat"
          className="mx-md mb-md"
        >
          <Text variant="body" color="secondary">
            Finish setting up your profile for the best recommendations.
          </Text>
        </Card>
      ) : null}

      <EditStyleKeywordsSection
        userId={userId}
        initialStyles={stylePreferences?.styles ?? []}
        taxonomies={taxonomiesQuery.data}
        isTaxonomiesLoading={taxonomiesQuery.isLoading}
        isTaxonomiesError={taxonomiesQuery.isError}
        onRetryTaxonomies={() => taxonomiesQuery.refetch()}
      />

      <EditWardrobeTypeSection
        userId={userId}
        initialWardrobeType={stylePreferences?.wardrobe_type}
      />

      <EditOccasionPrioritiesSection
        userId={userId}
        initialOccasions={stylePreferences?.occasions_priority ?? []}
        taxonomies={taxonomiesQuery.data}
        isTaxonomiesLoading={taxonomiesQuery.isLoading}
        isTaxonomiesError={taxonomiesQuery.isError}
        onRetryTaxonomies={() => taxonomiesQuery.refetch()}
      />

      <EditBudgetRangeSection
        userId={userId}
        initialBudgetRange={stylePreferences?.budget_range}
      />

      <EditFavouriteColoursSection
        userId={userId}
        initialColours={stylePreferences?.favourite_colours ?? []}
        taxonomies={taxonomiesQuery.data}
        isTaxonomiesLoading={taxonomiesQuery.isLoading}
        isTaxonomiesError={taxonomiesQuery.isError}
        onRetryTaxonomies={() => taxonomiesQuery.refetch()}
      />
    </ScrollView>
  );
}
