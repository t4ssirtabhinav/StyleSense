import { useState } from 'react';
import { View } from 'react-native';
import { Badge, Button, Text } from '../../../components/ui';
import { BUDGET_RANGES } from '../onboarding.constants';
import { useUpdateBudgetRangeMutation } from '../onboarding.queries';
import type { BudgetRangeKey } from '../onboarding.types';

// (SS-007) Edit Preferences — budget range section. Single-select, static
// BUDGET_RANGES (per docs/tickets/SS-007-design.md's "Files to
// create/modify" #5). Local component state — see
// EditStyleKeywordsSection.tsx's header comment for why.
export interface EditBudgetRangeSectionProps {
  userId: string;
  initialBudgetRange: BudgetRangeKey | undefined;
}

export function EditBudgetRangeSection({
  userId,
  initialBudgetRange,
}: EditBudgetRangeSectionProps) {
  const [budgetRange, setBudgetRange] = useState<BudgetRangeKey | undefined>(
    initialBudgetRange,
  );
  const mutation = useUpdateBudgetRangeMutation();

  const handleSave = () => {
    if (!budgetRange) {
      return;
    }
    mutation.mutate({ userId, budgetRange });
  };

  return (
    <View className="p-md" testID="edit-budget-range-section">
      <Text variant="heading">Budget range</Text>
      <View className="mb-md mt-sm flex-row flex-wrap gap-2">
        {BUDGET_RANGES.map((option) => (
          <Badge
            key={option.key}
            label={option.label}
            selected={budgetRange === option.key}
            onPress={() => setBudgetRange(option.key)}
          />
        ))}
      </View>

      {mutation.isError ? (
        <View className="mb-sm items-start">
          <Text variant="body" color="secondary">
            Couldn't save budget range.
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
          disabled={!budgetRange}
          accessibilityLabel="Save budget range"
        >
          Save
        </Button>
      </View>
    </View>
  );
}
