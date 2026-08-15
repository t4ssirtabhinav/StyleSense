import { AUTH_METHODS } from '../../../features/auth/auth.methods';

// auth.methods.ts -> PhoneLoginForm.tsx -> auth.service.ts imports
// lib/supabase.ts, which constructs the real Supabase client at module-load
// time and throws without env vars under Jest — same mocking approach as
// login.test.tsx.
jest.mock('../../../lib/supabase', () => ({ supabase: {} }));

describe('AUTH_METHODS', () => {
  it('has exactly one entry today, id "phone_otp", with a non-empty label and a defined Component', () => {
    expect(AUTH_METHODS).toHaveLength(1);
    expect(AUTH_METHODS[0].id).toBe('phone_otp');
    expect(AUTH_METHODS[0].label.length).toBeGreaterThan(0);
    expect(AUTH_METHODS[0].Component).toBeDefined();
  });
});
