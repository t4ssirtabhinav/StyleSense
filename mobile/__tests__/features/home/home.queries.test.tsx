import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { useUserGreetingQuery } from '../../../features/home/home.queries';
import * as homeService from '../../../features/home/home.service';

jest.mock('../../../features/home/home.service', () => ({
  fetchUserFirstName: jest.fn(),
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

describe('useUserGreetingQuery', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('is disabled (fetchStatus stays idle) when userId is undefined', async () => {
    const { result } = await renderHook(() => useUserGreetingQuery(undefined), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe('idle');
    expect(homeService.fetchUserFirstName).not.toHaveBeenCalled();
  });

  it('fires when userId is defined', async () => {
    (homeService.fetchUserFirstName as jest.Mock).mockResolvedValue(
      'Priya Sharma',
    );

    const { result } = await renderHook(() => useUserGreetingQuery('user-1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(homeService.fetchUserFirstName).toHaveBeenCalledWith('user-1');
    expect(result.current.data).toBe('Priya Sharma');
  });
});
