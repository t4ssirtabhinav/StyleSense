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

  it('tapping "Edit Preferences" calls router.push(\'/onboarding\') — BL-023 regression guard', async () => {
    const { getByText } = await render(<ProfileScreen />);
    fireEvent.press(getByText('Edit Preferences'));
    expect(mockPush).toHaveBeenCalledWith('/onboarding');
  });
});
