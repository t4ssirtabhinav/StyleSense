import { useState } from 'react';
import { ActivityIndicator, View } from 'react-native';
import {
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
} from '../wardrobe.constants';
import {
  useDeleteWardrobeItemWear,
  useLogWardrobeItemWear,
  useUpdateWardrobeItemWear,
  useWardrobeItemWearsQuery,
} from '../wardrobe.queries';
import type { WardrobeItemWearRow } from '../wardrobe.types';
import { WearDateField } from './WearDateField';

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
  const updateWear = useUpdateWardrobeItemWear();
  const deleteWear = useDeleteWardrobeItemWear();

  const wornOnLabel = formatWornOn(wear.worn_on);

  const handleUpdate = (isoDate: string) => {
    setConflictError(undefined);
    updateWear.mutate(
      { wearId: wear.id, itemId: wear.item_id, wornOn: isoDate },
      {
        onSuccess: () => setEditing(false),
        onError: (error) => {
          setConflictError(
            isUniqueViolation(error)
              ? WEAR_DUPLICATE_DATE_MESSAGE
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
      <Text variant="body">{wornOnLabel}</Text>
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

  const handleAddWear = (isoDate: string) => {
    if (!userId) {
      return;
    }
    logWear.mutate(
      { itemId, userId, wornOn: isoDate },
      { onSuccess: () => setAddingWear(false) },
    );
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
          <Button
            variant="secondary"
            accessibilityLabel="Cancel adding a wear"
            onPress={() => setAddingWear(false)}
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
