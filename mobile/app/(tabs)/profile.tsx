import { useRouter } from 'expo-router';
import { View } from 'react-native';
import { Avatar, Button, Text } from '../../components/ui';
import { useAuthStore } from '../../features/auth/auth.store';
import { useUserGreetingQuery } from '../../features/home/home.queries';
import { StyleScoreCard } from '../../features/style-score/components/StyleScoreCard';

// Not a bare empty state (unlike Wardrobe/Discover/Style) — ships one real,
// functioning entry point: "Edit Preferences", closing BL-023's long-open
// gap now that a Profile tab finally exists to navigate from.
export default function ProfileScreen() {
  const router = useRouter();
  const session = useAuthStore((state) => state.session);
  const userId = session?.user.id;
  const greetingQuery = useUserGreetingQuery(userId);

  const handleEditPreferences = () => {
    router.push('/edit-preferences');
  };

  return (
    <View
      testID="profile-screen"
      className="flex-1 items-center justify-center gap-sm p-lg"
    >
      <Avatar name={greetingQuery.data ?? undefined} size="lg" />
      <Text variant="heading">Profile</Text>
      <StyleScoreCard variant="full" />
      <Button
        variant="primary"
        onPress={handleEditPreferences}
        accessibilityLabel="Edit Preferences"
      >
        Edit Preferences
      </Button>
      <Text variant="caption" color="muted" className="text-center">
        More profile features are coming soon.
      </Text>
    </View>
  );
}
