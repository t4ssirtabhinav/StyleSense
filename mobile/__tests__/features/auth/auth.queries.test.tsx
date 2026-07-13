import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import {
  useSendOtpMutation,
  useUserProfileExistsQuery,
  useVerifyOtpMutation,
} from '../../../features/auth/auth.queries';
import * as authService from '../../../features/auth/auth.service';

jest.mock('../../../features/auth/auth.service', () => ({
  sendOtp: jest.fn(),
  verifyOtp: jest.fn(),
  checkUserProfileExists: jest.fn(),
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

describe('useSendOtpMutation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('calls through to sendOtp and exposes isPending/isSuccess', async () => {
    (authService.sendOtp as jest.Mock).mockResolvedValue(undefined);
    const { result } = await renderHook(() => useSendOtpMutation(), {
      wrapper: createWrapper(),
    });

    expect(result.current.isPending).toBe(false);
    result.current.mutate('9876543210');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    // react-query v5's mutationFn is invoked with a second (context) argument
    // beyond the variables — assert only the variables actually passed
    // through to sendOtp, not react-query's own internal call shape.
    expect((authService.sendOtp as jest.Mock).mock.calls[0][0]).toBe(
      '9876543210',
    );
  });

  it('exposes isError when the mutation rejects', async () => {
    (authService.sendOtp as jest.Mock).mockRejectedValue({
      code: 'network_error',
      message: 'No internet connection.',
    });
    const { result } = await renderHook(() => useSendOtpMutation(), {
      wrapper: createWrapper(),
    });

    result.current.mutate('9876543210');

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useVerifyOtpMutation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('calls through to verifyOtp with phone and token', async () => {
    const session = { user: { id: 'user-1' } };
    (authService.verifyOtp as jest.Mock).mockResolvedValue(session);
    const { result } = await renderHook(() => useVerifyOtpMutation(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ phone: '9876543210', token: '123456' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(authService.verifyOtp).toHaveBeenCalledWith('9876543210', '123456');
    expect(result.current.data).toBe(session);
  });
});

describe('useUserProfileExistsQuery', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('does not fire the query when userId is undefined', async () => {
    const { result } = await renderHook(
      () => useUserProfileExistsQuery(undefined),
      { wrapper: createWrapper() },
    );

    expect(result.current.fetchStatus).toBe('idle');
    expect(authService.checkUserProfileExists).not.toHaveBeenCalled();
  });

  it('fires the query and resolves when userId is provided', async () => {
    (authService.checkUserProfileExists as jest.Mock).mockResolvedValue(true);
    const { result } = await renderHook(
      () => useUserProfileExistsQuery('user-1'),
      {
        wrapper: createWrapper(),
      },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(authService.checkUserProfileExists).toHaveBeenCalledWith('user-1');
    expect(result.current.data).toBe(true);
  });
});
