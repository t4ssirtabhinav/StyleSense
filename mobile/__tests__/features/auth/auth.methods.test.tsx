import { AUTH_METHODS } from '../../../features/auth/auth.methods';

// auth.methods.ts -> PhoneLoginForm.tsx -> auth.service.ts imports
// lib/supabase.ts, which constructs the real Supabase client at module-load
// time and throws without env vars under Jest — same mocking approach as
// login.test.tsx.
jest.mock('../../../lib/supabase', () => ({ supabase: {} }));

// SS-072: auth.methods.ts -> EmailAuthForm.tsx -> hooks/useAnalytics ->
// lib/analytics.ts -> posthog-react-native/@sentry/react-native (ESM, not
// Jest-parseable without this mock) — same fix as login.test.tsx's own
// verification task, needed here because this file also resolves the real
// registry.
jest.mock('../../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({ track: jest.fn() }),
}));

describe('AUTH_METHODS', () => {
  // SS-072: was "has exactly one entry today"; now pins primacy-by-array-
  // order (docs/tickets/SS-072-design.md's Test plan #4), which
  // AuthMethodChooser.tsx's reshape depends on — AUTH_METHODS[0] must stay
  // 'phone_otp' for AC #1's "phone remains visually primary/default" to
  // hold.
  it('has exactly two entries; [0].id is "phone_otp" and [1].id is "email_password"', () => {
    expect(AUTH_METHODS).toHaveLength(2);
    expect(AUTH_METHODS[0].id).toBe('phone_otp');
    expect(AUTH_METHODS[0].label.length).toBeGreaterThan(0);
    expect(AUTH_METHODS[0].Component).toBeDefined();
    expect(AUTH_METHODS[1].id).toBe('email_password');
    expect(AUTH_METHODS[1].label.length).toBeGreaterThan(0);
    expect(AUTH_METHODS[1].Component).toBeDefined();
  });
});
