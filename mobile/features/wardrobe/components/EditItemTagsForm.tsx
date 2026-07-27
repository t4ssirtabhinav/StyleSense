import { useRef, useState } from 'react';
import { View } from 'react-native';
import {
  type AppBottomSheetRef,
  Badge,
  Button,
  IconButton,
  Input,
  Text,
} from '../../../components/ui';
import {
  MAX_USER_NOTES_LENGTH,
  OCCASION_BADGE_COLOR_MAP,
  OCCASION_TYPES,
  SEASON_TAGS,
} from '../wardrobe.constants';
import {
  useSaveWardrobeItemDetails,
  useSaveWardrobeItemTags,
} from '../wardrobe.queries';
import type {
  GarmentTagsDraft,
  OccasionType,
  SeasonTag,
  WardrobeItemDetailsDraft,
} from '../wardrobe.types';
import { CategoryPicker } from './CategoryPicker';
import { WearDateField } from './WearDateField';

export interface EditItemTagsFormProps {
  itemId: string;
  initialTags: GarmentTagsDraft;
  initialDetails: WardrobeItemDetailsDraft;
  onSaved: () => void;
  onCancel: () => void;
}

// ALWAYS ₹1,23,456 Indian numbering -- CLAUDE.md's India-specific currency
// rule. Whole rupees, not paise (design doc's Open question #5).
function formatIndianRupeesForInput(amount: number | null): string {
  if (amount == null) {
    return '';
  }
  return new Intl.NumberFormat('en-IN').format(amount);
}

function parseIndianRupeesInput(text: string): number | null {
  const digitsOnly = text.replace(/[^\d]/g, '');
  if (digitsOnly.length === 0) {
    return null;
  }
  return Number(digitsOnly);
}

function toggleInArray<T>(list: T[], value: T): T[] {
  return list.includes(value)
    ? list.filter((item) => item !== value)
    : [...list, value];
}

// Rendered inside ItemDetailSheet in edit mode. Reuses SS-013's
// CategoryPicker (imported, not duplicated) -- per docs/tickets/
// SS-014-design.md's Files section.
export function EditItemTagsForm({
  itemId,
  initialTags,
  initialDetails,
  onSaved,
  onCancel,
}: EditItemTagsFormProps) {
  const [draft, setDraft] = useState<GarmentTagsDraft>(initialTags);
  const [details, setDetails] =
    useState<WardrobeItemDetailsDraft>(initialDetails);
  const [saveError, setSaveError] = useState<string | undefined>(undefined);
  const categoryPickerRef = useRef<AppBottomSheetRef>(null);
  const saveTagsMutation = useSaveWardrobeItemTags();
  const saveDetailsMutation = useSaveWardrobeItemDetails();

  const toggleOccasion = (occasion: OccasionType) => {
    setDraft((current) => ({
      ...current,
      occasionTags: toggleInArray(current.occasionTags, occasion),
    }));
  };

  const toggleSeason = (season: SeasonTag) => {
    setDraft((current) => ({
      ...current,
      seasonTags: toggleInArray(current.seasonTags, season),
    }));
  };

  // Save fires two UPDATEs against the same row (disjoint column sets, so
  // neither clobbers the other) -- both must succeed before onSaved fires.
  // If the second fails after the first succeeded, the draft is kept and a
  // retryable error is shown rather than closing on a partial save (design
  // doc's Edge Cases: "Concurrent edit of tags + details").
  const handleSave = () => {
    setSaveError(undefined);
    saveTagsMutation.mutate(
      { itemId, tags: draft },
      {
        onSuccess: () => {
          saveDetailsMutation.mutate(
            { itemId, details },
            {
              onSuccess: onSaved,
              onError: () => {
                setSaveError(
                  'Tags saved, but the details failed to save. Please try again.',
                );
              },
            },
          );
        },
        onError: () => {
          setSaveError('Failed to save. Please try again.');
        },
      },
    );
  };

  const isSaving = saveTagsMutation.isPending || saveDetailsMutation.isPending;
  const notesLength = details.userNotes?.length ?? 0;

  return (
    <>
      <View className="mb-sm flex-row items-center gap-xs">
        <IconButton
          icon="arrow-back"
          accessibilityLabel="Back to item details"
          onPress={onCancel}
        />
        <Text variant="body" weight="bold">
          Edit item
        </Text>
      </View>

      <Button
        variant="secondary"
        accessibilityLabel="Choose category"
        onPress={() => categoryPickerRef.current?.present()}
      >
        {draft.category ?? 'Choose category'}
      </Button>
      <CategoryPicker
        ref={categoryPickerRef}
        onSelect={(category) =>
          setDraft((current) => ({ ...current, category }))
        }
      />

      <Input
        variant="text"
        label="Subcategory"
        value={draft.subcategory ?? ''}
        onChangeText={(text) =>
          setDraft((current) => ({ ...current, subcategory: text }))
        }
      />
      <View className="flex-row gap-sm">
        <View className="flex-1">
          <Input
            variant="text"
            label="Primary colour"
            value={draft.colorPrimary ?? ''}
            onChangeText={(text) =>
              setDraft((current) => ({ ...current, colorPrimary: text }))
            }
          />
        </View>
        <View className="flex-1">
          <Input
            variant="text"
            label="Secondary colour"
            value={draft.colorSecondary ?? ''}
            onChangeText={(text) =>
              setDraft((current) => ({ ...current, colorSecondary: text }))
            }
          />
        </View>
      </View>
      <View className="flex-row gap-sm">
        <View className="flex-1">
          <Input
            variant="text"
            label="Pattern"
            value={draft.pattern ?? ''}
            onChangeText={(text) =>
              setDraft((current) => ({ ...current, pattern: text }))
            }
          />
        </View>
        <View className="flex-1">
          <Input
            variant="text"
            label="Fabric"
            value={draft.fabric ?? ''}
            onChangeText={(text) =>
              setDraft((current) => ({ ...current, fabric: text }))
            }
          />
        </View>
      </View>

      <View className="mt-sm gap-xs">
        <Text variant="caption" color="secondary">
          Occasion
        </Text>
        <View
          testID="edit-occasion-badges-row"
          className="flex-row flex-wrap gap-xs"
        >
          {OCCASION_TYPES.map((occasion) => (
            <Badge
              key={occasion}
              testID={`edit-occasion-badge-${occasion}`}
              label={occasion}
              occasion={OCCASION_BADGE_COLOR_MAP[occasion]}
              selected={draft.occasionTags.includes(occasion)}
              onPress={() => toggleOccasion(occasion)}
            />
          ))}
        </View>
      </View>

      <View className="mt-sm gap-xs">
        <Text variant="caption" color="secondary">
          Season
        </Text>
        <View
          testID="edit-season-badges-row"
          className="flex-row flex-wrap gap-xs"
        >
          {SEASON_TAGS.map((season) => (
            <Badge
              key={season}
              testID={`edit-season-badge-${season}`}
              label={season}
              selected={draft.seasonTags.includes(season)}
              onPress={() => toggleSeason(season)}
            />
          ))}
        </View>
      </View>

      {/* SS-015: brand/purchase_price/purchase_date/user_notes -- the
       * fields the raw ticket named but SS-014 never built. */}
      <View className="mt-sm gap-xs">
        <Input
          variant="text"
          label="Brand"
          value={details.brand ?? ''}
          onChangeText={(text) =>
            setDetails((current) => ({ ...current, brand: text || null }))
          }
        />
        <Input
          variant="text"
          label="Purchase price (₹)"
          placeholder="0"
          value={formatIndianRupeesForInput(details.purchasePrice)}
          onChangeText={(text) =>
            setDetails((current) => ({
              ...current,
              purchasePrice: parseIndianRupeesInput(text),
            }))
          }
        />
        <WearDateField
          label="Purchase date"
          value={details.purchaseDate}
          onChange={(isoDate) =>
            setDetails((current) => ({ ...current, purchaseDate: isoDate }))
          }
        />
        <Input
          variant="text"
          label="Notes"
          multiline
          maxLength={MAX_USER_NOTES_LENGTH}
          value={details.userNotes ?? ''}
          onChangeText={(text) =>
            setDetails((current) => ({ ...current, userNotes: text || null }))
          }
        />
        <Text variant="caption" color="secondary">
          {`${notesLength}/${MAX_USER_NOTES_LENGTH}`}
        </Text>
      </View>

      {saveError ? (
        <Text testID="edit-item-save-error" variant="caption" color="secondary">
          {saveError}
        </Text>
      ) : null}

      <Button
        variant="primary"
        accessibilityLabel="Save"
        loading={isSaving}
        onPress={handleSave}
      >
        Save
      </Button>
    </>
  );
}
