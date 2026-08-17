import { cleanup, fireEvent, render } from '@testing-library/react-native';
import LoginScreen from '../../../app/(auth)/login';

// SS-072 (Deviation 2) rewrite of SS-071's original 2-case file — same
// reasoning as before: this file mocks features/auth/auth.methods so
// login.test.tsx (which resolves the REAL registry) stays untouched, and
// exercises AuthMethodChooser's new "primary inline by default, secondary
// as a button below it" shape instead of the old flat button menu.
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

  it('renders the primary method inline on a bare mount, and the secondary method as a button below it (AC #1 — phone is primary AND default)', async () => {
    const { getByText, queryByText } = await render(<LoginScreen />);

    expect(getByText('Phone form')).toBeOnTheScreen();
    expect(getByText('Continue with fake method')).toBeOnTheScreen();
    // Not a two-button menu: the secondary method's OWN form is not
    // rendered until its button is pressed.
    expect(queryByText('Fake method form')).toBeNull();
  });

  it("pressing the secondary method's label renders its component and hides the primary's, reachable via a Back affordance", async () => {
    const { getByText, getByLabelText, queryByText } = await render(
      <LoginScreen />,
    );

    await fireEvent.press(getByText('Continue with fake method'));

    expect(getByText('Fake method form')).toBeOnTheScreen();
    expect(queryByText('Phone form')).toBeNull();
    expect(queryByText('Continue with fake method')).toBeNull();

    await fireEvent.press(getByLabelText('Back'));

    expect(getByText('Phone form')).toBeOnTheScreen();
    expect(getByText('Continue with fake method')).toBeOnTheScreen();
    expect(queryByText('Fake method form')).toBeNull();
  });
});
