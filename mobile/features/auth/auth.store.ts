import type { Session } from '@supabase/supabase-js';
import { create } from 'zustand';

export interface AuthState {
  session: Session | null;
  isSessionLoading: boolean;
  setSession: (session: Session | null) => void;
  setSessionLoading: (loading: boolean) => void;
}

// This is the one piece of session state shared across the Auth Guard
// (app/(tabs)/_layout.tsx) and, indirectly, every screen. Everything else in
// this ticket (phone number in progress, OTP value, resend countdown) is
// local screen useState, not global store state — nothing outside the two
// auth screens needs it.
//
// `isSessionLoading` defaults to `true` (not `false`) to avoid a one-frame
// flash-redirect to /login for users who actually have a valid persisted
// session — hooks/useAuth.ts's initial getSession() call is asynchronous.
export const useAuthStore = create<AuthState>((set) => ({
  session: null,
  isSessionLoading: true,
  setSession: (session) => set({ session }),
  setSessionLoading: (isSessionLoading) => set({ isSessionLoading }),
}));
