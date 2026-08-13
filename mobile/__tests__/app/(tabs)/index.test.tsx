import { render } from '@testing-library/react-native';
import HomeScreen from '../../../app/(tabs)/index';
import { useAuthStore } from '../../../features/auth/auth.store';

// SS-005 (Home Screen Shell + Bottom Tab Navigation) full rewrite — the
// previous file was SS-008's disposable Card/Text smoke test, which no
// longer exists after this ticket. Child components (GreetingHeader,
// OccasionPillRow, WardrobeNudgeCard) call out to auth/query hooks, mocked
// here purely to keep this a composition smoke test rather than duplicating
// their own dedicated unit tests.
const mockPush = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock('../../../features/home/home.queries', () => ({
  useUserGreetingQuery: () => ({
    data: null,
    isSuccess: true,
    isLoading: false,
    isError: false,
  }),
}));

// SS-014: WardrobeNudgeCard now calls useWardrobeItemCountQuery, which pulls
// in the whole wardrobe.queries.ts module graph (including
// @sentry/react-native, via useUploadWardrobeItem's captureException call)
// -- unmocked, that real import fails to parse under this test's Jest
// transform (an unrelated @sentry/core ESM-only sub-dependency, not covered
// by jest.config.js's transformIgnorePatterns allow-list). Mocked here for
// the same "composition smoke test, not a re-test of the child's own
// behaviour" reason as home.queries above -- WardrobeNudgeCard.test.tsx
// covers the real hook's behaviour.
jest.mock('../../../features/wardrobe/wardrobe.queries', () => ({
  useWardrobeItemCountQuery: () => ({
    data: 0,
    isLoading: false,
    isError: false,
  }),
}));

// (SS-025) OccasionPillRow now calls useOccasionTaxonomy for pill colour --
// the real module's import chain reaches lib/supabase.ts (createClient at
// module scope), which throws without real Supabase env vars under Jest.
// Mocked here for the same "composition smoke test" reason as the two
// mocks above -- OccasionPillRow.test.tsx covers the real hook's behaviour.
jest.mock('../../../features/onboarding/onboarding.queries', () => ({
  useOccasionTaxonomy: () => ({
    occasions: [],
    topLevelOccasions: [],
    resolveOccasion: (raw: string) => raw,
    label: (slug: string) => slug,
    badgeColor: () => undefined,
    optionsIncluding: (tags: readonly string[]) =>
      tags.map((t) => ({ key: t })),
    isLoading: false,
    isError: false,
    isStale: false,
    refetch: jest.fn(),
  }),
}));

// SS-021: StyleScoreCard now calls useStyleScoreQuery, whose module graph
// (via style-score.queries.ts -> features/auth/auth.service.ts) reaches
// lib/supabase.ts (createClient at module scope), which throws without real
// Supabase env vars under Jest -- same "composition smoke test" reason as
// the mocks above. StyleScoreCard.test.tsx covers the real hook's
// behaviour.
jest.mock('../../../features/style-score/style-score.queries', () => ({
  useStyleScoreQuery: () => ({
    isLoading: false,
    isError: false,
    data: { total: 42, state: 'ok', breakdown: [], isPremium: false },
    refetch: jest.fn(),
  }),
}));

// StyleScoreCard also calls useAnalytics, whose module graph
// (hooks/useAnalytics.ts -> lib/analytics.ts) reaches @sentry/react-native,
// which ships ESM the default transform can't parse -- same
// "composition smoke test" reason as the mocks above.
jest.mock('../../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({ track: jest.fn() }),
}));

describe('HomeScreen (app/(tabs)/index.tsx)', () => {
  beforeEach(() => {
    useAuthStore.setState({
      session: { user: { id: 'user-1' } } as never,
      isSessionLoading: false,
    });
  });

  it('renders GreetingHeader, StyleScoreCard, OccasionPillRow, WardrobeNudgeCard, and TrendingPicksPlaceholder', async () => {
    const { getByTestId } = await render(<HomeScreen />);

    expect(getByTestId('greeting-header')).toBeOnTheScreen();
    expect(getByTestId('style-score-card')).toBeOnTheScreen();
    expect(getByTestId('occasion-pill-row')).toBeOnTheScreen();
    expect(getByTestId('wardrobe-nudge-card')).toBeOnTheScreen();
    expect(getByTestId('trending-picks-placeholder')).toBeOnTheScreen();
  });
});
