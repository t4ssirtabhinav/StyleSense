import { useState } from 'react';
import { View } from 'react-native';
import { Badge, Button, Text } from '../../../components/ui';
import { WARDROBE_TYPES } from '../onboarding.constants';
import { useUpdateWardrobeTypeMutation } from '../onboarding.queries';
import type { WardrobeTypeKey } from '../onboarding.types';

// (SS-007) Edit Preferences — wardrobe type section. Single-select, static
// WARDROBE_TYPES (per docs/tickets/SS-007-design.md's "Files to
// create/modify" #3). Local component state — see
// EditStyleKeywordsSection.tsx's header comment for why.
export interface EditWardrobeTypeSectionProps {
  userId: string;
  initialWardrobeType: WardrobeTypeKey | undefined;
}

export function EditWardrobeTypeSection({
  userId,
  initialWardrobeType,
}: EditWardrobeTypeSectionProps) {
  const [wardrobeType, setWardrobeType] = useState<WardrobeTypeKey | undefined>(
    initialWardrobeType,
  );
  const mutation = useUpdateWardrobeTypeMutation();

  const handleSave = () => {
    if (!wardrobeType) {
      return;
    }
    mutation.mutate({ userId, wardrobeType });
  };

  return (
    <View className="p-md" testID="edit-wardrobe-type-section">
      <Text variant="heading">Wardrobe type</Text>
      <View className="mb-md mt-sm flex-row flex-wrap gap-2">
        {WARDROBE_TYPES.map((option) => (
          <Badge
            key={option.key}
            label={option.label}
            selected={wardrobeType === option.key}
            onPress={() => setWardrobeType(option.key)}
          />
        ))}
      </View>

      {mutation.isError ? (
        <View className="mb-sm items-start">
          <Text variant="body" color="secondary">
            Couldn't save wardrobe type.
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
          disabled={!wardrobeType}
          accessibilityLabel="Save wardrobe type"
        >
          Save
        </Button>
      </View>
    </View>
  );
}
