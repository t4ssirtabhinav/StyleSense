import * as Haptics from 'expo-haptics';
import {
  act,
  fireEvent,
  renderRouter,
  screen,
} from 'expo-router/testing-library';
import { TabSlot, Tabs } from 'expo-router/ui';
import { Text } from 'react-native';
import { useCustomTabBar } from '../../../../features/navigation/components/CustomTabBar';
import { TAB_CONFIG } from '../../../../features/navigation/navigation.constants';

// SS-017 (Migrate off deprecated expo-router Tabs/tabBar API): full rewrite.
// CustomTabBar can no longer be rendered standalone with hand-built
// `{state, descriptors, navigation, insets}` props — TabTrigger's
// useTabTrigger() requires a real ancestor <Tabs> navigator context via
// useNavigatorContext(). Uses expo-router/testing-library's renderRouter()
// with a minimal in-memory route context so that context is real, not
// faked (design doc's Test plan).
//
// Deviation from the design doc, verified against the installed
// `expo-router@56.2.11` source: `useCustomTabBar()` (see CustomTabBar.tsx)
// is a hook, not a component — `Tabs` only discovers its `<TabList>`/
// `<TabTrigger>` triggers by structurally walking its OWN direct JSX
// children; it does not see through a nested custom component. The mock
// `_layout` below therefore calls the hook directly, exactly as the real
// app/(tabs)/_layout.tsx does, so its returned `<TabList>` element is a
// literal, un-wrapped child of `<Tabs>`.

jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn().mockResolvedValue(undefined),
  ImpactFeedbackStyle: { Light: 'light' },
}));

// TabBarItem imports the components/ui barrel for Text/colors, which also
// exports AppBottomSheet (@gorhom/bottom-sheet). Under this specific
// combination — `expo-router/testing-library`'s internal re-registration
// of the `react-native-reanimated` jest mock (build/testing-library/
// mocks.js) — `@gorhom/bottom-sheet`'s own module-load-time
// `Easing.out(Easing.exp)` (constants.ts) throws because `Easing` ends up
// undefined in this environment. Confirmed via isolated repro: this is a
// pre-existing interaction bug between expo-router/testing-library and
// @gorhom/bottom-sheet's jest mock, unrelated to CustomTabBar's own logic —
// reproduces even with a trivial renderRouter context that never touches
// CustomTabBar. Not spreading the real module (unlike this repo's other
// `@gorhom/bottom-sheet` mocks) is deliberate: pulling in
// `jest.requireActual` re-triggers the same broken
// `react-native-reanimated` resolution. This file doesn't render
// bottom-sheet behavior, so a minimal, fully-replaced stub of the two
// symbols components/ui/BottomSheet.tsx actually imports is sufficient and
// sidesteps the bug entirely.
jest.mock('@gorhom/bottom-sheet', () => {
  const react = jest.requireActual('react');
  const reactNative = jest.requireActual('react-native');

  const MockBottomSheetModal = react.forwardRef(
    (props: Record<string, unknown>, ref: React.Ref<unknown>) => {
      react.useImperativeHandle(ref, () => ({
        present: jest.fn(),
        dismiss: jest.fn(),
      }));
      return react.createElement(
        reactNative.View,
        { testID: 'mock-bottom-sheet-modal' },
        props.children,
      );
    },
  );
  MockBottomSheetModal.displayName = 'MockBottomSheetModal';

  return {
    BottomSheetModal: MockBottomSheetModal,
    BottomSheetView: reactNative.View,
  };
});

const mockUseSafeAreaInsets = jest.fn(() => ({
  top: 0,
  bottom: 0,
  left: 0,
  right: 0,
}));
// Spreading the real module (not a full replacement) is required: expo-
// router/react-navigation's own internals also depend on other exports
// from this module (e.g. SafeAreaProviderCompat-style usage deep inside
// the navigator machinery) — a bare `{ useSafeAreaInsets: ... }` object
// leaves those other exports `undefined`, which surfaces as a completely
// unrelated-looking "Element type is invalid" render crash. Confirmed via
// isolated repro: only `useSafeAreaInsets` needs overriding here.
jest.mock('react-native-safe-area-context', () => ({
  ...jest.requireActual('react-native-safe-area-context'),
  useSafeAreaInsets: () => mockUseSafeAreaInsets(),
}));

// react-native-screens ships native-backed ScreenContainer/Screen
// components with no native binding available under Jest, and this repo's
// jest config (unlike react-native-gesture-handler/@shopify/flash-list)
// doesn't wire up a screens-specific test mock — expo-router/ui's TabSlot
// renders these directly, so without a stand-in they resolve to `undefined`
// ("Element type is invalid") the moment renderRouter() actually renders.
// Plain View stand-ins are enough since this file asserts on
// CustomTabBar/TabBarItem output, not react-native-screens' native
// container behavior. `featureFlags.experiment` is also required directly:
// expo-router's own screensFeatureFlags.ts reads/writes it at import time
// as part of ExpoRoot.
jest.mock('react-native-screens', () => {
  const reactNative = jest.requireActual('react-native');
  return {
    ScreenContainer: reactNative.View,
    Screen: reactNative.View,
    ScreenStack: reactNative.View,
    ScreenStackItem: reactNative.View,
    enableScreens: () => {},
    enableFreeze: () => {},
    featureFlags: { experiment: {} },
  };
});

// Flat (no route-group) mock context — the group segment `(tabs)` in the
// real app tree contributes no URL segment, so this is behaviorally
// equivalent for exercising CustomTabBar's rendering + navigation.
function buildContext() {
  return {
    _layout: () => {
      const tabBar = useCustomTabBar();
      return (
        <Tabs>
          <TabSlot />
          {tabBar}
        </Tabs>
      );
    },
    index: () => <Text>Home Screen</Text>,
    wardrobe: () => <Text>Wardrobe Screen</Text>,
    style: () => <Text>Style Screen</Text>,
    discover: () => <Text>Discover Screen</Text>,
    profile: () => <Text>Profile Screen</Text>,
  };
}

// `@testing-library/react-native@14.x`'s `render()` is async (matching
// React 19's async `act()`), but the installed `expo-router@56.2.11`'s own
// `renderRouter()` doesn't await its internal `render()` call — verified by
// reading node_modules/@testing-library/react-native/dist/render.js
// (`async function render(...)`) against node_modules/expo-router/build/
// testing-library/index.js (`const result = rnTestingLibrary.render(...)`,
// no `await`). Calling `renderRouter()` (and any subsequent `fireEvent`)
// outside of `act()` leaves RNTL's `screen` singleton unbound
// ("`render` function has not been called") or produces "overlapping
// act() calls" warnings with inconsistent state. Wrapping every
// renderRouter()/fireEvent call in `await act(async () => { ... })` is the
// verified, reliable fix (confirmed via isolated repro) — not a style
// preference.
async function renderTabBar() {
  await act(async () => {
    renderRouter(buildContext(), { initialUrl: '/' });
  });
}

// `@testing-library/react-native`'s own default `fireEvent.press()` event
// (dist/event-builder/base.js's `baseSyntheticEvent()`) stubs
// `preventDefault`/`isDefaultPrevented` as two INDEPENDENT, stateless
// no-ops (`preventDefault: () => {}`, `isDefaultPrevented: () => false`) —
// calling `preventDefault()` never makes `isDefaultPrevented()` return
// true, unlike a real GestureResponderEvent. Confirmed via isolated repro:
// without this, the debounce test below silently fails to prove the
// blocking behavior (TabTrigger's own `isDefaultPrevented()` check inside
// build/ui/TabTrigger.js never sees the effect of our `preventDefault()`
// call). Passing a stateful pair as `fireEvent.press`'s second argument
// (deep-merged over the default stub) restores real event semantics for
// this one assertion.
function buildPreventableEvent() {
  let prevented = false;
  return {
    preventDefault: () => {
      prevented = true;
    },
    isDefaultPrevented: () => prevented,
  };
}

describe('CustomTabBar', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseSafeAreaInsets.mockReturnValue({
      top: 0,
      bottom: 0,
      left: 0,
      right: 0,
    });
  });

  it('renders all 5 tab labels from TAB_CONFIG', async () => {
    await renderTabBar();

    for (const tab of TAB_CONFIG) {
      expect(screen.getByText(tab.label)).toBeOnTheScreen();
    }
  });

  it('the initially-focused tab renders its activeIcon + dot indicator; a non-focused tab renders no dot', async () => {
    await renderTabBar();

    expect(screen.getByTestId('tab-dot-index')).toBeOnTheScreen();
    expect(screen.queryByTestId('tab-dot-wardrobe')).toBeNull();
  });

  it('pressing a tab navigates there', async () => {
    await renderTabBar();

    await act(async () => {
      fireEvent.press(screen.getByTestId('tab-wardrobe'));
    });

    expect(screen.getByText('Wardrobe Screen')).toBeOnTheScreen();
  });

  it('pressing the same tab twice within 400ms only navigates once (debounce)', async () => {
    await renderTabBar();

    const dateNowSpy = jest.spyOn(Date, 'now');
    dateNowSpy.mockReturnValue(1000);
    await act(async () => {
      fireEvent.press(
        screen.getByTestId('tab-wardrobe'),
        buildPreventableEvent(),
      );
    });
    expect(screen.getByText('Wardrobe Screen')).toBeOnTheScreen();

    dateNowSpy.mockReturnValue(1200); // 200ms later, within the 400ms window
    await act(async () => {
      fireEvent.press(screen.getByTestId('tab-style'), buildPreventableEvent());
    });

    // The second (debounced) press never navigated — still on Wardrobe.
    expect(screen.getByText('Wardrobe Screen')).toBeOnTheScreen();
    expect(screen.queryByText('Style Screen')).toBeNull();

    dateNowSpy.mockRestore();
  });

  it('calls Haptics.impactAsync once per handled (non-debounced) press', async () => {
    await renderTabBar();

    await act(async () => {
      fireEvent.press(screen.getByTestId('tab-style'));
    });

    expect(Haptics.impactAsync).toHaveBeenCalledTimes(1);
    expect(Haptics.impactAsync).toHaveBeenCalledWith(
      Haptics.ImpactFeedbackStyle.Light,
    );
  });

  it("reflects a non-zero insets.bottom in the tab bar's rendered height/padding", async () => {
    mockUseSafeAreaInsets.mockReturnValue({
      top: 0,
      bottom: 20,
      left: 0,
      right: 0,
    });
    await renderTabBar();

    expect(screen.getByTestId('custom-tab-bar')).toHaveProp(
      'style',
      expect.objectContaining({ height: 84, paddingBottom: 20 }),
    );
  });
});
