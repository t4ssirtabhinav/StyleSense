import { useState } from 'react';
import { View } from 'react-native';
import { Button } from '../../../components/ui';
import type { AuthMethodDescriptor } from '../auth.methods';

export interface AuthMethodChooserProps {
  methods: readonly AuthMethodDescriptor[];
}

// SS-071/SS-072 (Deviation 2): only ever mounted when AUTH_METHODS has 2+
// entries — login.tsx renders the single descriptor's Component directly
// otherwise, with no chooser chrome at all (AC #1's "must look exactly as
// today" half).
//
// Reshaped in SS-072 from a flat button menu to "primary method inline by
// default, secondary methods as buttons below it" — a menu has no
// "default" and fails AC #1's "phone remains visually primary/default",
// and it silently changed what a bare /login mount renders, breaking
// __tests__/app/(auth)/login.test.tsx (SS-003's original suite, which
// SS-071 went to deliberate lengths to keep passing unmodified). Array
// ORDER is primacy (auth.methods.ts's own comment) — methods[0] is always
// the default, every other entry is a secondary button, with no new
// descriptor field.
//
// Local useState, not Zustand — nothing outside this screen needs the
// selection, same reasoning auth.store.ts's own comment already records
// for the phone/OTP fields. `undefined` means "showing the primary
// method"; selecting a non-primary id shows that method instead; Back
// returns to `undefined`, i.e. back to the primary.
export function AuthMethodChooser({ methods }: AuthMethodChooserProps) {
  const [selectedId, setSelectedId] = useState<string | undefined>(undefined);

  const primary = methods[0];
  const secondaryMethods = methods.slice(1);
  const selected = secondaryMethods.find((method) => method.id === selectedId);

  if (selected) {
    const SelectedComponent = selected.Component;
    return (
      <View className="flex-1" testID="auth-method-chooser">
        <SelectedComponent />
        <View className="mx-md">
          <Button
            variant="ghost"
            onPress={() => setSelectedId(undefined)}
            accessibilityLabel="Back"
          >
            Back
          </Button>
        </View>
      </View>
    );
  }

  const PrimaryComponent = primary.Component;
  return (
    <View className="flex-1" testID="auth-method-chooser">
      <PrimaryComponent />
      {secondaryMethods.length > 0 ? (
        <View className="mx-md gap-sm">
          {secondaryMethods.map((method) => (
            <Button
              key={method.id}
              variant="secondary"
              onPress={() => setSelectedId(method.id)}
              fullWidth
              accessibilityLabel={method.label}
            >
              {method.label}
            </Button>
          ))}
        </View>
      ) : null}
    </View>
  );
}
