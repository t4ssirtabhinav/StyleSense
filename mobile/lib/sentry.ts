import * as Sentry from '@sentry/react-native';
import Constants from 'expo-constants';

// SS-009 — mobile-side Sentry wiring. `@sentry/react-native` was already a
// dependency (and app/_layout.tsx already called Sentry.captureException on
// a font-load error) but Sentry.init() was never called anywhere, making
// that existing call a silent no-op. This module is the one place that
// changes.

let isInitialized = false;

// Idempotent — app/_layout.tsx can theoretically remount in fast-refresh dev
// scenarios; a second Sentry.init() call must not re-register integrations.
export function initSentry(): void {
  if (isInitialized) {
    return;
  }

  const dsn = process.env.EXPO_PUBLIC_SENTRY_DSN;
  if (!dsn) {
    // The app must never fail to boot because monitoring credentials are
    // absent (e.g. a dev machine without mobile/.env.local filled in).
    return;
  }

  const environment =
    process.env.EXPO_PUBLIC_APP_ENV ?? (__DEV__ ? 'development' : 'production');
  const appVersion = Constants.expoConfig?.version ?? '0.0.0';

  Sentry.init({
    dsn,
    environment,
    release: `stylesense@${appVersion}`,
    tracesSampleRate: 0.1,
  });

  isInitialized = true;
}

// Wired centrally from hooks/useAuth.ts's session-change handler, covering
// every authenticated session (fresh OTP verify AND a returning user's
// persisted-session reopen) — not just the OTP-verify moment.
export function setSentryUserContext(userId: string, planTier?: string): void {
  Sentry.setUser({ id: userId });
  if (planTier) {
    Sentry.setTag('plan_tier', planTier);
  }
}

// Called on sign-out so an error thrown by a different logged-out user is
// never attributed to the previous user in the dashboard.
export function clearSentryUserContext(): void {
  Sentry.setUser(null);
}
