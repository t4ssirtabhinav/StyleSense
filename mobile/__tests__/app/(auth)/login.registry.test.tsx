import { cleanup, fireEvent, render } from '@testing-library/react-native';
import LoginScreen from '../../../app/(auth)/login';

// SS-071 AC #2 — a separate file from login.test.tsx specifically so that
// file stays mock-free of features/auth/auth.methods (proving AC #1's "the
// real one-entry registry renders exactly today's tree" unmodified, without
// this file's mock ever touching it).
//
// jest.mock() factories are hoisted above this file's own imports, so
// `Text` can't be referenced directly here (Jest's out-of-scope-variable
// guard) — required lazily inside the factory instead, same pattern as
// __tests__/app/(tabs)/_layout.test.tsx's own mocks.
jest.mock('../../../features/auth/auth.methods', () => {
  const react = jest.requireActual('react');
  const reactNative = jest.requireActual('react-native');
  return {
    AUTH_METHODS: [
      {
        id: 'phone_otp',
        label: 'Continue with mobile number',
        Component: () =>
          react.createElement(reactNative.Text, null, 'Phone form'),
      },
      {
        id: 'fake_method',
        label: 'Continue with fake method',
        Component: () =>
          react.createElement(reactNative.Text, null, 'Fake method form'),
      },
    ],
  };
});

describe('LoginScreen — method registry (2 entries)', () => {
  afterEach(async () => {
    await cleanup();
  });

  it('renders both method labels on the chooser', async () => {
    const { getByText } = await render(<LoginScreen />);

    expect(getByText('Continue with mobile number')).toBeOnTheScreen();
    expect(getByText('Continue with fake method')).toBeOnTheScreen();
  });

  it("pressing the second method's label renders its component, reachable via a Back affordance", async () => {
    const { getByText, getByLabelText, queryByText } = await render(
      <LoginScreen />,
    );

    await fireEvent.press(getByText('Continue with fake method'));

    expect(getByText('Fake method form')).toBeOnTheScreen();
    expect(queryByText('Continue with mobile number')).toBeNull();

    await fireEvent.press(getByLabelText('Back'));

    expect(getByText('Continue with mobile number')).toBeOnTheScreen();
    expect(getByText('Continue with fake method')).toBeOnTheScreen();
  });
});
