import { act, cleanup, fireEvent, render } from '@testing-library/react-native';
import { Platform } from 'react-native';
import ConfirmScreen from '../../../app/(auth)/confirm';

// Same reasoning as CheckYourEmailNotice.test.tsx: auth.queries.ts
// transitively imports lib/supabase.ts, which constructs the real client at
// module-load time and throws without env vars under Jest.
jest.mock('../../../lib/supabase', () => ({ supabase: {} }));

let mockTokenHashParam: string | undefined = 'the-token-hash';
const mockPush = jest.fn();
jest.mock('expo-router', () => ({
  useLocalSearchParams: () => ({ token_hash: mockTokenHashParam }),
  useRouter: () => ({ push: mockPush }),
}));

const mockConfirmMutate = jest.fn();
const mockAdoptMutate = jest.fn();
jest.mock('../../../features/auth/auth.queries', () => ({
  useConfirmEmailTokenMutation: () => ({ mutate: mockConfirmMutate }),
  useAdoptSessionFromUrlFragmentMutation: () => ({ mutate: mockAdoptMutate }),
}));

const FAKE_SESSION = { access_token: 'tok', user: { id: 'u1' } } as never;
const ORIGINAL_PLATFORM_OS = Platform.OS;

describe('ConfirmScreen (app/(auth)/confirm.tsx)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockTokenHashParam = 'the-token-hash';
    Platform.OS = ORIGINAL_PLATFORM_OS;
    // test-only global, reset between tests.
    (global as { window?: unknown }).window = undefined;
  });

  afterEach(async () => {
    await cleanup();
    Platform.OS = ORIGINAL_PLATFORM_OS;
    (global as { window?: unknown }).window = undefined;
  });

  // Test plan #16 — loading state renders a distinct `working` UI, not
  // blank, while the mutation is pending (mutate never calls back
  // synchronously in these tests unless we invoke the callbacks).
  it('renders a distinct working state on mount, before the mutation settles', async () => {
    const { getByTestId } = await render(<ConfirmScreen />);

    expect(getByTestId('confirm-working')).toBeOnTheScreen();
  });

  // Test plan #9.
  it('token_hash present, mutation resolves a session -> renders success; router.push is never called', async () => {
    const { getByTestId } = await render(<ConfirmScreen />);

    expect(mockConfirmMutate).toHaveBeenCalledWith(
      'the-token-hash',
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    );

    const { onSuccess } = mockConfirmMutate.mock.calls[0][1];
    await act(async () => onSuccess(FAKE_SESSION));

    expect(getByTestId('confirm-success')).toBeOnTheScreen();
    expect(mockPush).not.toHaveBeenCalled();
  });

  // Test plan #10.
  it('token_hash present, mutation rejects with invalid_or_expired_confirmation_link -> renders failure copy + working Sign in link, never the raw error', async () => {
    const { getByTestId, getByText, queryByText } = await render(
      <ConfirmScreen />,
    );

    const { onError } = mockConfirmMutate.mock.calls[0][1];
    await act(async () =>
      onError({
        code: 'invalid_or_expired_confirmation_link',
        message:
          'This link may have expired or already been used. Your account may already be confirmed — try signing in.',
      }),
    );

    expect(getByTestId('confirm-failed')).toBeOnTheScreen();
    expect(
      getByText(
        'This link may have expired or already been used. Your account may already be confirmed — try signing in.',
      ),
    ).toBeOnTheScreen();
    expect(queryByText(/raw supabase error/i)).toBeNull();

    await act(async () => {
      fireEvent.press(getByText('Sign in'));
    });
    expect(mockPush).toHaveBeenCalledWith('/login');
  });

  // Test plan #11.
  it('no token_hash param, web platform, hash carries both tokens -> falls back to adoptSessionFromUrlFragment, renders success', async () => {
    mockTokenHashParam = undefined;
    Platform.OS = 'web';
    global.window = {
      location: {
        hash: '#access_token=at1&refresh_token=rt1',
        pathname: '/confirm',
      },
      history: { replaceState: jest.fn() },
    } as never;

    const { getByTestId } = await render(<ConfirmScreen />);

    expect(mockAdoptMutate).toHaveBeenCalledTimes(1);
    expect(mockConfirmMutate).not.toHaveBeenCalled();

    const { onSuccess } = mockAdoptMutate.mock.calls[0][1];
    await act(async () => onSuccess(FAKE_SESSION));

    expect(getByTestId('confirm-success')).toBeOnTheScreen();
  });

  // Test plan #12.
  it('no token_hash param, no hash tokens either -> renders failed with the "no token" copy, not an indefinite spinner', async () => {
    mockTokenHashParam = undefined;
    Platform.OS = 'web';
    global.window = {
      location: { hash: '', pathname: '/confirm' },
      history: { replaceState: jest.fn() },
    } as never;

    const { getByTestId } = await render(<ConfirmScreen />);

    const { onSuccess } = mockAdoptMutate.mock.calls[0][1];
    await act(async () => onSuccess(null));

    expect(getByTestId('confirm-failed')).toBeOnTheScreen();
  });

  // Test plan #13.
  it('no token_hash param, native platform -> does not attempt the fragment fallback, renders failed', async () => {
    mockTokenHashParam = undefined;
    Platform.OS = 'ios';

    const { getByTestId } = await render(<ConfirmScreen />);

    expect(mockAdoptMutate).not.toHaveBeenCalled();
    expect(mockConfirmMutate).not.toHaveBeenCalled();
    expect(getByTestId('confirm-failed')).toBeOnTheScreen();
  });

  // Test plan #14 — pins the hasAttempted guard: a rerender before the
  // mutation resolves must not fire the underlying exchange a second time.
  it('a rerender before the mutation resolves calls the underlying exchange exactly once', async () => {
    const { rerender } = await render(<ConfirmScreen />);

    await act(async () => {
      rerender(<ConfirmScreen />);
    });
    await act(async () => {
      rerender(<ConfirmScreen />);
    });

    expect(mockConfirmMutate).toHaveBeenCalledTimes(1);
  });

  // Test plan #15 — window.history.replaceState fires once, only on the
  // success path.
  it('on success, window.history.replaceState is called exactly once; never on working or failed', async () => {
    Platform.OS = 'web';
    const replaceState = jest.fn();
    global.window = {
      location: { hash: '', pathname: '/confirm' },
      history: { replaceState },
    } as never;

    await render(<ConfirmScreen />);
    expect(replaceState).not.toHaveBeenCalled();

    const { onSuccess } = mockConfirmMutate.mock.calls[0][1];
    await act(async () => onSuccess(FAKE_SESSION));

    expect(replaceState).toHaveBeenCalledTimes(1);
  });
});
