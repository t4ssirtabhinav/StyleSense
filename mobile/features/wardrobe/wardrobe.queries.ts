import * as Sentry from '@sentry/react-native';
import { useMutation } from '@tanstack/react-query';
import { ANALYTICS_EVENTS } from '../../constants/analyticsEvents';
import { useAnalytics } from '../../hooks/useAnalytics';
import {
  EXPIRED_URL_MAX_RETRIES,
  RETRY_BACKOFF_FACTOR,
  RETRY_BASE_DELAY_MS,
  RETRY_MAX_ATTEMPTS,
  RETRY_MAX_DELAY_MS,
  UNKNOWN_UPLOAD_ERROR_MESSAGE,
} from './wardrobe.constants';
import {
  compressImageForUpload,
  requestUploadUrl,
  uploadToR2WithProgress,
} from './wardrobe.service';
import { useWardrobeUploadStore } from './wardrobe.store';
import type {
  UploadWardrobeItemInput,
  UploadWardrobeItemResult,
  WardrobeUploadError,
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

function isWardrobeUploadError(error: unknown): error is WardrobeUploadError {
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    'retryable' in error
  );
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
