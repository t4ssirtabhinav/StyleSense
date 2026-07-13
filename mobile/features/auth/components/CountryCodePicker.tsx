import { forwardRef, useImperativeHandle, useRef } from 'react';
import { Pressable } from 'react-native';
import {
  AppBottomSheet,
  type AppBottomSheetRef,
  Text,
} from '../../../components/ui';

export interface CountryCodePickerProps {
  onSelect?: (countryCode: string) => void;
}

const INDIA_COUNTRY_CODE = '+91';
const INDIA_ROW_LABEL = '🇮🇳 India +91';

// MVP scope: a single selectable row. No other country is specified anywhere
// in the ticket, schema, or backlog — do not invent a country list (see
// docs/tickets/SS-003-design.md's Open Questions #6).
export const CountryCodePicker = forwardRef<
  AppBottomSheetRef,
  CountryCodePickerProps
>(({ onSelect }, ref) => {
  const sheetRef = useRef<AppBottomSheetRef>(null);

  useImperativeHandle(ref, () => ({
    present: () => sheetRef.current?.present(),
    dismiss: () => sheetRef.current?.dismiss(),
  }));

  const handleSelect = () => {
    onSelect?.(INDIA_COUNTRY_CODE);
    sheetRef.current?.dismiss();
  };

  return (
    <AppBottomSheet ref={sheetRef}>
      <Pressable
        onPress={handleSelect}
        accessibilityRole="button"
        accessibilityLabel={INDIA_ROW_LABEL}
        className="flex-row items-center py-sm"
      >
        <Text variant="body">{INDIA_ROW_LABEL}</Text>
      </Pressable>
    </AppBottomSheet>
  );
});

CountryCodePicker.displayName = 'CountryCodePicker';
