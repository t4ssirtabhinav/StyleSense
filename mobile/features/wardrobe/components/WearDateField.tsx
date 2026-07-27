import { useState } from 'react';
import { View } from 'react-native';
import { Badge, Input } from '../../../components/ui';
import {
  WEAR_BEFORE_PURCHASE_DATE_MESSAGE,
  WEAR_FUTURE_DATE_MESSAGE,
  WEAR_INVALID_DATE_MESSAGE,
} from '../wardrobe.constants';

// SS-015: date entry without a native date-picker dependency (none is
// installed; @react-native-community/datetimepicker is a new native module
// with weak web support on this web-first app -- design doc's Open
// question #4). Two quick-pick Badges ("Today"/"Yesterday") plus a
// DD/MM/YYYY Input, validated locally against 'en-IN'/Asia/Kolkata "today"
// (CLAUDE.md's India-specific date rule) and (when provided) the item's
// purchase_date.

export interface WearDateFieldProps {
  /** ISO 'YYYY-MM-DD', or null for "not yet chosen". */
  value: string | null;
  onChange: (isoDate: string) => void;
  /** ISO 'YYYY-MM-DD', or null/undefined when the item has none. */
  purchaseDate?: string | null;
  label?: string;
}

const IST_DATE_FORMATTER = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Kolkata',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

// en-CA formats as YYYY-MM-DD, which is also a valid ISO date string --
// a well-known trick for getting a timezone-correct ISO date out of
// Intl.DateTimeFormat without a date library.
export function istTodayIso(): string {
  return IST_DATE_FORMATTER.format(new Date());
}

export function istYesterdayIso(): string {
  return IST_DATE_FORMATTER.format(new Date(Date.now() - 24 * 60 * 60 * 1000));
}

export function isoToDisplayDate(iso: string): string {
  const [year, month, day] = iso.split('-');
  return `${day}/${month}/${year}`;
}

// Rejects unparseable input and non-existent calendar dates (e.g.
// 31/02/2026) -- returns null for either rather than throwing.
export function displayDateToIso(display: string): string | null {
  const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(display.trim());
  if (!match) {
    return null;
  }
  const [, dd, mm, yyyy] = match;
  const day = Number(dd);
  const month = Number(mm);
  const year = Number(yyyy);
  if (month < 1 || month > 12 || day < 1 || day > 31) {
    return null;
  }

  const iso = `${yyyy}-${mm}-${dd}`;
  const parsed = new Date(`${iso}T00:00:00Z`);
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() + 1 !== month ||
    parsed.getUTCDate() !== day
  ) {
    return null;
  }
  return iso;
}

export function validateWearDateIso(
  iso: string,
  purchaseDate?: string | null,
): string | null {
  if (iso > istTodayIso()) {
    return WEAR_FUTURE_DATE_MESSAGE;
  }
  if (purchaseDate && iso < purchaseDate) {
    return WEAR_BEFORE_PURCHASE_DATE_MESSAGE;
  }
  return null;
}

export function WearDateField({
  value,
  onChange,
  purchaseDate,
  label = 'Date',
}: WearDateFieldProps) {
  const [text, setText] = useState(value ? isoToDisplayDate(value) : '');
  const [error, setError] = useState<string | undefined>(undefined);

  const applyIso = (iso: string) => {
    const validationError = validateWearDateIso(iso, purchaseDate);
    if (validationError) {
      setError(validationError);
      return;
    }
    setError(undefined);
    setText(isoToDisplayDate(iso));
    onChange(iso);
  };

  const handleTextChange = (nextText: string) => {
    setText(nextText);
    if (nextText.trim().length === 0) {
      setError(undefined);
      return;
    }
    const iso = displayDateToIso(nextText);
    if (!iso) {
      setError(WEAR_INVALID_DATE_MESSAGE);
      return;
    }
    applyIso(iso);
  };

  return (
    <View className="gap-xs">
      <View className="flex-row gap-xs">
        <Badge
          testID="wear-date-today"
          label="Today"
          selected={value === istTodayIso()}
          onPress={() => applyIso(istTodayIso())}
        />
        <Badge
          testID="wear-date-yesterday"
          label="Yesterday"
          selected={value === istYesterdayIso()}
          onPress={() => applyIso(istYesterdayIso())}
        />
      </View>
      <Input
        variant="text"
        label={label}
        placeholder="DD/MM/YYYY"
        value={text}
        onChangeText={handleTextChange}
        error={error}
      />
    </View>
  );
}
