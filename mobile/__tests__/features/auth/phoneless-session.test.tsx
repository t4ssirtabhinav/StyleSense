import { cleanup, render } from '@testing-library/react-native';
import TabsLayout from '../../../app/(tabs)/_layout';
import ProfileScreen from '../../../app/(tabs)/profile';
import { useAuthStore } from '../../../features/auth/auth.store';

// SS-071 AC #8 — no screen or hook assumes session.user.phone is non-null.
// SS-070's admin-created accounts (email-only) are exactly this shape, and
// the auto-provision trigger (002_onboarding_completed.sql) already writes
// a public.users row with phone IS NULL for them — not a hypothetical
// fixture.

const mockPush = jest.fn();
const mockReplace = jest.fn();
jest.mock('expo-router', () => {
  const react = jest.requireActual('react');
  const reactNative = jest.requireActual('react-native');
  return {
    useRouter: () => ({ push: mockPush, replace: mockReplace }),
    Redirect: ({ href }: { href: string }) =>
      react.createElement(reactNative.Text, { testID: 'redirect' }, href),
  };
});

jest.mock('../../../features/home/home.queries', () => ({
  useUserGreetingQuery: () => ({
    data: undefined,
    isSuccess: false,
    isLoading: true,
    isError: false,
  }),
}));

jest.mock('../../../features/style-score/style-score.queries', () => ({
  useStyleScoreQuery: () => ({
    isLoading: false,
    isError: false,
    data: { total: 0, state: 'ok', breakdown: [], isPremium: false },
    refetch: jest.fn(),
  }),
}));

jest.mock('../../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({ track: jest.fn() }),
}));

jest.mock('../../../features/auth/auth.queries', () => ({
  useSignOutMutation: () => ({ mutate: jest.fn(), isPending: false }),
}));

const mockUseAuthRouting = jest.fn();
jest.mock('../../../features/auth/useAuthRouting', () => ({
  useAuthRouting: () => mockUseAuthRouting(),
}));

jest.mock('expo-router/ui', () => {
  const react = jest.requireActual('react');
  const reactNative = jest.requireActual('react-native');
  const MockTabs = () =>
    react.createElement(
      reactNative.Text,
      { testID: 'tabs' },
      'guarded content',
    );
  return {
    Tabs: MockTabs,
    TabSlot: () => null,
    TabList: ({ children }: { children: React.ReactNode }) =>
      react.createElement(reactNative.View, null, children),
    TabTrigger: ({ children }: { children: React.ReactNode }) =>
      react.createElement(reactNative.View, null, children),
  };
});

jest.mock('react-native-safe-area-context', () => ({
  ...jest.requireActual('react-native-safe-area-context'),
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));

describe('Phone-less session fixtures (AC #8)', () => {
  afterEach(async () => {
    await cleanup();
    useAuthStore.setState({ session: null, isSessionLoading: true });
    jest.clearAllMocks();
  });

  it('ProfileScreen mounts and renders without throwing given an email-only, phone-null session', async () => {
    useAuthStore.setState({
      session: {
        user: { id: 'user-1', email: 'a@b.com', phone: null },
      } as never,
      isSessionLoading: false,
    });

    const { getByTestId, toJSON } = await render(<ProfileScreen />);

    expect(getByTestId('profile-screen')).toBeOnTheScreen();
    expect(JSON.stringify(toJSON())).not.toContain('undefined');
  });

  it('TabsLayout mounts and renders the guarded content without throwing given an email-only, phone-null session', async () => {
    useAuthStore.setState({
      session: {
        user: { id: 'user-1', email: 'a@b.com', phone: null },
      } as never,
      isSessionLoading: false,
    });
    mockUseAuthRouting.mockReturnValue({ status: 'app' });

    const { getByTestId } = await render(<TabsLayout />);

    expect(getByTestId('tabs')).toBeOnTheScreen();
  });

  it('ProfileScreen does not crash and renders no literal "undefined" with neither phone nor email on the session', async () => {
    useAuthStore.setState({
      session: { user: { id: 'user-1' } } as never,
      isSessionLoading: false,
    });

    const { getByTestId, toJSON } = await render(<ProfileScreen />);

    expect(getByTestId('profile-screen')).toBeOnTheScreen();
    expect(JSON.stringify(toJSON())).not.toContain('undefined');
  });

  it('TabsLayout does not crash with neither phone nor email on the session', async () => {
    useAuthStore.setState({
      session: { user: { id: 'user-1' } } as never,
      isSessionLoading: false,
    });
    mockUseAuthRouting.mockReturnValue({ status: 'app' });

    const { getByTestId } = await render(<TabsLayout />);

    expect(getByTestId('tabs')).toBeOnTheScreen();
  });
});
