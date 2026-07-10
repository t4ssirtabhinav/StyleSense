import { Pressable, Text as RNText, View } from 'react-native';

export type OccasionKey = 'wedding' | 'office' | 'festival' | 'casual';

export interface BadgeProps {
  /** Truncated to 20 chars + '…' if longer. */
  label: string;
  /** Colour-codes bg/text; omit for a neutral grey badge. */
  occasion?: OccasionKey;
  /** Toggled/active visual state, for SS-004/SS-005 multi-select pills. */
  selected?: boolean;
  /** Emoji or short icon slot, e.g. "💼". */
  icon?: string;
  /** If present, renders as a Pressable (chip); otherwise static (badge). */
  onPress?: () => void;
  /** Optional test hook — not part of the ticket's fixed API, purely additive. */
  testID?: string;
}

const MAX_LABEL_LENGTH = 20;

// Occasion colour -> text colour pairing (Architect's decision): wedding and
// festival are light gold/marigold, so they pair with dark text for
// contrast; office (blue) and casual (green) pair with white text.
// BL-008 (docs/BACKLOG.md, Open): only these 4 of 12 occasion_type values
// have colours defined; any other occasion falls back to the neutral style.
const OCCASION_STYLE: Record<OccasionKey, { bg: string; text: string }> = {
  wedding: { bg: 'bg-occasionWedding', text: 'text-textPrimary' },
  festival: { bg: 'bg-occasionFestival', text: 'text-textPrimary' },
  office: { bg: 'bg-occasionOffice', text: 'text-white' },
  casual: { bg: 'bg-occasionCasual', text: 'text-white' },
};

const NEUTRAL_STYLE = { bg: 'bg-surfaceSecondary', text: 'text-textSecondary' };

export function truncateBadgeLabel(label: string): string {
  if (label.length <= MAX_LABEL_LENGTH) return label;
  return `${label.slice(0, MAX_LABEL_LENGTH)}…`;
}

export function Badge({
  label,
  occasion,
  selected = false,
  icon,
  onPress,
  testID,
}: BadgeProps) {
  const style = occasion ? OCCASION_STYLE[occasion] : NEUTRAL_STYLE;
  const truncatedLabel = truncateBadgeLabel(label);

  const containerClassName = [
    'flex-row items-center self-start rounded-pill px-md py-xs',
    style.bg,
    selected ? 'border-2 border-textPrimary' : '',
  ]
    .filter(Boolean)
    .join(' ');

  const content = (
    <View testID={onPress ? undefined : testID} className={containerClassName}>
      {icon ? <RNText className="mr-xs text-sm">{icon}</RNText> : null}
      <RNText className={`font-body text-xs ${style.text}`}>
        {truncatedLabel}
      </RNText>
    </View>
  );

  if (onPress) {
    return (
      <Pressable
        testID={testID}
        onPress={onPress}
        accessibilityRole="button"
        accessibilityLabel={label}
      >
        {content}
      </Pressable>
    );
  }

  return content;
}
