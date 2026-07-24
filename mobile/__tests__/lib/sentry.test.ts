// SS-009. lib/sentry.ts has module-scope `isInitialized` state, so each test
// re-requires a fresh module instance via jest.isolateModules() (same
// pattern as __tests__/lib/supabase.test.ts) rather than importing once at
// the top of the file.

const mockInit = jest.fn();
const mockSetUser = jest.fn();
const mockSetTag = jest.fn();

jest.mock('@sentry/react-native', () => ({
  init: (...args: unknown[]) => mockInit(...args),
  setUser: (...args: unknown[]) => mockSetUser(...args),
  setTag: (...args: unknown[]) => mockSetTag(...args),
}));

jest.mock('expo-constants', () => ({
  __esModule: true,
  default: { expoConfig: { version: '1.2.3' } },
}));

describe('lib/sentry', () => {
  const ORIGINAL_ENV = process.env;

  beforeEach(() => {
    jest.clearAllMocks();
    process.env = { ...ORIGINAL_ENV };
  });

  afterAll(() => {
    process.env = ORIGINAL_ENV;
  });

  describe('initSentry', () => {
    it('calls Sentry.init with dsn/environment/release/tracesSampleRate when the DSN env var is set', () => {
      process.env.EXPO_PUBLIC_SENTRY_DSN = 'https://fake@sentry.io/1';
      process.env.EXPO_PUBLIC_APP_ENV = 'preview';

      jest.isolateModules(() => {
        const { initSentry } = require('../../lib/sentry');
        initSentry();
      });

      expect(mockInit).toHaveBeenCalledTimes(1);
      expect(mockInit).toHaveBeenCalledWith({
        dsn: 'https://fake@sentry.io/1',
        environment: 'preview',
        release: 'stylesense@1.2.3',
        tracesSampleRate: 0.1,
      });
    });

    it('does not call Sentry.init when the DSN env var is unset', () => {
      // `= undefined` would set the real Node env var to the *string*
      // "undefined" (process.env coerces any assigned value via String()),
      // not leave it genuinely unset — delete is the only way here.
      // biome-ignore lint/performance/noDelete: see comment above
      delete process.env.EXPO_PUBLIC_SENTRY_DSN;

      jest.isolateModules(() => {
        const { initSentry } = require('../../lib/sentry');
        initSentry();
      });

      expect(mockInit).not.toHaveBeenCalled();
    });

    it('calls Sentry.init only once across two calls (idempotency guard)', () => {
      process.env.EXPO_PUBLIC_SENTRY_DSN = 'https://fake@sentry.io/1';

      jest.isolateModules(() => {
        const { initSentry } = require('../../lib/sentry');
        initSentry();
        initSentry();
      });

      expect(mockInit).toHaveBeenCalledTimes(1);
    });
  });

  describe('setSentryUserContext', () => {
    it('calls Sentry.setUser({ id }) and Sentry.setTag when a plan tier is given', () => {
      jest.isolateModules(() => {
        const { setSentryUserContext } = require('../../lib/sentry');
        setSentryUserContext('user-1', 'premium');
      });

      expect(mockSetUser).toHaveBeenCalledWith({ id: 'user-1' });
      expect(mockSetTag).toHaveBeenCalledWith('plan_tier', 'premium');
    });

    it('calls Sentry.setUser but not Sentry.setTag when no plan tier is given', () => {
      jest.isolateModules(() => {
        const { setSentryUserContext } = require('../../lib/sentry');
        setSentryUserContext('user-1');
      });

      expect(mockSetUser).toHaveBeenCalledWith({ id: 'user-1' });
      expect(mockSetTag).not.toHaveBeenCalled();
    });
  });

  describe('clearSentryUserContext', () => {
    it('calls Sentry.setUser(null)', () => {
      jest.isolateModules(() => {
        const { clearSentryUserContext } = require('../../lib/sentry');
        clearSentryUserContext();
      });

      expect(mockSetUser).toHaveBeenCalledWith(null);
    });
  });
});
