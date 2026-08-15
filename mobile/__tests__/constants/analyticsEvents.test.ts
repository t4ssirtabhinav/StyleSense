import { ANALYTICS_EVENTS } from '../../constants/analyticsEvents';

describe('ANALYTICS_EVENTS', () => {
  // SS-021 added a 14th entry, STYLE_SCORE_SHARED, additive over the 13 the
  // SS-009 comment above ANALYTICS_EVENTS originally enumerated. SS-071
  // adds a 15th, SIGN_OUT — additive again, per AC #9/#11's "extend, never
  // weaken" discipline.
  it('has exactly 15 entries', () => {
    expect(Object.keys(ANALYTICS_EVENTS)).toHaveLength(15);
  });

  it('includes sign_out', () => {
    expect(Object.values(ANALYTICS_EVENTS)).toContain('sign_out');
  });

  it('every value is a unique, non-empty snake_case string', () => {
    const values = Object.values(ANALYTICS_EVENTS);
    const uniqueValues = new Set(values);

    expect(uniqueValues.size).toBe(values.length);
    for (const value of values) {
      expect(typeof value).toBe('string');
      expect(value.length).toBeGreaterThan(0);
      expect(value).toMatch(/^[a-z0-9]+(_[a-z0-9]+)*$/);
    }
  });

  it('includes app_opened', () => {
    expect(Object.values(ANALYTICS_EVENTS)).toContain('app_opened');
  });
});
