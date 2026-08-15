import { cleanup, render } from '@testing-library/react-native';
import LoginScreen from '../../../app/(auth)/login';

// SS-071 AC #2's test #4 — "with the real one-entry registry, no chooser
// affordance renders" — guards the "must look exactly as today" half of
// AC #1 from the other side. A separate file from login.registry.test.tsx
// (which mocks a 2-entry registry): Jest module mocks are per-file and
// hoisted, so exercising both a 2-entry and a 1-entry registry in one file
// would require jest.resetModules() between them, which reloads React
// itself as a second module instance and breaks the hooks dispatcher
// (`Cannot read properties of null (reading 'useState')`) — confirmed live
// while writing this suite. A fabricated one-entry registry here (rather
// than the real production PhoneLoginForm, which login.test.tsx already
// exercises unmodified) keeps this file's only job — asserting login.tsx's
// own `AUTH_METHODS.length === 1` branch renders no chooser — independent
// of PhoneLoginForm's own dependencies (auth.queries, lib/supabase, etc.).
jest.mock('../../../features/auth/auth.methods', () => {
  const react = jest.requireActual('react');
  const reactNative = jest.requireActual('react-native');
  return {
    AUTH_METHODS: [
      {
        id: 'phone_otp',
        label: 'Continue with mobile number',
        Component: () =>
          react.createElement(
            reactNative.Text,
            { testID: 'only-method' },
            'Phone form',
          ),
      },
    ],
  };
});

describe('LoginScreen — real one-entry registry shape', () => {
  afterEach(async () => {
    await cleanup();
  });

  it('renders no chooser affordance, and renders the single method directly', async () => {
    const { queryByTestId, getByTestId } = await render(<LoginScreen />);

    expect(queryByTestId('auth-method-chooser')).toBeNull();
    expect(getByTestId('only-method')).toBeOnTheScreen();
  });
});
