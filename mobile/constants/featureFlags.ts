// SS-026 — Typed PostHog feature-flag keys. Mirrors
// constants/analyticsEvents.ts's exact pattern (`as const` object + derived
// union type) and backend/services/feature_flags.py's `FeatureFlagKey` --
// the two lists have no shared source of truth and are kept in sync BY
// HAND (BL-092).
//
// One flag only — `paywall_copy_variant`, matching the epics doc's
// Sprint-5 "A/B ready: paywall copy and pricing can be remote-configured"
// requirement. This flag does not exist in the PostHog dashboard yet
// (BL-093) — no agent in this pipeline has dashboard access. The typed
// constant + wrapper ship and are unit-tested against a mocked client;
// true end-to-end verification needs a human to create the flag first.

export const FEATURE_FLAGS = {
  PAYWALL_COPY_VARIANT: 'paywall_copy_variant',
} as const;

export type FeatureFlagKey = (typeof FEATURE_FLAGS)[keyof typeof FEATURE_FLAGS];
