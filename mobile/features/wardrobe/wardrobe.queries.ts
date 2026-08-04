import * as Sentry from '@sentry/react-native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ANALYTICS_EVENTS } from '../../constants/analyticsEvents';
import { useAnalytics } from '../../hooks/useAnalytics';
import { supabase } from '../../lib/supabase';
import { useAuthStore } from '../auth/auth.store';
import { useOccasionTaxonomy } from '../onboarding/onboarding.queries';
import {
  EXPIRED_URL_MAX_RETRIES,
  GRID_IMAGE_URLS_STALE_TIME_MS,
  RETRY_BACKOFF_FACTOR,
  RETRY_BASE_DELAY_MS,
  RETRY_MAX_ATTEMPTS,
  RETRY_MAX_DELAY_MS,
  UNKNOWN_UPLOAD_ERROR_MESSAGE,
  WARDROBE_ITEMS_STALE_TIME_MS,
} from './wardrobe.constants';
import {
  compressImageForUpload,
  deleteWardrobeItem,
  deleteWardrobeItemWear,
  fetchWardrobeItemCount,
  fetchWardrobeItemImageUrl,
  fetchWardrobeItemImageUrls,
  fetchWardrobeItemWearStats,
  fetchWardrobeItemWears,
  fetchWardrobeItems,
  logWardrobeItemWear,
  removeBackground,
  requestUploadUrl,
  saveWardrobeItemDetails,
  saveWardrobeItemTags,
  tagItem,
  toggleWardrobeItemFavourite,
  updateWardrobeItemWear,
  uploadToR2WithProgress,
} from './wardrobe.service';
import { useWardrobeUploadStore } from './wardrobe.store';
import {
  type GarmentTagsDraft,
  type LogWearResult,
  type UploadWardrobeItemInput,
  type UploadWardrobeItemResult,
  type WardrobeItemDetailsDraft,
  type WardrobeItemRow,
  type WardrobeUploadError,
  isWardrobeUploadError,
} from './wardrobe.types';

// The only place this React Query hook is called from is components (per
// CLAUDE.md's anti-pattern rule extended to this domain: no direct Supabase
// calls in components -- only through features/<domain>/*.queries.ts). This
// is also the only file in this domain that imports useAnalytics/Sentry --
// wardrobe.service.ts is kept a pure API-call layer with no monitoring side
// effects (see docs/tickets/SS-010-design.md's "Monitoring & analytics
// wiring").

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function toWardrobeUploadError(error: unknown): WardrobeUploadError {
  if (isWardrobeUploadError(error)) {
    return error;
  }
  return {
    code: 'unknown',
    message: UNKNOWN_UPLOAD_ERROR_MESSAGE,
    retryable: true,
  };
}

// Terminal-failure Sentry capture only -- retry attempts exhausted (network
// or expired-URL) or the non-retryable policy-violation error. Never called
// for the routine "403, retried, second attempt succeeded" path (see
// "Monitoring & analytics wiring").
function captureTerminalUploadFailure(error: WardrobeUploadError): void {
  Sentry.captureException(error, { tags: { feature: 'wardrobe_upload' } });
}

export function useUploadWardrobeItem() {
  const { track } = useAnalytics();
  const setStatus = useWardrobeUploadStore((state) => state.setStatus);
  const updateProgress = useWardrobeUploadStore(
    (state) => state.updateProgress,
  );
  const setSuccess = useWardrobeUploadStore((state) => state.setSuccess);
  const setError = useWardrobeUploadStore((state) => state.setError);

  return useMutation<
    UploadWardrobeItemResult,
    WardrobeUploadError,
    UploadWardrobeItemInput
  >({
    mutationFn: async ({ taskId, localUri, source }) => {
      const compressed = await compressImageForUpload(localUri);

      setStatus(taskId, 'requesting_url');
      let uploadUrlResponse: Awaited<ReturnType<typeof requestUploadUrl>>;
      try {
        uploadUrlResponse = await requestUploadUrl({});
      } catch (rawError) {
        // A hard cap (e.g. wardrobe_limit_reached) is surfaced unchanged and
        // immediately -- retrying a hard cap is pointless, and this isn't an
        // error worth alerting on in Sentry (it's an expected business-rule
        // rejection, not an upload failure).
        const uploadError = toWardrobeUploadError(rawError);
        setError(taskId, uploadError);
        throw uploadError;
      }
      const existingItemCount = uploadUrlResponse.existingItemCount;

      let expiredUrlAttempts = 0;
      // The upload loop's first iteration is attempt #1.
      let networkAttempts = 0;
      let backoffDelay = RETRY_BASE_DELAY_MS;

      for (;;) {
        try {
          await uploadToR2WithProgress(
            uploadUrlResponse.uploadUrl,
            compressed.blob,
            uploadUrlResponse.contentType,
            (percent) => updateProgress(taskId, percent),
          );
          break;
        } catch (rawError) {
          const uploadError = toWardrobeUploadError(rawError);

          if (uploadError.code === 'expired_url') {
            if (expiredUrlAttempts >= EXPIRED_URL_MAX_RETRIES) {
              captureTerminalUploadFailure(uploadError);
              setError(taskId, uploadError);
              throw uploadError;
            }
            expiredUrlAttempts += 1;
            // Same itemId -> same R2 key, freshly re-signed uploadUrl.
            uploadUrlResponse = await requestUploadUrl({
              itemId: uploadUrlResponse.itemId,
            });
            continue;
          }

          if (!uploadError.retryable) {
            captureTerminalUploadFailure(uploadError);
            setError(taskId, uploadError);
            throw uploadError;
          }

          networkAttempts += 1;
          if (networkAttempts >= RETRY_MAX_ATTEMPTS) {
            captureTerminalUploadFailure(uploadError);
            setError(taskId, uploadError);
            throw uploadError;
          }
          await sleep(backoffDelay);
          backoffDelay = Math.min(
            backoffDelay * RETRY_BACKOFF_FACTOR,
            RETRY_MAX_DELAY_MS,
          );
        }
      }

      setSuccess(taskId, uploadUrlResponse.itemId);
      track(ANALYTICS_EVENTS.ITEM_UPLOADED, { source });
      if (existingItemCount === 0) {
        track(ANALYTICS_EVENTS.FIRST_ITEM_ADDED);
      }

      return { itemId: uploadUrlResponse.itemId, key: uploadUrlResponse.key };
    },
  });
}

// --- SS-013 additions ---

export interface ProcessWardrobeItemInput {
  itemId: string;
  jwt: string;
}

// Calls remove-bg then tag, sequentially, against the same item_id (BL-041's
// resolution -- see docs/tickets/SS-013-design.md's "Call sequencing"). Both
// endpoints dispatch async background work server-side and return 202
// immediately; this hook only owns request *order*, not completion --
// completion is signalled by the Realtime subscription the *screen* owns
// (per the design doc, subscriptions don't live in this file).
export function useProcessWardrobeItem() {
  return useMutation<void, WardrobeUploadError, ProcessWardrobeItemInput>({
    mutationFn: async ({ itemId, jwt }) => {
      await removeBackground(itemId, jwt);
      await tagItem(itemId, jwt);
    },
  });
}

export interface SaveWardrobeItemTagsInput {
  itemId: string;
  tags: GarmentTagsDraft;
}

// (SS-025) A thin re-export of the onboarding domain's occasion-taxonomy
// hook, so wardrobe components import their occasion vocabulary from their
// own domain's queries layer instead of reaching across into
// features/onboarding/ at the component layer.
//
// The cross-domain import is deliberately confined to this one line at the
// queries layer — there is exactly ONE taxonomy fetcher in the app (the
// ticket's own Technical Note). Promoting it to a `features/taxonomy/`
// domain so neither side has to reach across is logged as BL-089.
export function useOccasionOptions() {
  return useOccasionTaxonomy();
}

// This is now one of several places in this domain a direct Supabase table
// write happens (SS-014 adds favourite/worn/delete/list/count below) --
// mirrors SS-007's patchStylePreferences precedent for partial-field saves,
// and the same established shape as this file's Edge Function/Realtime
// calls -- everywhere else routes through the FastAPI endpoints. RLS-scoped
// via the caller's own session (supabase client already carries the user's
// auth token), never service_role.
//
// SS-014 retrofit: also invalidates the grid's item-list/count queries on
// success. This query key didn't exist when SS-013 shipped this hook, so a
// newly-saved item from the upload flow (ReviewStep.tsx, unmodified by this
// ticket) wouldn't otherwise appear in the grid without a manual
// pull-to-refresh. Reads `userId` from useAuthStore internally (rather than
// widening SaveWardrobeItemTagsInput with a required `userId` field) so
// ReviewStep.tsx's existing call site (`mutate({ itemId, tags })`) keeps
// compiling unchanged.
//
// SS-025: the UPDATE itself moved to wardrobe.service.ts's
// `saveWardrobeItemTags`, which normalises + dedupes the occasion slugs
// first (design §6.4 write boundaries 2 and 3). This hook keeps its
// signature and cache-invalidation behaviour exactly as SS-013/SS-014 left
// them.
export function useSaveWardrobeItemTags() {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.session?.user.id);

  return useMutation<void, Error, SaveWardrobeItemTagsInput>({
    mutationFn: ({ itemId, tags }) => saveWardrobeItemTags(itemId, tags),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: wardrobeItemsQueryKey(userId),
      });
      queryClient.invalidateQueries({
        queryKey: wardrobeItemCountQueryKey(userId),
      });
    },
  });
}

// --- SS-014 (Wardrobe Grid & Catalogue View) additions ---
// Per docs/tickets/SS-014-design.md's "Files to create/modify". userId is
// always included in the list/count/image-urls query keys (mirrors
// auth.queries.ts's own onboardingCompletedQueryKey precedent) so a device
// account-switch can't serve stale cross-user cache.

export function wardrobeItemsQueryKey(userId: string | undefined) {
  return ['wardrobe', 'items', userId] as const;
}

export function wardrobeItemCountQueryKey(userId: string | undefined) {
  return ['wardrobe', 'item-count', userId] as const;
}

export function wardrobeItemImageUrlsQueryKey(userId: string | undefined) {
  return ['wardrobe', 'item-image-urls', userId] as const;
}

export function wardrobeItemImageUrlQueryKey(itemId: string | undefined) {
  return ['wardrobe', 'item-image-url', itemId] as const;
}

export function useWardrobeItemsQuery(userId: string | undefined) {
  return useQuery({
    queryKey: wardrobeItemsQueryKey(userId),
    queryFn: fetchWardrobeItems,
    enabled: Boolean(userId),
    staleTime: WARDROBE_ITEMS_STALE_TIME_MS,
  });
}

export function useWardrobeItemCountQuery(userId: string | undefined) {
  return useQuery({
    queryKey: wardrobeItemCountQueryKey(userId),
    queryFn: fetchWardrobeItemCount,
    enabled: Boolean(userId),
  });
}

// Bulk-resolves signed thumbnail/original URLs for every currently-loaded
// item id at once (one call per useWardrobeItemsQuery success -- see design
// doc's "Bulk image-URL endpoint contract"), not one call per item.
export function useWardrobeItemImageUrlsQuery(
  userId: string | undefined,
  itemIds: string[],
  jwt: string | undefined,
) {
  return useQuery({
    queryKey: wardrobeItemImageUrlsQueryKey(userId),
    queryFn: () => fetchWardrobeItemImageUrls(itemIds, jwt as string),
    enabled: Boolean(userId) && Boolean(jwt) && itemIds.length > 0,
    staleTime: GRID_IMAGE_URLS_STALE_TIME_MS,
  });
}

// Wraps SS-013's existing fetchWardrobeItemImageUrl service function in a
// useQuery for the first time (SS-013 only exposed the raw call, consumed
// directly by ReviewStep.tsx's own useEffect) -- ItemDetailSheet fetches the
// full clean/original image only when the sheet opens, not the grid's bulk
// thumbnail.
export function useWardrobeItemImageUrlQuery(
  itemId: string | undefined,
  jwt: string | undefined,
) {
  return useQuery({
    queryKey: wardrobeItemImageUrlQueryKey(itemId),
    queryFn: () => fetchWardrobeItemImageUrl(itemId as string, jwt as string),
    enabled: Boolean(itemId) && Boolean(jwt),
  });
}

function useInvalidateWardrobeGridQueries() {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.session?.user.id);

  return () => {
    queryClient.invalidateQueries({ queryKey: wardrobeItemsQueryKey(userId) });
    queryClient.invalidateQueries({
      queryKey: wardrobeItemCountQueryKey(userId),
    });
  };
}

export interface ToggleWardrobeItemFavouriteInput {
  itemId: string;
  isFavourite: boolean;
}

interface WardrobeGridMutationContext {
  previousItems: WardrobeItemRow[] | undefined;
}

// SS-015: real optimistic behaviour (SS-014 shipped invalidate-only, which
// isn't what the AC's "instant" means) -- onMutate patches the cached items
// array directly, onError rolls back to the pre-mutation snapshot,
// onSettled always reconciles with the server.
export function useToggleWardrobeItemFavourite() {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.session?.user.id);
  const invalidateGridQueries = useInvalidateWardrobeGridQueries();

  return useMutation<
    void,
    Error,
    ToggleWardrobeItemFavouriteInput,
    WardrobeGridMutationContext
  >({
    mutationFn: ({ itemId, isFavourite }) =>
      toggleWardrobeItemFavourite(itemId, isFavourite),
    onMutate: async ({ itemId, isFavourite }) => {
      await queryClient.cancelQueries({
        queryKey: wardrobeItemsQueryKey(userId),
      });
      const previousItems = queryClient.getQueryData<WardrobeItemRow[]>(
        wardrobeItemsQueryKey(userId),
      );
      queryClient.setQueryData<WardrobeItemRow[]>(
        wardrobeItemsQueryKey(userId),
        (current) =>
          current?.map((item) =>
            item.id === itemId ? { ...item, is_favourite: isFavourite } : item,
          ),
      );
      return { previousItems };
    },
    onError: (_error, _variables, context) => {
      if (context) {
        queryClient.setQueryData(
          wardrobeItemsQueryKey(userId),
          context.previousItems,
        );
      }
    },
    onSettled: invalidateGridQueries,
  });
}

export interface DeleteWardrobeItemInput {
  itemId: string;
  jwt: string;
}

// SS-015: delete now goes through DELETE /wardrobe/items/{id} (jwt
// required) rather than a direct Supabase delete -- see
// wardrobe.service.ts's deleteWardrobeItem. onMutate removes the item from
// the cached array immediately (AC: "removes the item from the grid
// immediately"); onError restores it (e.g. the backend isn't reachable,
// BL-037 -- delete is the first destructive action to inherit that
// constraint).
export function useDeleteWardrobeItem() {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.session?.user.id);
  const invalidateGridQueries = useInvalidateWardrobeGridQueries();

  return useMutation<
    void,
    Error,
    DeleteWardrobeItemInput,
    WardrobeGridMutationContext
  >({
    mutationFn: ({ itemId, jwt }) => deleteWardrobeItem(itemId, jwt),
    onMutate: async ({ itemId }) => {
      await queryClient.cancelQueries({
        queryKey: wardrobeItemsQueryKey(userId),
      });
      const previousItems = queryClient.getQueryData<WardrobeItemRow[]>(
        wardrobeItemsQueryKey(userId),
      );
      queryClient.setQueryData<WardrobeItemRow[]>(
        wardrobeItemsQueryKey(userId),
        (current) => current?.filter((item) => item.id !== itemId),
      );
      return { previousItems };
    },
    onError: (_error, _variables, context) => {
      if (context) {
        queryClient.setQueryData(
          wardrobeItemsQueryKey(userId),
          context.previousItems,
        );
      }
    },
    onSettled: invalidateGridQueries,
  });
}

// --- SS-015 additions: dated wear-history log + item-details save --------

export function wardrobeItemWearsQueryKey(itemId: string | undefined) {
  // Keyed by itemId only (globally unique UUID, RLS scopes reads) -- unlike
  // the grid's user-keyed keys, an account switch on the same device is
  // still safe here (design doc's Edge Cases).
  return ['wardrobe', 'item-wears', itemId] as const;
}

export function useWardrobeItemWearsQuery(itemId: string | undefined) {
  return useQuery({
    queryKey: wardrobeItemWearsQueryKey(itemId),
    queryFn: () => fetchWardrobeItemWears(itemId as string),
    enabled: Boolean(itemId),
  });
}

export interface LogWardrobeItemWearInput {
  itemId: string;
  userId: string;
  wornOn: string;
  /** SS-035. Optional -- omitted/undefined behaves exactly like the
   * pre-SS-035 signature (writes null), so ItemDetailSheet's one-tap Mark
   * Worn call site keeps compiling and behaving identically (BL-121: that
   * one-tap default staying null is intentional, not a gap to close here). */
  occasionKey?: string | null;
}

// Inserts the wear, then reads back the trigger-recomputed wear_count/
// cost_per_wear for the toast -- never computes cost_per_wear client-side
// (it's a GENERATED column, BL-004).
export function useLogWardrobeItemWear() {
  const queryClient = useQueryClient();
  const invalidateGridQueries = useInvalidateWardrobeGridQueries();

  return useMutation<LogWearResult, Error, LogWardrobeItemWearInput>({
    mutationFn: async ({ itemId, userId, wornOn, occasionKey }) => {
      const { alreadyLogged } = await logWardrobeItemWear(
        itemId,
        userId,
        wornOn,
        occasionKey ?? null,
      );
      const stats = await fetchWardrobeItemWearStats(itemId);
      return {
        wearCount: stats.wearCount,
        costPerWear: stats.costPerWear,
        wornOn,
        occasionKey: occasionKey ?? null,
        alreadyLogged,
      };
    },
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({
        queryKey: wardrobeItemWearsQueryKey(variables.itemId),
      });
      invalidateGridQueries();
    },
  });
}

export interface UpdateWardrobeItemWearInput {
  wearId: string;
  itemId: string;
  wornOn: string;
  occasionKey: string | null;
}

export function useUpdateWardrobeItemWear() {
  const queryClient = useQueryClient();
  const invalidateGridQueries = useInvalidateWardrobeGridQueries();

  return useMutation<void, Error, UpdateWardrobeItemWearInput>({
    mutationFn: ({ wearId, wornOn, occasionKey }) =>
      updateWardrobeItemWear(wearId, wornOn, occasionKey),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: wardrobeItemWearsQueryKey(variables.itemId),
      });
      invalidateGridQueries();
    },
  });
}

export interface DeleteWardrobeItemWearInput {
  wearId: string;
  itemId: string;
}

export function useDeleteWardrobeItemWear() {
  const queryClient = useQueryClient();
  const invalidateGridQueries = useInvalidateWardrobeGridQueries();

  return useMutation<void, Error, DeleteWardrobeItemWearInput>({
    mutationFn: ({ wearId }) => deleteWardrobeItemWear(wearId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: wardrobeItemWearsQueryKey(variables.itemId),
      });
      invalidateGridQueries();
    },
  });
}

export interface SaveWardrobeItemDetailsInput {
  itemId: string;
  details: WardrobeItemDetailsDraft;
}

export function useSaveWardrobeItemDetails() {
  const invalidateGridQueries = useInvalidateWardrobeGridQueries();

  return useMutation<void, Error, SaveWardrobeItemDetailsInput>({
    mutationFn: ({ itemId, details }) =>
      saveWardrobeItemDetails(itemId, details),
    onSuccess: invalidateGridQueries,
  });
}
