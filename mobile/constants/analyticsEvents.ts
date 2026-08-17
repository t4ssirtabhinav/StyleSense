// SS-009 — Error Monitoring & Analytics Instrumentation.
//
// Typed analytics event constants: 13 entries — the 12 named in the raw
// ticket's Description plus `app_opened`, which the ticket's own Acceptance
// Criteria separately requires ("PostHog records an app_opened event on
// launch"). Only `app_opened` (app/_layout.tsx) and `register`
// (app/(auth)/verify-otp.tsx) have a real call site today — the other 10
// belong to features that don't exist in this repo yet (wardrobe upload,
// styling-AI reward screen, premium paywall, social share, try-on, Discover
// category filter). Each owning feature ticket wires its own `track()` call
// when built; see docs/BACKLOG.md BL-049.
//
// This is the first file in mobile/constants/ — CLAUDE.md's Anti-Patterns
// section already names constants/api.ts as the required home for hardcoded
// URLs, establishing the folder convention this file follows.
//
// SS-021 adds a 14th entry, STYLE_SCORE_SHARED (real call site:
// features/style-score/components/StyleScoreCard.tsx), and gives
// PREMIUM_PAYWALL_VIEWED its first real call site
// (features/style-score/components/StyleScoreBreakdown.tsx) — one of
// BL-049's remaining uncalled events, not all of them.

export const ANALYTICS_EVENTS = {
  APP_OPENED: 'app_opened',
  INSTALL: 'install',
  REGISTER: 'register',
  FIRST_ITEM_ADDED: 'first_item_added',
  FIRST_SUGGESTION_VIEWED: 'first_suggestion_viewed',
  FIRST_OUTFIT_SAVED: 'first_outfit_saved',
  PREMIUM_PAYWALL_VIEWED: 'premium_paywall_viewed',
  SUBSCRIPTION_STARTED: 'subscription_started',
  ITEM_UPLOADED: 'item_uploaded',
  OUTFIT_SHARED: 'outfit_shared',
  AFFILIATE_LINK_CLICKED: 'affiliate_link_clicked',
  TRYON_GENERATED: 'tryon_generated',
  CATEGORY_FILTERED: 'category_filtered',
  // SS-021 — deliberately NOT reusing outfit_shared, which is a funnel
  // metric for a different object (an accepted outfit, not the style
  // score).
  STYLE_SCORE_SHARED: 'style_score_shared',
  // SS-071 — first sign-out call site (features/auth/auth.queries.ts's
  // useSignOutMutation, fired from app/(tabs)/profile.tsx's confirm step).
  // Partially closes BL-049's "events with no call site" gap by shipping
  // one that lands WITH its call site in the same ticket.
  SIGN_OUT: 'sign_out',
} as const;

export type AnalyticsEventName =
  (typeof ANALYTICS_EVENTS)[keyof typeof ANALYTICS_EVENTS];

// Per-event property shapes. None contain phone/name/email by construction —
// lib/analytics.ts's capture() additionally enforces this at runtime (defense
// in depth) so a future event definition that accidentally adds a PII-shaped
// field still fails loudly in dev rather than silently leaking to PostHog in
// production.
export interface AnalyticsEventProperties {
  app_opened: Record<string, never>;
  install: Record<string, never>;
  // SS-072 — widened to the two AuthMethodId values that can register today
  // (features/auth/auth.methods.ts). sign_out is deliberately NOT widened
  // here (BL-182, out of scope — profile.tsx hardcodes 'phone_otp' there).
  register: { method: 'phone_otp' | 'email_password' };
  first_item_added: { category?: string };
  first_suggestion_viewed: Record<string, never>;
  first_outfit_saved: Record<string, never>;
  premium_paywall_viewed: { source: string };
  subscription_started: { plan: 'monthly' | 'annual' };
  item_uploaded: { category?: string; source: 'camera' | 'gallery' };
  outfit_shared: { channel?: string };
  affiliate_link_clicked: { retailer?: string };
  tryon_generated: { outfit_id?: string };
  category_filtered: { category: string };
  style_score_shared: { channel?: string };
  // AuthMethodId (features/auth/auth.methods.ts) — never a phone/email, per
  // this file's own no-PII discipline (see the comment block above).
  sign_out: { method: 'phone_otp' };
}
