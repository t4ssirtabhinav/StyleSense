import { cleanup, fireEvent, render } from '@testing-library/react-native';
import ProfileScreen from '../../../app/(tabs)/profile';
import { useAuthStore } from '../../../features/auth/auth.store';

const mockPush = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock('../../../features/home/home.queries', () => ({
  useUserGreetingQuery: () => ({
    data: 'Priya Sharma',
    isSuccess: true,
    isLoading: false,
    isError: false,
  }),
}));

// SS-021: StyleScoreCard now calls useStyleScoreQuery, whose module graph
// reaches lib/supabase.ts (createClient at module scope), which throws
// without real Supabase env vars under Jest -- same "composition smoke
// test" reason as home.queries above. StyleScoreCard.test.tsx covers the
// real hook's behaviour.
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

describe('ProfileScreen (app/(tabs)/profile.tsx)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useAuthStore.setState({
      session: { user: { id: 'user-1' } } as never,
      isSessionLoading: false,
    });
  });

  afterEach(async () => {
    await cleanup();
    useAuthStore.setState({ session: null, isSessionLoading: true });
  });

  it('renders the "Edit Preferences" button', async () => {
    const { getByText } = await render(<ProfileScreen />);
    expect(getByText('Edit Preferences')).toBeOnTheScreen();
  });

  it('renders StyleScoreCard', async () => {
    const { getByTestId } = await render(<ProfileScreen />);
    expect(getByTestId('style-score-card')).toBeOnTheScreen();
  });

  // (SS-007 revision) BL-025: repointed from '/onboarding' (full wizard
  // replay) to the new dedicated '/edit-preferences' screen.
  it('tapping "Edit Preferences" calls router.push(\'/edit-preferences\')', async () => {
    const { getByText } = await render(<ProfileScreen />);
    fireEvent.press(getByText('Edit Preferences'));
    expect(mockPush).toHaveBeenCalledWith('/edit-preferences');
  });
});
