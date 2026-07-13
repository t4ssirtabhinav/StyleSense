import { cleanup, render } from '@testing-library/react-native';
import TabsLayout from '../../../app/(tabs)/_layout';
import { useAuthStore } from '../../../features/auth/auth.store';

jest.mock('expo-router', () => {
  const react = jest.requireActual('react');
  const reactNative = jest.requireActual('react-native');
  return {
    Redirect: ({ href }: { href: string }) =>
      react.createElement(reactNative.Text, { testID: 'redirect' }, href),
    Slot: () =>
      react.createElement(
        reactNative.Text,
        { testID: 'slot' },
        'guarded content',
      ),
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

  it('renders the guarded child content (<Slot />) when a valid session exists', async () => {
    useAuthStore.setState({
      isSessionLoading: false,
      session: { user: { id: 'user-1' } } as never,
    });
    const { getByTestId, queryByTestId } = await render(<TabsLayout />);

    expect(getByTestId('slot')).toBeOnTheScreen();
    expect(queryByTestId('redirect')).toBeNull();
  });
});
