// SS-010 — Cloudflare R2 Presigned Upload Infrastructure.
// Concrete values transcribed verbatim from docs/tickets/SS-010-design.md's
// "Concrete values" section, plus the Architect's own reasonable choices
// (retry/backoff, compression ladder) flagged as such there.

// Compression (client-side, before ever calling requestUploadUrl).
export const MAX_UPLOAD_WIDTH = 1200;
export const COMPRESS_QUALITY_START = 0.8;
export const COMPRESS_QUALITY_STEP = 0.1;
export const COMPRESS_QUALITY_FLOOR = 0.5;
export const MAX_COMPRESSED_SIZE_BYTES = 2 * 1024 * 1024; // 2MB

// Server-side R2 policy bounds (see Edge Function) — mirrored here only for
// client-side sanity/logging, not enforced client-side (R2 is the source of
// truth for these).
export const MIN_UPLOAD_SIZE_BYTES = 1024; // 1KB
export const MAX_UPLOAD_SIZE_BYTES = 3 * 1024 * 1024; // 3MB

export const FREE_TIER_WARDROBE_CAP = 50;
export const PRESIGNED_URL_EXPIRY_SECONDS = 300;

// Retry/backoff — Architect's own reasonable choices, not pinned by the raw
// ticket.
export const RETRY_BASE_DELAY_MS = 1000;
export const RETRY_BACKOFF_FACTOR = 2;
export const RETRY_MAX_DELAY_MS = 8000;
// Total attempts (including the first) for a plain network failure.
export const RETRY_MAX_ATTEMPTS = 3;
// Additional attempts (beyond the first) after an expired-URL (403) failure.
export const EXPIRED_URL_MAX_RETRIES = 2;

// A task still 'uploading' with no progress update in longer than this is
// treated as stalled (see Edge Cases — app backgrounded/closed mid-upload).
export const STALE_UPLOAD_THRESHOLD_MS = 30_000;

// Keep in sync with supabase/functions/get-upload-url/index.ts's own copy of
// this string — duplicated, not imported, because the Edge Function is a
// separately-deployed Deno runtime that cannot import from mobile/.
export const WARDROBE_LIMIT_MESSAGE =
  "You've reached the free plan's 50-item wardrobe limit. Upgrade to premium for unlimited items.";

export const NETWORK_ERROR_MESSAGE =
  'No internet connection. Please check your network and try again.';
export const EXPIRED_URL_ERROR_MESSAGE =
  'Your upload link expired. Please try again.';
export const INVALID_FILE_ERROR_MESSAGE =
  "This photo couldn't be uploaded. Please try a different photo.";
export const UNKNOWN_UPLOAD_ERROR_MESSAGE =
  'Something went wrong while uploading. Please try again.';

// --- SS-013 (Wardrobe Item Upload Flow UI) ---
// WARDROBE_CATEGORIES/OCCASION_TYPES/SEASON_TAGS transcribed verbatim from
// docs/tickets/SS-013-design.md's "Concrete values" section (itself
// transcribed from supabase/migrations/001_initial.sql).

import type {
  OccasionType,
  SeasonTag,
  WardrobeCategory,
} from './wardrobe.types';

export interface CategoryOption {
  value: WardrobeCategory;
  label: string;
}

function humanize(value: string): string {
  return value
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

const WARDROBE_CATEGORY_VALUES: WardrobeCategory[] = [
  'western_top',
  'western_bottom',
  'western_dress',
  'western_outerwear',
  'ethnic_kurta',
  'ethnic_saree',
  'ethnic_lehenga',
  'ethnic_anarkali',
  'ethnic_salwar_kameez',
  'ethnic_dupatta',
  'ethnic_sherwani',
  'indo_western',
  'footwear_formal',
  'footwear_casual',
  'footwear_ethnic',
  'footwear_sports',
  'accessory_bag',
  'accessory_jewellery',
  'accessory_watch',
  'accessory_belt',
  'accessory_scarf',
];

export const WARDROBE_CATEGORIES: CategoryOption[] =
  WARDROBE_CATEGORY_VALUES.map((value) => ({ value, label: humanize(value) }));

export const OCCASION_TYPES: OccasionType[] = [
  'office',
  'casual',
  'date_night',
  'wedding_guest',
  'festival',
  'puja',
  'party',
  'travel',
  'workout',
  'beach',
  'formal_event',
  'college',
];

export const SEASON_TAGS: SeasonTag[] = ['summer', 'winter', 'monsoon', 'all'];

export const MAX_BATCH_SIZE = 10;
export const REALTIME_CHANNEL_PREFIX = 'wardrobe_item_';
// AC: "may take longer on slow connections" hint after 10s of no status
// change within a single stage.
export const SLOW_NETWORK_HINT_DELAY_MS = 10000;

// BL-057 (accepted for MVP): permanent, unconditional Capture-step copy.
export const ONE_ITEM_AT_A_TIME_TIP =
  'Tip: photograph one item at a time for the best results';

export const LOW_CONFIDENCE_THRESHOLD = 0.7;

// wedding_guest (occasion_type) vs. Badge's 'wedding' OccasionKey -- see
// docs/tickets/SS-013-design.md's "Concrete values" note on this mismatch.
export const OCCASION_BADGE_COLOR_MAP: Partial<
  Record<OccasionType, 'wedding' | 'office' | 'festival' | 'casual'>
> = {
  wedding_guest: 'wedding',
  office: 'office',
  festival: 'festival',
  casual: 'casual',
};
