import * as Sentry from '@sentry/react-native';
import { PostHog } from 'posthog-react-native';
import type {
  AnalyticsEventName,
  AnalyticsEventProperties,
} from '../constants/analyticsEvents';

// posthog-react-native doesn't re-export its PostHogEventProperties type
// from its public entrypoint (only @posthog/core does, an undeclared
// transitive dependency this package shouldn't import from directly) --
// deriving the same type structurally off PostHog.capture()'s own second
// parameter instead.
type PostHogCaptureProperties = Parameters<PostHog['capture']>[1];

// SS-009 — mobile-side PostHog wiring. `posthog-react-native` was already a
// dependency but had zero references anywhere in mobile/ outside
// package.json — this module is the singleton client + the only place
// `.capture()`/`.identify()`/`.reset()` are called from.

const DEFAULT_POSTHOG_HOST = 'https://us.i.posthog.com';

// Defense in depth: capture() rejects any event-property key that looks like
// PII, even on an already-supposedly-safe internal call site — a future
// ticket accidentally passing `{ phone: ... }` should fail loudly in
// dev/tests, not silently leak to PostHog in production.
const BANNED_PII_KEYS = ['phone', 'phone_number', 'name', 'full_name', 'email'];

let client: PostHog | null = null;

// Idempotent — app/_layout.tsx can theoretically remount in fast-refresh dev
// scenarios; a second call must not construct a second client.
export function initAnalytics(): void {
  if (client) {
    return;
  }

  const apiKey = process.env.EXPO_PUBLIC_POSTHOG_API_KEY;
  if (!apiKey) {
    // The app must never fail to boot because monitoring credentials are
    // absent (e.g. a dev machine without mobile/.env.local filled in).
    return;
  }

  const host = process.env.EXPO_PUBLIC_POSTHOG_HOST ?? DEFAULT_POSTHOG_HOST;
  client = new PostHog(apiKey, { host });
}

function sanitizeProperties(
  properties: Record<string, unknown> | undefined,
): Record<string, unknown> | undefined {
  if (!properties) {
    return properties;
  }

  const bannedKeysFound = Object.keys(properties).filter((key) =>
    BANNED_PII_KEYS.includes(key.toLowerCase()),
  );
  if (bannedKeysFound.length === 0) {
    return properties;
  }

  if (__DEV__) {
    // Fails loud during development/tests — a PII leak introduced locally
    // must never wait until production to be caught.
    throw new Error(
      `analytics.capture(): banned PII key(s) [${bannedKeysFound.join(', ')}] found in event properties`,
    );
  }

  // Fails safe in production: a telemetry bug should never crash the app —
  // strip the offending keys, report the bug, and still send the rest.
  Sentry.captureMessage(
    `analytics.capture(): stripped PII key(s) [${bannedKeysFound.join(', ')}] from event properties`,
    'warning',
  );
  const sanitized = { ...properties };
  for (const key of bannedKeysFound) {
    delete sanitized[key];
  }
  return sanitized;
}

// Fire-and-forget by design (the ticket's own "never await in UI code"
// note) — callers never await this. `__DEV__` skips only the network send,
// never the PII assertion above (see docs/tickets/SS-009-design.md's Edge
// Cases), so a leak introduced locally is still caught before it ever
// reaches production.
export function capture<E extends AnalyticsEventName>(
  event: E,
  properties?: AnalyticsEventProperties[E],
): void {
  const sanitized = sanitizeProperties(
    properties as Record<string, unknown> | undefined,
  );

  if (__DEV__) {
    return;
  }
  if (!client) {
    return;
  }

  try {
    // AnalyticsEventProperties' per-event shapes are all flat records of
    // JSON-primitive-safe fields (see constants/analyticsEvents.ts) --
    // structurally compatible with PostHog's index-signature'd
    // PostHogEventProperties, but TS can't verify that without a cast since
    // sanitizeProperties widens to a plain Record for the PII scan above.
    client.capture(event, sanitized as PostHogCaptureProperties);
  } catch {
    // Analytics must never crash the app.
  }
}

export function identifyAnalyticsUser(userId: string): void {
  try {
    client?.identify(userId);
  } catch {
    // Analytics must never crash the app.
  }
}

export function resetAnalyticsUser(): void {
  try {
    client?.reset();
  } catch {
    // Analytics must never crash the app.
  }
}

// SS-026 — the ONE shared client. A second `new PostHog(...)` instance
// would diverge distinct_id/session state from the one already
// `.identify()`-ing users via initAnalytics() above. `null` before
// initAnalytics() has run or when the API key was absent — callers must
// handle that (see lib/featureFlags.ts).
export function getAnalyticsClient(): PostHog | null {
  return client;
}
