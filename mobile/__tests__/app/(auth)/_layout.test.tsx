import { cleanup, render } from '@testing-library/react-native';
import AuthLayout from '../../../app/(auth)/_layout';

// SS-071 AC #3 — this is the BL-168 regression suite: mirrors today's live
// reproduction (a valid session on /login rendering the login form instead
// of redirecting) as an explicit assertion, and covers the cold-open /
// /onboarding-preservation cases the deleted verify-otp.tsx useEffect never
// did.

let mockPathname = '/login';
jest.mock('expo-router', () => {
  const react = jest.requireActual('react');
  const reactNative = jest.requireActual('react-native');
  return {
    usePathname: () => mockPathname,
    Redirect: ({ href }: { href: string }) =>
      react.createElement(reactNative.Text, { testID: 'redirect' }, href),
    Stack: () =>
      react.createElement(reactNative.Text, { testID: 'auth-stack' }, 'stack'),
  };
});

const mockUseAuthRouting = jest.fn();
jest.mock('../../../features/auth/useAuthRouting', () => ({
  useAuthRouting: () => mockUseAuthRouting(),
}));

describe('AuthLayout ((auth) forward guard)', () => {
  afterEach(async () => {
    await cleanup();
    mockPathname = '/login';
    jest.clearAllMocks();
  });

  it('BL-168 regression: pathname /login, a valid session, onboarding_completed true -> redirects to / (not the login stack)', async () => {
    mockPathname = '/login';
    mockUseAuthRouting.mockReturnValue({ status: 'app' });

    const { getByTestId, queryByTestId } = await render(<AuthLayout />);

    expect(getByTestId('redirect')).toHaveTextContent('/');
    expect(queryByTestId('auth-stack')).toBeNull();
  });

  it('pathname /login, a valid session, onboarding_completed false -> redirects to /onboarding', async () => {
    mockPathname = '/login';
    mockUseAuthRouting.mockReturnValue({ status: 'onboarding' });

    const { getByTestId, queryByTestId } = await render(<AuthLayout />);

    expect(getByTestId('redirect')).toHaveTextContent('/onboarding');
    expect(queryByTestId('auth-stack')).toBeNull();
  });

  it('pathname /login, no session -> renders the Stack (children), no redirect', async () => {
    mockPathname = '/login';
    mockUseAuthRouting.mockReturnValue({ status: 'unauthenticated' });

    const { getByTestId, queryByTestId } = await render(<AuthLayout />);

    expect(getByTestId('auth-stack')).toBeOnTheScreen();
    expect(queryByTestId('redirect')).toBeNull();
  });

  it('pathname /login, session loading -> renders the auth-entry-loading Card, no redirect (no flash)', async () => {
    mockPathname = '/login';
    mockUseAuthRouting.mockReturnValue({ status: 'loading' });

    const { getByTestId, queryByTestId } = await render(<AuthLayout />);

    expect(getByTestId('auth-entry-loading')).toBeOnTheScreen();
    expect(queryByTestId('redirect')).toBeNull();
    expect(queryByTestId('auth-stack')).toBeNull();
  });

  it('pathname /verify-otp with a fresh completed session behaves the same as /login -> redirects to /', async () => {
    mockPathname = '/verify-otp';
    mockUseAuthRouting.mockReturnValue({ status: 'app' });

    const { getByTestId } = await render(<AuthLayout />);

    expect(getByTestId('redirect')).toHaveTextContent('/');
  });

  it('pathname /verify-otp with a fresh incomplete session -> redirects to /onboarding', async () => {
    mockPathname = '/verify-otp';
    mockUseAuthRouting.mockReturnValue({ status: 'onboarding' });

    const { getByTestId } = await render(<AuthLayout />);

    expect(getByTestId('redirect')).toHaveTextContent('/onboarding');
  });

  it('pathname /onboarding with a session and onboarding_completed true -> renders children, no redirect (SS-016 preservation + anti-loop guarantee)', async () => {
    mockPathname = '/onboarding';
    mockUseAuthRouting.mockReturnValue({ status: 'app' });

    const { getByTestId, queryByTestId } = await render(<AuthLayout />);

    expect(getByTestId('auth-stack')).toBeOnTheScreen();
    expect(queryByTestId('redirect')).toBeNull();
  });

  it('pathname /onboarding with no session -> renders children, no redirect (onboarding.tsx owns its own session guard)', async () => {
    mockPathname = '/onboarding';
    mockUseAuthRouting.mockReturnValue({ status: 'unauthenticated' });

    const { getByTestId, queryByTestId } = await render(<AuthLayout />);

    expect(getByTestId('auth-stack')).toBeOnTheScreen();
    expect(queryByTestId('redirect')).toBeNull();
  });

  // SS-073 Test plan #17-20 — AC #2's "pinned by tests on both sides":
  // /confirm is now a GUARDED_ROUTE, mirroring /login and /verify-otp
  // exactly (no code distinguishes "same user's session" from "a
  // different user's session" — both are the 'app' status and both are
  // resolved identically, by construction, so one test covers both).

  it('SS-073: pathname /confirm, useAuthRouting() returns { status: "app" } -> redirects to / (same-user or different-user session, both resolved identically)', async () => {
    mockPathname = '/confirm';
    mockUseAuthRouting.mockReturnValue({ status: 'app' });

    const { getByTestId, queryByTestId } = await render(<AuthLayout />);

    expect(getByTestId('redirect')).toHaveTextContent('/');
    expect(queryByTestId('auth-stack')).toBeNull();
  });

  it('SS-073: pathname /confirm, useAuthRouting() returns { status: "onboarding" } -> redirects to /onboarding', async () => {
    mockPathname = '/confirm';
    mockUseAuthRouting.mockReturnValue({ status: 'onboarding' });

    const { getByTestId, queryByTestId } = await render(<AuthLayout />);

    expect(getByTestId('redirect')).toHaveTextContent('/onboarding');
    expect(queryByTestId('auth-stack')).toBeNull();
  });

  it('SS-073: pathname /confirm, useAuthRouting() returns { status: "unauthenticated" } -> renders the Stack (falls through to confirm.tsx), no redirect — the cold-open case', async () => {
    mockPathname = '/confirm';
    mockUseAuthRouting.mockReturnValue({ status: 'unauthenticated' });

    const { getByTestId, queryByTestId } = await render(<AuthLayout />);

    expect(getByTestId('auth-stack')).toBeOnTheScreen();
    expect(queryByTestId('redirect')).toBeNull();
  });

  it('SS-073: pathname /(auth)/confirm (route-group-prefixed form) behaves identically to /confirm — redirects to / when a session is live', async () => {
    mockPathname = '/(auth)/confirm';
    mockUseAuthRouting.mockReturnValue({ status: 'app' });

    const { getByTestId } = await render(<AuthLayout />);

    expect(getByTestId('redirect')).toHaveTextContent('/');
  });
});
