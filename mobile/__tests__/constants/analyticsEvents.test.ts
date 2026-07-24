import { ANALYTICS_EVENTS } from '../../constants/analyticsEvents';

describe('ANALYTICS_EVENTS', () => {
  it('has exactly 13 entries', () => {
    expect(Object.keys(ANALYTICS_EVENTS)).toHaveLength(13);
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
