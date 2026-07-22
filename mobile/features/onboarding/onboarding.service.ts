import { supabase } from '../../lib/supabase';
import type { Json } from '../../types/supabase';
import type { GenderKey, StylePreferences } from './onboarding.types';

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
    .select('full_name, gender, city, style_preferences')
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
  };
}
