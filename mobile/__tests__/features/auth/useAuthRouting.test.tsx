import { renderHook } from '@testing-library/react-native';
import { useAuthStore } from '../../../features/auth/auth.store';
import { useAuthRouting } from '../../../features/auth/useAuthRouting';

const mockUseOnboardingCompletedQuery = jest.fn();
jest.mock('../../../features/auth/auth.queries', () => ({
  useOnboardingCompletedQuery: (userId: string | undefined) =>
    mockUseOnboardingCompletedQuery(userId),
}));

describe('useAuthRouting', () => {
  afterEach(() => {
    useAuthStore.setState({ session: null, isSessionLoading: true });
    jest.clearAllMocks();
  });

  it('returns "loading" while isSessionLoading is true, regardless of query state', async () => {
    useAuthStore.setState({ isSessionLoading: true, session: null });
    mockUseOnboardingCompletedQuery.mockReturnValue({
      isSuccess: true,
      data: true,
    });

    const { result } = await renderHook(() => useAuthRouting());
    expect(result.current).toEqual({ status: 'loading' });
  });

  it('returns "unauthenticated" when session is null and not loading', async () => {
    useAuthStore.setState({ isSessionLoading: false, session: null });
    mockUseOnboardingCompletedQuery.mockReturnValue({
      isSuccess: false,
      data: undefined,
    });

    const { result } = await renderHook(() => useAuthRouting());
    expect(result.current).toEqual({ status: 'unauthenticated' });
  });

  it('returns "loading" when session is present but the onboarding query has not settled (no-flash discipline)', async () => {
    useAuthStore.setState({
      isSessionLoading: false,
      session: { user: { id: 'user-1' } } as never,
    });
    mockUseOnboardingCompletedQuery.mockReturnValue({
      isSuccess: false,
      data: undefined,
    });

    const { result } = await renderHook(() => useAuthRouting());
    expect(result.current).toEqual({ status: 'loading' });
  });

  it('returns "onboarding" when data is false', async () => {
    useAuthStore.setState({
      isSessionLoading: false,
      session: { user: { id: 'user-1' } } as never,
    });
    mockUseOnboardingCompletedQuery.mockReturnValue({
      isSuccess: true,
      data: false,
    });

    const { result } = await renderHook(() => useAuthRouting());
    expect(result.current).toEqual({ status: 'onboarding' });
  });

  it('returns "app" when data is true', async () => {
    useAuthStore.setState({
      isSessionLoading: false,
      session: { user: { id: 'user-1' } } as never,
    });
    mockUseOnboardingCompletedQuery.mockReturnValue({
      isSuccess: true,
      data: true,
    });

    const { result } = await renderHook(() => useAuthRouting());
    expect(result.current).toEqual({ status: 'app' });
  });

  it('fails safe to "onboarding", never "app", when the query resolved falsy/undefined despite isSuccess', async () => {
    useAuthStore.setState({
      isSessionLoading: false,
      session: { user: { id: 'user-1' } } as never,
    });
    mockUseOnboardingCompletedQuery.mockReturnValue({
      isSuccess: true,
      data: undefined,
    });

    const { result } = await renderHook(() => useAuthRouting());
    expect(result.current).toEqual({ status: 'onboarding' });
  });
});
