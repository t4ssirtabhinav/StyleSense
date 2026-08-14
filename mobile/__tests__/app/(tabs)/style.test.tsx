import {
  act,
  cleanup,
  fireEvent,
  render,
  waitFor,
} from '@testing-library/react-native';
import StyleScreen from '../../../app/(tabs)/style';
import { useAuthStore } from '../../../features/auth/auth.store';
import { useOutfitAiStore } from '../../../features/outfit-ai/outfit-ai.store';

// All mocked child components below return `null` (or a minimal stand-in)
// and only record their received props via a spy -- mirrors
// wardrobe.test.tsx's own established pattern (no JSX inside jest.mock()
// factories, NativeWind's babel plugin rejects out-of-scope references).

let mockParams: { occasion?: string } = {};
const mockPush = jest.fn();
jest.mock('expo-router', () => ({
  useLocalSearchParams: () => mockParams,
  useRouter: () => ({ push: mockPush }),
}));

const mockUseOccasionTaxonomy = jest.fn();
jest.mock('../../../features/onboarding/onboarding.queries', () => ({
  useOccasionTaxonomy: () => mockUseOccasionTaxonomy(),
}));

const mockTrack = jest.fn();
jest.mock('../../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({ track: mockTrack }),
}));

const mockHasFiredOnceEvent = jest.fn();
const mockMarkOnceEventFired = jest.fn();
jest.mock('../../../lib/storage', () => ({
  hasFiredOnceEvent: (...args: unknown[]) => mockHasFiredOnceEvent(...args),
  markOnceEventFired: (...args: unknown[]) => mockMarkOnceEventFired(...args),
}));

const mockUseWardrobeItemCountQuery = jest.fn();
const mockGenerateMutate = jest.fn();
const mockGenerateReset = jest.fn();
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

const mockSkeletonDeckRender = jest.fn();
jest.mock(
  '../../../features/outfit-ai/components/SuggestionSkeletonDeck',
  () => ({
    SuggestionSkeletonDeck: () => {
      mockSkeletonDeckRender();
      return null;
    },
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

function samplePortfolioResponse() {
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
    weather: null,
  };
}

describe('StyleScreen (app/(tabs)/style.tsx)', () => {
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
    mockHasFiredOnceEvent.mockResolvedValue(false);
    mockUseWardrobeItemCountQuery.mockReturnValue({
      data: 5,
      isLoading: false,
    });
    mockUseGenerateSuggestionsMutation.mockReturnValue({
      mutate: mockGenerateMutate,
      isPending: false,
      isError: false,
    });
  });

  it('zero wardrobe items renders the upload CTA and never calls the suggestions service', async () => {
    mockUseWardrobeItemCountQuery.mockReturnValue({
      data: 0,
      isLoading: false,
    });

    const { getByText, getByLabelText } = await render(<StyleScreen />);

    expect(getByText('Add a few pieces first')).toBeOnTheScreen();
    await fireEvent.press(getByLabelText('Add items'));
    expect(mockPush).toHaveBeenCalledWith('/wardrobe/upload');
    expect(mockGenerateMutate).not.toHaveBeenCalled();
  });

  it('tapping an occasion tile fires the request immediately (AC #1, one tap)', async () => {
    await render(<StyleScreen />);

    const onSelect = mockOccasionGridRender.mock.calls[0][0].onSelect;
    await act(async () => {
      onSelect('office');
    });

    expect(mockGenerateMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        request: expect.objectContaining({
          occasion: 'office',
          exclude_fingerprints: [],
        }),
        jwt: 'jwt-token',
      }),
      expect.anything(),
    );
  });

  it('a ?occasion= deep link pre-selects and auto-fires with zero taps', async () => {
    mockParams = { occasion: 'office' };

    await render(<StyleScreen />);

    await waitFor(() => {
      expect(mockGenerateMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          request: expect.objectContaining({ occasion: 'office' }),
        }),
        expect.anything(),
      );
    });
  });

  it('skeleton deck renders while pending', async () => {
    mockUseGenerateSuggestionsMutation.mockReturnValue({
      mutate: mockGenerateMutate,
      isPending: true,
      isError: false,
    });

    await render(<StyleScreen />);

    expect(mockSkeletonDeckRender).toHaveBeenCalled();
  });

  it('error state renders the retry copy and a back-to-occasions escape hatch on a rejected mutation', async () => {
    mockUseGenerateSuggestionsMutation.mockReturnValue({
      mutate: mockGenerateMutate,
      reset: mockGenerateReset,
      isPending: false,
      isError: true,
    });

    const { getByLabelText } = await render(<StyleScreen />);

    expect(getByLabelText('Retry')).toBeOnTheScreen();
    expect(getByLabelText('Back to occasions')).toBeOnTheScreen();
  });

  it('"Back to occasions" resets the mutation instead of retrying, so a repeatedly-failing request never traps the user', async () => {
    mockUseGenerateSuggestionsMutation.mockReturnValue({
      mutate: mockGenerateMutate,
      reset: mockGenerateReset,
      isPending: false,
      isError: true,
    });

    const { getByLabelText } = await render(<StyleScreen />);
    await fireEvent.press(getByLabelText('Back to occasions'));

    expect(mockGenerateReset).toHaveBeenCalled();
    expect(mockGenerateMutate).not.toHaveBeenCalled();
  });

  it('a successful response renders the OutfitCardDeck with the response shape', async () => {
    mockUseGenerateSuggestionsMutation.mockReturnValue({
      mutate: (_args: unknown, opts: { onSuccess: (data: unknown) => void }) =>
        opts.onSuccess(samplePortfolioResponse()),
      isPending: false,
      isError: false,
    });

    await render(<StyleScreen />);

    const onSelect = mockOccasionGridRender.mock.calls[0][0].onSelect;
    await act(async () => {
      onSelect('office');
    });

    await waitFor(() => {
      expect(mockOutfitCardDeckRender).toHaveBeenCalledWith(
        expect.objectContaining({
          occasionKey: 'office',
          sessionId: 'session-1',
          limitedOptions: false,
        }),
      );
    });
  });

  it('first_suggestion_viewed fires once on the first non-empty deck and not again on a regenerate', async () => {
    mockUseGenerateSuggestionsMutation.mockReturnValue({
      mutate: (_args: unknown, opts: { onSuccess: (data: unknown) => void }) =>
        opts.onSuccess(samplePortfolioResponse()),
      isPending: false,
      isError: false,
    });

    await render(<StyleScreen />);
    const onSelect = mockOccasionGridRender.mock.calls[0][0].onSelect;

    await act(async () => {
      onSelect('office');
    });
    await waitFor(() => expect(mockHasFiredOnceEvent).toHaveBeenCalled());
    await waitFor(() => expect(mockTrack).toHaveBeenCalledTimes(1));

    // Second fire (regenerate) -- hasFiredOnceEvent now resolves true, so
    // track() must not be called a second time.
    mockHasFiredOnceEvent.mockResolvedValue(true);
    await act(async () => {
      onSelect('office');
    });
    await waitFor(() => expect(mockHasFiredOnceEvent).toHaveBeenCalledTimes(2));
    expect(mockTrack).toHaveBeenCalledTimes(1);
  });
});
