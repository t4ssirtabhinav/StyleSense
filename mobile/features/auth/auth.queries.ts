import type { Session } from '@supabase/supabase-js';
import { useMutation, useQuery } from '@tanstack/react-query';
import { checkUserProfileExists, sendOtp, verifyOtp } from './auth.service';
import type { AuthError } from './auth.types';

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

export function useUserProfileExistsQuery(userId: string | undefined) {
  return useQuery({
    queryKey: ['auth', 'profile-exists', userId],
    queryFn: () => checkUserProfileExists(userId as string),
    enabled: Boolean(userId),
  });
}
