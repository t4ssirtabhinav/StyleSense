import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { useCallback, useRef } from 'react';
import { Pressable, View } from 'react-native';
import { Text, colors } from '../../../components/ui';
import {
  TAB_BAR_CONTENT_HEIGHT,
  TAB_BAR_DOT_SIZE,
  TAB_CONFIG,
  TAB_PRESS_DEBOUNCE_MS,
} from '../navigation.constants';
import type { CustomTabBarProps } from '../navigation.types';

// Raw View/Pressable are used here deliberately, the same way Card.tsx/
// Badge.tsx/IconButton.tsx use them internally — this IS the tab-bar chrome
// primitive, and needs precise height/safe-area composition that Card's
// fixed variant styles don't expose.
export function CustomTabBar({ state, navigation, insets }: CustomTabBarProps) {
  // Debounce window is global (one shared ref), not per-tab — rapid presses
  // across *different* tabs are ignored too, per the design doc's Edge Cases
  // section ("any press within 400ms of the previous handled press").
  const lastHandledPressRef = useRef(0);

  const handlePress = useCallback(
    (routeName: string) => {
      const now = Date.now();
      if (now - lastHandledPressRef.current < TAB_PRESS_DEBOUNCE_MS) {
        return;
      }
      lastHandledPressRef.current = now;

      // expo-haptics no-ops silently on web/unsupported devices per its own
      // docs — still wrapped so a rejection (e.g. simulator without haptics
      // hardware) never blocks navigation.
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});

      navigation.navigate(routeName);
    },
    [navigation],
  );

  return (
    <View
      testID="custom-tab-bar"
      className="flex-row border-t border-textMuted bg-surfacePrimary"
      style={{
        height: TAB_BAR_CONTENT_HEIGHT + insets.bottom,
        paddingBottom: insets.bottom,
      }}
    >
      {TAB_CONFIG.map((tab) => {
        const routeIndex = state.routes.findIndex(
          (route) => route.name === tab.name,
        );
        const focused = routeIndex !== -1 && state.index === routeIndex;
        const iconName = focused ? tab.activeIcon : tab.inactiveIcon;
        const iconColor = focused ? colors.accent.marigold : colors.text.muted;

        return (
          <Pressable
            key={tab.name}
            testID={`tab-${tab.name}`}
            accessibilityRole="button"
            accessibilityLabel={tab.accessibilityLabel}
            accessibilityState={{ selected: focused }}
            onPress={() => handlePress(tab.name)}
            className="flex-1 items-center justify-center"
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
      })}
    </View>
  );
}
