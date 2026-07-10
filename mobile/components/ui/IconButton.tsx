import { Ionicons } from '@expo/vector-icons';
import type { ComponentProps } from 'react';
import { Pressable } from 'react-native';
import { colors } from './tokens';

export type IconButtonSize = 'sm' | 'md' | 'lg';
export type IconButtonVariant = 'filled' | 'ghost';

export interface IconButtonProps {
  icon: ComponentProps<typeof Ionicons>['name'];
  onPress: () => void;
  size?: IconButtonSize;
  /** filled = bg accent.peacock, white icon; ghost = transparent, icon in text.primary. */
  variant?: IconButtonVariant;
  disabled?: boolean;
  /** Required, not optional — no icon-only button ships without an a11y label. */
  accessibilityLabel: string;
}

const ICON_SIZE_PX: Record<IconButtonSize, number> = { sm: 16, md: 24, lg: 32 };
const CONTAINER_SIZE_CLASS: Record<IconButtonSize, string> = {
  sm: 'h-8 w-8',
  md: 'h-10 w-10',
  lg: 'h-12 w-12',
};

export function IconButton({
  icon,
  onPress,
  size = 'md',
  variant = 'ghost',
  disabled = false,
  accessibilityLabel,
}: IconButtonProps) {
  const iconColor = disabled
    ? colors.text.muted
    : variant === 'filled'
      ? '#FFFFFF'
      : colors.text.primary;

  const containerClassName = [
    'items-center justify-center rounded-pill',
    CONTAINER_SIZE_CLASS[size],
    variant === 'filled' ? 'bg-peacock' : 'bg-transparent',
    disabled ? 'opacity-50' : '',
  ]
    .filter(Boolean)
    .join(' ');

  const handlePress = () => {
    if (disabled) return;
    onPress();
  };

  return (
    <Pressable
      onPress={handlePress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      accessibilityState={{ disabled }}
      className={containerClassName}
    >
      <Ionicons name={icon} size={ICON_SIZE_PX[size]} color={iconColor} />
    </Pressable>
  );
}
