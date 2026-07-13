import { useRouter } from 'expo-router';
import { View } from 'react-native';
import { Button, Card, Text } from '../../components/ui';

// Disposable placeholder — same pattern SS-008's Architect used for the old
// top-level app/index.tsx (see docs/tickets/SS-008-design.md's migration
// decision). A screen has to exist at this route or the post-auth "new
// user" redirect (app/(auth)/verify-otp.tsx) 404s; full onboarding logic is
// SS-004's job entirely. Do not add real onboarding logic here — flag this
// file explicitly to whoever reviews the PR as disposable.
export default function OnboardingScreen() {
  const router = useRouter();

  return (
    <Card
      testID="onboarding-screen"
      variant="flat"
      className="m-md flex-1 items-center justify-center"
    >
      <Text variant="heading">Welcome to StyleSense</Text>
      <Text variant="body" className="mt-sm">
        Onboarding coming soon.
      </Text>
      <View className="mt-md">
        <Button onPress={() => router.replace('/')}>Continue</Button>
      </View>
    </Card>
  );
}
