import { View } from 'react-native';
import { Button, Card, Text } from '../../../components/ui';

export interface ResumePromptProps {
  /** Scrolls the pager to index 1 (Step 2) after pre-filling the store. */
  onContinue: () => void;
  /** Routes home without completing onboarding. */
  onSkip: () => void;
}

// Shown before Step 1 when a returning user has onboarding_completed: false
// AND already has a non-null full_name (i.e. got past Step 1 before
// abandoning) — per docs/tickets/SS-004-design.md's "Files to
// create/modify" #11 and "Incremental save" section.
export function ResumePrompt({ onContinue, onSkip }: ResumePromptProps) {
  return (
    <Card testID="resume-prompt" variant="flat" className="m-md items-center">
      <Text variant="heading">Welcome back!</Text>
      <Text variant="body" className="mt-sm text-center">
        Looks like you started setting up your style profile. Want to pick up
        where you left off?
      </Text>
      <View className="mt-md w-full">
        <Button onPress={onContinue} fullWidth>
          Continue Setup
        </Button>
      </View>
      <View className="mt-sm w-full">
        <Button variant="ghost" onPress={onSkip} fullWidth>
          Skip for now
        </Button>
      </View>
    </Card>
  );
}
