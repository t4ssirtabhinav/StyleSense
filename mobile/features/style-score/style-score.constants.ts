// SS-021 — every weight, target, threshold and copy string for the style
// score lives here, `as const`. This is the ONLY place a magic number for
// this feature may live (docs/tickets/SS-021-design.md §6) — recalibration
// is a one-file diff, no logic change. Every value here is an Architect
// invention with no product sign-off (BL-145): non-blocking, but flagged so
// it isn't mistaken for a settled product decision.
import type { StyleScoreDimension } from './style-score.types';

export const STYLE_SCORE_WEIGHTS: Record<StyleScoreDimension, number> = {
  wardrobe_variety: 30,
  occasion_coverage: 30,
  cost_efficiency: 20,
  activity: 20,
} as const;

export const VARIETY_TARGET_DISTINCT_CATEGORIES = 8;

export const COST_PER_WEAR_EXCELLENT_RUPEES = 100;
export const COST_PER_WEAR_POOR_RUPEES = 2000;

export const ACTIVITY_OUTFIT_POINTS = 2;
export const ACTIVITY_WEAR_POINTS = 1;
export const ACTIVITY_TARGET_POINTS = 16;

export const STYLE_SCORE_TIP_THRESHOLD = 70;
export const STYLE_SCORE_STALE_TIME_MS = 60_000;
export const STYLE_SCORE_MAX_ITEMS = 2000;

export const CIRCULAR_PROGRESS_SIZE_DEFAULT = 120;
export const CIRCULAR_PROGRESS_STROKE_DEFAULT = 10;

export const STYLE_SCORE_LABELS: Record<StyleScoreDimension, string> = {
  wardrobe_variety: 'Wardrobe Variety',
  occasion_coverage: 'Occasion Coverage',
  cost_efficiency: 'Cost Efficiency',
  activity: 'Activity',
} as const;

export const STYLE_SCORE_TIPS: Record<StyleScoreDimension, string> = {
  wardrobe_variety:
    'Add pieces from categories you are missing — ethnic wear, footwear and accessories all count.',
  occasion_coverage:
    'Tag your items with more occasions so we can style you for everything from Office to Wedding Guest.',
  cost_efficiency:
    'Wear what you already own and log it — every wear lowers your cost per wear.',
  activity:
    'Save an outfit or log what you wore today to keep your score moving.',
} as const;

export const STYLE_SCORE_ALL_GOOD_COPY =
  'Your wardrobe is in great shape. Keep it up!';
export const STYLE_SCORE_EMPTY_COPY =
  'Add your first item to start building your style score.';
export const STYLE_SCORE_LOCKED_COPY =
  'Unlock your 4 sub-scores and personalised tips with Premium.';
export const STYLE_SCORE_ERROR_COPY =
  'We could not calculate your style score right now.';
export const STYLE_SCORE_TITLE = 'Style Score';
export const STYLE_SCORE_SHARE_CTA = 'Share Score';

// Declared dimension order — StyleScoreResult.breakdown is always in this
// order regardless of which dimensions are null (design §5.6, test plan).
export const STYLE_SCORE_DIMENSION_ORDER: readonly StyleScoreDimension[] = [
  'wardrobe_variety',
  'occasion_coverage',
  'cost_efficiency',
  'activity',
] as const;
