// Domain types for SS-004 (User Onboarding Wizard). Per
// docs/tickets/SS-004-design.md's "Files to create/modify" #4.
//
// gender/wardrobe_type/budget_range stay as fixed TS unions per the ticket's
// Technical Note explicitly calling these three "structurally stable".
// style_keywords/occasion_types/colour_palette are DB-backed (see
// onboarding.taxonomies.service.ts) — their valid values are no longer
// statically enumerable, hence the `string` widening below
// (2026-07-13 revision).

import type { OccasionKey } from '../../components/ui';

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

// (SS-025) A row of the `occasions` registry — the single occasion
// vocabulary for the whole app, replacing both the `occasion_type` DB enum
// and the retired 9-row `occasion_types` onboarding table.
//
// `badgeColor` is a DESIGN-TOKEN KEY (Badge's own OccasionKey union), not a
// hex — the DB's NOT NULL + CHECK guarantees every occasion has one, which
// is what makes BL-008's 4-of-12 colour gap structurally impossible rather
// than merely fixed. Still validated at read time by
// `occasionBadgeColor()`; a value outside the four renders neutral rather
// than crashing on an undefined NativeWind class.
export interface OccasionOption extends TaxonomyOption {
  badgeColor: OccasionKey;
  kind: string;
  /** `null` = a genuine top-level umbrella. Onboarding Step 3 and the home
   * pill row source only these, so inserting a specific occasion with a
   * parent (e.g. `ganesh_chaturthi` under `festival`) reaches wardrobe
   * tagging/filters/AI vocabulary without flooding the wizard. */
  parentKey: string | null;
  /** `null` means UNIVERSAL / pan-India, NOT "no regions" — see
   * `occasionAppliesTo()` in onboarding.occasions.ts. Never write
   * `regionScope?.includes(r) ?? false`; that inverts the meaning and every
   * pan-India occasion disappears. The empty array is forbidden by a DB
   * CHECK so "applies nowhere" is unrepresentable. */
  regionScope: string[] | null;
  /** Same null semantics as `regionScope`. */
  cultureScope: string[] | null;
}

export interface OccasionAlias {
  alias: string;
  occasionKey: string;
}

export interface OnboardingTaxonomies {
  styleKeywords: TaxonomyOption[];
  occasions: OccasionOption[];
  occasionAliases: OccasionAlias[];
  colourPalette: ColourPaletteOption[];
  /** (SS-025) true when this payload came from the last-known-good
   * AsyncStorage cache rather than a live fetch (design §6.5). Consumers
   * render it identically to a fresh payload — it exists so a UI can
   * optionally surface staleness, and so tests can prove the fallback
   * actually fired. */
  isStale: boolean;
}
