import { render } from '@testing-library/react-native';
import HomeScreen from '../../../app/(tabs)/index';

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

describe('HomeScreen (app/(tabs)/index.tsx)', () => {
  it('renders GreetingHeader, OccasionPillRow, WardrobeNudgeCard, and TrendingPicksPlaceholder', async () => {
    const { getByTestId } = await render(<HomeScreen />);

    expect(getByTestId('greeting-header')).toBeOnTheScreen();
    expect(getByTestId('occasion-pill-row')).toBeOnTheScreen();
    expect(getByTestId('wardrobe-nudge-card')).toBeOnTheScreen();
    expect(getByTestId('trending-picks-placeholder')).toBeOnTheScreen();
  });
});
