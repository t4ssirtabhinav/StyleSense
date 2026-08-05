import { useState } from 'react';
import { ActivityIndicator, View } from 'react-native';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  IconButton,
  Text,
} from '../../../components/ui';
import { useAuthStore } from '../../auth/auth.store';
import {
  NO_WEARS_HEADING,
  NO_WEARS_SUBTEXT,
  WEAR_DUPLICATE_DATE_MESSAGE,
  WEAR_DUPLICATE_DATE_OCCASION_MESSAGE,
  WEAR_OCCASION_NONE_CHIP_LABEL,
} from '../wardrobe.constants';
import {
  useDeleteWardrobeItemWear,
  useLogWardrobeItemWear,
  useOccasionOptions,
  useUpdateWardrobeItemWear,
  useWardrobeItemWearsQuery,
} from '../wardrobe.queries';
import type { WardrobeItemWearRow } from '../wardrobe.types';
import { WearDateField } from './WearDateField';
import { WearOccasionField } from './WearOccasionField';

export interface WearHistorySectionProps {
  itemId: string;
  purchaseDate: string | null;
  onBack: () => void;
}

// 'en-IN'/Asia/Kolkata -- CLAUDE.md's India-specific date rule, mirrors
// ItemDetailSheet's own formatLastWornDate.
function formatWornOn(iso: string): string {
  return new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(new Date(`${iso}T00:00:00Z`));
}

// Postgres unique_violation -- surfaced by PostgREST as { code: '23505' }.
// Never leaked to the UI as a raw error string (design doc's Edge Cases).
function isUniqueViolation(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    (error as { code?: unknown }).code === '23505'
  );
}

interface WearRowProps {
  wear: WardrobeItemWearRow;
  purchaseDate: string | null;
}

function WearRow({ wear, purchaseDate }: WearRowProps) {
  const [editing, setEditing] = useState(false);
  const [deleteArmed, setDeleteArmed] = useState(false);
  const [conflictError, setConflictError] = useState<string | undefined>(
    undefined,
  );
  // SS-035: local draft state so a date edit and an occasion edit can each
  // be applied independently while the other stays whatever it already was
  // -- neither write should silently clear the other.
  //
  // wear.occasion_key: WardrobeItemWearRow is `Tables<'wardrobe_item_wears'>`
  // (wardrobe.types.ts) -- a generated type. It picks this column up for
  // free once mobile/types/supabase.ts is regenerated against the pushed
  // migration (design §9 Q4, QA's job per §8 step 6); CLAUDE.md forbids
  // hand-editing the generated file or a local interface to work around it,
  // so this line does not typecheck until that regeneration happens, by
  // design (see this ticket's worklog).
  const [draftOccasionKey, setDraftOccasionKey] = useState<string | null>(
    wear.occasion_key ?? null,
  );
  const updateWear = useUpdateWardrobeItemWear();
  const deleteWear = useDeleteWardrobeItemWear();
  const occasionTaxonomy = useOccasionOptions();

  const wornOnLabel = formatWornOn(wear.worn_on);
  const occasionKey: string | null = wear.occasion_key ?? null;

  const handleUpdate = (isoDate: string) => {
    setConflictError(undefined);
    updateWear.mutate(
      {
        wearId: wear.id,
        itemId: wear.item_id,
        wornOn: isoDate,
        occasionKey: draftOccasionKey,
      },
      {
        onSuccess: () => setEditing(false),
        onError: (error) => {
          setConflictError(
            isUniqueViolation(error)
              ? draftOccasionKey
                ? WEAR_DUPLICATE_DATE_OCCASION_MESSAGE
                : WEAR_DUPLICATE_DATE_MESSAGE
              : 'Something went wrong. Please try again.',
          );
        },
      },
    );
  };

  const handleDelete = () => {
    if (!deleteArmed) {
      setDeleteArmed(true);
      return;
    }
    deleteWear.mutate({ wearId: wear.id, itemId: wear.item_id });
  };

  if (editing) {
    return (
      <Card
        variant="outlined"
        testID={`wear-row-${wear.id}`}
        className="mb-xs gap-xs"
      >
        <WearDateField
          value={wear.worn_on}
          purchaseDate={purchaseDate}
          onChange={handleUpdate}
        />
        <WearOccasionField
          value={draftOccasionKey}
          onChange={setDraftOccasionKey}
        />
        {conflictError ? (
          <Text variant="caption" color="secondary">
            {conflictError}
          </Text>
        ) : null}
        <Button
          variant="secondary"
          accessibilityLabel="Cancel editing this wear"
          onPress={() => setEditing(false)}
        >
          Cancel
        </Button>
      </Card>
    );
  }

  return (
    <Card
      variant="outlined"
      testID={`wear-row-${wear.id}`}
      className="mb-xs flex-row items-center justify-between"
    >
      <View className="gap-xs">
        <Text variant="body">{wornOnLabel}</Text>
        {occasionKey ? (
          <Badge
            testID={`wear-row-occasion-${wear.id}`}
            label={occasionTaxonomy.label(occasionKey)}
            occasion={occasionTaxonomy.badgeColor(occasionKey)}
          />
        ) : (
          <Text
            testID={`wear-row-no-occasion-${wear.id}`}
            variant="caption"
            color="secondary"
          >
            {WEAR_OCCASION_NONE_CHIP_LABEL}
          </Text>
        )}
      </View>
      <View className="flex-row gap-xs">
        <IconButton
          icon="create-outline"
          accessibilityLabel={`Edit wear on ${wornOnLabel}`}
          onPress={() => setEditing(true)}
        />
        <IconButton
          icon="trash-outline"
          accessibilityLabel={
            deleteArmed
              ? `Tap again to confirm delete of wear on ${wornOnLabel}`
              : `Delete wear on ${wornOnLabel}`
          }
          onPress={handleDelete}
        />
      </View>
    </Card>
  );
}

// Rendered inside ItemDetailSheet as a third mode ('wears'), per the design
// doc -- no new route, no nested bottom sheet (BL-010).
export function WearHistorySection({
  itemId,
  purchaseDate,
  onBack,
}: WearHistorySectionProps) {
  const userId = useAuthStore((state) => state.session?.user.id);
  const wearsQuery = useWardrobeItemWearsQuery(itemId);
  const logWear = useLogWardrobeItemWear();
  const [addingWear, setAddingWear] = useState(false);
  // SS-035: optional occasion for the "Add a wear" card. Stays null unless
  // the user picks one -- the quick path (WearDateField's Today/Yesterday
  // chips fire onChange immediately) still logs a wear with no occasion in
  // one tap, matching ItemDetailSheet's own one-tap default (BL-121).
  const [newWearOccasionKey, setNewWearOccasionKey] = useState<string | null>(
    null,
  );

  const handleAddWear = (isoDate: string) => {
    if (!userId) {
      return;
    }
    logWear.mutate(
      { itemId, userId, wornOn: isoDate, occasionKey: newWearOccasionKey },
      {
        onSuccess: () => {
          setAddingWear(false);
          setNewWearOccasionKey(null);
        },
      },
    );
  };

  const handleCancelAddWear = () => {
    setAddingWear(false);
    setNewWearOccasionKey(null);
  };

  return (
    <View>
      <View className="mb-sm flex-row items-center gap-xs">
        <IconButton
          icon="arrow-back"
          accessibilityLabel="Back to item details"
          onPress={onBack}
        />
        <Text variant="body" weight="bold">
          Wear history
        </Text>
      </View>

      {wearsQuery.isLoading ? (
        <View testID="wear-history-loading" className="items-center py-lg">
          <ActivityIndicator />
        </View>
      ) : null}

      {wearsQuery.isError ? (
        <Text testID="wear-history-error" variant="caption" color="secondary">
          Couldn't load wear history. Please try again.
        </Text>
      ) : null}

      {wearsQuery.isSuccess && wearsQuery.data.length === 0 ? (
        <EmptyState
          testID="wear-history-empty"
          icon="calendar-outline"
          heading={NO_WEARS_HEADING}
          subtext={NO_WEARS_SUBTEXT}
        />
      ) : null}

      {wearsQuery.isSuccess && wearsQuery.data.length > 0
        ? wearsQuery.data.map((wear) => (
            <WearRow key={wear.id} wear={wear} purchaseDate={purchaseDate} />
          ))
        : null}

      {addingWear ? (
        <Card variant="outlined" className="mt-sm gap-xs">
          <WearDateField
            value={null}
            purchaseDate={purchaseDate}
            onChange={handleAddWear}
          />
          <WearOccasionField
            value={newWearOccasionKey}
            onChange={setNewWearOccasionKey}
          />
          <Button
            variant="secondary"
            accessibilityLabel="Cancel adding a wear"
            onPress={handleCancelAddWear}
          >
            Cancel
          </Button>
        </Card>
      ) : (
        <Button
          variant="secondary"
          accessibilityLabel="Add a wear"
          onPress={() => setAddingWear(true)}
        >
          Add a wear
        </Button>
      )}
    </View>
  );
}
