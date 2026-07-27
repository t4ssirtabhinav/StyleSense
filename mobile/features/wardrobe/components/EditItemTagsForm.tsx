import { useRef, useState } from 'react';
import { View } from 'react-native';
import {
  type AppBottomSheetRef,
  Badge,
  Button,
  Input,
  Text,
} from '../../../components/ui';
import {
  OCCASION_BADGE_COLOR_MAP,
  OCCASION_TYPES,
  SEASON_TAGS,
} from '../wardrobe.constants';
import { useSaveWardrobeItemTags } from '../wardrobe.queries';
import type {
  GarmentTagsDraft,
  OccasionType,
  SeasonTag,
} from '../wardrobe.types';
import { CategoryPicker } from './CategoryPicker';

export interface EditItemTagsFormProps {
  itemId: string;
  initialTags: GarmentTagsDraft;
  onSaved: () => void;
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
  onSaved,
}: EditItemTagsFormProps) {
  const [draft, setDraft] = useState<GarmentTagsDraft>(initialTags);
  const categoryPickerRef = useRef<AppBottomSheetRef>(null);
  const saveMutation = useSaveWardrobeItemTags();

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

  const handleSave = () => {
    saveMutation.mutate({ itemId, tags: draft }, { onSuccess: onSaved });
  };

  return (
    <>
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

      <Button
        variant="primary"
        accessibilityLabel="Save"
        loading={saveMutation.isPending}
        onPress={handleSave}
      >
        Save
      </Button>
    </>
  );
}
