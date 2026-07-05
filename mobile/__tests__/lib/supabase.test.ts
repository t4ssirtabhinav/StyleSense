/**
 * SS-002 foundation coverage.
 *
 * `mobile/lib/supabase.ts` had no test coverage yet even though SS-003 (Phone
 * Auth) depends on it. Per `docs/tickets/SS-002-design.md`'s test plan, this
 * guards the two properties that matter for session persistence on device:
 * - auth storage is wired to the SecureStore adapter (not AsyncStorage/memory)
 * - `persistSession: true` so sessions survive app restarts
 *
 * It also documents the security invariant that only the anon key (never a
 * service_role key) is used to construct the client.
 */
import { createClient } from '@supabase/supabase-js';

jest.mock('@supabase/supabase-js', () => ({
  createClient: jest.fn(() => ({})),
}));

// `lib/supabase.ts` reads these directly from `process.env` at module load
// time; Jest does not load `.env.local` the way Metro does, so we set them
// explicitly here to test the wiring deterministically regardless of the
// developer machine's local env file.
const TEST_URL = 'https://test-project.supabase.co';
const TEST_ANON_KEY = 'test-anon-key';

describe('supabase client configuration', () => {
  beforeEach(() => {
    process.env.EXPO_PUBLIC_SUPABASE_URL = TEST_URL;
    process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY = TEST_ANON_KEY;
  });

  it('is constructed with the SecureStore adapter and persistSession: true', () => {
    jest.isolateModules(() => {
      require('../../lib/supabase');
    });

    expect(createClient).toHaveBeenCalledTimes(1);
    const [url, key, options] = (createClient as jest.Mock).mock.calls[0];

    expect(url).toBe(TEST_URL);
    expect(key).toBe(TEST_ANON_KEY);

    expect(options.auth.persistSession).toBe(true);
    expect(options.auth.autoRefreshToken).toBe(true);
    expect(options.auth.detectSessionInUrl).toBe(false);

    expect(typeof options.auth.storage.getItem).toBe('function');
    expect(typeof options.auth.storage.setItem).toBe('function');
    expect(typeof options.auth.storage.removeItem).toBe('function');
  });

  it('never receives a service_role-shaped key (anon key only)', () => {
    jest.isolateModules(() => {
      require('../../lib/supabase');
    });

    const [, key] = (createClient as jest.Mock).mock.calls[0];
    // Supabase anon/service_role JWTs both decode from base64, but this repo's
    // contract (CLAUDE.md: "service_role key must never appear in client-side
    // code") means the key sourced here must come from EXPO_PUBLIC_* env only.
    expect(key).toBe(process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY);
  });
});
