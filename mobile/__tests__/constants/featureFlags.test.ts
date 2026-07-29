import { FEATURE_FLAGS } from '../../constants/featureFlags';

describe('FEATURE_FLAGS', () => {
  it('has exactly 1 entry today', () => {
    expect(Object.keys(FEATURE_FLAGS)).toHaveLength(1);
  });

  it('every value is a unique, non-empty snake_case string', () => {
    const values = Object.values(FEATURE_FLAGS);
    const uniqueValues = new Set(values);

    expect(uniqueValues.size).toBe(values.length);
    for (const value of values) {
      expect(typeof value).toBe('string');
      expect(value.length).toBeGreaterThan(0);
      expect(value).toMatch(/^[a-z0-9]+(_[a-z0-9]+)*$/);
    }
  });

  it('includes paywall_copy_variant', () => {
    expect(Object.values(FEATURE_FLAGS)).toContain('paywall_copy_variant');
  });
});
