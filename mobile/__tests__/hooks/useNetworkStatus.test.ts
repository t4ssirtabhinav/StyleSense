import { act, renderHook } from '@testing-library/react-native';
import { useNetworkStatus } from '../../hooks/useNetworkStatus';

const mockUseNetworkState = jest.fn();
jest.mock('expo-network', () => ({
  useNetworkState: () => mockUseNetworkState(),
}));

describe('useNetworkStatus', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('isOffline is false when expo-network reports isConnected=true', async () => {
    mockUseNetworkState.mockReturnValue({
      type: 'WIFI',
      isConnected: true,
      isInternetReachable: true,
    });

    const { result } = await renderHook(() => useNetworkStatus());

    expect(result.current.isOffline).toBe(false);
  });

  it('isOffline is true when expo-network reports isConnected=false', async () => {
    mockUseNetworkState.mockReturnValue({
      type: 'NONE',
      isConnected: false,
      isInternetReachable: false,
    });

    const { result } = await renderHook(() => useNetworkStatus());

    expect(result.current.isOffline).toBe(true);
  });

  it('treats an undefined isConnected (not yet resolved) as online, not offline', async () => {
    mockUseNetworkState.mockReturnValue({});

    const { result } = await renderHook(() => useNetworkStatus());

    expect(result.current.isOffline).toBe(false);
  });

  it('reflects a transition from online to offline across re-renders', async () => {
    mockUseNetworkState.mockReturnValue({ isConnected: true });
    const { result, rerender } = await renderHook(() => useNetworkStatus());
    expect(result.current.isOffline).toBe(false);

    mockUseNetworkState.mockReturnValue({ isConnected: false });
    await act(async () => {
      rerender(undefined);
    });

    expect(result.current.isOffline).toBe(true);
  });
});
