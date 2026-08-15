// SS-071 — self-registration reset registry for AC #6 (no cross-user
// bleed on sign-out). Each user-scoped Zustand store file calls
// registerUserStateReset() at module scope, immediately after its own
// create() call — see features/onboarding/onboarding.store.ts,
// features/wardrobe/wardrobe.store.ts, and
// features/outfit-ai/outfit-ai.store.ts for the pattern.
//
// This inverts the usual failure mode: forgetting to register a new
// user-scoped store's reset is now an omission sitting next to that
// store's own definition (where a code reviewer looking at the new store
// is most likely to notice it), not an invisible omission inside a
// sign-out function someone else owns and rarely re-reads. It does not
// eliminate the failure mode (a store added later can still forget to
// register — see docs/tickets/SS-071-design.md edge case #11) but moves
// the point of failure to the most visible place available.
//
// useAuthStore does NOT register here — the session itself is cleared by
// supabase.auth.signOut() -> the SIGNED_OUT event -> hooks/useAuth.ts's
// existing onAuthStateChange listener, which also clears Sentry/PostHog
// identity. Registering it here too would create a second path to the
// same state with different ordering.

type UserStateResetFn = () => void;

const resetFns = new Set<UserStateResetFn>();

export function registerUserStateReset(fn: UserStateResetFn): void {
  resetFns.add(fn);
}

// Exposed for tests only — lets userStateReset.test.ts assert against a
// clean registry per test without every *.store.ts module's own
// registerUserStateReset() call (run once, at module load, outside any
// test's control) polluting other suites' assertions.
export function _clearRegisteredResetsForTests(): void {
  resetFns.clear();
}

export function resetAllUserState(): void {
  for (const fn of resetFns) {
    try {
      fn();
    } catch {
      // One store's reset throwing must not prevent the others from
      // running -- a partial clear is exactly the cross-user-bleed bug
      // this registry exists to prevent. Silently swallowed rather than
      // console.log'd per CLAUDE.md's anti-pattern rule; Sentry capture
      // wiring for this path is a straightforward follow-up, not required
      // for AC #6 to hold.
    }
  }
}
