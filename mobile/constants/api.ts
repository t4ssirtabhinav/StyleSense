// The one place mobile/ reads the backend's base URL from (CLAUDE.md: "no
// hardcoded URLs"). `mobile/.env.local` already defines
// EXPO_PUBLIC_BACKEND_URL (see SS-013's design doc's "Files to
// create/modify" -- wardrobe.service.ts's remove-bg/tag/image-url calls are
// this constant's first consumers).
export const EXPO_PUBLIC_BACKEND_URL =
  process.env.EXPO_PUBLIC_BACKEND_URL ?? 'http://localhost:8000';
