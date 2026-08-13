import { getIstMonthStart } from '../../../features/style-score/style-score.date';

describe('getIstMonthStart', () => {
  it('returns the 1st of the current IST month at 00:00 IST as a UTC isoTimestamp (UTC instant in a different month than IST)', () => {
    // 2026-07-31T20:00:00Z + 05:30 = 2026-08-01T01:30 IST -> August in IST,
    // still July in UTC.
    const now = new Date('2026-07-31T20:00:00.000Z');
    const result = getIstMonthStart(now);
    // 2026-08-01T00:00 IST == 2026-07-31T18:30:00Z
    expect(result.isoTimestamp).toBe('2026-07-31T18:30:00.000Z');
  });

  it('returns isoDate as YYYY-MM-01 matching the same IST month', () => {
    const now = new Date('2026-07-31T20:00:00.000Z');
    const result = getIstMonthStart(now);
    expect(result.isoDate).toBe('2026-08-01');
  });

  it('is stable across a January boundary (year rollover)', () => {
    // 2025-12-31T20:00:00Z + 05:30 = 2026-01-01T01:30 IST -> January 2026.
    const now = new Date('2025-12-31T20:00:00.000Z');
    const result = getIstMonthStart(now);
    expect(result.isoDate).toBe('2026-01-01');
    expect(result.isoTimestamp).toBe('2025-12-31T18:30:00.000Z');
  });
});
