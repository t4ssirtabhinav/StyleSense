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

// SS-009: Sentry/PostHog user-context wiring, mocked so these tests assert
// on the wiring itself without depending on the real SDKs.
const mockSetSentryUserContext = jest.fn();
const mockClearSentryUserContext = jest.fn();
jest.mock('../../lib/sentry', () => ({
  setSentryUserContext: (...args: unknown[]) =>
    mockSetSentryUserContext(...args),
  clearSentryUserContext: () => mockClearSentryUserContext(),
}));

const mockIdentifyAnalyticsUser = jest.fn();
const mockResetAnalyticsUser = jest.fn();
jest.mock('../../lib/analytics', () => ({
  identifyAnalyticsUser: (...args: unknown[]) =>
    mockIdentifyAnalyticsUser(...args),
  resetAnalyticsUser: () => mockResetAnalyticsUser(),
}));

const mockFetchUserPlanTier = jest.fn();
jest.mock('../../features/auth/auth.service', () => ({
  fetchUserPlanTier: (...args: unknown[]) => mockFetchUserPlanTier(...args),
}));

describe('useAuth', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    capturedAuthStateCallback = undefined;
    mockFetchUserPlanTier.mockResolvedValue(null);
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

  it('calls setSentryUserContext/identifyAnalyticsUser with the session user id on a resolved non-null session', async () => {
    const fakeSession = { user: { id: 'user-1' } };
    mockGetSession.mockResolvedValue({ data: { session: fakeSession } });
    mockFetchUserPlanTier.mockResolvedValue(null);

    await renderHook(() => useAuth());

    await waitFor(() => {
      expect(useAuthStore.getState().isSessionLoading).toBe(false);
    });

    expect(mockSetSentryUserContext).toHaveBeenCalledWith('user-1');
    expect(mockIdentifyAnalyticsUser).toHaveBeenCalledWith('user-1');
  });

  it('calls setSentryUserContext again with the tier once fetchUserPlanTier resolves', async () => {
    const fakeSession = { user: { id: 'user-1' } };
    mockGetSession.mockResolvedValue({ data: { session: fakeSession } });
    mockFetchUserPlanTier.mockResolvedValue('premium');

    await renderHook(() => useAuth());

    await waitFor(() => {
      expect(useAuthStore.getState().isSessionLoading).toBe(false);
    });

    await waitFor(() => {
      expect(mockSetSentryUserContext).toHaveBeenCalledWith(
        'user-1',
        'premium',
      );
    });
  });

  it('calls clearSentryUserContext/resetAnalyticsUser on a SIGNED_OUT event (session -> null)', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } });
    await renderHook(() => useAuth());

    await waitFor(() => {
      expect(useAuthStore.getState().isSessionLoading).toBe(false);
    });

    mockClearSentryUserContext.mockClear();
    mockResetAnalyticsUser.mockClear();

    useAuthStore.setState({ session: { user: { id: 'user-1' } } as never });
    capturedAuthStateCallback?.('SIGNED_OUT', null);

    expect(mockClearSentryUserContext).toHaveBeenCalledTimes(1);
    expect(mockResetAnalyticsUser).toHaveBeenCalledTimes(1);
  });
});
