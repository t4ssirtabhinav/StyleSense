// SS-026 — PostHog feature flags, mobile side. Deliberately separate from
// `app_config` (see backend/services/app_config.py's module docstring) —
// this is user-targeted, cohort-scoped, eventually-consistent-by-nature,
// vendor-owned config, not server-side/atomic/auditable settings.
//
// [VERIFIED 2026-07-29 against the installed posthog-react-native@4.52.0
// dist/posthog-rn.d.ts]: `isFeatureEnabled(key: string): boolean | undefined`;
// `useFeatureFlag(flag: string, client?: PostHog): FeatureFlagValue | undefined`
// (dist/hooks/useFeatureFlag.d.ts). Both signatures match this file's usage
// exactly — no cast needed.

import { useFeatureFlag } from 'posthog-react-native';
import type { FeatureFlagKey } from '../constants/featureFlags';
import { getAnalyticsClient } from './analytics';

// Non-hook path (stores, one-off checks outside a component).
export function isFeatureEnabled(
  flag: FeatureFlagKey,
  defaultValue = false,
): boolean {
  const client = getAnalyticsClient();
  if (!client) {
    return defaultValue;
  }
  try {
    const result = client.isFeatureEnabled(flag);
    return typeof result === 'boolean' ? result : defaultValue;
  } catch {
    return defaultValue; // a flags outage must never crash the app
  }
}

// Hook path. Always passes the shared client explicitly rather than
// relying on a <PostHogProvider> context — none is mounted anywhere in
// this repo [VERIFIED 2026-07-29, grep: no PostHogProvider/usePostHog
// reference anywhere in mobile/]. posthog-react-native's useFeatureFlag
// falls back to a context client when none is passed, and that context is
// unmounted here — it logs one console.error and returns undefined rather
// than throwing, so passing our own client explicitly is both correct and
// avoids that log entirely.
export function useTypedFeatureFlag(
  flag: FeatureFlagKey,
  defaultValue = false,
): boolean {
  const client = getAnalyticsClient() ?? undefined;
  const value = useFeatureFlag(flag, client);
  return typeof value === 'boolean' ? value : defaultValue;
}
