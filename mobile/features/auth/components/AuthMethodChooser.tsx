import { useState } from 'react';
import { View } from 'react-native';
import { Button, Card, Text } from '../../../components/ui';
import type { AuthMethodDescriptor } from '../auth.methods';

export interface AuthMethodChooserProps {
  methods: readonly AuthMethodDescriptor[];
}

// SS-071: only ever mounted when AUTH_METHODS has 2+ entries — login.tsx
// renders the single descriptor's Component directly otherwise, with no
// chooser chrome at all (AC #1's "must look exactly as today" half). Local
// useState, not Zustand — nothing outside this screen needs the selection,
// same reasoning auth.store.ts's own comment already records for the
// phone/OTP fields.
export function AuthMethodChooser({ methods }: AuthMethodChooserProps) {
  const [selectedId, setSelectedId] = useState<string | undefined>(undefined);

  const selected = methods.find((method) => method.id === selectedId);

  if (selected) {
    const SelectedComponent = selected.Component;
    return (
      <View className="flex-1">
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

  return (
    <Card
      testID="auth-method-chooser"
      variant="flat"
      className="m-md flex-1 justify-center gap-sm"
    >
      <Text variant="heading" className="mb-md">
        Continue with
      </Text>
      {methods.map((method) => (
        <Button
          key={method.id}
          onPress={() => setSelectedId(method.id)}
          fullWidth
          accessibilityLabel={method.label}
        >
          {method.label}
        </Button>
      ))}
    </Card>
  );
}
