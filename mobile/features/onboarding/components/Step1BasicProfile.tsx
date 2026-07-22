import { useRef } from 'react';
import { Pressable, View } from 'react-native';
import {
  type AppBottomSheetRef,
  Badge,
  Input,
  Text,
} from '../../../components/ui';
import { GENDER_OPTIONS } from '../onboarding.constants';
import { useOnboardingStore } from '../onboarding.store';
import { CityPicker } from './CityPicker';

// Name (Input variant="text"), gender (4 single-select Badge chips), city
// (CityPicker trigger + selected value display). Per
// docs/tickets/SS-004-design.md's "Files to create/modify" #14.
export function Step1BasicProfile() {
  const fullName = useOnboardingStore((state) => state.fullName);
  const setFullName = useOnboardingStore((state) => state.setFullName);
  const gender = useOnboardingStore((state) => state.gender);
  const setGender = useOnboardingStore((state) => state.setGender);
  const city = useOnboardingStore((state) => state.city);
  const setCity = useOnboardingStore((state) => state.setCity);

  const cityPickerRef = useRef<AppBottomSheetRef>(null);

  // Fix pass 4, 2026-07-22 (SS-004 Fix 2): the FlashList pager
  // (app/(auth)/onboarding.tsx) requires each step to occupy the pager's
  // full height for paging/snapping to work, so this step's content area
  // is much taller than its 3 fields (name/gender/city) need — without
  // vertical alignment, `justify-start` (RN's default) glues the fields to
  // the top and leaves a large, visually empty gap above the pinned
  // footer. Of the four steps, this one has the sparsest content, so
  // `justify-center` is applied straightforwardly (no risk of an
  // already-full step ending up awkwardly centered with big gaps on both
  // sides — see Step4BudgetColours, which is left unchanged for that
  // reason).
  return (
    <View className="flex-1 justify-center p-md">
      <Input
        variant="text"
        label="Full name"
        value={fullName}
        onChangeText={setFullName}
        placeholder="Your name"
      />
      <Text variant="caption" color="secondary" className="mb-xs mt-md">
        Gender
      </Text>
      <View className="flex-row flex-wrap gap-2">
        {GENDER_OPTIONS.map((option) => (
          <Badge
            key={option.key}
            label={option.label}
            selected={gender === option.key}
            onPress={() => setGender(option.key)}
          />
        ))}
      </View>
      <Text variant="caption" color="secondary" className="mb-xs mt-md">
        City
      </Text>
      <Pressable
        onPress={() => cityPickerRef.current?.present()}
        accessibilityRole="button"
        accessibilityLabel="Select city"
        className="rounded-md border border-textMuted px-md py-sm"
      >
        <Text variant="body">
          {city.length > 0 ? city : 'Select your city'}
        </Text>
      </Pressable>
      <CityPicker ref={cityPickerRef} onSelect={setCity} />
    </View>
  );
}
