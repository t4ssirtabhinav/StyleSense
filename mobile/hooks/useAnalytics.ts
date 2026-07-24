import { useCallback } from 'react';
import type {
  AnalyticsEventName,
  AnalyticsEventProperties,
} from '../constants/analyticsEvents';
import { capture } from '../lib/analytics';

export interface UseAnalyticsResult {
  track: <E extends AnalyticsEventName>(
    event: E,
    properties?: AnalyticsEventProperties[E],
  ) => void;
}

// Type-safe wrapper over lib/analytics.ts's capture(), memoized per
// CLAUDE.md's "always use useCallback for event handlers passed to child
// components" rule — track() is stable across re-renders since it closes
// over nothing render-dependent.
export function useAnalytics(): UseAnalyticsResult {
  const track = useCallback(
    <E extends AnalyticsEventName>(
      event: E,
      properties?: AnalyticsEventProperties[E],
    ) => {
      capture(event, properties);
    },
    [],
  );

  return { track };
}
