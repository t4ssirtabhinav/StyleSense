import type { Session } from '@supabase/supabase-js';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  adoptSessionFromUrlFragment,
  checkOnboardingCompleted,
  confirmEmailToken,
  fetchUserPlanTier,
  resendConfirmationEmail,
  sendOtp,
  signInWithEmail,
  signOut,
  signUpWithEmail,
  verifyOtp,
} from './auth.service';
import { useAuthStore } from './auth.store';
import type { AuthError, EmailSignUpResult } from './auth.types';
import { resetAllUserState } from './userStateReset';

// The only place these React Query hooks are called from is components (per
// CLAUDE.md's anti-pattern rule extended to this domain: no direct Supabase
// calls in components — only through features/<domain>/*.queries.ts).
//
// Both mutations are typed with AuthError as the TError generic (rather than
// react-query's default Error) since auth.service.ts's sendOtp/verifyOtp
// always throw the typed AuthError, never a raw Error — this lets
// consumers' onError handlers read `.code`/`.message` without an unsafe cast.

export function useSendOtpMutation() {
  return useMutation<void, AuthError, string>({ mutationFn: sendOtp });
}

export function useVerifyOtpMutation() {
  return useMutation<Session, AuthError, { phone: string; token: string }>({
    mutationFn: ({ phone, token }) => verifyOtp(phone, token),
  });
}

// SS-072 — same TError-generic-as-AuthError shape as the two mutations
// above; signUpWithEmail/signInWithEmail always throw the typed AuthError,
// never a raw Error (see auth.service.ts).
//
// REVISION 2 (2026-08-17): retyped from Session to EmailSignUpResult —
// signUpWithEmail no longer throws on a null session (that is now a
// success: { status: 'confirmation_required', email }). Consumers must
// branch on `.status`.
export function useSignUpWithEmailMutation() {
  return useMutation<
    EmailSignUpResult,
    AuthError,
    { email: string; password: string }
  >({
    mutationFn: ({ email, password }) => signUpWithEmail(email, password),
  });
}

export function useSignInWithEmailMutation() {
  return useMutation<Session, AuthError, { email: string; password: string }>({
    mutationFn: ({ email, password }) => signInWithEmail(email, password),
  });
}

// SS-072 REVISION 2 (AC #12) — backs CheckYourEmailNotice's Resend control.
// TVariables is the email string directly (no object wrapper needed, unlike
// the two mutations above — resendConfirmationEmail takes a single arg).
export function useResendConfirmationEmailMutation() {
  return useMutation<void, AuthError, string>({
    mutationFn: (email) => resendConfirmationEmail(email),
  });
}

// SS-073 — same TError-generic-as-AuthError shape as every other mutation
// in this file. confirmEmailToken/adoptSessionFromUrlFragment always throw
// the typed AuthError, never a raw Error (see auth.service.ts).
export function useConfirmEmailTokenMutation() {
  return useMutation<Session, AuthError, string>({
    mutationFn: (tokenHash) => confirmEmailToken(tokenHash),
  });
}

// TVariables is `void` — adoptSessionFromUrlFragment takes no arguments
// (it reads window.location.hash itself). Resolves `Session | null`
// (`null` means "no fragment tokens present", not a failure — confirm.tsx
// branches on that to fall through to its own `failed` state).
export function useAdoptSessionFromUrlFragmentMutation() {
  return useMutation<Session | null, AuthError, void>({
    mutationFn: () => adoptSessionFromUrlFragment(),
  });
}

// Exported so other domains that need to invalidate this query (e.g.
// onboarding.queries.ts's useCompleteOnboardingMutation, on completion) use
// the exact same key instead of duplicating the literal and risking drift.
// This query key is OWNED by this file — always build it via this helper.
export function onboardingCompletedQueryKey(userId: string | undefined) {
  return ['auth', 'onboarding-completed', userId] as const;
}

export function useOnboardingCompletedQuery(userId: string | undefined) {
  return useQuery({
    queryKey: onboardingCompletedQueryKey(userId),
    queryFn: () => checkOnboardingCompleted(userId as string),
    enabled: Boolean(userId),
  });
}

// SS-014: feeds the free-tier banner and the floating add-button's gating
// logic (design doc's Files section) -- same file-layering precedent as
// useOnboardingCompletedQuery above, wrapping the existing (SS-009)
// fetchUserPlanTier service function in a useQuery for the first time.
export function planTierQueryKey(userId: string | undefined) {
  return ['auth', 'plan-tier', userId] as const;
}

export function usePlanTierQuery(userId: string | undefined) {
  return useQuery({
    queryKey: planTierQueryKey(userId),
    queryFn: () => fetchUserPlanTier(userId as string),
    enabled: Boolean(userId),
  });
}

// SS-071 — AC #5/#6/#7. Ordering is load-bearing (design doc's "Sign-out"
// section):
//   1. cancelQueries() — settle in-flight fetches before the session dies
//      (edge case: a mutation/query in flight during sign-out).
//   2. signOut() — never rejects (see auth.service.ts's own comment on the
//      verified SDK failure-path finding).
//   3+4 (in `finally`, so they run even if step 2 unexpectedly throws):
//      defensively null the in-memory session, resetAllUserState(), then
//      queryClient.clear() — clear must be AFTER cancel and AFTER the
//      service call, so a late-resolving query can't repopulate the cache
//      post-clear. This is what makes AC #7 hold by construction: a failed
//      network signOut still clears local state and still reaches login.
//
// useAuthStore's session is NOT in the userStateReset registry (that
// registry is for user-DATA stores only) — it's normally cleared by
// supabase.auth.signOut() -> SIGNED_OUT -> hooks/useAuth.ts's existing
// onAuthStateChange listener. The explicit setSession(null) here is
// defensive, not redundant: verified against the installed
// @supabase/auth-js@2.108.2 (see auth.service.ts), a signOut() failure on
// the "real" (non-ignorable) error branch skips the SDK's own
// _removeSession() call and therefore never fires SIGNED_OUT — without
// this line, that specific branch would leave the user looking
// signed-in in the UI even though the mutation is telling profile.tsx to
// navigate to /login.
export function useSignOutMutation() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, void>({
    mutationFn: async () => {
      await queryClient.cancelQueries();
      try {
        await signOut();
      } finally {
        useAuthStore.getState().setSession(null);
        resetAllUserState();
        queryClient.clear();
      }
    },
  });
}
