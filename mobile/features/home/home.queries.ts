import { useQuery } from '@tanstack/react-query';
import { fetchUserFirstName } from './home.service';

// The only place this React Query hook is called from is components (per
// CLAUDE.md's anti-pattern rule extended to this domain: no direct Supabase
// calls in components — only through features/<domain>/*.queries.ts).
export function useUserGreetingQuery(userId: string | undefined) {
  return useQuery<string | null>({
    queryKey: ['home', 'greeting', userId],
    queryFn: () => fetchUserFirstName(userId as string),
    enabled: Boolean(userId),
  });
}
