import { cleanup, fireEvent, render } from '@testing-library/react-native';
import ProfileScreen from '../../../app/(tabs)/profile';
import { useAuthStore } from '../../../features/auth/auth.store';

const mockPush = jest.fn();
const mockReplace = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
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
const mockTrack = jest.fn();
jest.mock('../../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({ track: mockTrack }),
}));

// SS-071: profile.tsx's own Sign Out button drives useSignOutMutation
// directly -- mocked here rather than exercising the real mutation's
// React Query plumbing, which is signOut.test.tsx's job.
const mockSignOutMutate = jest.fn();
let mockIsPending = false;
jest.mock('../../../features/auth/auth.queries', () => ({
  useSignOutMutation: () => ({
    mutate: mockSignOutMutate,
    isPending: mockIsPending,
  }),
}));

describe('ProfileScreen (app/(tabs)/profile.tsx)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockIsPending = false;
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

  it('renders a "Sign Out" button with an accessibility label', async () => {
    const { getByLabelText } = await render(<ProfileScreen />);
    expect(getByLabelText('Sign Out')).toBeOnTheScreen();
  });

  it('pressing "Sign Out" shows the confirm affordance without signing out yet; Cancel returns to the default state', async () => {
    const { getByLabelText, getByTestId, queryByTestId } = await render(
      <ProfileScreen />,
    );

    await fireEvent.press(getByLabelText('Sign Out'));

    expect(getByTestId('sign-out-confirm')).toBeOnTheScreen();
    expect(mockSignOutMutate).not.toHaveBeenCalled();

    await fireEvent.press(getByLabelText('Cancel'));

    expect(queryByTestId('sign-out-confirm')).toBeNull();
    expect(mockSignOutMutate).not.toHaveBeenCalled();
  });

  it('confirming Sign Out fires the mutation, tracks sign_out, and calls router.replace("/login")', async () => {
    mockSignOutMutate.mockImplementation(
      (_vars: unknown, { onSuccess }: { onSuccess: () => void }) => {
        onSuccess();
      },
    );
    const { getByLabelText } = await render(<ProfileScreen />);

    await fireEvent.press(getByLabelText('Sign Out'));
    await fireEvent.press(getByLabelText('Confirm Sign Out'));

    expect(mockSignOutMutate).toHaveBeenCalledWith(
      undefined,
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
    expect(mockTrack).toHaveBeenCalledWith('sign_out', {
      method: 'phone_otp',
    });
    expect(mockReplace).toHaveBeenCalledWith('/login');
  });

  it('the confirm Sign Out button is disabled while the mutation is pending (double-tap protection)', async () => {
    mockIsPending = true;
    const { getByLabelText } = await render(<ProfileScreen />);

    await fireEvent.press(getByLabelText('Sign Out'));

    expect(getByLabelText('Confirm Sign Out')).toBeDisabled();
  });
});
