import { supabase } from '../../lib/supabase';
import type { Json } from '../../types/supabase';
import type {
  BudgetRangeKey,
  GenderKey,
  OccasionPriorityKey,
  StyleKeywordKey,
  StylePreferences,
  WardrobeTypeKey,
} from './onboarding.types';

// The only place besides hooks/features/auth that calls
// supabase.from('users') for this domain — per CLAUDE.md's "no direct
// Supabase calls outside features/<domain>/*.queries.ts" rule extended to
// this service layer that backs onboarding.queries.ts. Reference-table reads
// (style_keywords/occasion_types/colour_palette) live in
// onboarding.taxonomies.service.ts instead — see that file's header comment
// for why it's kept separate.

export interface Step1ProfileInput {
  fullName: string;
  gender: GenderKey;
  city: string;
}

export interface OnboardingProgress {
  fullName: string;
  gender: GenderKey | undefined;
  city: string;
  stylePreferences: StylePreferences | null;
  // (SS-007 revision) needed by mobile/app/edit-preferences.tsx to decide
  // whether to show the "finish setting up your profile" banner — see
  // docs/tickets/SS-007-design.md's "Files to create/modify" #1.
  onboardingCompleted: boolean;
}

// Incremental save: Step 1's "Next" persists full_name/gender/city
// immediately (dedicated top-level users columns, cheap partial update) —
// see docs/tickets/SS-004-design.md's "Incremental save" section for why
// this is a separate, earlier write from completeOnboarding below.
export async function saveStep1Profile(
  userId: string,
  { fullName, gender, city }: Step1ProfileInput,
): Promise<void> {
  const { error } = await supabase
    .from('users')
    .update({ full_name: fullName, gender, city })
    .eq('id', userId);

  if (error) {
    throw error;
  }
}

// "Get Started" — single write of the full style_preferences JSONB blob plus
// onboarding_completed: true.
export async function completeOnboarding(
  userId: string,
  data: StylePreferences,
): Promise<void> {
  // StylePreferences is a closed interface (fixed keys, typed arrays), so it
  // isn't structurally assignable to Json's index signature — cast, same as
  // any strongly-typed JSONB payload written through this generated client.
  const { error } = await supabase
    .from('users')
    .update({
      style_preferences: data as unknown as Json,
      onboarding_completed: true,
    })
    .eq('id', userId);

  if (error) {
    throw error;
  }
}

// Reads back whatever's already saved, used to pre-fill the wizard on
// resume/edit-preferences re-entry. Resolves to null (rather than throwing)
// when there's no row/no data to resume from.
export async function fetchOnboardingProgress(
  userId: string,
): Promise<OnboardingProgress | null> {
  const { data, error } = await supabase
    .from('users')
    .select('full_name, gender, city, style_preferences, onboarding_completed')
    .eq('id', userId)
    .maybeSingle();

  if (error) {
    throw error;
  }

  if (!data) {
    return null;
  }

  return {
    fullName: data.full_name ?? '',
    gender: (data.gender as GenderKey | null) ?? undefined,
    city: data.city ?? '',
    stylePreferences:
      (data.style_preferences as StylePreferences | null) ?? null,
    onboardingCompleted: data.onboarding_completed ?? false,
  };
}

// (SS-007) Granular Preferences Editor — read-merge-write partial update of
// a single style_preferences key, backing the 5 exported wrappers below. Not
// an atomic DB-level jsonb merge (Supabase JS's `.update()` can't express
// `jsonb || jsonb` without a new RPC/stored procedure, out of scope for this
// ticket) — logged as BL-036 (docs/BACKLOG.md) rather than silently fixed.
// Throws on either the read or the write error, matching every other method
// in this file.
async function patchStylePreferences(
  userId: string,
  patch: Partial<StylePreferences>,
): Promise<void> {
  const { data, error: readError } = await supabase
    .from('users')
    .select('style_preferences')
    .eq('id', userId)
    .maybeSingle();

  if (readError) {
    throw readError;
  }

  const current =
    (data?.style_preferences as Partial<StylePreferences> | null) ?? {};
  const merged = { ...current, ...patch };

  const { error: writeError } = await supabase
    .from('users')
    .update({ style_preferences: merged as unknown as Json })
    .eq('id', userId);

  if (writeError) {
    throw writeError;
  }
}

export async function updateStyleKeywords(
  userId: string,
  styles: StyleKeywordKey[],
): Promise<void> {
  return patchStylePreferences(userId, { styles });
}

export async function updateWardrobeType(
  userId: string,
  wardrobeType: WardrobeTypeKey,
): Promise<void> {
  return patchStylePreferences(userId, { wardrobe_type: wardrobeType });
}

export async function updateOccasionPriorities(
  userId: string,
  occasions: OccasionPriorityKey[],
): Promise<void> {
  return patchStylePreferences(userId, { occasions_priority: occasions });
}

export async function updateBudgetRange(
  userId: string,
  budgetRange: BudgetRangeKey,
): Promise<void> {
  return patchStylePreferences(userId, { budget_range: budgetRange });
}

export async function updateFavouriteColours(
  userId: string,
  colours: string[],
): Promise<void> {
  return patchStylePreferences(userId, { favourite_colours: colours });
}
