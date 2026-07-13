import { useEffect } from 'react';
import { Platform } from 'react-native';

// Best-effort, largely untestable Android SMS auto-read — explicitly scoped
// as a documented no-op stub in this pass, not a real integration (see
// docs/tickets/SS-003-design.md's "SMS auto-read" section and BL-019 in
// docs/BACKLOG.md). Wired unconditionally from app/(auth)/verify-otp.tsx so
// a real implementation later is additive — no screen-level changes needed
// once a package is chosen.
export function useSmsAutoRead(onCodeReceived: (code: string) => void): void {
  // onCodeReceived is intentionally listed as a dependency even though this
  // stub's body doesn't call it yet — a real SMS Retriever/User Consent
  // integration (BL-019) will need it, and keeping the dependency now means
  // no screen-level or hook-signature change is required when that lands.
  // biome-ignore lint/correctness/useExhaustiveDependencies: see comment above
  useEffect(() => {
    if (Platform.OS !== 'android') return; // no-op on web/iOS — no SMS Retriever API exists there
    // TODO(SS-003 follow-up): wire a real SMS Retriever / SMS User Consent
    // integration once a concrete Expo-SDK-56-compatible package is chosen
    // (see docs/BACKLOG.md, BL-019). Deliberately not implemented here — no
    // package is installed, and it could not be device-tested even if it
    // were (BL-013: dev server unreachable from a phone on the same WiFi).
  }, [onCodeReceived]);
}
