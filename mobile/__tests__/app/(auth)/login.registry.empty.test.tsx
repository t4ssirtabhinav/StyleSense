import { cleanup, render } from '@testing-library/react-native';
import LoginScreen from '../../../app/(auth)/login';

// SS-071 design doc edge case #12 — AUTH_METHODS should never be empty in
// practice, but the type allows it (`readonly AuthMethodDescriptor[]`), and
// this is the boundary-sweep test for that empty case: login.tsx must
// render a neutral message rather than crash on AUTH_METHODS[0]. A
// separate file (same reasoning as login.registry.test.tsx / .single —
// per-file static jest.mock).
jest.mock('../../../features/auth/auth.methods', () => ({
  AUTH_METHODS: [],
}));

describe('LoginScreen — empty registry (boundary case)', () => {
  afterEach(async () => {
    await cleanup();
  });

  it('renders a neutral message instead of crashing when AUTH_METHODS is empty', async () => {
    const { getByTestId, getByText } = await render(<LoginScreen />);

    expect(getByTestId('login-screen')).toBeOnTheScreen();
    expect(
      getByText('No sign-in method is available right now.'),
    ).toBeOnTheScreen();
  });
});
