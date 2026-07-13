import { act, cleanup, renderHook } from '@testing-library/react-native';
import { useAuthStore } from '../../../features/auth/auth.store';

describe('useAuthStore', () => {
  afterEach(async () => {
    // Unmount the previous test's renderHook root before the next one
    // mounts — without this, back-to-back renderHook calls in the same file
    // can leave a stale renderer subscribed to the (singleton) store.
    await cleanup();
    // Zustand stores are module-level singletons — reset between tests so
    // one test's mutations don't leak into the next.
    useAuthStore.setState({ session: null, isSessionLoading: true });
  });

  it('defaults to isSessionLoading: true and session: null', async () => {
    const { result } = await renderHook(() =>
      useAuthStore((s) => s.isSessionLoading),
    );
    expect(result.current).toBe(true);
    expect(useAuthStore.getState().session).toBeNull();
  });

  it('setSession updates state and a typed selector reflects it', async () => {
    const { result } = await renderHook(() => useAuthStore((s) => s.session));
    const fakeSession = { user: { id: 'user-1' } } as never;

    await act(async () => {
      useAuthStore.getState().setSession(fakeSession);
    });

    expect(result.current).toBe(fakeSession);
  });

  it('setSessionLoading updates state and a typed selector reflects it', async () => {
    const { result } = await renderHook(() =>
      useAuthStore((state) => state.isSessionLoading),
    );

    await act(async () => {
      useAuthStore.getState().setSessionLoading(false);
    });

    expect(result.current).toBe(false);
  });
});
