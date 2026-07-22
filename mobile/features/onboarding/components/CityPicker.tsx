import { forwardRef, useImperativeHandle, useRef, useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import {
  AppBottomSheet,
  type AppBottomSheetRef,
  Input,
  Text,
} from '../../../components/ui';
import { TOP_50_INDIAN_CITIES } from '../onboarding.constants';

export interface CityPickerProps {
  onSelect: (cityName: string) => void;
}

const OTHER_ROW_LABEL = 'Other';
// BL-007 (docs/BACKLOG.md, Open): this is the one place SS-004 reuses the
// same parked errorPlaceholder path Input.tsx already established — not a
// second error colour, and not a resolution of BL-007.
const OTHER_CITY_ERROR = 'Please enter your city name.';

// AppBottomSheet (reused from components/ui, same pattern as SS-003's
// CountryCodePicker) containing a search Input filtering
// TOP_50_INDIAN_CITIES by name, plus a final "Other" row. Per
// docs/tickets/SS-004-design.md's "Files to create/modify" #12.
export const CityPicker = forwardRef<AppBottomSheetRef, CityPickerProps>(
  ({ onSelect }, ref) => {
    const sheetRef = useRef<AppBottomSheetRef>(null);
    const [query, setQuery] = useState('');
    const [showOtherInput, setShowOtherInput] = useState(false);
    const [otherText, setOtherText] = useState('');

    useImperativeHandle(ref, () => ({
      present: () => sheetRef.current?.present(),
      dismiss: () => sheetRef.current?.dismiss(),
    }));

    const trimmedQuery = query.trim().toLowerCase();
    const filteredCities =
      trimmedQuery.length === 0
        ? TOP_50_INDIAN_CITIES
        : TOP_50_INDIAN_CITIES.filter((city) =>
            city.name.toLowerCase().includes(trimmedQuery),
          );

    const handleSelectCity = (cityName: string) => {
      onSelect(cityName);
      setShowOtherInput(false);
      setOtherText('');
      setQuery('');
      sheetRef.current?.dismiss();
    };

    const handleOtherTextChange = (text: string) => {
      setOtherText(text);
      onSelect(text);
    };

    return (
      <AppBottomSheet ref={sheetRef}>
        <Input
          variant="search"
          value={query}
          onChangeText={setQuery}
          placeholder="Search city"
        />
        <ScrollView className="mt-sm" testID="city-picker-list">
          {filteredCities.map((city) => (
            <Pressable
              key={city.id}
              onPress={() => handleSelectCity(city.name)}
              accessibilityRole="button"
              accessibilityLabel={city.name}
              className="py-sm"
            >
              <Text variant="body">{city.name}</Text>
            </Pressable>
          ))}
          <Pressable
            onPress={() => setShowOtherInput(true)}
            accessibilityRole="button"
            accessibilityLabel={OTHER_ROW_LABEL}
            className="py-sm"
          >
            <Text variant="body">{OTHER_ROW_LABEL}</Text>
          </Pressable>
          {showOtherInput ? (
            <View className="mt-sm">
              <Input
                variant="text"
                value={otherText}
                onChangeText={handleOtherTextChange}
                placeholder="Enter your city"
                error={
                  otherText.trim().length === 0 ? OTHER_CITY_ERROR : undefined
                }
                autoFocus
              />
            </View>
          ) : null}
        </ScrollView>
      </AppBottomSheet>
    );
  },
);

CityPicker.displayName = 'CityPicker';
