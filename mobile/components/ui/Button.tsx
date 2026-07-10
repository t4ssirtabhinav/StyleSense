import type { ReactNode } from 'react';
import { ActivityIndicator, Pressable } from 'react-native';
import { Text } from './Text';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost';

export interface ButtonProps {
  variant?: ButtonVariant;
  disabled?: boolean;
  /** Shows a spinner, disables press, keeps the variant's colours at reduced opacity. */
  loading?: boolean;
  fullWidth?: boolean;
  /** Leading icon slot. */
  icon?: ReactNode;
  onPress: () => void;
  children: ReactNode;
  accessibilityLabel?: string;
}

// Colour mapping (Architect's decision — the ticket fixes hex values but not
// which variant uses which):
// - primary: bg accent.marigold / dark text (marigold is too light for
//   legible white text)
// - secondary: 1px peacock border, transparent bg, peacock text
// - ghost: no border/bg, peacock text, minimal padding
const VARIANT_CLASS: Record<
  ButtonVariant,
  { container: string; text: string }
> = {
  primary: { container: 'bg-brand', text: 'text-textPrimary' },
  secondary: {
    container: 'border border-peacock bg-transparent',
    text: 'text-peacock',
  },
  ghost: { container: 'bg-transparent px-xs', text: 'text-peacock' },
};

// disabled (any variant): bg/border text.muted, white text, non-interactive.
const DISABLED_CLASS = {
  container: 'border border-textMuted bg-textMuted',
  text: 'text-white',
};

export function Button({
  variant = 'primary',
  disabled = false,
  loading = false,
  fullWidth = false,
  icon,
  onPress,
  children,
  accessibilityLabel,
}: ButtonProps) {
  const isDisabled = disabled || loading;
  const style = isDisabled ? DISABLED_CLASS : VARIANT_CLASS[variant];

  const containerClassName = [
    'flex-row items-center justify-center rounded-md px-md py-sm',
    style.container,
    fullWidth ? 'w-full' : '',
    loading ? 'opacity-70' : '',
  ]
    .filter(Boolean)
    .join(' ');

  const handlePress = () => {
    if (isDisabled) return;
    onPress();
  };

  return (
    <Pressable
      onPress={handlePress}
      disabled={isDisabled}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      accessibilityState={{ disabled: isDisabled }}
      className={containerClassName}
    >
      {loading ? (
        <ActivityIndicator
          testID="button-spinner"
          className="mr-xs"
          color={isDisabled ? '#FFFFFF' : undefined}
        />
      ) : (
        icon
      )}
      <Text variant="heading" weight="bold" className={style.text}>
        {children}
      </Text>
    </Pressable>
  );
}
