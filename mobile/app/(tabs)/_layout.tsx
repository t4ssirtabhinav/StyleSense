import { Redirect } from 'expo-router';
import { TabSlot, Tabs } from 'expo-router/ui';
import { Card, Text } from '../../components/ui';
import { useAuthRouting } from '../../features/auth/useAuthRouting';
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
  // SS-071: reads the same shared decision (useAuthRouting) that
  // app/(auth)/_layout.tsx's forward guard consumes, rather than checking
  // session presence alone — this is what closes BL-168's second half (AC
  // #4): a returning user with a valid session and incomplete onboarding,
  // who opens the app cold and never passes through an auth screen, is now
  // routed to /onboarding instead of dropped straight into the tabs.
  const routing = useAuthRouting();
  // Called unconditionally, alongside the other hooks above, before either
  // early return below — Rules of Hooks: a hook call placed after an early
  // return would be skipped on some renders (routing.status === 'loading')
  // and run on others, which React disallows.
  const tabBar = useCustomTabBar();

  // `routing.status === 'loading'` covers both the first-render race where
  // hooks/useAuth.ts's initial getSession() call is still in flight AND the
  // onboarding-completed query settling — avoiding a one-frame
  // flash-redirect to /login for users with a valid persisted session, and
  // a flash toward the wrong destination while onboarding status is still
  // resolving (design doc's "no flash" note, edge case #9).
  if (routing.status === 'loading') {
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

  if (routing.status === 'unauthenticated') {
    return <Redirect href="/login" />;
  }

  if (routing.status === 'onboarding') {
    return <Redirect href="/onboarding" />;
  }

  return (
    <Tabs>
      {/* minHeight: 0 is load-bearing, not decoration (2026-08-12
          investigation): expo-router/ui's TabSlot renders react-native-
          screens' ScreenContainer with `flexGrow: 1, flexShrink: 0` but no
          minHeight override (node_modules/expo-router/build/ui/TabSlot.js).
          A flex column item defaults to `min-height: auto`, which lets it
          refuse to shrink below its own content's natural size -- verified
          via live DOM measurement (Chrome DevTools Protocol against the
          real authenticated /wardrobe route, not just reasoning about it):
          without this, wardrobe-grid rendered at its full natural height
          (2320px for 20 items) instead of the ~700px actually available,
          pushing CustomTabBar (a sibling of this TabSlot, below it) to
          y=2406-2470 -- entirely outside the 844px viewport, and clipped/
          unreachable under global.css's html/body/#root `overflow: hidden`
          fix rather than merely off-screen-but-scrollable. Every screen's
          own flex-1 chain (e.g. app/(tabs)/wardrobe.tsx's own minHeight: 0
          chain) assumed this outer link already behaved correctly; it did
          not. `style` is TabSlot's only exposed override point for this
          third-party container -- see its own source for how it merges. */}
      <TabSlot style={{ minHeight: 0 }} />
      {tabBar}
    </Tabs>
  );
}
