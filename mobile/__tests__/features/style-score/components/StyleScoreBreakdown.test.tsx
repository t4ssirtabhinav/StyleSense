import { render } from '@testing-library/react-native';
import { StyleScoreBreakdown } from '../../../../features/style-score/components/StyleScoreBreakdown';
import { STYLE_SCORE_TIP_THRESHOLD } from '../../../../features/style-score/style-score.constants';
import type { StyleScoreDimensionResult } from '../../../../features/style-score/style-score.types';

const mockTrack = jest.fn();
jest.mock('../../../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({ track: mockTrack }),
}));

const BREAKDOWN: StyleScoreDimensionResult[] = [
  {
    dimension: 'wardrobe_variety',
    label: 'Wardrobe Variety',
    score: 90,
    weight: 30,
    tip: null,
  },
  {
    dimension: 'occasion_coverage',
    label: 'Occasion Coverage',
    score: 40,
    weight: 30,
    tip: 'Tag your items with more occasions...',
  },
  {
    dimension: 'cost_efficiency',
    label: 'Cost Efficiency',
    score: null,
    weight: 20,
    tip: null,
  },
  {
    dimension: 'activity',
    label: 'Activity',
    score: 60,
    weight: 20,
    tip: 'Save an outfit...',
  },
];

describe('StyleScoreBreakdown', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders a tip for a dimension below the threshold and no tip above it', async () => {
    const { getByText, queryByText } = await render(
      <StyleScoreBreakdown
        breakdown={BREAKDOWN}
        isPremium
        onUpgrade={jest.fn()}
      />,
    );
    expect(BREAKDOWN[1].score).toBeLessThan(STYLE_SCORE_TIP_THRESHOLD);
    expect(getByText('Tag your items with more occasions...')).toBeTruthy();
    expect(queryByText('Save an outfit...')).toBeTruthy();
  });

  it('renders "—" rather than 0 for a null sub-score', async () => {
    const { getByText } = await render(
      <StyleScoreBreakdown
        breakdown={BREAKDOWN}
        isPremium
        onUpgrade={jest.fn()}
      />,
    );
    expect(getByText('—')).toBeTruthy();
  });

  it('fires premium_paywall_viewed with { source: "style_score" } exactly once when rendered for a free user', async () => {
    await render(
      <StyleScoreBreakdown
        breakdown={BREAKDOWN}
        isPremium={false}
        onUpgrade={jest.fn()}
      />,
    );
    expect(mockTrack).toHaveBeenCalledTimes(1);
    expect(mockTrack).toHaveBeenCalledWith('premium_paywall_viewed', {
      source: 'style_score',
    });
  });

  it('does not fire premium_paywall_viewed for a premium user', async () => {
    await render(
      <StyleScoreBreakdown
        breakdown={BREAKDOWN}
        isPremium
        onUpgrade={jest.fn()}
      />,
    );
    expect(mockTrack).not.toHaveBeenCalled();
  });

  it('never renders sub-score values for a free user', async () => {
    const { queryByText } = await render(
      <StyleScoreBreakdown
        breakdown={BREAKDOWN}
        isPremium={false}
        onUpgrade={jest.fn()}
      />,
    );
    expect(queryByText('90')).toBeNull();
    expect(queryByText('40')).toBeNull();
    expect(queryByText('60')).toBeNull();
    expect(queryByText('Wardrobe Variety')).toBeNull();
  });
});
