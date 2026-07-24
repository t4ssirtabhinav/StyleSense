import type { TabConfig } from './navigation.types';

// Icon names verified against the installed @expo/vector-icons' Ionicons
// glyph map (docs/tickets/SS-005-design.md's "Concrete values" table) —
// `home`/`home-outline`/`shirt`/`shirt-outline`/`sparkles`/
// `sparkles-outline`/`compass`/`compass-outline`/`person`/`person-outline`
// all confirmed present.
export const TAB_CONFIG: TabConfig[] = [
  {
    name: 'index',
    label: 'Home',
    activeIcon: 'home',
    inactiveIcon: 'home-outline',
    accessibilityLabel: 'Home tab',
    href: '/',
  },
  {
    name: 'wardrobe',
    label: 'Wardrobe',
    activeIcon: 'shirt',
    inactiveIcon: 'shirt-outline',
    accessibilityLabel: 'Wardrobe tab',
    href: '/wardrobe',
  },
  {
    name: 'style',
    label: 'Style',
    activeIcon: 'sparkles',
    inactiveIcon: 'sparkles-outline',
    accessibilityLabel: 'Style tab',
    href: '/style',
  },
  {
    name: 'discover',
    label: 'Discover',
    activeIcon: 'compass',
    inactiveIcon: 'compass-outline',
    accessibilityLabel: 'Discover tab',
    href: '/discover',
  },
  {
    name: 'profile',
    label: 'Profile',
    activeIcon: 'person',
    inactiveIcon: 'person-outline',
    accessibilityLabel: 'Profile tab',
    href: '/profile',
  },
];

// A press within this many ms of the previously *handled* press is ignored
// (rapid tab switching / double-tap edge case) — design doc's Edge Cases
// section names the requirement, not a duration; this is the Architect's
// concrete value.
export const TAB_PRESS_DEBOUNCE_MS = 400;

// Content height, excluding the safe-area inset added on top of it (total
// rendered height = TAB_BAR_CONTENT_HEIGHT + insets.bottom).
export const TAB_BAR_CONTENT_HEIGHT = 64;

export const TAB_BAR_DOT_SIZE = 6;
