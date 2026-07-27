import { Ionicons } from '@expo/vector-icons';
import { forwardRef } from 'react';
import { Pressable, View } from 'react-native';
import { Text, colors } from '../../../components/ui';
import { TAB_BAR_DOT_SIZE } from '../navigation.constants';
import type { TabBarItemProps } from '../navigation.types';

// Raw View/Pressable are used here deliberately, the same way Card.tsx/
// Badge.tsx/IconButton.tsx use them internally — this IS the tab-bar chrome
// primitive, and needs precise height/safe-area composition that Card's
// fixed variant styles don't expose.
//
// This must be a forwardRef component: `<TabTrigger asChild>` renders
// @radix-ui/react-slot's RN-shimmed `Slot`, which clones this element and
// needs somewhere to attach a ref (React.RefAttributes<View> is part of
// TabTriggerSlotProps) — a plain function component here would produce a
// silent "Function components cannot be given refs" warning at best, or
// break Slot's cloning at worst.
export const TabBarItem = forwardRef<View, TabBarItemProps>(function TabBarItem(
  // SS-014 fix pass (2026-07-27) -- manual-verification finding #6: `style`
  // is destructured out here deliberately. `TabTrigger`'s `asChild` path
  // (expo-router/ui's build/ui/TabTrigger.js) renders this element inside
  // `@radix-ui/react-slot`'s `Slot`, whose own `mergeProps` (dist/index.js)
  // only lets a *child's own* prop override the slot's -- since this
  // component never declared its own `style` prop, TabTrigger's injected
  // `styles.tabTrigger` (`{ flexDirection: 'row', justifyContent:
  // 'space-between' }`, hardcoded in that library, not configurable) won
  // outright once spread onto the inner Pressable, which is exactly what
  // put the focus dot to the *right* of the icon instead of below it (both
  // confirmed by reading the installed `expo-router@56.2.11` and
  // `@radix-ui/react-slot` source directly, not assumed). Discarding that
  // injected style and applying our own explicit column layout after the
  // spread restores the intended vertical (icon -> dot -> label) stack.
  { isFocused, tab, style: _injectedRowStyle, ...pressableProps },
  ref,
) {
  const focused = Boolean(isFocused);
  const iconName = focused ? tab.activeIcon : tab.inactiveIcon;
  const iconColor = focused ? colors.accent.marigold : colors.text.muted;

  return (
    <Pressable
      ref={ref}
      testID={`tab-${tab.name}`}
      accessibilityRole="button"
      accessibilityLabel={tab.accessibilityLabel}
      accessibilityState={{ selected: focused }}
      className="flex-1 items-center justify-center"
      {...pressableProps}
      style={{ flexDirection: 'column' }}
    >
      <Ionicons name={iconName} size={24} color={iconColor} />
      {focused ? (
        <View
          testID={`tab-dot-${tab.name}`}
          className="mt-xs rounded-pill bg-brand"
          style={{ width: TAB_BAR_DOT_SIZE, height: TAB_BAR_DOT_SIZE }}
        />
      ) : null}
      <Text
        variant="caption"
        color={focused ? 'marigold' : 'muted'}
        className="mt-xs"
      >
        {tab.label}
      </Text>
    </Pressable>
  );
});
