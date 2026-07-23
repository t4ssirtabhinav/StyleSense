import { cleanup, render } from '@testing-library/react-native';
import TabsLayout from '../../../app/(tabs)/_layout';
import { useAuthStore } from '../../../features/auth/auth.store';

// SS-005 (Home Screen Shell + Bottom Tab Navigation): extends the existing
// expo-router mock to also stub Tabs/Tabs.Screen (previously only mocked
// Redirect/Slot, back when this layout rendered <Slot />).
jest.mock('expo-router', () => {
  const react = jest.requireActual('react');
  const reactNative = jest.requireActual('react-native');

  const MockTabs = ({ children }: { children: React.ReactNode }) => {
    void children;
    return react.createElement(
      reactNative.Text,
      { testID: 'tabs' },
      'guarded content',
    );
  };
  MockTabs.Screen = () => null;

  return {
    Redirect: ({ href }: { href: string }) =>
      react.createElement(reactNative.Text, { testID: 'redirect' }, href),
    Tabs: MockTabs,
  };
});

describe('TabsLayout (Auth Guard)', () => {
  afterEach(async () => {
    // Unmount before resetting store state — otherwise the still-mounted
    // previous render's subscription triggers a state update outside act().
    await cleanup();
    useAuthStore.setState({ session: null, isSessionLoading: true });
  });

  it('renders the loading Card/Text and not <Redirect> while isSessionLoading is true (first-render race guard)', async () => {
    useAuthStore.setState({ isSessionLoading: true, session: null });
    const { getByText, queryByTestId } = await render(<TabsLayout />);

    expect(getByText('Loading…')).toBeOnTheScreen();
    expect(queryByTestId('redirect')).toBeNull();
  });

  it('renders <Redirect href="/login" /> when isSessionLoading is false and session is null', async () => {
    useAuthStore.setState({ isSessionLoading: false, session: null });
    const { getByTestId } = await render(<TabsLayout />);

    expect(getByTestId('redirect')).toHaveTextContent('/login');
  });

  it('renders the guarded child content (<Tabs>) when a valid session exists', async () => {
    useAuthStore.setState({
      isSessionLoading: false,
      session: { user: { id: 'user-1' } } as never,
    });
    const { getByTestId, queryByTestId } = await render(<TabsLayout />);

    expect(getByTestId('tabs')).toBeOnTheScreen();
    expect(queryByTestId('redirect')).toBeNull();
  });
});
