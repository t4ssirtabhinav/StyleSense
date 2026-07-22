import { supabase } from '../../lib/supabase';
import type {
  ColourPaletteOption,
  OnboardingTaxonomies,
  TaxonomyOption,
} from './onboarding.types';

// Kept as its own file rather than folded into onboarding.service.ts, since
// it reads three shared reference tables with no user_id scoping at all (a
// different access pattern from every other method in onboarding.service.ts,
// which all key off userId) — per
// docs/tickets/SS-004-design.md's "Files to create/modify" #8
// (2026-07-13 revision).

// If any of the three queries throws, the whole function rejects (no
// partial-success handling) — the query hook's isError state covers this
// uniformly for the caller rather than each step independently handling a
// subset failing.
export async function fetchOnboardingTaxonomies(): Promise<OnboardingTaxonomies> {
  const [styleKeywordsResult, occasionTypesResult, colourPaletteResult] =
    await Promise.all([
      supabase
        .from('style_keywords')
        .select('key, label, sort_order')
        .eq('active', true)
        .order('sort_order', { ascending: true }),
      supabase
        .from('occasion_types')
        .select('key, label, sort_order')
        .eq('active', true)
        .order('sort_order', { ascending: true }),
      supabase
        .from('colour_palette')
        .select('key, label, hex, sort_order')
        .eq('active', true)
        .order('sort_order', { ascending: true }),
    ]);

  if (styleKeywordsResult.error) {
    throw styleKeywordsResult.error;
  }
  if (occasionTypesResult.error) {
    throw occasionTypesResult.error;
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

  const occasionTypes: TaxonomyOption[] = (occasionTypesResult.data ?? []).map(
    (row) => ({
      key: row.key,
      label: row.label,
      sortOrder: row.sort_order,
    }),
  );

  const colourPalette: ColourPaletteOption[] = (
    colourPaletteResult.data ?? []
  ).map((row) => ({
    key: row.key,
    label: row.label,
    hex: row.hex,
    sortOrder: row.sort_order,
  }));

  return { styleKeywords, occasionTypes, colourPalette };
}
