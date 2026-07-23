import { supabase } from '../../lib/supabase';

// The only place besides features/auth and features/onboarding that calls
// supabase.from('users') — per CLAUDE.md's "no direct Supabase calls outside
// features/<domain>/*.queries.ts" rule extended to this service layer that
// backs home.queries.ts.

// Fails safe to null (never throws) — this backs decorative personalization
// (the Home greeting), not a form/transaction, so a lookup failure should
// never crash the Home screen. Same fail-safe pattern as
// features/auth/auth.service.ts's checkOnboardingCompleted.
export async function fetchUserFirstName(
  userId: string,
): Promise<string | null> {
  try {
    const { data } = await supabase
      .from('users')
      .select('full_name')
      .eq('id', userId)
      .maybeSingle();
    return data?.full_name ?? null;
  } catch {
    return null;
  }
}
