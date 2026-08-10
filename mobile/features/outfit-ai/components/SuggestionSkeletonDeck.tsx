import { View } from 'react-native';
import { Skeleton, Text } from '../../../components/ui';
import { LOADING_COPY, SKELETON_DECK_SIZE } from '../outfit-ai.constants';

// Static NativeWind classes (never a dynamic inline style, CLAUDE.md) for
// the stacked-card offset — one entry per SKELETON_DECK_SIZE position.
const STACK_OFFSET_CLASSES = ['top-0', 'top-2', 'top-4'];

// The loading state (design §5). `BL-139`: cold-call latency is ~6s, not
// <4s (measured 16.2–16.7s for the LLM leg against a 6s router timeout in
// the worst case) — this is designed for a genuinely multi-second wait,
// with an honest progress affordance rather than a spinner that implies
// imminence. SKELETON_DECK_SIZE (3) is a VISUAL constant only — never
// assumed to be the real portfolio size (which may legitimately be 1 or 2,
// `limited_options`).
export function SuggestionSkeletonDeck() {
  return (
    <View
      testID="suggestion-skeleton-deck"
      className="flex-1 items-center gap-md p-lg"
    >
      <Text variant="body" color="secondary">
        {LOADING_COPY}
      </Text>
      <View className="w-full items-center">
        {STACK_OFFSET_CLASSES.slice(0, SKELETON_DECK_SIZE).map(
          (offsetClassName) => (
            // Unique per iteration (fixed, non-reorderable class strings) --
            // no array index needed as the key.
            <View
              key={offsetClassName}
              className={`absolute w-full ${offsetClassName}`}
            >
              <Skeleton variant="card" height={280} />
            </View>
          ),
        )}
      </View>
    </View>
  );
}
