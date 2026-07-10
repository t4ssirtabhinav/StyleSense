import type { ReactNode } from 'react';
import { View } from 'react-native';

export type CardVariant = 'elevated' | 'flat' | 'outlined';

export interface CardProps {
  variant?: CardVariant;
  /** Additive only (padding/margin/width) — do not use to override the
   * variant's bg/border/radius. */
  className?: string;
  children: ReactNode;
  /** Optional test hook — not part of the ticket's fixed API, purely additive. */
  testID?: string;
}

// Radius-per-variant is an Architect decision (design doc, not fixed by the
// ticket): chosen so the 3 variants are visually/testably distinct.
const VARIANT_CLASS: Record<CardVariant, string> = {
  elevated: 'rounded-lg bg-surfacePrimary shadow-md',
  flat: 'rounded-md bg-surfaceSecondary',
  outlined: 'rounded-sm border border-textMuted bg-surfacePrimary',
};

export function Card({
  variant = 'flat',
  className,
  children,
  testID,
}: CardProps) {
  const composedClassName = [VARIANT_CLASS[variant], 'p-md', className]
    .filter(Boolean)
    .join(' ');

  return (
    <View testID={testID} className={composedClassName}>
      {children}
    </View>
  );
}
