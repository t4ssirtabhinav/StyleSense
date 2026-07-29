import { renderHook } from '@testing-library/react-native';
import { getAnalyticsClient } from '../../lib/analytics';
import { isFeatureEnabled, useTypedFeatureFlag } from '../../lib/featureFlags';

const mockUseFeatureFlag = jest.fn();
jest.mock('posthog-react-native', () => ({
  useFeatureFlag: (...args: unknown[]) => mockUseFeatureFlag(...args),
}));

jest.mock('../../lib/analytics', () => ({
  getAnalyticsClient: jest.fn(),
}));

const mockGetAnalyticsClient = getAnalyticsClient as jest.Mock;

describe('lib/featureFlags', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('isFeatureEnabled', () => {
    it('returns defaultValue when getAnalyticsClient() is null', () => {
      mockGetAnalyticsClient.mockReturnValue(null);

      expect(isFeatureEnabled('paywall_copy_variant', true)).toBe(true);
      expect(isFeatureEnabled('paywall_copy_variant', false)).toBe(false);
    });

    it("returns the client's .isFeatureEnabled() boolean result when present", () => {
      const client = { isFeatureEnabled: jest.fn().mockReturnValue(true) };
      mockGetAnalyticsClient.mockReturnValue(client);

      expect(isFeatureEnabled('paywall_copy_variant', false)).toBe(true);
      expect(client.isFeatureEnabled).toHaveBeenCalledWith(
        'paywall_copy_variant',
      );
    });

    it('returns defaultValue when the client throws', () => {
      const client = {
        isFeatureEnabled: jest.fn(() => {
          throw new Error('posthog outage');
        }),
      };
      mockGetAnalyticsClient.mockReturnValue(client);

      expect(isFeatureEnabled('paywall_copy_variant', true)).toBe(true);
    });

    it('returns defaultValue when the underlying value is a non-boolean (multivariate) flag', () => {
      const client = {
        isFeatureEnabled: jest.fn().mockReturnValue('variant-a'),
      };
      mockGetAnalyticsClient.mockReturnValue(client);

      expect(isFeatureEnabled('paywall_copy_variant', false)).toBe(false);
    });
  });

  describe('useTypedFeatureFlag', () => {
    it('calls the mocked useFeatureFlag(flag, client) with the shared client instance when a client exists', async () => {
      const client = { id: 'shared-client' };
      mockGetAnalyticsClient.mockReturnValue(client);
      mockUseFeatureFlag.mockReturnValue(true);

      const { result } = await renderHook(() =>
        useTypedFeatureFlag('paywall_copy_variant', false),
      );

      expect(mockUseFeatureFlag).toHaveBeenCalledWith(
        'paywall_copy_variant',
        client,
      );
      expect(result.current).toBe(true);
    });

    it('passes undefined (not a null client) when no analytics client exists', async () => {
      mockGetAnalyticsClient.mockReturnValue(null);
      mockUseFeatureFlag.mockReturnValue(undefined);

      await renderHook(() =>
        useTypedFeatureFlag('paywall_copy_variant', false),
      );

      expect(mockUseFeatureFlag).toHaveBeenCalledWith(
        'paywall_copy_variant',
        undefined,
      );
    });

    it('returns defaultValue when the underlying hook resolves to a non-boolean or undefined', async () => {
      mockGetAnalyticsClient.mockReturnValue({ id: 'shared-client' });

      mockUseFeatureFlag.mockReturnValue(undefined);
      const { result: undefinedResult } = await renderHook(() =>
        useTypedFeatureFlag('paywall_copy_variant', true),
      );
      expect(undefinedResult.current).toBe(true);

      mockUseFeatureFlag.mockReturnValue('variant-a');
      const { result: multivariateResult } = await renderHook(() =>
        useTypedFeatureFlag('paywall_copy_variant', false),
      );
      expect(multivariateResult.current).toBe(false);
    });
  });
});
