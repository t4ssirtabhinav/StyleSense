// SS-021 — pure, synchronous style-score formula. No Date, no network, no
// imports outside ./style-score.constants + ./style-score.types (design
// §5.1). This is the testable core of the ticket.

import {
  ACTIVITY_OUTFIT_POINTS,
  ACTIVITY_TARGET_POINTS,
  ACTIVITY_WEAR_POINTS,
  COST_PER_WEAR_EXCELLENT_RUPEES,
  COST_PER_WEAR_POOR_RUPEES,
  STYLE_SCORE_DIMENSION_ORDER,
  STYLE_SCORE_LABELS,
  STYLE_SCORE_TIPS,
  STYLE_SCORE_TIP_THRESHOLD,
  STYLE_SCORE_WEIGHTS,
  VARIETY_TARGET_DISTINCT_CATEGORIES,
} from './style-score.constants';
import type {
  StyleScoreDimension,
  StyleScoreDimensionResult,
  StyleScoreInputs,
  StyleScoreResult,
} from './style-score.types';

function safeNumber(value: number): number {
  return Number.isFinite(value) ? value : 0;
}

function clamp01(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.min(1, Math.max(0, value));
}

function round100(value: number): number {
  return Math.min(100, Math.max(0, Math.round(value)));
}

function scoreWardrobeVariety(inputs: StyleScoreInputs): number | null {
  if (inputs.itemCount === 0) {
    return null;
  }
  const distinct = Math.max(0, safeNumber(inputs.distinctCategories));
  const ratio = clamp01(distinct / VARIETY_TARGET_DISTINCT_CATEGORIES);
  return round100(100 * ratio);
}

function scoreOccasionCoverage(inputs: StyleScoreInputs): number | null {
  if (inputs.itemCount === 0 || inputs.activeOccasionKeys.length === 0) {
    return null;
  }
  const activeSet = new Set(inputs.activeOccasionKeys);
  const coveredSet = new Set(
    inputs.coveredOccasionKeys.filter((key) => activeSet.has(key)),
  );
  const ratio = clamp01(coveredSet.size / activeSet.size);
  return round100(100 * ratio);
}

function scoreCostEfficiency(inputs: StyleScoreInputs): number | null {
  if (inputs.costPerWearValues.length === 0) {
    return null;
  }
  const values = inputs.costPerWearValues.map(safeNumber);
  const avg = values.reduce((sum, v) => sum + v, 0) / values.length;
  const span = COST_PER_WEAR_POOR_RUPEES - COST_PER_WEAR_EXCELLENT_RUPEES;
  const ratio = clamp01((COST_PER_WEAR_POOR_RUPEES - avg) / span);
  return round100(100 * ratio);
}

function scoreActivity(inputs: StyleScoreInputs): number | null {
  if (inputs.itemCount === 0) {
    return null;
  }
  const outfits = Math.max(0, safeNumber(inputs.outfitsThisMonth));
  const wears = Math.max(0, safeNumber(inputs.wearsThisMonth));
  const points =
    ACTIVITY_OUTFIT_POINTS * outfits + ACTIVITY_WEAR_POINTS * wears;
  const ratio = clamp01(points / ACTIVITY_TARGET_POINTS);
  return round100(100 * ratio);
}

const DIMENSION_SCORERS: Record<
  StyleScoreDimension,
  (inputs: StyleScoreInputs) => number | null
> = {
  wardrobe_variety: scoreWardrobeVariety,
  occasion_coverage: scoreOccasionCoverage,
  cost_efficiency: scoreCostEfficiency,
  activity: scoreActivity,
};

export function computeStyleScore(inputs: StyleScoreInputs): StyleScoreResult {
  const breakdown: StyleScoreDimensionResult[] =
    STYLE_SCORE_DIMENSION_ORDER.map((dimension) => {
      const score = DIMENSION_SCORERS[dimension](inputs);
      const tip =
        score !== null && score < STYLE_SCORE_TIP_THRESHOLD
          ? STYLE_SCORE_TIPS[dimension]
          : null;
      return {
        dimension,
        label: STYLE_SCORE_LABELS[dimension],
        score,
        weight: STYLE_SCORE_WEIGHTS[dimension],
        tip,
      };
    });

  const contributing = breakdown.filter(
    (entry): entry is StyleScoreDimensionResult & { score: number } =>
      entry.score !== null,
  );

  let total = 0;
  if (contributing.length > 0) {
    const weightedSum = contributing.reduce(
      (sum, entry) => sum + entry.weight * entry.score,
      0,
    );
    const weightTotal = contributing.reduce(
      (sum, entry) => sum + entry.weight,
      0,
    );
    total = weightTotal > 0 ? Math.round(weightedSum / weightTotal) : 0;
  }
  total = round100(safeNumber(total));

  return {
    total,
    state: inputs.itemCount === 0 ? 'empty_wardrobe' : 'ok',
    breakdown,
  };
}
