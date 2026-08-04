// Domain types for SS-010 (Cloudflare R2 Presigned Upload Infrastructure).
// Per docs/tickets/SS-010-design.md's "Files to create/modify".

import type { Tables } from '../../types/supabase';
//
// NOTE (post-review amendment, see design doc's "Concrete values" ->
// "Server-side Content-Type/size enforcement"): the design's amended plan
// called for an S3-compatible presigned POST policy
// (`@aws-sdk/s3-presigned-post`) with a `content-length-range` condition.
// Live-verified against the real Cloudflare R2 credentials now in `.env`
// (2026-07-24): R2 rejects presigned POST entirely --
// `501 NotImplemented: "Presigned post requests are not yet implemented"`.
// Per the design's own documented fallback, this ticket reverts to a
// presigned PUT (`UploadUrlResponse.uploadUrl`, no `fields`/policy object) —
// see wardrobe.service.ts's `uploadToR2WithProgress` and the Edge Function
// for how Content-Type enforcement is still achieved despite this (a
// second, related live finding: a plain pinned `ContentType` on the PUT
// command does NOT get enforced by R2 unless `content-type` is forced into
// the signed headers via `signableHeaders` -- confirmed live too). The
// `content-length-range` size enforcement has no PUT-based equivalent and
// stays an open gap (flagged back per the design's own instructions -- see
// this ticket's worklog/report, not silently dropped).

export type WardrobeUploadSource = 'camera' | 'gallery';

export interface UploadUrlRequest {
  /** Present only on a retry (see Edge Cases: expired-URL mid-upload) so the
   * Edge Function re-signs the *same* R2 key instead of minting a new one. */
  itemId?: string;
}

export interface UploadUrlResponse {
  uploadUrl: string;
  itemId: string;
  key: string;
  /** ISO 8601 timestamp, ~`PRESIGNED_URL_EXPIRY_SECONDS` from the call. */
  expiresAt: string;
  contentType: 'image/jpeg';
  /** The caller's wardrobe_items count *before* this upload, as already
   * queried by the Edge Function for the free-tier cap check -- reused by
   * wardrobe.queries.ts for the FIRST_ITEM_ADDED analytics funnel step
   * instead of a second, redundant query. */
  existingItemCount: number;
}

export type WardrobeUploadErrorCode =
  | 'network_error'
  | 'expired_url'
  | 'wardrobe_limit_reached'
  | 'invalid_file'
  | 'unknown';

export interface WardrobeUploadError {
  code: WardrobeUploadErrorCode;
  message: string;
  /** false for wardrobe_limit_reached and invalid_file -- retrying either
   * against a fresh URL/policy would fail identically. */
  retryable: boolean;
}

// SS-019 (Fix SS-013 upload-flow regressions) -- moved here from
// wardrobe.queries.ts (was a private local helper) so upload.tsx's
// processItem catch block can reuse the same guard for the
// wardrobe_limit_reached batch-stop fix, per the design doc's "Files to
// create/modify".
export function isWardrobeUploadError(
  error: unknown,
): error is WardrobeUploadError {
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    'retryable' in error
  );
}

export type WardrobeUploadStatus =
  | 'idle'
  | 'compressing'
  | 'requesting_url'
  | 'uploading'
  | 'success'
  | 'error';

export interface WardrobeUploadTask {
  /** Client-generated, not the same as R2's itemId until the upload
   * actually starts (see wardrobe.store.ts). */
  taskId: string;
  localUri: string;
  source: WardrobeUploadSource;
  status: WardrobeUploadStatus;
  /** 0-100. */
  progress: number;
  itemId?: string;
  error?: WardrobeUploadError;
  /** epoch ms of the last progress update -- used to derive a "stale"
   * (backgrounded/closed mid-upload) check. */
  lastProgressAt: number;
}

export interface UploadWardrobeItemInput {
  taskId: string;
  localUri: string;
  source: WardrobeUploadSource;
}

export interface UploadWardrobeItemResult {
  itemId: string;
  key: string;
}

// --- SS-013 (Wardrobe Item Upload Flow UI -- Capture/Processing/Review) ---
// Per docs/tickets/SS-013-design.md's "Concrete values to use, not invent" --
// transcribed verbatim, not re-derived.

export type UploadFlowStep = 'capture' | 'processing' | 'review';

export type WardrobeCategory =
  | 'western_top'
  | 'western_bottom'
  | 'western_dress'
  | 'western_outerwear'
  | 'ethnic_kurta'
  | 'ethnic_saree'
  | 'ethnic_lehenga'
  | 'ethnic_anarkali'
  | 'ethnic_salwar_kameez'
  | 'ethnic_dupatta'
  | 'ethnic_sherwani'
  | 'indo_western'
  | 'footwear_formal'
  | 'footwear_casual'
  | 'footwear_ethnic'
  | 'footwear_sports'
  | 'accessory_bag'
  | 'accessory_jewellery'
  | 'accessory_watch'
  | 'accessory_belt'
  | 'accessory_scarf';

// (SS-025) The 12-member `OccasionType` union is GONE, along with the
// `occasion_type` Postgres ENUM it mirrored. Occasions are now a
// data-driven registry (`occasions` table) — adding one is an INSERT, so
// the compiler cannot enumerate them any more.
//
// That trade is paid for with runtime normalisation and validation at every
// write boundary (design §6.4's six-boundary matrix): the app-layer
// normaliser in wardrobe.service.ts, the backend `OccasionNormalizer`, and
// the DB `BEFORE INSERT OR UPDATE` triggers that cover the write paths that
// do not exist yet. `BL-078` stays Active as a standing obligation for
// every NEW occasion write path.
//
// No `OccasionType` alias is kept deliberately — the compiler is what
// found every call site during this migration.
export type OccasionSlug = string;

export type SeasonTag = 'summer' | 'winter' | 'monsoon' | 'all';

export type WardrobeItemProcessingStatus =
  | 'uploaded'
  | 'bg_removed'
  | 'bg_pending';

export type WardrobeContentFlag = 'ok' | 'not_clothing' | 'nsfw' | 'other';

// The editable-in-Review shape (SS-012's tagging output, plus the draft
// state the user can edit before saving).
export interface GarmentTagsDraft {
  category: WardrobeCategory | null;
  subcategory: string | null;
  colorPrimary: string | null;
  colorSecondary: string | null;
  pattern: string | null;
  fabric: string | null;
  occasionTags: OccasionSlug[];
  seasonTags: SeasonTag[];
  confidence: number;
  alternatives?: WardrobeCategory[];
  contentFlag: WardrobeContentFlag;
  containsPerson: boolean;
}

export type BatchItemStatus =
  | 'queued'
  | 'uploading'
  | 'removing_bg'
  | 'tagging'
  | 'ready'
  | 'review'
  | 'saved'
  | 'failed';

export interface BatchItemState {
  taskId: string;
  itemId?: string;
  localUri: string;
  source: WardrobeUploadSource;
  status: BatchItemStatus;
  tags?: GarmentTagsDraft;
  error?: string;
}

// Shape of the Realtime `postgres_changes` UPDATE payload's `.new` this
// domain reads. Widened by SS-019 (was missing the 8 tag columns +
// ai_tags.tagging's confidence/alternatives/moderation sub-fields, which is
// why the Review form never actually saw Gemini's tagging output -- see
// docs/tickets/SS-019-design.md's "Concrete values", transcribed verbatim
// from supabase/migrations/001_initial.sql and
// backend/services/wardrobe_tagging_service.py's tag_columns/_tagging_payload).
export interface WardrobeItemRealtimeRow {
  id: string;
  processing_status: WardrobeItemProcessingStatus;
  category: WardrobeCategory | null;
  subcategory: string | null;
  color_primary: string | null;
  color_secondary: string | null;
  pattern: string | null;
  fabric: string | null;
  occasion_tags: OccasionSlug[] | null;
  season_tags: SeasonTag[] | null;
  ai_tags: {
    tagging?: {
      status?: 'tagging' | 'tagged' | 'flagged' | 'failed';
      confidence?: number;
      alternatives?: WardrobeCategory[];
      moderation?: {
        content_flag?: WardrobeContentFlag;
        contains_person?: boolean;
      };
    };
    bg_removal?: { status?: string };
  } | null;
}

// --- SS-014 (Wardrobe Grid & Catalogue View) ---
// Per docs/tickets/SS-014-design.md's "Concrete values" / "Files to
// create/modify" -- transcribed verbatim, not re-derived.

// Generated type only (CLAUDE.md: "Supabase types from auto-generated
// types/supabase.ts ONLY") -- never hand-duplicate its columns.
export type WardrobeItemRow = Tables<'wardrobe_items'>;

export type CategoryGroup = 'ethnic' | 'western' | 'footwear' | 'accessories';

export type CategoryFilterValue = 'all' | CategoryGroup | 'favourites';

export type WardrobeSortOption =
  | 'newest'
  | 'most_worn'
  | 'least_worn'
  | 'cost_per_wear';

export interface WardrobeItemImageUrlInfo {
  url: string;
  source: 'thumbnail' | 'original';
}

export type WardrobeItemImageUrlsMap = Record<string, WardrobeItemImageUrlInfo>;

export interface WardrobeFilterState {
  categoryFilter: CategoryFilterValue;
  occasionFilter: OccasionSlug | 'all';
  seasonFilter: SeasonTag | 'all';
  colorFilter: string | 'all';
  search: string;
  sort: WardrobeSortOption;
}

// --- SS-015 (Wardrobe Item Edit, Delete & Mark Worn) ---
// Per docs/tickets/SS-015-design.md's "Files to create/modify" -- generated
// type only (CLAUDE.md), transcribed verbatim.

export type WardrobeItemWearRow = Tables<'wardrobe_item_wears'>;

export interface WardrobeItemDetailsDraft {
  brand: string | null;
  purchasePrice: number | null;
  purchaseDate: string | null;
  userNotes: string | null;
}

export interface LogWearResult {
  wearCount: number;
  costPerWear: number | null;
  wornOn: string;
  /** SS-035. null = no occasion selected (the one-tap "Mark Worn" default). */
  occasionKey: string | null;
  alreadyLogged: boolean;
}
