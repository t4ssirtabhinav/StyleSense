import * as Crypto from 'expo-crypto';
import { SaveFormat, manipulateAsync } from 'expo-image-manipulator';
import { EXPO_PUBLIC_BACKEND_URL } from '../../constants/api';
import { supabase } from '../../lib/supabase';
import {
  COMPRESS_QUALITY_FLOOR,
  COMPRESS_QUALITY_START,
  COMPRESS_QUALITY_STEP,
  EXPIRED_URL_ERROR_MESSAGE,
  INVALID_FILE_ERROR_MESSAGE,
  MAX_COMPRESSED_SIZE_BYTES,
  MAX_UPLOAD_WIDTH,
  NETWORK_ERROR_MESSAGE,
  UNKNOWN_UPLOAD_ERROR_MESSAGE,
  WARDROBE_LIMIT_MESSAGE,
} from './wardrobe.constants';
import type {
  GarmentTagsDraft,
  UploadUrlRequest,
  UploadUrlResponse,
  WardrobeItemImageUrlsMap,
  WardrobeItemRealtimeRow,
  WardrobeItemRow,
  WardrobeUploadError,
  WardrobeUploadErrorCode,
} from './wardrobe.types';

// The only place `supabase.functions.invoke` is called from for this domain
// (mirrors auth.service.ts/home.service.ts's existing "only place
// supabase.* is called from" pattern). No monitoring side effects here --
// that's wardrobe.queries.ts's job (see docs/tickets/SS-010-design.md's
// "Monitoring & analytics wiring").

export interface CompressedImage {
  uri: string;
  blob: Blob;
  size: number;
}

async function fetchAsBlob(uri: string): Promise<Blob> {
  const response = await fetch(uri);
  return response.blob();
}

// Quality ladder: start at 0.8, step down by 0.1 to a floor of 0.5, checked
// against the already-fetched Blob's own size (no extra file-size API
// needed). Never uploads the uncompressed original, however large.
export async function compressImageForUpload(
  localUri: string,
): Promise<CompressedImage> {
  let quality = COMPRESS_QUALITY_START;
  let result = await manipulateAsync(
    localUri,
    [{ resize: { width: MAX_UPLOAD_WIDTH } }],
    { compress: quality, format: SaveFormat.JPEG },
  );
  let blob = await fetchAsBlob(result.uri);

  while (
    blob.size > MAX_COMPRESSED_SIZE_BYTES &&
    quality > COMPRESS_QUALITY_FLOOR
  ) {
    quality = Math.max(
      COMPRESS_QUALITY_FLOOR,
      Math.round((quality - COMPRESS_QUALITY_STEP) * 100) / 100,
    );
    result = await manipulateAsync(
      localUri,
      [{ resize: { width: MAX_UPLOAD_WIDTH } }],
      { compress: quality, format: SaveFormat.JPEG },
    );
    blob = await fetchAsBlob(result.uri);
  }

  return { uri: result.uri, blob, size: blob.size };
}

function buildWardrobeUploadError(
  code: WardrobeUploadErrorCode,
  message: string,
  retryable = true,
): WardrobeUploadError {
  return { code, message, retryable };
}

// supabase.functions.invoke's error on a non-2xx response is a
// FunctionsHttpError whose `.context` is the raw Response object (not a
// parsed body) -- see @supabase/functions-js's FunctionsClient.invoke.
async function toRequestUploadUrlError(
  error: unknown,
): Promise<WardrobeUploadError> {
  const context = (
    error as
      | { context?: { status?: number; json?: () => Promise<unknown> } }
      | null
      | undefined
  )?.context;

  if (context?.status === 403 && typeof context.json === 'function') {
    try {
      const body = (await context.json()) as
        | { code?: string; message?: string }
        | undefined;
      if (body?.code === 'wardrobe_limit_reached') {
        return buildWardrobeUploadError(
          'wardrobe_limit_reached',
          body.message ?? WARDROBE_LIMIT_MESSAGE,
          false,
        );
      }
    } catch {
      // Body wasn't parseable JSON -- fall through to the generic mapping.
    }
  }

  return buildWardrobeUploadError('unknown', UNKNOWN_UPLOAD_ERROR_MESSAGE);
}

export async function requestUploadUrl(
  request: UploadUrlRequest,
): Promise<UploadUrlResponse> {
  const { data, error } = await supabase.functions.invoke<UploadUrlResponse>(
    'get-upload-url',
    { body: request },
  );

  if (error) {
    throw await toRequestUploadUrlError(error);
  }
  if (!data) {
    throw buildWardrobeUploadError('unknown', UNKNOWN_UPLOAD_ERROR_MESSAGE);
  }
  return data;
}

// XMLHttpRequest (not expo-file-system's native-only createUploadTask) so
// this one code path works identically on web and native -- see the design
// doc's "Upload transport" note. A raw-body PUT, not a multipart/form-data
// POST: see wardrobe.types.ts's header comment for why (R2 doesn't support
// presigned POST policies -- live-verified 2026-07-24).
export function uploadToR2WithProgress(
  uploadUrl: string,
  blob: Blob,
  contentType: string,
  onProgress?: (percent: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', uploadUrl, true);
    xhr.setRequestHeader('Content-Type', contentType);

    xhr.upload.onprogress = (event: ProgressEvent) => {
      if (!onProgress || !event.lengthComputable) {
        return;
      }
      onProgress(Math.round((event.loaded / event.total) * 100));
    };

    // Distinguishes an expired/invalid signature (403) and a policy
    // violation (400) from a generic network/server failure by inspecting
    // xhr.status in onload, not just onerror (see Edge Cases).
    xhr.onload = () => {
      if (xhr.status === 200 || xhr.status === 204) {
        resolve();
        return;
      }
      if (xhr.status === 403) {
        reject(
          buildWardrobeUploadError('expired_url', EXPIRED_URL_ERROR_MESSAGE),
        );
        return;
      }
      if (xhr.status === 400) {
        // Non-retryable: the same file would fail identically against a
        // fresh signature.
        reject(
          buildWardrobeUploadError(
            'invalid_file',
            INVALID_FILE_ERROR_MESSAGE,
            false,
          ),
        );
        return;
      }
      // Any other non-2xx (e.g. R2 500 / temporarily unreachable) is
      // treated as a generic, retryable network-class failure.
      reject(buildWardrobeUploadError('network_error', NETWORK_ERROR_MESSAGE));
    };

    xhr.onerror = () => {
      reject(buildWardrobeUploadError('network_error', NETWORK_ERROR_MESSAGE));
    };

    xhr.send(blob);
  });
}

// --- SS-013 additions: POST /wardrobe/remove-bg, POST /wardrobe/tag, and a
// Realtime subscription wrapper. Both REST calls use constants/api.ts's
// base URL, never a hardcoded host (CLAUDE.md).

async function postWardrobeAction(
  path: '/wardrobe/remove-bg' | '/wardrobe/tag',
  itemId: string,
  jwt: string,
): Promise<void> {
  const response = await fetch(`${EXPO_PUBLIC_BACKEND_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${jwt}`,
    },
    body: JSON.stringify({ item_id: itemId }),
  });

  if (response.status !== 202) {
    throw buildWardrobeUploadError('unknown', UNKNOWN_UPLOAD_ERROR_MESSAGE);
  }
}

export async function removeBackground(
  itemId: string,
  jwt: string,
): Promise<void> {
  await postWardrobeAction('/wardrobe/remove-bg', itemId, jwt);
}

export async function tagItem(itemId: string, jwt: string): Promise<void> {
  await postWardrobeAction('/wardrobe/tag', itemId, jwt);
}

export async function fetchWardrobeItemImageUrl(
  itemId: string,
  jwt: string,
): Promise<{ url: string; source: 'clean' | 'original' }> {
  const response = await fetch(
    `${EXPO_PUBLIC_BACKEND_URL}/wardrobe/items/${itemId}/image-url`,
    { headers: { Authorization: `Bearer ${jwt}` } },
  );
  if (!response.ok) {
    throw buildWardrobeUploadError('unknown', UNKNOWN_UPLOAD_ERROR_MESSAGE);
  }
  return response.json();
}

// Thin wrapper around a Supabase Realtime `postgres_changes` UPDATE
// subscription -- the readiness signal (processing_status='bg_removed' AND
// ai_tags.tagging.status='tagged'|'flagged') is combined by the *caller*
// (the screen owning the subscription lifecycle, per the design doc), not
// here. Returns an unsubscribe function.
export function subscribeToItemUpdates(
  itemId: string,
  onUpdate: (row: WardrobeItemRealtimeRow) => void,
): () => void {
  const channel = supabase
    .channel(`wardrobe_item_${itemId}`)
    .on(
      'postgres_changes',
      {
        event: 'UPDATE',
        schema: 'public',
        table: 'wardrobe_items',
        filter: `id=eq.${itemId}`,
      },
      (payload: { new: WardrobeItemRealtimeRow }) => {
        onUpdate(payload.new);
      },
    )
    .subscribe();

  return () => {
    supabase.removeChannel(channel);
  };
}

// SS-019 -- pure decode of a WardrobeItemRealtimeRow into the Review form's
// editable draft shape. Co-located with subscribeToItemUpdates (the thing
// whose payload it decodes), per the design doc. Deliberately NOT called on
// a 'failed' tagging status by this file's callers -- see
// docs/tickets/SS-019-design.md's Edge Cases: the backend never writes
// tag_columns on failure, so this function's output would be a real-looking
// but entirely empty prefill rather than an honest "fill manually" state.
export function mapRealtimeRowToTagsDraft(
  row: WardrobeItemRealtimeRow,
): GarmentTagsDraft {
  const tagging = row.ai_tags?.tagging;
  return {
    category: row.category,
    subcategory: row.subcategory,
    colorPrimary: row.color_primary,
    colorSecondary: row.color_secondary,
    pattern: row.pattern,
    fabric: row.fabric,
    occasionTags: row.occasion_tags ?? [],
    seasonTags: row.season_tags ?? [],
    confidence: tagging?.confidence ?? 1,
    alternatives: tagging?.alternatives,
    contentFlag: tagging?.moderation?.content_flag ?? 'ok',
    containsPerson: tagging?.moderation?.contains_person ?? false,
  };
}

// In-batch dedupe only (see Edge Cases -- scoped down from the ticket's
// literal "check against existing items" wording; a true cross-wardrobe
// check needs an image_hash column, logged as BL-043). SHA-256 of the
// compressed image's base64, compared by the caller against hashes already
// seen in the same upload session.
export async function computeBatchDedupeHash(
  base64Data: string,
): Promise<string> {
  return Crypto.digestStringAsync(
    Crypto.CryptoDigestAlgorithm.SHA256,
    base64Data,
  );
}

// --- SS-014 additions: list/count/bulk-image-urls reads plus
// favourite/worn/delete direct-writes. Same established shape as this
// file's existing Edge Function/Realtime calls above -- this file (not just
// wardrobe.queries.ts's useSaveWardrobeItemTags) is where this domain's raw
// Supabase calls live; queries.ts wraps these in React Query hooks, never
// calls Supabase directly itself for these.

export async function fetchWardrobeItems(): Promise<WardrobeItemRow[]> {
  const { data, error } = await supabase
    .from('wardrobe_items')
    .select('*')
    .order('created_at', { ascending: false });
  if (error) {
    throw error;
  }
  return data ?? [];
}

export async function fetchWardrobeItemCount(): Promise<number> {
  const { count, error } = await supabase
    .from('wardrobe_items')
    .select('id', { count: 'exact', head: true });
  if (error) {
    throw error;
  }
  return count ?? 0;
}

export async function fetchWardrobeItemImageUrls(
  itemIds: string[],
  jwt: string,
): Promise<WardrobeItemImageUrlsMap> {
  const response = await fetch(
    `${EXPO_PUBLIC_BACKEND_URL}/wardrobe/items/image-urls`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${jwt}`,
      },
      body: JSON.stringify({ item_ids: itemIds }),
    },
  );
  if (!response.ok) {
    throw buildWardrobeUploadError('unknown', UNKNOWN_UPLOAD_ERROR_MESSAGE);
  }
  const body = (await response.json()) as { urls: WardrobeItemImageUrlsMap };
  return body.urls;
}

export async function toggleWardrobeItemFavourite(
  itemId: string,
  isFavourite: boolean,
): Promise<void> {
  const { error } = await supabase
    .from('wardrobe_items')
    .update({ is_favourite: isFavourite })
    .eq('id', itemId);
  if (error) {
    throw error;
  }
}

// Caller supplies the already-incremented count (read from the already-cached
// useWardrobeItemsQuery data) -- not an atomic server-side increment (design
// doc's Concrete values: BL-036/BL-066's read-then-write race class, a third
// instance, accepted for the same reason: low real-world concurrent-write
// likelihood for a single user's own wardrobe).
export async function markWardrobeItemWorn(
  itemId: string,
  nextWearCount: number,
): Promise<void> {
  const { error } = await supabase
    .from('wardrobe_items')
    .update({
      wear_count: nextWearCount,
      last_worn_at: new Date().toISOString(),
    })
    .eq('id', itemId);
  if (error) {
    throw error;
  }
}

export async function deleteWardrobeItem(itemId: string): Promise<void> {
  const { error } = await supabase
    .from('wardrobe_items')
    .delete()
    .eq('id', itemId);
  if (error) {
    throw error;
  }
}
