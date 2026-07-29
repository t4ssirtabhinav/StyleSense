// SS-025 — pure, I/O-free helpers over a fetched occasion registry
// snapshot. No React, no Supabase, no AsyncStorage: unit-testable without
// mocks, and callable from both hooks (onboarding.queries.ts) and plain
// service functions (wardrobe.service.ts's write path).
//
// Lives under features/onboarding/ because that is where the single
// taxonomy fetcher already lives (the ticket's own Technical Note: "extend
// onboarding.taxonomies.service.ts rather than adding a second taxonomy
// fetcher"). Promoting this to a features/taxonomy/ domain is logged as
// BL-089 — do not fork a second copy under features/wardrobe/.

import type { OccasionKey } from '../../components/ui';
import type { OccasionOption, OnboardingTaxonomies } from './onboarding.types';

/** Badge's four occasion colour families — the exact value set the
 * `occasions.badge_color` CHECK constrains to. Any registry value outside
 * this set renders neutral rather than producing an undefined NativeWind
 * class. */
export const BADGE_OCCASION_KEYS: readonly OccasionKey[] = [
  'wedding',
  'office',
  'festival',
  'casual',
];

/** A single selectable/renderable occasion chip. `badgeColor` is optional
 * because an unknown or deactivated slug legitimately has no registry row
 * and must still render (neutral). */
export interface OccasionChoice {
  key: string;
  label: string;
  badgeColor?: OccasionKey;
}

/** Humanised fallback label for a slug with no registry row — an unknown
 * AI-emitted tag, or an occasion deactivated since the item was tagged.
 * Never a blank chip (design §6.2). Same transformation the retired
 * `humanize()` in wardrobe.constants.ts applied. */
export function humanizeOccasionSlug(slug: string): string {
  return slug
    .split('_')
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

/**
 * Step 1 of the normalisation contract (design §3.6), byte-identical to
 * `public.occasion_normalize_shape` in 007_occasions_registry.sql and to
 * `OccasionNormalizer._shape` in the backend:
 *
 *   trim -> lower -> collapse runs of whitespace and '-' to a single '_'
 *   -> strip every character outside [a-z0-9_]
 *
 * Returns '' for an input that normalises to nothing (empty/whitespace/
 * all-punctuation). Callers treat '' as "drop this entry".
 */
export function normalizeOccasionSlug(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, '_')
    .replace(/[^a-z0-9_]/g, '');
}

/**
 * Steps 1-4 of the normalisation contract. Canonical key wins BEFORE the
 * alias lookup — that ordering is what makes an alias/key collision inert
 * (design §3.3), so do not reorder it.
 *
 * An unrecognised slug is returned normalised-but-unmapped. It is never
 * dropped and never throws: the DB trigger records it in
 * `occasion_unknown_tags` on write.
 */
export function resolveOccasionKey(
  raw: string,
  snapshot: OnboardingTaxonomies | undefined,
): string {
  const shaped = normalizeOccasionSlug(raw);
  if (!shaped || !snapshot) {
    return shaped;
  }
  if (snapshot.occasions.some((option) => option.key === shaped)) {
    return shaped;
  }
  const alias = snapshot.occasionAliases.find(
    (entry) => entry.alias === shaped,
  );
  return alias ? alias.occasionKey : shaped;
}

/** Normalise + dedupe (preserving FIRST-occurrence order — never sorted, so
 * a save round-trip cannot gratuitously reorder a user's tags) and drop
 * entries that normalise to nothing. */
export function normalizeOccasionTags(
  raw: readonly string[],
  snapshot: OnboardingTaxonomies | undefined,
): string[] {
  const result: string[] = [];
  for (const entry of raw) {
    const resolved = resolveOccasionKey(entry, snapshot);
    if (resolved && !result.includes(resolved)) {
      result.push(resolved);
    }
  }
  return result;
}

function findOption(
  slug: string,
  snapshot: OnboardingTaxonomies | undefined,
): OccasionOption | undefined {
  return snapshot?.occasions.find((option) => option.key === slug);
}

/** Registry label, falling back to the humanised slug. Never returns an
 * empty string for a non-empty slug — WardrobeFilterSheet used to render
 * the raw slug, which stops being acceptable once occasions can be
 * arbitrary (design §8 edge case 9). */
export function occasionLabel(
  slug: string,
  snapshot: OnboardingTaxonomies | undefined,
): string {
  return findOption(slug, snapshot)?.label ?? humanizeOccasionSlug(slug);
}

/** Registry badge token, or `undefined` (= Badge's neutral style) for a
 * slug that is not in the snapshot, or whose stored `badge_color` is
 * outside Badge's four keys. */
export function occasionBadgeColor(
  slug: string,
  snapshot: OnboardingTaxonomies | undefined,
): OccasionKey | undefined {
  const badgeColor = findOption(slug, snapshot)?.badgeColor;
  if (badgeColor && BADGE_OCCASION_KEYS.includes(badgeColor)) {
    return badgeColor;
  }
  return undefined;
}

/** Top-level umbrellas only (`parent_key IS NULL`), in `sort_order`. This is
 * what keeps the registry's growth from flooding onboarding Step 3 and the
 * home pill row. */
export function topLevelOccasions(
  snapshot: OnboardingTaxonomies | undefined,
): OccasionOption[] {
  return (snapshot?.occasions ?? []).filter(
    (option) => option.parentKey === null,
  );
}

/**
 * The UNION rule (design §5.3): the active registry, plus any slug already
 * on the item/draft that the registry does not (or no longer) contains.
 *
 * Without this, an unknown Gemini slug or a since-deactivated occasion is
 * invisible in the Review/Edit pickers and gets silently dropped on the
 * next save — the sharpest regression risk in the whole ticket. Extra slugs
 * are appended in their own order, after the registry, exactly once each,
 * with a humanised label and no badge colour.
 */
export function activeOccasionsPlus(
  currentTags: readonly string[],
  snapshot: OnboardingTaxonomies | undefined,
): OccasionChoice[] {
  const registry = snapshot?.occasions ?? [];
  const choices: OccasionChoice[] = registry.map((option) => ({
    key: option.key,
    label: option.label,
    badgeColor: BADGE_OCCASION_KEYS.includes(option.badgeColor)
      ? option.badgeColor
      : undefined,
  }));

  const seen = new Set(choices.map((choice) => choice.key));
  for (const tag of currentTags) {
    if (!tag || seen.has(tag)) {
      continue;
    }
    seen.add(tag);
    choices.push({ key: tag, label: humanizeOccasionSlug(tag) });
  }

  return choices;
}

/**
 * The canonical applicability predicate (design §3.1), the TypeScript
 * counterpart of:
 *
 *   (region_scope  IS NULL OR :user_region  = ANY(region_scope))
 *   AND (culture_scope IS NULL OR :user_culture = ANY(culture_scope))
 *
 * NULL means UNIVERSAL / pan-India, not "no regions". Never write
 * `option.regionScope?.includes(region) ?? false` — that inverts the null
 * meaning and every pan-India occasion silently disappears.
 *
 * Unused by this ticket's screens (all 12 seed rows are universal); it
 * exists so SS-027/SS-030 copy this one implementation instead of
 * re-deriving the predicate and getting the null case wrong.
 */
export function occasionAppliesTo(
  option: Pick<OccasionOption, 'regionScope' | 'cultureScope'>,
  user: { region?: string | null; culture?: string | null },
): boolean {
  const regionOk =
    option.regionScope === null ||
    (user.region != null && option.regionScope.includes(user.region));
  const cultureOk =
    option.cultureScope === null ||
    (user.culture != null && option.cultureScope.includes(user.culture));
  return regionOk && cultureOk;
}
