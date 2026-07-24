import { renderHook } from '@testing-library/react-native';
import { useAnalytics } from '../../hooks/useAnalytics';

const mockCapture = jest.fn();

jest.mock('../../lib/analytics', () => ({
  capture: (...args: unknown[]) => mockCapture(...args),
}));

describe('useAnalytics', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("track() calls lib/analytics.ts's capture with the given event name and properties", async () => {
    const { result } = await renderHook(() => useAnalytics());

    result.current.track('register', { method: 'phone_otp' });

    expect(mockCapture).toHaveBeenCalledWith('register', {
      method: 'phone_otp',
    });
  });

  it('the returned track reference is stable across re-renders', async () => {
    const { result, rerender } = await renderHook(() => useAnalytics());
    const firstTrack = result.current.track;

    rerender({});

    expect(result.current.track).toBe(firstTrack);
  });
});
