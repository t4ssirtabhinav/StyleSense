import { Redirect, Tabs } from 'expo-router';
import { Card, Text } from '../../components/ui';
import { useAuthStore } from '../../features/auth/auth.store';
import { CustomTabBar } from '../../features/navigation/components/CustomTabBar';
import { TAB_CONFIG } from '../../features/navigation/navigation.constants';

// The Auth Guard wrapping the (tabs) route group. SS-005 (Home Screen Shell
// + Bottom Tab Navigation) replaces the previous <Slot /> placeholder with
// the real 5-tab <Tabs> navigator + custom tab bar, once a valid session
// exists — the guard logic above it (loading Card / <Redirect>) is
// unchanged.
export default function TabsLayout() {
  const session = useAuthStore((state) => state.session);
  const isSessionLoading = useAuthStore((state) => state.isSessionLoading);

  // `isSessionLoading` must default to true (see auth.store.ts) — this
  // guards the first-render race where hooks/useAuth.ts's initial
  // getSession() call is still in flight, avoiding a one-frame
  // flash-redirect to /login for users who actually have a valid persisted
  // session.
  if (isSessionLoading) {
    return (
      <Card
        testID="auth-guard-loading"
        variant="flat"
        className="m-md flex-1 items-center justify-center"
      >
        <Text variant="body">Loading…</Text>
      </Card>
    );
  }

  if (!session) {
    return <Redirect href="/login" />;
  }

  return (
    <Tabs
      screenOptions={{ headerShown: false }}
      tabBar={(props) => <CustomTabBar {...props} />}
    >
      {TAB_CONFIG.map((tab) => (
        <Tabs.Screen
          key={tab.name}
          name={tab.name}
          options={{ title: tab.label }}
        />
      ))}
    </Tabs>
  );
}
