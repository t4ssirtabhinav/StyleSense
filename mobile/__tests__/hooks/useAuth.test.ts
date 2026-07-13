import { renderHook, waitFor } from '@testing-library/react-native';
import { useAuthStore } from '../../features/auth/auth.store';
import { useAuth } from '../../hooks/useAuth';

const mockGetSession = jest.fn();
const mockUnsubscribe = jest.fn();
let capturedAuthStateCallback:
  | ((event: string, session: unknown) => void)
  | undefined;

jest.mock('../../lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: (...args: unknown[]) => mockGetSession(...args),
      onAuthStateChange: (
        callback: (event: string, session: unknown) => void,
      ) => {
        capturedAuthStateCallback = callback;
        return { data: { subscription: { unsubscribe: mockUnsubscribe } } };
      },
    },
  },
}));

describe('useAuth', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    capturedAuthStateCallback = undefined;
    useAuthStore.setState({ session: null, isSessionLoading: true });
  });

  it('sets isSessionLoading(false) and session after the initial getSession() resolves', async () => {
    const fakeSession = { user: { id: 'user-1' } };
    mockGetSession.mockResolvedValue({ data: { session: fakeSession } });

    const setSessionLoadingSpy = jest.spyOn(
      useAuthStore.getState(),
      'setSessionLoading',
    );

    await renderHook(() => useAuth());

    // isSessionLoading is set to true synchronously on mount (matches the
    // store's own default, defensively re-asserted by the hook).
    expect(setSessionLoadingSpy).toHaveBeenCalledWith(true);

    await waitFor(() => {
      expect(useAuthStore.getState().isSessionLoading).toBe(false);
    });
    expect(useAuthStore.getState().session).toBe(fakeSession);
  });

  it('updates the store to session: null on a later SIGNED_OUT event', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } });

    await renderHook(() => useAuth());

    await waitFor(() => {
      expect(useAuthStore.getState().isSessionLoading).toBe(false);
    });

    useAuthStore.setState({ session: { user: { id: 'user-1' } } as never });
    capturedAuthStateCallback?.('SIGNED_OUT', null);

    expect(useAuthStore.getState().session).toBeNull();
  });

  it('calls subscription.unsubscribe() on unmount', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } });
    const { unmount } = await renderHook(() => useAuth());

    await waitFor(() => {
      expect(useAuthStore.getState().isSessionLoading).toBe(false);
    });

    await unmount();
    expect(mockUnsubscribe).toHaveBeenCalledTimes(1);
  });
});
