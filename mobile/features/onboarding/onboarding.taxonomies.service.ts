import { readCachedTaxonomies, writeCachedTaxonomies } from '../../lib/storage';
import { supabase } from '../../lib/supabase';
import type {
  ColourPaletteOption,
  OccasionAlias,
  OccasionOption,
  OnboardingTaxonomies,
  TaxonomyOption,
} from './onboarding.types';

// Kept as its own file rather than folded into onboarding.service.ts, since
// it reads shared reference tables with no user_id scoping at all (a
// different access pattern from every other method in onboarding.service.ts,
// which all key off userId) — per
// docs/tickets/SS-004-design.md's "Files to create/modify" #8
// (2026-07-13 revision).
//
// (SS-025) This is THE single taxonomy fetcher for the whole app — wardrobe
// filters, upload Review, item edit and the home pill row all read the
// occasion vocabulary through it. Do not add a second one (the ticket's own
// Technical Note; BL-089 tracks promoting it out of features/onboarding/).
// The 9-row `occasion_types` table it used to read was dropped by
// 009_drop_occasion_type_and_merge_taxonomy.sql; `occasions` (12 rows,
// registry-backed, with badge colour + hierarchy) replaces it, and
// `occasion_aliases` carries the two load-bearing renames
// (wedding -> wedding_guest, date -> date_night).

// If any of the four queries throws, the whole function rejects (no
// partial-success handling) — the query hook's isError state covers this
// uniformly for the caller rather than each step independently handling a
// subset failing. (SS-025) …except that a rejection is now first given a
// chance to be served from the last-known-good AsyncStorage cache, so a
// cold start without network renders real chips instead of nothing.
async function fetchFromSupabase(): Promise<OnboardingTaxonomies> {
  const [
    styleKeywordsResult,
    occasionsResult,
    occasionAliasesResult,
    colourPaletteResult,
  ] = await Promise.all([
    supabase
      .from('style_keywords')
      .select('key, label, sort_order')
      .eq('active', true)
      .order('sort_order', { ascending: true }),
    // Active rows only (design §9 open question 4, signed off): a
    // deactivated occasion is hidden from pickers but its chip still
    // renders via the humanised-slug fallback wherever an item already
    // carries it — the same code path unknown AI slugs already need, so
    // fetching retired vocabulary to the client buys nothing.
    supabase
      .from('occasions')
      .select(
        'key, label, badge_color, kind, parent_key, sort_order, region_scope, culture_scope',
      )
      .eq('is_active', true)
      .order('sort_order', { ascending: true }),
    supabase.from('occasion_aliases').select('alias, occasion_key'),
    supabase
      .from('colour_palette')
      .select('key, label, hex, sort_order')
      .eq('active', true)
      .order('sort_order', { ascending: true }),
  ]);

  if (styleKeywordsResult.error) {
    throw styleKeywordsResult.error;
  }
  if (occasionsResult.error) {
    throw occasionsResult.error;
  }
  if (occasionAliasesResult.error) {
    throw occasionAliasesResult.error;
  }
  if (colourPaletteResult.error) {
    throw colourPaletteResult.error;
  }

  const styleKeywords: TaxonomyOption[] = (styleKeywordsResult.data ?? []).map(
    (row) => ({
      key: row.key,
      label: row.label,
      sortOrder: row.sort_order,
    }),
  );

  const occasions: OccasionOption[] = (occasionsResult.data ?? []).map(
    (row) => ({
      key: row.key,
      label: row.label,
      // The DB's NOT NULL + CHECK guarantees one of Badge's four keys;
      // occasionBadgeColor() re-checks at render time anyway, so a future
      // widened CHECK degrades to a neutral chip rather than an undefined
      // NativeWind class.
      badgeColor: row.badge_color as OccasionOption['badgeColor'],
      kind: row.kind,
      parentKey: row.parent_key,
      sortOrder: row.sort_order,
      regionScope: row.region_scope,
      cultureScope: row.culture_scope,
    }),
  );

  const occasionAliases: OccasionAlias[] = (
    occasionAliasesResult.data ?? []
  ).map((row) => ({
    alias: row.alias,
    occasionKey: row.occasion_key,
  }));

  const colourPalette: ColourPaletteOption[] = (
    colourPaletteResult.data ?? []
  ).map((row) => ({
    key: row.key,
    label: row.label,
    hex: row.hex,
    sortOrder: row.sort_order,
  }));

  return {
    styleKeywords,
    occasions,
    occasionAliases,
    colourPalette,
    isStale: false,
  };
}

export async function fetchOnboardingTaxonomies(): Promise<OnboardingTaxonomies> {
  try {
    const fresh = await fetchFromSupabase();
    // Fire-and-forget would race the tests and hide write failures; awaiting
    // is cheap (one AsyncStorage.setItem) and writeCachedTaxonomies never
    // throws.
    await writeCachedTaxonomies(fresh);
    return fresh;
  } catch (error) {
    const cached = await readCachedTaxonomies();
    if (cached) {
      return { ...cached.payload, isStale: true };
    }
    // No cache and no network (first-ever launch offline) — reject, so the
    // consumer renders its error + retry state. Deliberately NOT a bundled
    // fallback vocabulary: that would reintroduce the hardcoded constant
    // this ticket's AC removes (design §6.5 / §9 open question 3).
    throw error;
  }
}
