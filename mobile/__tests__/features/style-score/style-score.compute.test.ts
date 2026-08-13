import { computeStyleScore } from '../../../features/style-score/style-score.compute';
import {
  ACTIVITY_TARGET_POINTS,
  COST_PER_WEAR_EXCELLENT_RUPEES,
  COST_PER_WEAR_POOR_RUPEES,
  STYLE_SCORE_TIP_THRESHOLD,
  VARIETY_TARGET_DISTINCT_CATEGORIES,
} from '../../../features/style-score/style-score.constants';
import type { StyleScoreInputs } from '../../../features/style-score/style-score.types';

const BASE_INPUTS: StyleScoreInputs = {
  itemCount: 0,
  distinctCategories: 0,
  coveredOccasionKeys: [],
  activeOccasionKeys: [],
  costPerWearValues: [],
  outfitsThisMonth: 0,
  wearsThisMonth: 0,
};

function inputs(overrides: Partial<StyleScoreInputs>): StyleScoreInputs {
  return { ...BASE_INPUTS, ...overrides };
}

describe('computeStyleScore', () => {
  it('returns total: 0, state: empty_wardrobe and all four score: null for itemCount: 0', () => {
    const result = computeStyleScore(inputs({ itemCount: 0 }));
    expect(result.total).toBe(0);
    expect(result.state).toBe('empty_wardrobe');
    expect(result.breakdown.every((entry) => entry.score === null)).toBe(true);
  });

  it('scores wardrobe_variety as 100 at exactly VARIETY_TARGET_DISTINCT_CATEGORIES and stays 100 above it', () => {
    const atTarget = computeStyleScore(
      inputs({
        itemCount: 10,
        distinctCategories: VARIETY_TARGET_DISTINCT_CATEGORIES,
      }),
    );
    const aboveTarget = computeStyleScore(
      inputs({
        itemCount: 30,
        distinctCategories: VARIETY_TARGET_DISTINCT_CATEGORIES + 5,
      }),
    );
    const variety = (r: ReturnType<typeof computeStyleScore>) =>
      r.breakdown.find((d) => d.dimension === 'wardrobe_variety')?.score;

    expect(variety(atTarget)).toBe(100);
    expect(variety(aboveTarget)).toBe(100);
  });

  it('scores wardrobe_variety proportionally below target (4/8 -> 50)', () => {
    const result = computeStyleScore(
      inputs({ itemCount: 4, distinctCategories: 4 }),
    );
    const variety = result.breakdown.find(
      (d) => d.dimension === 'wardrobe_variety',
    );
    expect(variety?.score).toBe(50);
  });

  it('counts an ethnic category identically to a western one toward variety (no special-casing)', () => {
    const western = computeStyleScore(
      inputs({ itemCount: 2, distinctCategories: 2 }),
    );
    const ethnic = computeStyleScore(
      inputs({ itemCount: 2, distinctCategories: 2 }),
    );
    const varietyOf = (r: ReturnType<typeof computeStyleScore>) =>
      r.breakdown.find((d) => d.dimension === 'wardrobe_variety')?.score;
    expect(varietyOf(western)).toBe(varietyOf(ethnic));
  });

  it('scores occasion_coverage as covered / active x 100 using only the intersection with activeOccasionKeys', () => {
    const result = computeStyleScore(
      inputs({
        itemCount: 5,
        coveredOccasionKeys: ['office', 'wedding_guest'],
        activeOccasionKeys: ['office', 'wedding_guest', 'casual', 'festival'],
      }),
    );
    const coverage = result.breakdown.find(
      (d) => d.dimension === 'occasion_coverage',
    );
    expect(coverage?.score).toBe(50);
  });

  it('ignores an unknown/retired occasion slug in coveredOccasionKeys so coverage cannot exceed 100', () => {
    const result = computeStyleScore(
      inputs({
        itemCount: 5,
        coveredOccasionKeys: ['office', 'some_retired_slug'],
        activeOccasionKeys: ['office'],
      }),
    );
    const coverage = result.breakdown.find(
      (d) => d.dimension === 'occasion_coverage',
    );
    expect(coverage?.score).toBe(100);
  });

  it('counts a duplicated occasion slug across two items once', () => {
    const result = computeStyleScore(
      inputs({
        itemCount: 5,
        coveredOccasionKeys: ['office', 'office', 'office'],
        activeOccasionKeys: ['office', 'casual'],
      }),
    );
    const coverage = result.breakdown.find(
      (d) => d.dimension === 'occasion_coverage',
    );
    expect(coverage?.score).toBe(50);
  });

  it('returns occasion_coverage: null when activeOccasionKeys is empty (no divide-by-zero)', () => {
    const result = computeStyleScore(
      inputs({ itemCount: 5, activeOccasionKeys: [] }),
    );
    const coverage = result.breakdown.find(
      (d) => d.dimension === 'occasion_coverage',
    );
    expect(coverage?.score).toBeNull();
  });

  it('scores cost_efficiency 100 at or below excellent, 0 at or above poor, and linearly between', () => {
    const excellent = computeStyleScore(
      inputs({
        itemCount: 3,
        costPerWearValues: [COST_PER_WEAR_EXCELLENT_RUPEES],
      }),
    );
    const belowExcellent = computeStyleScore(
      inputs({ itemCount: 3, costPerWearValues: [10] }),
    );
    const poor = computeStyleScore(
      inputs({
        itemCount: 3,
        costPerWearValues: [COST_PER_WEAR_POOR_RUPEES],
      }),
    );
    const abovePoor = computeStyleScore(
      inputs({ itemCount: 3, costPerWearValues: [5000] }),
    );
    const midpoint =
      (COST_PER_WEAR_EXCELLENT_RUPEES + COST_PER_WEAR_POOR_RUPEES) / 2;
    const middle = computeStyleScore(
      inputs({ itemCount: 3, costPerWearValues: [midpoint] }),
    );
    const ce = (r: ReturnType<typeof computeStyleScore>) =>
      r.breakdown.find((d) => d.dimension === 'cost_efficiency')?.score;

    expect(ce(excellent)).toBe(100);
    expect(ce(belowExcellent)).toBe(100);
    expect(ce(poor)).toBe(0);
    expect(ce(abovePoor)).toBe(0);
    expect(ce(middle)).toBe(50);
  });

  it('returns cost_efficiency: null for an empty costPerWearValues and renormalises the total over the remaining three weights', () => {
    // wardrobe_variety=100 (30), occasion_coverage=100 (30), activity=0 (20)
    // -> contributing weight = 80, weighted sum = 100*30 + 100*30 + 0*20 = 6000
    // total = round(6000/80) = 75
    const result = computeStyleScore(
      inputs({
        itemCount: 8,
        distinctCategories: VARIETY_TARGET_DISTINCT_CATEGORIES,
        coveredOccasionKeys: ['office'],
        activeOccasionKeys: ['office'],
        costPerWearValues: [],
        outfitsThisMonth: 0,
        wearsThisMonth: 0,
      }),
    );
    const costEfficiency = result.breakdown.find(
      (d) => d.dimension === 'cost_efficiency',
    );
    expect(costEfficiency?.score).toBeNull();
    expect(result.total).toBe(75);
  });

  it('scores activity from 2 x outfits + 1 x wears, capping at 100 beyond ACTIVITY_TARGET_POINTS', () => {
    const partial = computeStyleScore(
      inputs({ itemCount: 3, outfitsThisMonth: 2, wearsThisMonth: 4 }),
    );
    // points = 2*2 + 1*4 = 8 -> 8/16 = 50
    const capped = computeStyleScore(
      inputs({ itemCount: 3, outfitsThisMonth: 20, wearsThisMonth: 20 }),
    );
    const activity = (r: ReturnType<typeof computeStyleScore>) =>
      r.breakdown.find((d) => d.dimension === 'activity')?.score;

    expect(activity(partial)).toBe(50);
    expect(activity(capped)).toBe(100);
  });

  it('scores activity: 0 (not null) for a non-empty wardrobe with no outfits and no wears this month', () => {
    const result = computeStyleScore(
      inputs({ itemCount: 3, outfitsThisMonth: 0, wearsThisMonth: 0 }),
    );
    const activity = result.breakdown.find((d) => d.dimension === 'activity');
    expect(activity?.score).toBe(0);
  });

  it('computes the weighted total over all four dimensions to an exact expected integer for a fully-populated fixture', () => {
    // wardrobe_variety: 8/8 -> 100 (weight 30)
    // occasion_coverage: 2/4 -> 50 (weight 30)
    // cost_efficiency: avg 100 -> 100 (weight 20)
    // activity: (2*1 + 1*8)/16 = 10/16 -> 62.5 -> round -> 63 (weight 20)
    // weighted sum = 100*30 + 50*30 + 100*20 + 63*20 = 3000+1500+2000+1260=7760
    // total = round(7760/100) = 78
    const result = computeStyleScore(
      inputs({
        itemCount: 8,
        distinctCategories: VARIETY_TARGET_DISTINCT_CATEGORIES,
        coveredOccasionKeys: ['office', 'casual'],
        activeOccasionKeys: ['office', 'casual', 'festival', 'wedding_guest'],
        costPerWearValues: [COST_PER_WEAR_EXCELLENT_RUPEES],
        outfitsThisMonth: 1,
        wearsThisMonth: 8,
      }),
    );
    expect(result.total).toBe(78);
  });

  it('attaches a tip only to dimensions scoring below STYLE_SCORE_TIP_THRESHOLD, and null above it', () => {
    const result = computeStyleScore(
      inputs({
        itemCount: 8,
        distinctCategories: VARIETY_TARGET_DISTINCT_CATEGORIES, // 100, no tip
        coveredOccasionKeys: [],
        activeOccasionKeys: ['office'], // 0, tip
        costPerWearValues: [],
        outfitsThisMonth: 0,
        wearsThisMonth: 0, // 0, tip
      }),
    );
    const variety = result.breakdown.find(
      (d) => d.dimension === 'wardrobe_variety',
    );
    const coverage = result.breakdown.find(
      (d) => d.dimension === 'occasion_coverage',
    );
    const activity = result.breakdown.find((d) => d.dimension === 'activity');

    expect(variety?.score).toBeGreaterThanOrEqual(STYLE_SCORE_TIP_THRESHOLD);
    expect(variety?.tip).toBeNull();
    expect(coverage?.tip).not.toBeNull();
    expect(activity?.tip).not.toBeNull();
  });

  it('returns a finite, clamped 0..100 total for hostile inputs (NaN, Infinity, negative counts)', () => {
    const result = computeStyleScore(
      inputs({
        itemCount: 5,
        distinctCategories: Number.NaN,
        coveredOccasionKeys: [],
        activeOccasionKeys: ['office'],
        costPerWearValues: [Number.POSITIVE_INFINITY, Number.NaN],
        outfitsThisMonth: -5,
        wearsThisMonth: Number.NaN,
      }),
    );
    expect(Number.isFinite(result.total)).toBe(true);
    expect(result.total).toBeGreaterThanOrEqual(0);
    expect(result.total).toBeLessThanOrEqual(100);
    for (const entry of result.breakdown) {
      if (entry.score !== null) {
        expect(Number.isFinite(entry.score)).toBe(true);
        expect(entry.score).toBeGreaterThanOrEqual(0);
        expect(entry.score).toBeLessThanOrEqual(100);
      }
    }
  });

  it('always returns all four dimensions in the declared order regardless of which are null', () => {
    const result = computeStyleScore(inputs({ itemCount: 0 }));
    expect(result.breakdown.map((entry) => entry.dimension)).toEqual([
      'wardrobe_variety',
      'occasion_coverage',
      'cost_efficiency',
      'activity',
    ]);
  });
});
