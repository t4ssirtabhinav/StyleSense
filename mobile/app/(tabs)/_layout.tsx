import { Redirect } from 'expo-router';
import { TabSlot, Tabs } from 'expo-router/ui';
import { Card, Text } from '../../components/ui';
import { useAuthStore } from '../../features/auth/auth.store';
import { useCustomTabBar } from '../../features/navigation/components/CustomTabBar';

// The Auth Guard wrapping the (tabs) route group. SS-005 (Home Screen Shell
// + Bottom Tab Navigation) replaces the previous <Slot /> placeholder with
// the real 5-tab <Tabs> navigator + custom tab bar, once a valid session
// exists — the guard logic above it (loading Card / <Redirect>) is
// unchanged.
//
// SS-017 (Migrate off deprecated expo-router Tabs/tabBar API): migrates
// from the deprecated render-prop `<Tabs tabBar={...}>` (top-level
// `expo-router` export) to `expo-router/ui`'s headless
// `Tabs`/`TabSlot`/`TabList`/`TabTrigger` primitives. The set of
// screens/routes is now defined implicitly by the `<TabTrigger>` entries
// rendered inside `useCustomTabBar()`'s `<TabList>` — there is no
// `Tabs.Screen`/`options.title` equivalent here anymore (that `title` was
// already visually inert: no header is shown, and the tab bar already
// renders each tab's label itself).
//
// `useCustomTabBar()` is called directly in THIS component's render body
// (not rendered as `<CustomTabBar />`) — see CustomTabBar.tsx's own comment
// for why: `Tabs` discovers its triggers by structurally walking its own
// direct JSX children for literal `TabList`/`TabTrigger` elements, and does
// not see through a nested custom component boundary. Calling the hook
// here means its returned `<TabList>` element is a literal, un-wrapped
// child of `<Tabs>`, as required.
export default function TabsLayout() {
  const session = useAuthStore((state) => state.session);
  const isSessionLoading = useAuthStore((state) => state.isSessionLoading);
  // Called unconditionally, alongside the other hooks above, before either
  // early return below — Rules of Hooks: a hook call placed after an early
  // return would be skipped on some renders (isSessionLoading === true) and
  // run on others, which React disallows.
  const tabBar = useCustomTabBar();

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
    <Tabs>
      <TabSlot />
      {tabBar}
    </Tabs>
  );
}
