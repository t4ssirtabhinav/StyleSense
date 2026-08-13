// SS-021 — Style Score Calculation + Display.
// Types for the client-side style-score computation. Deliberately flat and
// free of Date/Supabase types so the whole formula (style-score.compute.ts)
// is testable from a literal object — see docs/tickets/SS-021-design.md §5.1.

export type StyleScoreDimension =
  | 'wardrobe_variety'
  | 'occasion_coverage'
  | 'cost_efficiency'
  | 'activity';

/** Everything computeStyleScore needs. */
export interface StyleScoreInputs {
  itemCount: number;
  distinctCategories: number;
  /** Occasion keys appearing in at least one item's occasion_tags. May
   *  contain unknown/retired slugs (SS-025 never drops them). */
  coveredOccasionKeys: string[];
  /** occasions.key WHERE is_active — the denominator. */
  activeOccasionKeys: string[];
  /** cost_per_wear (WHOLE RUPEES — BL-075) for qualifying items only. */
  costPerWearValues: number[];
  outfitsThisMonth: number;
  wearsThisMonth: number;
}

export interface StyleScoreDimensionResult {
  dimension: StyleScoreDimension;
  label: string;
  /** 0-100 integer, or null = not enough data (excluded from the total). */
  score: number | null;
  weight: number;
  /** Improvement tip, present only when score !== null && score < threshold. */
  tip: string | null;
}

export interface StyleScoreResult {
  /** 0-100 integer. ALWAYS a number — never null, never NaN. */
  total: number;
  state: 'ok' | 'empty_wardrobe';
  /** Always all four dimensions, in the declared order. */
  breakdown: StyleScoreDimensionResult[];
}

export interface StyleScoreSummary extends StyleScoreResult {
  isPremium: boolean;
}
