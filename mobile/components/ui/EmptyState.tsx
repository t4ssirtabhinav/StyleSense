import { Ionicons } from '@expo/vector-icons';
import type { ComponentProps, ReactNode } from 'react';
import { View } from 'react-native';
import { Text } from './Text';
import { colors } from './tokens';

export interface EmptyStateProps {
  /** Illustration placeholder — a large centered Ionicons glyph (no real
   * illustration assets exist in this repo yet). */
  icon: ComponentProps<typeof Ionicons>['name'];
  heading: string;
  subtext: string;
  /** Optional CTA slot — rendered only when provided. */
  children?: ReactNode;
  testID?: string;
}

// Generic, reusable empty-state primitive — same category as Card/Badge in
// this design system, introduced by SS-005 rather than SS-008. Used by the
// Wardrobe/Discover/Style/Profile tabs.
export function EmptyState({
  icon,
  heading,
  subtext,
  children,
  testID,
}: EmptyStateProps) {
  return (
    <View
      testID={testID}
      className="flex-1 items-center justify-center gap-sm p-lg"
    >
      <Ionicons
        testID="empty-state-icon"
        name={icon}
        size={64}
        color={colors.text.muted}
      />
      <Text variant="heading">{heading}</Text>
      <Text variant="caption" color="secondary" className="text-center">
        {subtext}
      </Text>
      {children}
    </View>
  );
}
