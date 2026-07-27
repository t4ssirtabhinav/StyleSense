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

describe('HomeScreen (app/(tabs)/index.tsx)', () => {
  it('renders GreetingHeader, OccasionPillRow, WardrobeNudgeCard, and TrendingPicksPlaceholder', async () => {
    const { getByTestId } = await render(<HomeScreen />);

    expect(getByTestId('greeting-header')).toBeOnTheScreen();
    expect(getByTestId('occasion-pill-row')).toBeOnTheScreen();
    expect(getByTestId('wardrobe-nudge-card')).toBeOnTheScreen();
    expect(getByTestId('trending-picks-placeholder')).toBeOnTheScreen();
  });
});
