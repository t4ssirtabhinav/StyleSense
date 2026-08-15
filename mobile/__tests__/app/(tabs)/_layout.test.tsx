import { cleanup, render } from '@testing-library/react-native';
import TabsLayout from '../../../app/(tabs)/_layout';

// SS-005 (Home Screen Shell + Bottom Tab Navigation): extends the existing
// expo-router mock to also stub Tabs/Tabs.Screen (previously only mocked
// Redirect/Slot, back when this layout rendered <Slot />).
//
// SS-017 (Migrate off deprecated expo-router Tabs/tabBar API): `_layout.tsx`
// now also imports Tabs/TabSlot from the separate `expo-router/ui` module
// specifier — that needs its own trivial-passthrough mock too, or this test
// hits real (un-mocked) headless-tabs navigation machinery. This test stays
// a light smoke test of "did we get past the auth guard" — tab-bar behavior
// itself is CustomTabBar.test.tsx's job (design doc's Test plan, option a).
jest.mock('expo-router', () => {
  const react = jest.requireActual('react');
  const reactNative = jest.requireActual('react-native');

  return {
    Redirect: ({ href }: { href: string }) =>
      react.createElement(reactNative.Text, { testID: 'redirect' }, href),
  };
});

// SS-071: this layout's guard now reads the shared useAuthRouting() decision
// instead of the auth store's session/isSessionLoading fields directly —
// mocked here rather than driving it indirectly through useAuthStore, which
// would also require mocking useOnboardingCompletedQuery's React Query
// plumbing for no benefit (see docs/tickets/SS-071-design.md's Files
// table for this file).
const mockUseAuthRouting = jest.fn();
jest.mock('../../../features/auth/useAuthRouting', () => ({
  useAuthRouting: () => mockUseAuthRouting(),
}));

// `useCustomTabBar()` (see CustomTabBar.tsx) constructs real
// `<TabList>`/`<TabTrigger>` elements as part of its own hook body, even
// though `MockTabs` below never renders them — NativeWind's JSX interop
// (react-native-css-interop/wrap-jsx.ts) inspects every element's `type`
// eagerly (`type.displayName`) at *creation* time, not just at render
// time, so leaving `TabList`/`TabTrigger` undefined here (only mocking
// `Tabs`/`TabSlot`, as a first pass assumed was enough) throws immediately
// with an unrelated-looking "Cannot read properties of undefined (reading
// 'displayName')". Trivial passthrough stand-ins for all four exports are
// required.
jest.mock('expo-router/ui', () => {
  const react = jest.requireActual('react');
  const reactNative = jest.requireActual('react-native');

  const MockTabs = ({ children }: { children: React.ReactNode }) =>
    react.createElement(
      reactNative.Text,
      { testID: 'tabs' },
      'guarded content',
    );
  const MockTabSlot = () => null;
  const MockTabList = ({ children }: { children: React.ReactNode }) =>
    react.createElement(reactNative.View, null, children);
  const MockTabTrigger = ({ children }: { children: React.ReactNode }) =>
    react.createElement(reactNative.View, null, children);

  return {
    Tabs: MockTabs,
    TabSlot: MockTabSlot,
    TabList: MockTabList,
    TabTrigger: MockTabTrigger,
  };
});

// `useCustomTabBar()` (see CustomTabBar.tsx) is now called unconditionally
// at the top of TabsLayout, before either early-return branch (Rules of
// Hooks) — so all three tests below reach it, even the ones that never
// render `<Tabs>`. Its body calls `useSafeAreaInsets()` for real; the
// `<TabList>`/`<TabTrigger>` elements it constructs are discarded/never
// rendered here (MockTabs ignores its `children` prop), so no further
// `expo-router/ui` mocking is needed beyond what's above.
// Spreading the real module (not a full replacement) is required — NativeWind's
// react-native-css-interop applies its own cssInterop mapping to this
// module's other exports (e.g. SafeAreaView) at import time; a bare
// `{ useSafeAreaInsets: ... }` replacement leaves those undefined and
// crashes with an unrelated-looking "Cannot read properties of undefined
// (reading 'displayName')". Confirmed via isolated repro (same class of
// issue as CustomTabBar.test.tsx's own mock, see its comment).
jest.mock('react-native-safe-area-context', () => ({
  ...jest.requireActual('react-native-safe-area-context'),
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));

describe('TabsLayout (Auth Guard)', () => {
  afterEach(async () => {
    // Unmount before resetting mocks — otherwise the still-mounted
    // previous render's subscription triggers a state update outside act().
    await cleanup();
    jest.clearAllMocks();
  });

  it('renders the loading Card/Text and not <Redirect> while routing.status is "loading" (first-render race guard)', async () => {
    mockUseAuthRouting.mockReturnValue({ status: 'loading' });
    const { getByText, queryByTestId } = await render(<TabsLayout />);

    expect(getByText('Loading…')).toBeOnTheScreen();
    expect(queryByTestId('redirect')).toBeNull();
  });

  it('renders <Redirect href="/login" /> when routing.status is "unauthenticated"', async () => {
    mockUseAuthRouting.mockReturnValue({ status: 'unauthenticated' });
    const { getByTestId } = await render(<TabsLayout />);

    expect(getByTestId('redirect')).toHaveTextContent('/login');
  });

  // SS-071 AC #4 — the cold-open case: a valid session with
  // onboarding_completed: false, never having passed through an auth
  // screen, is routed to /onboarding rather than dropped into the tabs.
  it('renders <Redirect href="/onboarding" /> when routing.status is "onboarding"', async () => {
    mockUseAuthRouting.mockReturnValue({ status: 'onboarding' });
    const { getByTestId, queryByTestId } = await render(<TabsLayout />);

    expect(getByTestId('redirect')).toHaveTextContent('/onboarding');
    expect(queryByTestId('tabs')).toBeNull();
  });

  it('renders the guarded child content (<Tabs>) when routing.status is "app"', async () => {
    mockUseAuthRouting.mockReturnValue({ status: 'app' });
    const { getByTestId, queryByTestId } = await render(<TabsLayout />);

    expect(getByTestId('tabs')).toBeOnTheScreen();
    expect(queryByTestId('redirect')).toBeNull();
  });
});
