import { useState } from 'react';
import { Pressable } from 'react-native';
import { Text } from '../../../components/ui';

export interface ReasoningDisclosureProps {
  rationale: string;
  testID?: string;
}

// Collapsed 2-line snippet -> expanded full rationale (AC #3). The
// rationale renders identically whether it's LLM prose or the rule-based
// degrade text (E0 tier, budget-denied, or SS-020's latency timeout,
// `BL-139`'s "expected path", not a failure) -- no "AI unavailable" badge,
// no visual second-class treatment (design edge cases).
export function ReasoningDisclosure({
  rationale,
  testID,
}: ReasoningDisclosureProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Pressable
      testID={testID ?? 'reasoning-disclosure'}
      accessibilityRole="button"
      accessibilityLabel={
        expanded ? 'Collapse styling notes' : 'Expand styling notes'
      }
      onPress={() => setExpanded((prev) => !prev)}
    >
      <Text
        variant="caption"
        color="secondary"
        numberOfLines={expanded ? undefined : 2}
      >
        {rationale}
      </Text>
    </Pressable>
  );
}
