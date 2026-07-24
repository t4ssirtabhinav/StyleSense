import { act, cleanup, render } from '@testing-library/react-native';

// SS-009: app/_layout.tsx calls initSentry()/initAnalytics() at MODULE
// scope (before the RootLayout component body runs), and fires
// track(ANALYTICS_EVENTS.APP_OPENED) once on mount. jest.mock() factories
// are hoisted above this file's imports (including the default import of
// the module under test below), so the mocked lib/sentry.ts/lib/analytics.ts
// are already in place by the time app/_layout.tsx's module-scope code runs.

const mockInitSentry = jest.fn();
const mockInitAnalytics = jest.fn();
const mockTrack = jest.fn();

jest.mock('../../lib/sentry', () => ({
  initSentry: () => mockInitSentry(),
  setSentryUserContext: jest.fn(),
  clearSentryUserContext: jest.fn(),
}));

jest.mock('../../lib/analytics', () => ({
  initAnalytics: () => mockInitAnalytics(),
  capture: jest.fn(),
  identifyAnalyticsUser: jest.fn(),
  resetAnalyticsUser: jest.fn(),
}));

jest.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({ track: mockTrack }),
}));

jest.mock('../../hooks/useAuth', () => ({
  useAuth: jest.fn(),
}));

jest.mock('@sentry/react-native', () => ({
  captureException: jest.fn(),
  wrap: (Component: unknown) => Component,
}));

jest.mock('expo-font', () => ({
  useFonts: () => [true, undefined],
}));

jest.mock('expo-router', () => {
  const react = jest.requireActual('react');
  const reactNative = jest.requireActual('react-native');
  return {
    Stack: () => react.createElement(reactNative.Text, null, 'stack'),
  };
});

// NativeWind's global.css is a raw CSS file — Jest has no transform for it
// (no other test imports app/_layout.tsx, so this gap was previously
// unexercised); it's a side-effect-only import with no exports to preserve.
jest.mock('../../global.css', () => ({}));

// A real (top-of-file, ES-syntax) `import` here would be hoisted by Babel's
// commonjs transform above this file's own `const mockInitSentry = ...`
// declarations (ES import hoisting is honored across the whole module,
// regardless of source-line position), running app/_layout.tsx's
// module-scope initSentry()/initAnalytics() calls before the mock
// functions they call even exist. A plain `require()` executes in place,
// after those consts are already assigned.
// eslint-disable-next-line @typescript-eslint/no-var-requires
const RootLayout = require('../../app/_layout').default;

describe('app/_layout', () => {
  afterEach(async () => {
    await cleanup();
  });

  it('calls initSentry() and initAnalytics() exactly once (module-scope side effect)', () => {
    expect(mockInitSentry).toHaveBeenCalledTimes(1);
    expect(mockInitAnalytics).toHaveBeenCalledTimes(1);
  });

  it('fires track(APP_OPENED) exactly once on mount, not on every re-render', async () => {
    mockTrack.mockClear();
    const { rerender } = await render(<RootLayout />);

    expect(mockTrack).toHaveBeenCalledTimes(1);
    expect(mockTrack).toHaveBeenCalledWith('app_opened');

    await act(async () => {
      rerender(<RootLayout />);
    });

    expect(mockTrack).toHaveBeenCalledTimes(1);
  });
});
