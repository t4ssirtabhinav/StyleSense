import { forwardRef, useState } from 'react';
import { Pressable } from 'react-native';
import {
  AppBottomSheet,
  type AppBottomSheetRef,
  Input,
  Text,
} from '../../../components/ui';
import { WARDROBE_CATEGORIES } from '../wardrobe.constants';
import type { WardrobeCategory } from '../wardrobe.types';

export interface CategoryPickerProps {
  onSelect: (category: WardrobeCategory) => void;
}

// BottomSheet + searchable list over the 21-value WARDROBE_CATEGORIES, per
// docs/tickets/SS-013-design.md's CategoryPicker spec.
export const CategoryPicker = forwardRef<
  AppBottomSheetRef,
  CategoryPickerProps
>(({ onSelect }, ref) => {
  const [query, setQuery] = useState('');

  const visible = WARDROBE_CATEGORIES.filter((option) =>
    option.label.toLowerCase().includes(query.toLowerCase()),
  );

  const handleSelect = (category: WardrobeCategory) => {
    onSelect(category);
    if (ref && 'current' in ref) {
      ref.current?.dismiss();
    }
  };

  return (
    <AppBottomSheet ref={ref}>
      <Input
        variant="search"
        value={query}
        onChangeText={setQuery}
        placeholder="Search categories"
      />
      {visible.map((option) => (
        <Pressable
          key={option.value}
          testID={`category-row-${option.value}`}
          accessibilityRole="button"
          onPress={() => handleSelect(option.value)}
          className="py-sm"
        >
          <Text variant="body">{option.label}</Text>
        </Pressable>
      ))}
    </AppBottomSheet>
  );
});

CategoryPicker.displayName = 'CategoryPicker';
