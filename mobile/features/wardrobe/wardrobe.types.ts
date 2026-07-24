// Domain types for SS-010 (Cloudflare R2 Presigned Upload Infrastructure).
// Per docs/tickets/SS-010-design.md's "Files to create/modify".
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
