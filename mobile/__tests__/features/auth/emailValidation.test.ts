import {
  normalizeEmail,
  validateEmail,
  validatePassword,
} from '../../../features/auth/auth.service';

// auth.service.ts's top-level import of lib/supabase.ts constructs the real
// Supabase client at module-load time and throws without env vars under
// Jest — same mocking approach as auth.service.test.ts / login.test.tsx.
jest.mock('../../../lib/supabase', () => ({ supabase: {} }));

// docs/tickets/SS-072-design.md's Test plan #5-7.
describe('normalizeEmail', () => {
  it('trims surrounding whitespace and lowercases', () => {
    expect(normalizeEmail('  User@X.com ')).toBe('user@x.com');
  });
});

describe('validateEmail', () => {
  it('rejects an empty string', () => {
    expect(validateEmail('')).toEqual({
      valid: false,
      message: 'Please enter a valid email address.',
    });
  });

  it('rejects a string with no @', () => {
    expect(validateEmail('not-an-email')).toEqual({
      valid: false,
      message: 'Please enter a valid email address.',
    });
  });

  it('rejects a string with no domain dot', () => {
    expect(validateEmail('user@domain')).toEqual({
      valid: false,
      message: 'Please enter a valid email address.',
    });
  });

  it('accepts a normal address', () => {
    expect(validateEmail('user@example.com')).toEqual({ valid: true });
  });

  it('accepts an address with surrounding whitespace/case (normalized internally)', () => {
    expect(validateEmail('  User@X.com ')).toEqual({ valid: true });
  });
});

describe('validatePassword', () => {
  it('rejects fewer than 8 characters with the exact message', () => {
    expect(validatePassword('short7c')).toEqual({
      valid: false,
      message: 'Password must be at least 8 characters.',
    });
  });

  it('accepts exactly 8 characters', () => {
    expect(validatePassword('exactly8')).toEqual({ valid: true });
  });

  it('does not trim — a password of 8 spaces is accepted', () => {
    expect(validatePassword('        ')).toEqual({ valid: true });
  });
});
