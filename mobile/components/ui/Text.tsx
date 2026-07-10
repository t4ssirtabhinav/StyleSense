import type { ComponentProps, ReactNode } from 'react';
import { Text as RNText } from 'react-native';

export type TextVariant = 'display' | 'heading' | 'body' | 'caption' | 'mono';
export type TextColor =
  | 'primary'
  | 'secondary'
  | 'muted'
  | 'marigold'
  | 'peacock'
  | 'rose'
  | 'emerald';
export type TextScript = 'latin' | 'devanagari';
export type TextWeight = 'regular' | 'bold';

export interface TextProps
  extends Omit<ComponentProps<typeof RNText>, 'children'> {
  variant?: TextVariant;
  color?: TextColor;
  script?: TextScript;
  weight?: TextWeight;
  children?: ReactNode;
}

const SIZE_CLASS: Record<TextVariant, string> = {
  display: 'text-3xl',
  heading: 'text-xl',
  body: 'text-base',
  caption: 'text-xs',
  mono: 'text-sm',
};

// Maps variant + weight to the fontFamily classes defined in tailwind.config.js.
// 'body' and 'caption' only ship Regular + Medium (no Bold face loaded), so
// weight='bold' falls back to the Medium face for those two variants.
const FONT_CLASS: Record<TextVariant, Record<TextWeight, string>> = {
  display: { regular: 'font-display', bold: 'font-display-bold' },
  heading: { regular: 'font-heading', bold: 'font-heading-semibold' },
  body: { regular: 'font-body', bold: 'font-body-medium' },
  caption: { regular: 'font-body', bold: 'font-body-medium' },
  mono: { regular: 'font-mono', bold: 'font-mono-bold' },
};

const COLOR_CLASS: Record<TextColor, string> = {
  primary: 'text-textPrimary',
  secondary: 'text-textSecondary',
  muted: 'text-textMuted',
  marigold: 'text-brand',
  peacock: 'text-peacock',
  rose: 'text-rose',
  emerald: 'text-emerald',
};

const HINDI_FONT_CLASS = 'font-hindi';

export function Text({
  variant = 'body',
  color,
  script = 'latin',
  weight = 'regular',
  className,
  children,
  ...rest
}: TextProps) {
  const resolvedColor: TextColor =
    color ?? (variant === 'caption' ? 'muted' : 'primary');
  const fontClass =
    script === 'devanagari' ? HINDI_FONT_CLASS : FONT_CLASS[variant][weight];
  const composedClassName = [
    SIZE_CLASS[variant],
    fontClass,
    COLOR_CLASS[resolvedColor],
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <RNText className={composedClassName} {...rest}>
      {children}
    </RNText>
  );
}
