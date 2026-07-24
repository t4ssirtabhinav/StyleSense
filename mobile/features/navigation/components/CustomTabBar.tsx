import * as Haptics from 'expo-haptics';
import { TabList, TabTrigger } from 'expo-router/ui';
import { useCallback, useRef } from 'react';
import type { GestureResponderEvent } from 'react-native';
import { View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import {
  TAB_BAR_CONTENT_HEIGHT,
  TAB_CONFIG,
  TAB_PRESS_DEBOUNCE_MS,
} from '../navigation.constants';
import { TabBarItem } from './TabBarItem';

// Raw View is used here deliberately, the same way Card.tsx/Badge.tsx/
// IconButton.tsx use it internally — this IS the tab-bar chrome primitive,
// and needs precise height/safe-area composition that Card's fixed variant
// styles don't expose.
//
// SS-017 (Migrate off deprecated expo-router Tabs/tabBar API): CustomTabBar
// is now prop-less — the `{ state, descriptors, navigation, insets }`
// render-prop shape no longer exists under `expo-router/ui`'s headless
// tabs. It reads safe-area insets itself and renders a <TabList> of
// <TabTrigger>s, each wrapping a TabBarItem via `asChild`.
//
// Deviation from docs/tickets/SS-017-design.md's literal
// `<Tabs><TabSlot /><CustomTabBar /></Tabs>` composition, verified against
// the installed `expo-router@56.2.11` source (build/ui/Tabs.js's
// `parseTriggersFromChildren`): `Tabs` discovers its screens/triggers by
// structurally walking its OWN direct JSX children (only recursing into
// React.Fragment) looking for literal `TabList`/`TabTrigger` element types —
// it does NOT render/inspect what a nested custom component like
// `<CustomTabBar />` will eventually return. Confirmed via isolated repro:
// nesting `<TabList>` inside any custom component (not just this one)
// makes `Tabs` throw "Couldn't find any screens for the navigator" because
// zero triggers are ever discovered. Exporting this as a *hook*
// (`useCustomTabBar`), called directly inside `_layout.tsx`'s own render
// body so its returned `<TabList>` element is a literal, un-wrapped child
// of `<Tabs>`, is the minimal fix that preserves every other part of the
// design (same file, same visuals/logic, same customization surface).
export function useCustomTabBar() {
  const insets = useSafeAreaInsets();

  // Debounce window is global (one shared ref), not per-tab — rapid presses
  // across *different* tabs are ignored too, per the design doc's Edge Cases
  // section ("any press within 400ms of the previous handled press").
  const lastHandledPressRef = useRef(0);

  // SS-017: under expo-router/ui, TabTrigger owns navigation itself (no
  // imperative `navigation.navigate(...)` call to gate anymore). Per the
  // design doc's Verification section, TabTrigger's internal
  // handleOnPress calls this onPress FIRST, then checks
  // `event.isDefaultPrevented()` before emitting `tabPress`/switching tabs —
  // so the debounced case must call `event.preventDefault()` rather than
  // just returning early.
  const handleTriggerPress = useCallback((event: GestureResponderEvent) => {
    const now = Date.now();
    if (now - lastHandledPressRef.current < TAB_PRESS_DEBOUNCE_MS) {
      event.preventDefault();
      return;
    }
    lastHandledPressRef.current = now;

    // expo-haptics no-ops silently on web/unsupported devices per its own
    // docs — still wrapped so a rejection (e.g. simulator without haptics
    // hardware) never blocks navigation.
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
  }, []);

  return (
    <TabList asChild>
      <View
        testID="custom-tab-bar"
        className="flex-row border-t border-textMuted bg-surfacePrimary"
        style={{
          height: TAB_BAR_CONTENT_HEIGHT + insets.bottom,
          paddingBottom: insets.bottom,
        }}
      >
        {TAB_CONFIG.map((tab) => (
          <TabTrigger
            key={tab.name}
            name={tab.name}
            href={tab.href}
            asChild
            onPress={handleTriggerPress}
          >
            <TabBarItem tab={tab} />
          </TabTrigger>
        ))}
      </View>
    </TabList>
  );
}
