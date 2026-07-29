// SS-009. lib/analytics.ts has module-scope `client` singleton state, so
// each test re-requires a fresh module instance via jest.isolateModules()
// (same pattern as __tests__/lib/supabase.test.ts and lib/sentry.test.ts).

const mockPostHogConstructor = jest.fn();
const mockCapture = jest.fn();
const mockIdentify = jest.fn();
const mockReset = jest.fn();

jest.mock('posthog-react-native', () => ({
  PostHog: class {
    constructor(apiKey: string, options: unknown) {
      mockPostHogConstructor(apiKey, options);
    }
    capture = (...args: unknown[]) => mockCapture(...args);
    identify = (...args: unknown[]) => mockIdentify(...args);
    reset = (...args: unknown[]) => mockReset(...args);
  },
}));

const mockCaptureMessage = jest.fn();
jest.mock('@sentry/react-native', () => ({
  captureMessage: (...args: unknown[]) => mockCaptureMessage(...args),
}));

describe('lib/analytics', () => {
  const ORIGINAL_ENV = process.env;
  const ORIGINAL_DEV = (global as { __DEV__?: boolean }).__DEV__;

  beforeEach(() => {
    jest.clearAllMocks();
    process.env = { ...ORIGINAL_ENV };
  });

  afterEach(() => {
    (global as { __DEV__?: boolean }).__DEV__ = ORIGINAL_DEV;
  });

  afterAll(() => {
    process.env = ORIGINAL_ENV;
  });

  describe('initAnalytics', () => {
    it('constructs the PostHog client with the configured API key/host when the env var is set', () => {
      process.env.EXPO_PUBLIC_POSTHOG_API_KEY = 'test-key';
      process.env.EXPO_PUBLIC_POSTHOG_HOST = 'https://eu.i.posthog.com';

      jest.isolateModules(() => {
        const { initAnalytics } = require('../../lib/analytics');
        initAnalytics();
      });

      expect(mockPostHogConstructor).toHaveBeenCalledWith('test-key', {
        host: 'https://eu.i.posthog.com',
      });
    });

    it('does not construct a client when the API key env var is unset', () => {
      // `= undefined` would set the real Node env var to the *string*
      // "undefined" (process.env coerces any assigned value via String()),
      // not leave it genuinely unset — delete is the only way here.
      // biome-ignore lint/performance/noDelete: see comment above
      delete process.env.EXPO_PUBLIC_POSTHOG_API_KEY;

      jest.isolateModules(() => {
        const { initAnalytics } = require('../../lib/analytics');
        initAnalytics();
      });

      expect(mockPostHogConstructor).not.toHaveBeenCalled();
    });
  });

  describe('capture', () => {
    it('does not call the underlying client .capture() when __DEV__ is true', () => {
      process.env.EXPO_PUBLIC_POSTHOG_API_KEY = 'test-key';
      (global as { __DEV__?: boolean }).__DEV__ = true;

      jest.isolateModules(() => {
        const { initAnalytics, capture } = require('../../lib/analytics');
        initAnalytics();
        capture('app_opened');
      });

      expect(mockCapture).not.toHaveBeenCalled();
    });

    it('calls the underlying client .capture(event, properties) when __DEV__ is false', () => {
      process.env.EXPO_PUBLIC_POSTHOG_API_KEY = 'test-key';
      (global as { __DEV__?: boolean }).__DEV__ = false;

      jest.isolateModules(() => {
        const { initAnalytics, capture } = require('../../lib/analytics');
        initAnalytics();
        capture('register', { method: 'phone_otp' });
      });

      expect(mockCapture).toHaveBeenCalledWith('register', {
        method: 'phone_otp',
      });
    });

    it('throws when properties contains a banned PII key under __DEV__/test conditions', () => {
      (global as { __DEV__?: boolean }).__DEV__ = true;

      jest.isolateModules(() => {
        const { capture } = require('../../lib/analytics');
        expect(() =>
          capture('register', {
            method: 'phone_otp',
            phone: '9876543210',
          } as never),
        ).toThrow();
      });
    });
  });

  describe('identifyAnalyticsUser', () => {
    it("calls the client's .identify(id)", () => {
      process.env.EXPO_PUBLIC_POSTHOG_API_KEY = 'test-key';

      jest.isolateModules(() => {
        const {
          initAnalytics,
          identifyAnalyticsUser,
        } = require('../../lib/analytics');
        initAnalytics();
        identifyAnalyticsUser('user-1');
      });

      expect(mockIdentify).toHaveBeenCalledWith('user-1');
    });
  });

  describe('resetAnalyticsUser', () => {
    it("calls the client's .reset()", () => {
      process.env.EXPO_PUBLIC_POSTHOG_API_KEY = 'test-key';

      jest.isolateModules(() => {
        const {
          initAnalytics,
          resetAnalyticsUser,
        } = require('../../lib/analytics');
        initAnalytics();
        resetAnalyticsUser();
      });

      expect(mockReset).toHaveBeenCalledTimes(1);
    });
  });

  describe('getAnalyticsClient', () => {
    it('returns the same constructed instance initAnalytics() built', () => {
      process.env.EXPO_PUBLIC_POSTHOG_API_KEY = 'test-key';

      jest.isolateModules(() => {
        const {
          initAnalytics,
          getAnalyticsClient,
          capture,
        } = require('../../lib/analytics');
        initAnalytics();
        const client = getAnalyticsClient();
        expect(client).not.toBeNull();

        // Identity check via the mocked constructor: calling a method on
        // the object returned by getAnalyticsClient() should reach the
        // same mock capture() that initAnalytics()'s own internal client
        // would call.
        (global as { __DEV__?: boolean }).__DEV__ = false;
        capture('app_opened');
        expect(mockCapture).toHaveBeenCalledTimes(1);

        client?.capture('app_opened', {});
        expect(mockCapture).toHaveBeenCalledTimes(2);
      });
    });

    it('returns null before initAnalytics() has been called', () => {
      process.env.EXPO_PUBLIC_POSTHOG_API_KEY = 'test-key';

      jest.isolateModules(() => {
        const { getAnalyticsClient } = require('../../lib/analytics');
        expect(getAnalyticsClient()).toBeNull();
      });
    });

    it('returns null when the API key was absent', () => {
      // biome-ignore lint/performance/noDelete: see comment above initAnalytics tests
      delete process.env.EXPO_PUBLIC_POSTHOG_API_KEY;

      jest.isolateModules(() => {
        const {
          initAnalytics,
          getAnalyticsClient,
        } = require('../../lib/analytics');
        initAnalytics();
        expect(getAnalyticsClient()).toBeNull();
      });
    });
  });
});
