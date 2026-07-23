import type { Ionicons } from '@expo/vector-icons';
import type { Tabs } from 'expo-router';
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
}

// Developer-phase verification note (docs/tickets/SS-005-design.md's Open
// Question #1): `expo-router@~56.2.11`'s own type definitions do NOT
// re-export `BottomTabBarProps` from the package's top-level entry point
// (only from the internal `build/react-navigation/bottom-tabs` path, which
// isn't a documented/stable import surface). Rather than deep-importing an
// internal build path, this derives the exact render-prop shape structurally
// from the public `Tabs` component's own `tabBar` prop type — verified
// against the installed package's `.d.ts` files to still be
// `{ state, descriptors, navigation, insets }`, matching this design's
// assumption. `Tabs` itself is re-exported from `expo-router`'s top level
// (marked `@deprecated` in favour of `expo-router/js-tabs`'s newer
// declarative API, but still fully functional in this version) — see
// worklog for the migration-later note.
type TabBarRenderProp = NonNullable<ComponentProps<typeof Tabs>['tabBar']>;
export type CustomTabBarProps = Parameters<TabBarRenderProp>[0];
