import { useEffect } from 'react';
import { useAuthStore } from '../features/auth/auth.store';
import { supabase } from '../lib/supabase';

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
        }
      } catch {
        // A failed initial session fetch is treated the same as "no
        // session" — the Auth Guard then correctly redirects to /login
        // instead of hanging on a permanent loading state.
        if (isMounted) {
          setSession(null);
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
    });

    return () => {
      isMounted = false;
      subscription.unsubscribe();
    };
  }, []);
}
