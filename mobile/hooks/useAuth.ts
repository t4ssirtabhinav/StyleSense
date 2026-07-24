import type { Session } from '@supabase/supabase-js';
import { useEffect } from 'react';
import { fetchUserPlanTier } from '../features/auth/auth.service';
import { useAuthStore } from '../features/auth/auth.store';
import { identifyAnalyticsUser, resetAnalyticsUser } from '../lib/analytics';
import { clearSentryUserContext, setSentryUserContext } from '../lib/sentry';
import { supabase } from '../lib/supabase';

// SS-009: covers every authenticated session — a fresh OTP verify AND a
// returning user's persisted-session reopen (verify-otp.tsx alone would
// only cover the former). `plan_tier` is fetched fire-and-forget (never
// awaited) and fails safe to skipping the tag, matching the ticket's own
// "never await in UI code" note extended to monitoring context.
function syncMonitoringContext(session: Session | null): void {
  if (!session) {
    clearSentryUserContext();
    resetAnalyticsUser();
    return;
  }

  const userId = session.user.id;
  setSentryUserContext(userId);
  identifyAnalyticsUser(userId);

  fetchUserPlanTier(userId)
    .then((planTier) => {
      if (planTier) {
        setSentryUserContext(userId, planTier);
      }
    })
    .catch(() => {
      // fetchUserPlanTier already fails safe to null internally; this catch
      // exists only as defense in depth against an unexpected throw.
    });
}

// Device/platform-capability-style hook (same category as CLAUDE.md's named
// useCamera/useLocation examples), called exactly once, from root
// app/_layout.tsx. Writes into features/auth/auth.store.ts, does not return
// the session itself — consumers read the store directly via a typed
// selector. This hook's only job is wiring the auth-state listener, once.
export function useAuth(): void {
  useEffect(() => {
    const { setSession, setSessionLoading } = useAuthStore.getState();
    let isMounted = true;

    setSessionLoading(true);

    const seedInitialSession = async () => {
      try {
        const {
          data: { session },
        } = await supabase.auth.getSession();
        if (isMounted) {
          setSession(session);
          syncMonitoringContext(session);
        }
      } catch {
        // A failed initial session fetch is treated the same as "no
        // session" — the Auth Guard then correctly redirects to /login
        // instead of hanging on a permanent loading state.
        if (isMounted) {
          setSession(null);
          syncMonitoringContext(null);
        }
      } finally {
        if (isMounted) {
          setSessionLoading(false);
        }
      }
    };

    seedInitialSession();

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      syncMonitoringContext(session);
    });

    return () => {
      isMounted = false;
      subscription.unsubscribe();
    };
  }, []);
}
