import { Ionicons } from '@expo/vector-icons';
import { Pressable, View } from 'react-native';
import { Badge, Button, Skeleton, Text } from '../../../components/ui';
import { colors } from '../../../components/ui/tokens';
import { BUDGET_RANGES } from '../onboarding.constants';
import { useOnboardingTaxonomiesQuery } from '../onboarding.queries';
import { useOnboardingStore } from '../onboarding.store';

const COLOUR_PALETTE_COUNT = 12;
const MAX_COLOURS = 5;

// Corner-badge checkmark (fix pass 3, 2026-07-22 — SS-004 colour-swatch
// redesign v3, point 6): the badge has its own solid, fixed background —
// unlike the fix-pass-2 on-swatch overlay, it never needs to be recomputed
// per-swatch against each of the 12 seeded hexes. Marigold (`colors.accent.
// marigold`) ties selection to the brand's own CTA accent (same token as the
// selected-state border below); its own relative luminance (~0.66, using the
// same simple perceptual formula this file used pre-redesign) reads better
// with a dark icon than white, so the checkmark uses `colors.text.primary`.
const CHECKMARK_BADGE_BG = colors.accent.marigold;
const CHECKMARK_ICON_COLOR = colors.text.primary;
const CHECKMARK_BADGE_OFFSET = -4;

interface ColourSwatchProps {
  hex: string;
  label: string;
  selected: boolean;
  onPress: () => void;
}

// v3 redesign (fix pass 3, 2026-07-22 — SS-004 colour-swatch fix, third
// round; see docs/worklog/SS-004.md's "Developer — fix pass 3" section for
// the full point-by-point rationale):
// - 64px rounded SQUARE (`h-16 w-16 rounded-lg`), not a 56px circle —
//   deliberate deviation from the raw ticket's literal "12-colour circles"
//   AC wording, directed by the user.
// - Border is ALWAYS visible (`border-2`, constant width to avoid layout
//   shift), only its colour changes: `border-textMuted` at rest,
//   `border-brand` (marigold) + `shadow-md` when selected — no
//   scale/transform animation. The previous version's `scale: 1.08` on a
//   wrapping Animated.View was the diagnosed cause of the caption
//   misalignment complaint; removed entirely rather than tuned down.
// - Checkmark moved off the swatch face entirely into a small corner badge
//   (`colour-swatch-check`, absolutely positioned bottom-right, own solid
//   background) so a selected swatch's colour stays fully visible.
// - Caption uses `numberOfLines={2}` inside a `min-h-9` (36px, ~2 lines of
//   `variant="caption"` text) fixed-height container, so neither a short
//   name ("Grey") nor a long one ("Marigold/Mustard") ever shifts the
//   swatch+caption cell's total height, selected or not.
//
// Fix pass 4, 2026-07-22 (SS-004 Fix 1): the caption's wrapping container
// was `w-full`, which resolves to the width of its parent — the `w-1/4`
// grid column (wider than the 64px swatch, due to the column's own
// padding/gutter) — not the swatch's own 64px footprint. Combined with
// `items-center` (which only centers a child within available width, it
// doesn't constrain the child's own intrinsic width), a `Text` with no
// explicit width sizes to its full un-wrapped string, so longer labels
// ("Marigold/Mustard", "Royal Blue", "Pastel Blue") overflowed past the
// swatch's right edge instead of wrapping at 64px. Changed to `w-16` (64px,
// identical to the swatch's `h-16 w-16`) so `numberOfLines={2}` actually
// wraps within the swatch's own width, and both boxes are now identically
// sized + centered within the same `w-1/4` column — which also fixes the
// "colour blocks not vertically aligned" symptom, since nothing can drift
// between swatches with short vs. long labels once both boxes share a fixed
// width.
function ColourSwatch({ hex, label, selected, onPress }: ColourSwatchProps) {
  return (
    <View className="w-1/4 items-center py-xs">
      <Pressable
        onPress={onPress}
        accessibilityRole="button"
        accessibilityLabel={label}
        accessibilityState={{ selected }}
        className={`relative h-16 w-16 items-center justify-center rounded-lg border-2 ${
          selected ? 'border-brand shadow-md' : 'border-textMuted'
        }`}
        style={{ backgroundColor: hex }}
      >
        {selected ? (
          <View
            testID="colour-swatch-check"
            className="absolute h-5 w-5 items-center justify-center rounded-pill"
            style={{
              bottom: CHECKMARK_BADGE_OFFSET,
              right: CHECKMARK_BADGE_OFFSET,
              backgroundColor: CHECKMARK_BADGE_BG,
            }}
          >
            <Ionicons name="checkmark" size={12} color={CHECKMARK_ICON_COLOR} />
          </View>
        ) : null}
      </Pressable>
      <View className="mt-xs min-h-9 w-16 items-center justify-start px-xs">
        <Text
          variant="caption"
          color="secondary"
          numberOfLines={2}
          className="text-center"
        >
          {label}
        </Text>
      </View>
    </View>
  );
}

// Budget chips (single-select, static BUDGET_RANGES) + colour grid
// (2026-07-13 revision: DB-backed colourPalette, 4x3 grid, capped
// multi-select at 5; fix pass 2, 2026-07-22: swatch selection redesigned per
// Bug 2 — bigger swatches, checkmark overlay, shadow + scale lift, colour-
// name caption; fix pass 3, 2026-07-22: v3 redesign — 64px rounded square
// (not circle), always-visible border, corner checkmark badge, no
// scale/transform, fixed-height 2-line caption — see ColourSwatch above).
// Loading state renders 12 Skeleton variant="circle" in the same grid
// wrapper (not TaxonomyChipsSkeleton — circles, not pills; untouched by fix
// pass 3, kept exactly as-is per the "only ColourSwatch itself changes"
// instruction). Per docs/tickets/SS-004-design.md's "Files to create/modify"
// #17.
export function Step4BudgetColours() {
  const { data, isLoading, isError, isSuccess, refetch } =
    useOnboardingTaxonomiesQuery();

  const budgetRange = useOnboardingStore((state) => state.budgetRange);
  const setBudgetRange = useOnboardingStore((state) => state.setBudgetRange);
  const favouriteColours = useOnboardingStore(
    (state) => state.favouriteColours,
  );
  const toggleColour = useOnboardingStore((state) => state.toggleColour);

  const atCap = favouriteColours.length >= MAX_COLOURS;

  // Fix pass 4, 2026-07-22 (SS-004 Fix 2): deliberately NOT changed to
  // `justify-center` like Step1/Step2/Step3 — this step's content (heading
  // + budget chips + a 12-swatch, 3-row colour grid) already substantially
  // fills the pager's available height, unlike the other three steps'
  // sparser field/chip layouts. Centering it further would risk exactly
  // the awkward gap-above-and-below sandwich the fix is meant to remove,
  // rather than fixing anything.
  return (
    <View className="flex-1 p-md">
      <Text variant="heading">Budget & favourite colours</Text>
      <Text variant="caption" color="secondary" className="mb-xs mt-md">
        Budget range
      </Text>
      <View className="flex-row flex-wrap gap-2">
        {BUDGET_RANGES.map((option) => (
          <Badge
            key={option.key}
            label={option.label}
            selected={budgetRange === option.key}
            onPress={() => setBudgetRange(option.key)}
          />
        ))}
      </View>

      <Text variant="caption" color="secondary" className="mb-xs mt-md">
        Favourite colours (up to 5)
      </Text>

      {isLoading ? (
        <View className="flex-row flex-wrap">
          {Array.from({ length: COLOUR_PALETTE_COUNT }, (_, index) => (
            <View
              // biome-ignore lint/suspicious/noArrayIndexKey: fixed-count placeholder circles, not a reorderable list
              key={index}
              className="w-1/4 items-center justify-center py-xs"
            >
              <Skeleton variant="circle" />
            </View>
          ))}
        </View>
      ) : null}

      {isError ? (
        <View className="items-start">
          <Text variant="body" color="secondary">
            Couldn't load colour options.
          </Text>
          <Button variant="ghost" onPress={() => refetch()}>
            Retry
          </Button>
        </View>
      ) : null}

      {isSuccess && data.colourPalette.length === 0 ? (
        <Text variant="body" color="secondary">
          No options available right now.
        </Text>
      ) : null}

      {isSuccess && data.colourPalette.length > 0 ? (
        <View className="flex-row flex-wrap" testID="colour-palette-grid">
          {data.colourPalette.map((option) => {
            const selected = favouriteColours.includes(option.hex);
            return (
              <ColourSwatch
                key={option.key}
                hex={option.hex}
                label={option.label}
                selected={selected}
                onPress={() => toggleColour(option.hex)}
              />
            );
          })}
        </View>
      ) : null}

      {atCap ? (
        <Text variant="caption" color="secondary" className="mt-sm">
          You can select up to 5 colours.
        </Text>
      ) : null}
    </View>
  );
}
