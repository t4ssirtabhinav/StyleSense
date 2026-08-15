import { useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';
import { Avatar, Button, Text } from '../../components/ui';
import { ANALYTICS_EVENTS } from '../../constants/analyticsEvents';
import { useSignOutMutation } from '../../features/auth/auth.queries';
import { useAuthStore } from '../../features/auth/auth.store';
import { useUserGreetingQuery } from '../../features/home/home.queries';
import { StyleScoreCard } from '../../features/style-score/components/StyleScoreCard';
import { useAnalytics } from '../../hooks/useAnalytics';

// Not a bare empty state (unlike Wardrobe/Discover/Style) — ships one real,
// functioning entry point: "Edit Preferences", closing BL-023's long-open
// gap now that a Profile tab finally exists to navigate from.
//
// SS-071: adds Sign Out, the app's first sign-out surface (BL-167). No
// Dialog/Modal/Alert primitive exists in components/ui/ (verified —
// logged as BL-179, not built here), so confirmation is a two-step inline
// swap rather than a native Alert.alert (not web-friendly; this app is
// web-first).
export default function ProfileScreen() {
  const router = useRouter();
  const session = useAuthStore((state) => state.session);
  const userId = session?.user.id;
  const greetingQuery = useUserGreetingQuery(userId);
  const signOutMutation = useSignOutMutation();
  const { track } = useAnalytics();
  const [isConfirmingSignOut, setIsConfirmingSignOut] = useState(false);

  const handleEditPreferences = () => {
    router.push('/edit-preferences');
  };

  const handleSignOutPress = () => {
    setIsConfirmingSignOut(true);
  };

  const handleCancelSignOut = () => {
    setIsConfirmingSignOut(false);
  };

  const handleConfirmSignOut = () => {
    signOutMutation.mutate(undefined, {
      onSuccess: () => {
        track(ANALYTICS_EVENTS.SIGN_OUT, { method: 'phone_otp' });
        router.replace('/login');
      },
    });
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
      {isConfirmingSignOut ? (
        <View testID="sign-out-confirm" className="items-center gap-sm">
          <Text variant="body">Sign out of StyleSense?</Text>
          <View className="flex-row gap-sm">
            <Button
              variant="secondary"
              onPress={handleConfirmSignOut}
              disabled={signOutMutation.isPending}
              loading={signOutMutation.isPending}
              accessibilityLabel="Confirm Sign Out"
            >
              Sign Out
            </Button>
            <Button
              variant="ghost"
              onPress={handleCancelSignOut}
              disabled={signOutMutation.isPending}
              accessibilityLabel="Cancel"
            >
              Cancel
            </Button>
          </View>
        </View>
      ) : (
        <Button
          variant="secondary"
          onPress={handleSignOutPress}
          accessibilityLabel="Sign Out"
        >
          Sign Out
        </Button>
      )}
      <Text variant="caption" color="muted" className="text-center">
        More profile features are coming soon.
      </Text>
    </View>
  );
}
