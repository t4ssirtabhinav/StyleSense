import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, renderHook, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { onboardingCompletedQueryKey } from '../../../features/auth/auth.queries';
import { useAuthStore } from '../../../features/auth/auth.store';
import {
  useCompleteOnboardingMutation,
  useOnboardingProgressQuery,
  useOnboardingTaxonomiesQuery,
  useSaveStep1Mutation,
} from '../../../features/onboarding/onboarding.queries';
import * as onboardingService from '../../../features/onboarding/onboarding.service';
import * as onboardingTaxonomiesService from '../../../features/onboarding/onboarding.taxonomies.service';

jest.mock('../../../features/onboarding/onboarding.service', () => ({
  saveStep1Profile: jest.fn(),
  completeOnboarding: jest.fn(),
  fetchOnboardingProgress: jest.fn(),
}));

jest.mock('../../../features/onboarding/onboarding.taxonomies.service', () => ({
  fetchOnboardingTaxonomies: jest.fn(),
}));

// onboarding.queries.ts now imports onboardingCompletedQueryKey from
// features/auth/auth.queries.ts (real module, kept real here so the key
// helper's actual behaviour is exercised) — which in turn imports
// features/auth/auth.service.ts, which imports lib/supabase.ts and throws
// without real Supabase env vars. Mocking auth.service (same convention as
// __tests__/features/auth/auth.queries.test.tsx) keeps that import chain
// from ever reaching lib/supabase.ts.
jest.mock('../../../features/auth/auth.service', () => ({
  sendOtp: jest.fn(),
  verifyOtp: jest.fn(),
  checkOnboardingCompleted: jest.fn(),
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

// Exposes the underlying QueryClient (rather than hiding it inside the
// Wrapper closure) so tests can spy on invalidateQueries directly.
function createWrapperWithClient() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { Wrapper, queryClient };
}

describe('useSaveStep1Mutation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('calls through to saveStep1Profile and exposes isPending/isSuccess', async () => {
    (onboardingService.saveStep1Profile as jest.Mock).mockResolvedValue(
      undefined,
    );
    const { result } = await renderHook(() => useSaveStep1Mutation(), {
      wrapper: createWrapper(),
    });

    expect(result.current.isPending).toBe(false);
    result.current.mutate({
      userId: 'user-1',
      input: { fullName: 'Priya', gender: 'woman', city: 'Mumbai' },
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(onboardingService.saveStep1Profile).toHaveBeenCalledWith('user-1', {
      fullName: 'Priya',
      gender: 'woman',
      city: 'Mumbai',
    });
  });

  it('exposes isError when the mutation rejects', async () => {
    (onboardingService.saveStep1Profile as jest.Mock).mockRejectedValue(
      new Error('network error'),
    );
    const { result } = await renderHook(() => useSaveStep1Mutation(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({
      userId: 'user-1',
      input: { fullName: 'Priya', gender: 'woman', city: 'Mumbai' },
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useCompleteOnboardingMutation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('calls through to completeOnboarding and exposes isPending/isSuccess', async () => {
    (onboardingService.completeOnboarding as jest.Mock).mockResolvedValue(
      undefined,
    );
    const { result } = await renderHook(() => useCompleteOnboardingMutation(), {
      wrapper: createWrapper(),
    });

    const data = {
      styles: ['ethnic'],
      wardrobe_type: 'mostly_ethnic' as const,
      occasions_priority: ['office'],
      budget_range: '1000_3000' as const,
      favourite_colours: ['#000000'],
      gender: 'woman' as const,
    };
    result.current.mutate({ userId: 'user-1', data });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(onboardingService.completeOnboarding).toHaveBeenCalledWith(
      'user-1',
      data,
    );
  });

  // Regression guard (SS-004 fix pass 2, CRITICAL bug): completion must
  // invalidate BOTH the onboarding-progress query it always invalidated AND
  // the auth domain's onboarding-completed query that verify-otp.tsx routes
  // on — this is the second time a completion side-effect missed a query
  // key (progress vs. auth-completion), so this test asserts the coupling
  // explicitly rather than relying on it being remembered next time.
  it('invalidates both the onboarding-progress query and the auth onboarding-completed query on success', async () => {
    (onboardingService.completeOnboarding as jest.Mock).mockResolvedValue(
      undefined,
    );
    const { Wrapper, queryClient } = createWrapperWithClient();
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');

    const { result } = await renderHook(() => useCompleteOnboardingMutation(), {
      wrapper: Wrapper,
    });

    const data = {
      styles: ['ethnic'],
      wardrobe_type: 'mostly_ethnic' as const,
      occasions_priority: ['office'],
      budget_range: '1000_3000' as const,
      favourite_colours: ['#000000'],
      gender: 'woman' as const,
    };
    result.current.mutate({ userId: 'user-1', data });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['onboarding', 'progress', 'user-1'],
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: onboardingCompletedQueryKey('user-1'),
    });
  });
});

describe('useOnboardingProgressQuery', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('is disabled (enabled: false) when userId is undefined', async () => {
    const { result } = await renderHook(
      () => useOnboardingProgressQuery(undefined),
      { wrapper: createWrapper() },
    );

    expect(result.current.fetchStatus).toBe('idle');
    expect(onboardingService.fetchOnboardingProgress).not.toHaveBeenCalled();
  });
});

describe('useOnboardingTaxonomiesQuery', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useAuthStore.setState({ session: null, isSessionLoading: true });
  });

  afterEach(async () => {
    // Unmount before resetting store state — otherwise the still-mounted
    // previous render's subscription triggers a state update outside act()
    // (same convention as app/(tabs)/_layout.test.tsx's afterEach).
    await cleanup();
    useAuthStore.setState({ session: null, isSessionLoading: true });
  });

  // Regression guard for the "no options available" bug: RLS silently
  // returns an empty-but-"successful" result for an unauthenticated read of
  // these reference tables, and the 24h staleTime/Infinity gcTime above
  // would then cache that empty result for the rest of the app session —
  // even after the user later authenticates. Gating on session presence is
  // the fix; this test asserts the query cannot fire pre-session at all.
  it('does not fire (fetchStatus stays idle) when there is no session', async () => {
    useAuthStore.setState({ session: null, isSessionLoading: false });

    const { result } = await renderHook(() => useOnboardingTaxonomiesQuery(), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe('idle');
    expect(
      onboardingTaxonomiesService.fetchOnboardingTaxonomies,
    ).not.toHaveBeenCalled();
  });

  it('fires once a real session exists', async () => {
    useAuthStore.setState({
      session: { user: { id: 'user-1' } } as never,
      isSessionLoading: false,
    });
    (
      onboardingTaxonomiesService.fetchOnboardingTaxonomies as jest.Mock
    ).mockResolvedValue({
      styleKeywords: [],
      occasionTypes: [],
      colourPalette: [],
    });

    const { result } = await renderHook(() => useOnboardingTaxonomiesQuery(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(
      onboardingTaxonomiesService.fetchOnboardingTaxonomies,
    ).toHaveBeenCalledTimes(1);
  });

  it('is loading before resolution', async () => {
    useAuthStore.setState({
      session: { user: { id: 'user-1' } } as never,
      isSessionLoading: false,
    });
    let resolvePromise: (value: unknown) => void = () => {};
    (
      onboardingTaxonomiesService.fetchOnboardingTaxonomies as jest.Mock
    ).mockReturnValue(
      new Promise((resolve) => {
        resolvePromise = resolve;
      }),
    );

    const { result } = await renderHook(() => useOnboardingTaxonomiesQuery(), {
      wrapper: createWrapper(),
    });

    expect(result.current.isLoading).toBe(true);
    resolvePromise({ styleKeywords: [], occasionTypes: [], colourPalette: [] });
  });

  it('resolves data matching the mocked OnboardingTaxonomies shape on success', async () => {
    useAuthStore.setState({
      session: { user: { id: 'user-1' } } as never,
      isSessionLoading: false,
    });
    const mockData = {
      styleKeywords: [{ key: 'ethnic', label: 'Ethnic', sortOrder: 1 }],
      occasionTypes: [{ key: 'office', label: 'Office', sortOrder: 1 }],
      colourPalette: [
        { key: 'black', label: 'Black', hex: '#000000', sortOrder: 1 },
      ],
    };
    (
      onboardingTaxonomiesService.fetchOnboardingTaxonomies as jest.Mock
    ).mockResolvedValue(mockData);

    const { result } = await renderHook(() => useOnboardingTaxonomiesQuery(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockData);
  });

  it('exposes isError and a populated error when the fetch rejects', async () => {
    useAuthStore.setState({
      session: { user: { id: 'user-1' } } as never,
      isSessionLoading: false,
    });
    (
      onboardingTaxonomiesService.fetchOnboardingTaxonomies as jest.Mock
    ).mockRejectedValue(new Error('network error'));

    const { result } = await renderHook(() => useOnboardingTaxonomiesQuery(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeTruthy();
  });
});
