import { act, cleanup, render, waitFor } from '@testing-library/react-native';
import StyleScreen from '../../../app/(tabs)/style';
import { useAuthStore } from '../../../features/auth/auth.store';
import { useOutfitAiStore } from '../../../features/outfit-ai/outfit-ai.store';

// Mirrors style.test.tsx's own established mocking pattern (no JSX inside
// jest.mock() factories).

let mockParams: { occasion?: string } = {};
jest.mock('expo-router', () => ({
  useLocalSearchParams: () => mockParams,
  useRouter: () => ({ push: jest.fn() }),
}));

const mockUseOccasionTaxonomy = jest.fn();
jest.mock('../../../features/onboarding/onboarding.queries', () => ({
  useOccasionTaxonomy: () => mockUseOccasionTaxonomy(),
}));

jest.mock('../../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({ track: jest.fn() }),
}));

jest.mock('../../../lib/storage', () => ({
  hasFiredOnceEvent: jest.fn().mockResolvedValue(true),
  markOnceEventFired: jest.fn(),
}));

const mockUseWardrobeItemCountQuery = jest.fn();
const mockUseGenerateSuggestionsMutation = jest.fn();
jest.mock('../../../features/outfit-ai/outfit-ai.queries', () => ({
  useWardrobeItemCountQuery: (...args: unknown[]) =>
    mockUseWardrobeItemCountQuery(...args),
  useGenerateSuggestionsMutation: () => mockUseGenerateSuggestionsMutation(),
}));

const mockOccasionGridRender = jest.fn();
jest.mock('../../../features/outfit-ai/components/OccasionGrid', () => ({
  OccasionGrid: (props: unknown) => {
    mockOccasionGridRender(props);
    return null;
  },
}));

const mockOutfitCardDeckRender = jest.fn();
jest.mock('../../../features/outfit-ai/components/OutfitCardDeck', () => ({
  OutfitCardDeck: (props: unknown) => {
    mockOutfitCardDeckRender(props);
    return null;
  },
}));

jest.mock(
  '../../../features/outfit-ai/components/SuggestionSkeletonDeck',
  () => ({
    SuggestionSkeletonDeck: () => null,
  }),
);

function setFakeSession() {
  useAuthStore.setState({
    session: {
      user: { id: 'user-1' },
      access_token: 'jwt-token',
      // biome-ignore lint/suspicious/noExplicitAny: minimal fake Session for tests
    } as any,
    isSessionLoading: false,
  });
}

function samplePortfolioResponse(weather: unknown) {
  return {
    portfolio: [
      {
        item_ids: ['item-a', 'item-b'],
        category_labels: { 'item-a': 'Top', 'item-b': 'Bottom' },
        total_score: 0.82,
        rationale: 'a solid pick',
        rationale_language: 'en',
        is_exploration: false,
        gap_flags: [],
        rank: 1,
        outfit_fingerprint: 'a'.repeat(64),
      },
    ],
    limited_options: false,
    gap_report: {
      excluded_missing_color_or_category: 0,
      missing_slots: [],
      weather_exclusions_relaxed: false,
    },
    engine_version: 'engine-v2',
    effort_tier: 'E2',
    cache_hit: false,
    generated_at: '2026-08-07T00:00:00.000Z',
    session_id: 'session-1',
    occasion_key: 'office',
    weather,
  };
}

describe('StyleScreen — weather chip (SS-022)', () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    mockParams = {};
    jest.clearAllMocks();
    useOutfitAiStore.setState({
      selectedOccasionKey: null,
      deckIndex: 0,
      dismissedFingerprints: [],
      sessionId: null,
    });
    setFakeSession();
    mockUseOccasionTaxonomy.mockReturnValue({
      resolveOccasion: (raw: string) => raw,
      topLevelOccasions: [{ key: 'office', label: 'Office', sortOrder: 1 }],
    });
    mockUseWardrobeItemCountQuery.mockReturnValue({
      data: 5,
      isLoading: false,
    });
  });

  it('shows the chip when the response includes weather', async () => {
    mockUseGenerateSuggestionsMutation.mockReturnValue({
      mutate: (_args: unknown, opts: { onSuccess: (data: unknown) => void }) =>
        opts.onSuccess(
          samplePortfolioResponse({
            city: 'Mumbai',
            temp_c: 28.4,
            condition: 'partly_cloudy',
            humidity: 71,
            is_heavy_rain: false,
          }),
        ),
      isPending: false,
      isError: false,
    });

    const { getByTestId, getByText } = await render(<StyleScreen />);
    const onSelect = mockOccasionGridRender.mock.calls[0][0].onSelect;
    await act(async () => {
      onSelect('office');
    });

    await waitFor(() => {
      expect(getByTestId('weather-chip')).toBeOnTheScreen();
    });
    expect(getByText('Dressing for 28°C, partly cloudy')).toBeOnTheScreen();
    // The deck itself still renders — the chip is additive, not a gate.
    expect(mockOutfitCardDeckRender).toHaveBeenCalled();
  });

  it('shows the deck with no chip when weather is null — never blanks the screen', async () => {
    mockUseGenerateSuggestionsMutation.mockReturnValue({
      mutate: (_args: unknown, opts: { onSuccess: (data: unknown) => void }) =>
        opts.onSuccess(samplePortfolioResponse(null)),
      isPending: false,
      isError: false,
    });

    const { queryByTestId } = await render(<StyleScreen />);
    const onSelect = mockOccasionGridRender.mock.calls[0][0].onSelect;
    await act(async () => {
      onSelect('office');
    });

    await waitFor(() => {
      expect(mockOutfitCardDeckRender).toHaveBeenCalled();
    });
    expect(queryByTestId('weather-chip')).toBeNull();
  });

  it('a response omitting the weather field entirely never blanks the screen', async () => {
    // Simulates a caller that omits the field entirely (a legacy/malformed
    // response) — indistinguishable from `undefined` at the JS level, which
    // is exactly the belt-and-braces case WeatherChip's `!weather` guards.
    const responseWithoutWeatherKey = samplePortfolioResponse(undefined);

    mockUseGenerateSuggestionsMutation.mockReturnValue({
      mutate: (_args: unknown, opts: { onSuccess: (data: unknown) => void }) =>
        opts.onSuccess(responseWithoutWeatherKey),
      isPending: false,
      isError: false,
    });

    const { queryByTestId } = await render(<StyleScreen />);
    const onSelect = mockOccasionGridRender.mock.calls[0][0].onSelect;
    await act(async () => {
      onSelect('office');
    });

    await waitFor(() => {
      expect(mockOutfitCardDeckRender).toHaveBeenCalled();
    });
    expect(queryByTestId('weather-chip')).toBeNull();
  });
});
