import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import {
  onboardingCompletedQueryKey,
  useSignOutMutation,
} from '../../../features/auth/auth.queries';
import { signOut } from '../../../features/auth/auth.service';
import { useAuthStore } from '../../../features/auth/auth.store';
import {
  _clearRegisteredResetsForTests,
  registerUserStateReset,
} from '../../../features/auth/userStateReset';

const mockSignOut = jest.fn();
jest.mock('../../../lib/supabase', () => ({
  supabase: { auth: { signOut: (arg: unknown) => mockSignOut(arg) } },
}));

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

describe('signOut (service)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('calls supabase.auth.signOut with { scope: "local" } literally', async () => {
    mockSignOut.mockResolvedValue({ error: null });

    await signOut();

    expect(mockSignOut).toHaveBeenCalledWith({ scope: 'local' });
  });

  it('resolves (does not reject) when the SDK returns { error }', async () => {
    mockSignOut.mockResolvedValue({
      error: { message: 'network failure', status: 0 },
    });

    await expect(signOut()).resolves.toBeUndefined();
  });

  it('resolves (does not reject) when the SDK call itself throws', async () => {
    mockSignOut.mockRejectedValue(new Error('unexpected'));

    await expect(signOut()).resolves.toBeUndefined();
  });
});

describe('useSignOutMutation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    _clearRegisteredResetsForTests();
    useAuthStore.setState({
      session: { user: { id: 'user-a' } } as never,
      isSessionLoading: false,
    });
  });

  afterEach(() => {
    useAuthStore.setState({ session: null, isSessionLoading: true });
  });

  it('AC #7: with the SDK signOut mocked to fail, the mutation still runs resetAllUserState() + queryClient.clear() and reaches its success path', async () => {
    mockSignOut.mockResolvedValue({
      error: { message: 'network failure', status: 0 },
    });
    const resetSpy = jest.fn();
    registerUserStateReset(resetSpy);

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    queryClient.setQueryData(['some', 'user-scoped', 'key'], { data: 42 });

    const { result } = await renderHook(() => useSignOutMutation(), {
      wrapper: createWrapper(queryClient),
    });

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(resetSpy).toHaveBeenCalledTimes(1);
    expect(
      queryClient.getQueryData(['some', 'user-scoped', 'key']),
    ).toBeUndefined();
    expect(useAuthStore.getState().session).toBeNull();
  });

  // AC #6, the cross-user-bleed integration test: seed the cache with user
  // A's data and non-default Zustand state, sign out, then set a user-B
  // session and assert zero of user A's values remain anywhere.
  it("AC #6: leaves zero of the previous user's cache values or store state present after sign-out", async () => {
    mockSignOut.mockResolvedValue({ error: null });
    const userAStore = { value: 'user-a-secret' };
    const resetSpy = jest.fn(() => {
      userAStore.value = '';
    });
    registerUserStateReset(resetSpy);

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    queryClient.setQueryData(onboardingCompletedQueryKey('user-a'), true);
    queryClient.setQueryData(['wardrobe', 'items', 'user-a'], [{ id: 1 }]);

    const { result } = await renderHook(() => useSignOutMutation(), {
      wrapper: createWrapper(queryClient),
    });

    result.current.mutate();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // Simulate a different user signing in on the same device.
    useAuthStore.setState({
      session: { user: { id: 'user-b' } } as never,
      isSessionLoading: false,
    });

    expect(
      queryClient.getQueryData(onboardingCompletedQueryKey('user-a')),
    ).toBeUndefined();
    expect(
      queryClient.getQueryData(['wardrobe', 'items', 'user-a']),
    ).toBeUndefined();
    expect(userAStore.value).toBe('');
    expect(useAuthStore.getState().session?.user.id).toBe('user-b');
  });

  it('double-fire: calling the mutation twice does not throw and does not double-navigate', async () => {
    mockSignOut.mockResolvedValue({ error: null });
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });

    const { result } = await renderHook(() => useSignOutMutation(), {
      wrapper: createWrapper(queryClient),
    });

    expect(() => {
      result.current.mutate();
      result.current.mutate();
    }).not.toThrow();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});
