import type { Ionicons } from '@expo/vector-icons';
import type { Href } from 'expo-router';
import type { TabTriggerSlotProps } from 'expo-router/ui';
import type { ComponentProps } from 'react';

// SS-005 (Home Screen Shell + Bottom Tab Navigation): the fixed 5-tab set —
// route file names under app/(tabs)/, not display labels.
export type TabRouteName =
  | 'index'
  | 'wardrobe'
  | 'style'
  | 'discover'
  | 'profile';

export type IoniconName = ComponentProps<typeof Ionicons>['name'];

export interface TabConfig {
  name: TabRouteName;
  label: string;
  activeIcon: IoniconName;
  inactiveIcon: IoniconName;
  accessibilityLabel: string;
  href: Href;
}

// SS-017 (Migrate off deprecated expo-router Tabs/tabBar API): CustomTabBar
// no longer receives a `{ state, descriptors, navigation, insets }`
// render-prop shape — that prop no longer exists under `expo-router/ui`'s
// headless tabs. Per-tab rendering now lives in TabBarItem, rendered as the
// `asChild` child of a `<TabTrigger>`, which clones this element and merges
// in `TabTriggerSlotProps` (isFocused, href, plus standard Pressable props)
// via @radix-ui/react-slot — see docs/tickets/SS-017-design.md's
// Verification section for the confirmed wiring.
export type TabBarItemProps = TabTriggerSlotProps & { tab: TabConfig };
