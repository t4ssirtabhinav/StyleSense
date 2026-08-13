import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { Share } from 'react-native';
import { useAuthStore } from '../../../../features/auth/auth.store';
import { StyleScoreCard } from '../../../../features/style-score/components/StyleScoreCard';
import * as styleScoreCardExport from '../../../../features/style-score/share/styleScoreCardExport';
import * as styleScoreQueries from '../../../../features/style-score/style-score.queries';

const mockPush = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

const mockTrack = jest.fn();
jest.mock('../../../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({ track: mockTrack }),
}));

jest.mock('../../../../features/style-score/style-score.queries', () => ({
  useStyleScoreQuery: jest.fn(),
}));

jest.mock(
  '../../../../features/style-score/share/styleScoreCardExport',
  () => ({
    exportStyleScoreCard: jest.fn(),
  }),
);

const FAKE_USER_ID = 'user-1';
function setFakeSession() {
  useAuthStore.setState({
    // biome-ignore lint/suspicious/noExplicitAny: minimal fake Session for tests
    session: { user: { id: FAKE_USER_ID } } as any,
    isSessionLoading: false,
  });
}
function clearSession() {
  useAuthStore.setState({ session: null, isSessionLoading: false });
}

const PREMIUM_BREAKDOWN = [
  {
    dimension: 'wardrobe_variety',
    label: 'Wardrobe Variety',
    score: 80,
    weight: 30,
    tip: null,
  },
  {
    dimension: 'occasion_coverage',
    label: 'Occasion Coverage',
    score: 50,
    weight: 30,
    tip: 'tip1',
  },
  {
    dimension: 'cost_efficiency',
    label: 'Cost Efficiency',
    score: 70,
    weight: 20,
    tip: null,
  },
  {
    dimension: 'activity',
    label: 'Activity',
    score: 40,
    weight: 20,
    tip: 'tip2',
  },
] as const;

describe('StyleScoreCard', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    setFakeSession();
  });

  it('renders nothing when there is no session', async () => {
    clearSession();
    (styleScoreQueries.useStyleScoreQuery as jest.Mock).mockReturnValue({
      isLoading: false,
      isError: false,
      data: undefined,
      refetch: jest.fn(),
    });
    const { queryByTestId } = await render(
      <StyleScoreCard variant="compact" />,
    );
    expect(queryByTestId('style-score-card')).toBeNull();
  });

  it('renders a Skeleton while loading', async () => {
    (styleScoreQueries.useStyleScoreQuery as jest.Mock).mockReturnValue({
      isLoading: true,
      isError: false,
      data: undefined,
      refetch: jest.fn(),
    });
    const { getByTestId } = await render(<StyleScoreCard variant="compact" />);
    expect(getByTestId('skeleton')).toBeTruthy();
  });

  it('renders the error copy + a working retry button on error (never a 0)', async () => {
    const refetch = jest.fn();
    (styleScoreQueries.useStyleScoreQuery as jest.Mock).mockReturnValue({
      isLoading: false,
      isError: true,
      data: undefined,
      refetch,
    });
    const { getByText, getByLabelText, queryByText } = await render(
      <StyleScoreCard variant="compact" />,
    );
    expect(
      getByText('We could not calculate your style score right now.'),
    ).toBeTruthy();
    expect(queryByText('0')).toBeNull();
    fireEvent.press(getByLabelText('Retry'));
    expect(refetch).toHaveBeenCalled();
  });

  it('renders the empty-wardrobe copy and the add-items CTA for state: empty_wardrobe', async () => {
    (styleScoreQueries.useStyleScoreQuery as jest.Mock).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        total: 0,
        state: 'empty_wardrobe',
        breakdown: [],
        isPremium: false,
      },
      refetch: jest.fn(),
    });
    const { getByText, getByLabelText } = await render(
      <StyleScoreCard variant="compact" />,
    );
    expect(
      getByText('Add your first item to start building your style score.'),
    ).toBeTruthy();
    fireEvent.press(getByLabelText('Add your first item'));
    expect(mockPush).toHaveBeenCalledWith('/wardrobe');
  });

  it('variant="compact" renders the total but no breakdown, no upsell and no share button', async () => {
    (styleScoreQueries.useStyleScoreQuery as jest.Mock).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        total: 72,
        state: 'ok',
        breakdown: PREMIUM_BREAKDOWN,
        isPremium: true,
      },
      refetch: jest.fn(),
    });
    const { getByText, queryByText, queryByTestId } = await render(
      <StyleScoreCard variant="compact" />,
    );
    expect(getByText('72')).toBeTruthy();
    expect(queryByTestId('style-score-breakdown')).toBeNull();
    expect(queryByText('Share Score')).toBeNull();
  });

  it('variant="full" renders the breakdown and the share button', async () => {
    (styleScoreQueries.useStyleScoreQuery as jest.Mock).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        total: 72,
        state: 'ok',
        breakdown: PREMIUM_BREAKDOWN,
        isPremium: true,
      },
      refetch: jest.fn(),
    });
    const { getByTestId, getByText } = await render(
      <StyleScoreCard variant="full" />,
    );
    expect(getByTestId('style-score-breakdown')).toBeTruthy();
    expect(getByText('Share Score')).toBeTruthy();
  });

  it('free user sees the total and the locked upsell, and no sub-score value appears anywhere in the tree', async () => {
    (styleScoreQueries.useStyleScoreQuery as jest.Mock).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        total: 55,
        state: 'ok',
        breakdown: PREMIUM_BREAKDOWN,
        isPremium: false,
      },
      refetch: jest.fn(),
    });
    const { getByText, queryByText } = await render(
      <StyleScoreCard variant="full" />,
    );
    expect(getByText('55')).toBeTruthy();
    expect(
      getByText('Unlock your 4 sub-scores and personalised tips with Premium.'),
    ).toBeTruthy();
    expect(queryByText('80')).toBeNull();
    expect(queryByText('50')).toBeNull();
    expect(queryByText('70')).toBeNull();
    expect(queryByText('40')).toBeNull();
  });

  it('premium user sees all four sub-score values with their labels', async () => {
    (styleScoreQueries.useStyleScoreQuery as jest.Mock).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        total: 72,
        state: 'ok',
        breakdown: PREMIUM_BREAKDOWN,
        isPremium: true,
      },
      refetch: jest.fn(),
    });
    const { getByText } = await render(<StyleScoreCard variant="full" />);
    for (const entry of PREMIUM_BREAKDOWN) {
      expect(getByText(entry.label)).toBeTruthy();
      expect(getByText(String(entry.score))).toBeTruthy();
    }
  });

  it('share button calls exportStyleScoreCard, passes the resulting text to Share.share, and tracks style_score_shared', async () => {
    (styleScoreQueries.useStyleScoreQuery as jest.Mock).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        total: 72,
        state: 'ok',
        breakdown: PREMIUM_BREAKDOWN,
        isPremium: true,
      },
      refetch: jest.fn(),
    });
    (styleScoreCardExport.exportStyleScoreCard as jest.Mock).mockResolvedValue({
      kind: 'text',
      body: 'My score is 72/100',
    });
    const shareSpy = jest
      .spyOn(Share, 'share')
      .mockResolvedValue({ action: 'sharedAction', activityType: 'mail' });

    const { getByLabelText } = await render(<StyleScoreCard variant="full" />);
    fireEvent.press(getByLabelText('Share Score'));

    await waitFor(() =>
      expect(styleScoreCardExport.exportStyleScoreCard).toHaveBeenCalledWith({
        total: 72,
      }),
    );
    await waitFor(() =>
      expect(shareSpy).toHaveBeenCalledWith({ message: 'My score is 72/100' }),
    );
    await waitFor(() =>
      expect(mockTrack).toHaveBeenCalledWith('style_score_shared', {
        channel: 'mail',
      }),
    );
  });

  it('a rejected/cancelled Share.share does not throw or unmount the card', async () => {
    (styleScoreQueries.useStyleScoreQuery as jest.Mock).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        total: 72,
        state: 'ok',
        breakdown: PREMIUM_BREAKDOWN,
        isPremium: true,
      },
      refetch: jest.fn(),
    });
    (styleScoreCardExport.exportStyleScoreCard as jest.Mock).mockResolvedValue({
      kind: 'text',
      body: 'My score is 72/100',
    });
    jest.spyOn(Share, 'share').mockRejectedValue(new Error('cancelled'));

    const { getByText, getByLabelText } = await render(
      <StyleScoreCard variant="full" />,
    );
    fireEvent.press(getByLabelText('Share Score'));

    await waitFor(() =>
      expect(styleScoreCardExport.exportStyleScoreCard).toHaveBeenCalled(),
    );
    expect(getByText('Share Score')).toBeTruthy();
  });
});
