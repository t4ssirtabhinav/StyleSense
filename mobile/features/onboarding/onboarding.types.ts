// Domain types for SS-004 (User Onboarding Wizard). Per
// docs/tickets/SS-004-design.md's "Files to create/modify" #4.
//
// gender/wardrobe_type/budget_range stay as fixed TS unions per the ticket's
// Technical Note explicitly calling these three "structurally stable".
// style_keywords/occasion_types/colour_palette are DB-backed (see
// onboarding.taxonomies.service.ts) — their valid values are no longer
// statically enumerable, hence the `string` widening below
// (2026-07-13 revision).

export type GenderKey = 'woman' | 'man' | 'non_binary' | 'prefer_not_to_say';

export type WardrobeTypeKey =
  | 'mostly_western'
  | 'mostly_ethnic'
  | 'equal_mix'
  | 'mostly_formal'
  | 'mostly_casual';

export type BudgetRangeKey =
  | '500_1000'
  | '1000_3000'
  | '3000_10000'
  | '10000_plus';

// (2026-07-13 revision) widened from fixed unions to `string` — valid values
// now come from the DB (style_keywords.key / occasion_types.key where
// active = true), not a closed TS union.
export type StyleKeywordKey = string;
export type OccasionPriorityKey = string;

export interface IndianCity {
  id: string;
  name: string;
  state: string;
  lat: number;
  lng: number;
}

export type OnboardingStepId =
  | 'basic-profile'
  | 'style-wardrobe'
  | 'occasion-priorities'
  | 'budget-colours';

// Transcribed verbatim from the ticket's Technical Notes (see design doc's
// "Concrete values" section). `gender` is intentionally duplicated from
// users.gender at the top level — do not deduplicate this away.
export interface StylePreferences {
  styles: StyleKeywordKey[];
  wardrobe_type: WardrobeTypeKey;
  occasions_priority: OccasionPriorityKey[]; // max 3
  budget_range: BudgetRangeKey;
  favourite_colours: string[]; // hex codes, max 5
  gender: GenderKey;
}

// (2026-07-13 revision) DB-backed taxonomy shapes.
export interface TaxonomyOption {
  key: string;
  label: string;
  sortOrder: number;
}

export interface ColourPaletteOption extends TaxonomyOption {
  hex: string;
}

export interface OnboardingTaxonomies {
  styleKeywords: TaxonomyOption[];
  occasionTypes: TaxonomyOption[];
  colourPalette: ColourPaletteOption[];
}
