import { Redirect, Slot } from 'expo-router';
import { Card, Text } from '../../components/ui';
import { useAuthStore } from '../../features/auth/auth.store';

// The Auth Guard wrapping the (tabs) route group. Deliberately renders
// <Slot />, not Expo Router's <Tabs>, yet — there is no tab-bar UI to render
// until SS-005 lands; using Slot here means SS-005's Architect pass can drop
// <Tabs> in around/inside this same guard without redesigning the guard
// logic itself.
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

  return <Slot />;
}
