import { useRouter } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ScrollView } from 'react-native';
import { type AppBottomSheetRef, IconButton } from '../../components/ui';
import { useAuthStore } from '../../features/auth/auth.store';
import { BatchSummaryToast } from '../../features/wardrobe/components/BatchSummaryToast';
import {
  CaptureStep,
  type CaptureStepImage,
} from '../../features/wardrobe/components/CaptureStep';
import { CategoryPicker } from '../../features/wardrobe/components/CategoryPicker';
import { ProcessingStep } from '../../features/wardrobe/components/ProcessingStep';
import { ReviewStep } from '../../features/wardrobe/components/ReviewStep';
import {
  useProcessWardrobeItem,
  useUploadWardrobeItem,
} from '../../features/wardrobe/wardrobe.queries';
import {
  mapRealtimeRowToTagsDraft,
  subscribeToItemUpdates,
} from '../../features/wardrobe/wardrobe.service';
import { useWardrobeBatchStore } from '../../features/wardrobe/wardrobe.store';
import {
  type GarmentTagsDraft,
  type WardrobeCategory,
  type WardrobeItemRealtimeRow,
  isWardrobeUploadError,
} from '../../features/wardrobe/wardrobe.types';

const DEFAULT_TAGS_DRAFT: GarmentTagsDraft = {
  category: null,
  subcategory: null,
  colorPrimary: null,
  colorSecondary: null,
  pattern: null,
  fabric: null,
  occasionTags: [],
  seasonTags: [],
  confidence: 1,
  contentFlag: 'ok',
  containsPerson: false,
};

type ScreenStep = 'capture' | 'processing' | 'review' | 'summary';

// 3-step Capture -> Processing -> Review flow, driven by a local step state
// machine (not 3 separate routes), per docs/tickets/SS-013-design.md.
export default function WardrobeUploadScreen() {
  const router = useRouter();
  const jwt = useAuthStore((state) => state.session?.access_token);

  const items = useWardrobeBatchStore((state) => state.items);
  const currentIndex = useWardrobeBatchStore((state) => state.currentIndex);
  const initBatch = useWardrobeBatchStore((state) => state.initBatch);
  const updateItemStatus = useWardrobeBatchStore(
    (state) => state.updateItemStatus,
  );
  const updateItemTags = useWardrobeBatchStore((state) => state.updateItemTags);
  const advanceToNext = useWardrobeBatchStore((state) => state.advanceToNext);
  const resetBatch = useWardrobeBatchStore((state) => state.reset);

  const [screenStep, setScreenStep] = useState<ScreenStep>('capture');
  // SS-019: surfaces the free-tier-cap message when a batch stops early due
  // to wardrobe_limit_reached (see processItem's catch block below). Only
  // ever set from the upload step's error -- see design doc's "Concrete
  // values".
  const [limitReachedMessage, setLimitReachedMessage] = useState<string | null>(
    null,
  );
  const uploadMutation = useUploadWardrobeItem();
  const processMutation = useProcessWardrobeItem();
  const unsubscribeRef = useRef<(() => void) | null>(null);

  const currentItem = items[currentIndex];

  const processItem = useCallback(
    async (taskId: string, localUri: string) => {
      if (!jwt) return;
      try {
        updateItemStatus(taskId, 'uploading');
        const uploadResult = await uploadMutation.mutateAsync({
          taskId,
          localUri,
          source: currentItem?.source ?? 'camera',
        });
        updateItemStatus(taskId, 'removing_bg', {
          itemId: uploadResult.itemId,
        });

        unsubscribeRef.current?.();
        unsubscribeRef.current = subscribeToItemUpdates(
          uploadResult.itemId,
          (row: WardrobeItemRealtimeRow) => {
            const taggingStatus = row.ai_tags?.tagging?.status;
            if (
              row.processing_status === 'bg_removed' &&
              taggingStatus === 'tagging'
            ) {
              updateItemStatus(taskId, 'tagging', {
                itemId: uploadResult.itemId,
              });
            }
            if (
              row.processing_status === 'bg_removed' &&
              (taggingStatus === 'tagged' || taggingStatus === 'flagged')
            ) {
              // SS-019 headline fix: the Realtime row's tag columns now
              // actually reach the Review form's draft state, instead of
              // always falling back to DEFAULT_TAGS_DRAFT.
              updateItemTags(taskId, mapRealtimeRowToTagsDraft(row));
              updateItemStatus(taskId, 'review', {
                itemId: uploadResult.itemId,
              });
              setScreenStep('review');
            }
            // SS-019: previously no handler at all for 'failed' -- the user
            // was stuck on Processing indefinitely. Falls back to the blank
            // DEFAULT_TAGS_DRAFT by deliberately NOT calling updateItemTags
            // here (the backend never writes tag_columns on failure -- see
            // wardrobe.types.ts's WardrobeItemRealtimeRow doc comment).
            if (
              row.processing_status === 'bg_removed' &&
              taggingStatus === 'failed'
            ) {
              updateItemStatus(taskId, 'review', {
                itemId: uploadResult.itemId,
              });
              setScreenStep('review');
            }
          },
        );

        await processMutation.mutateAsync({ itemId: uploadResult.itemId, jwt });
      } catch (rawError) {
        // SS-019: a wardrobe_limit_reached 403 (free-tier cap, only possible
        // from uploadMutation.mutateAsync -- bg-removal has no cap check) is
        // detected once and stops the whole batch with a clear message,
        // instead of every remaining queued item independently retrying and
        // failing identically (see design doc's Edge Cases).
        const uploadError = isWardrobeUploadError(rawError) ? rawError : null;
        if (uploadError?.code === 'wardrobe_limit_reached') {
          updateItemStatus(taskId, 'failed', { error: uploadError.message });
          const store = useWardrobeBatchStore.getState();
          for (const item of store.items) {
            if (item.status === 'queued') {
              updateItemStatus(item.taskId, 'failed', {
                error: uploadError.message,
              });
            }
          }
          setLimitReachedMessage(uploadError.message);
          setScreenStep('summary');
          return;
        }

        // Batch with one failure: mark it and move on regardless -- the
        // batch loop never blocks on one failure (design doc Edge Cases).
        // Reads live store state via getState() (not the render-closured
        // items/currentIndex) -- this catch can fire after advanceToNext()
        // has already moved currentIndex on, so the closured values would
        // be stale and could re-select the very item that just failed.
        updateItemStatus(taskId, 'failed', { error: 'Processing failed' });
        advanceToNext();
        const store = useWardrobeBatchStore.getState();
        const nextItem = store.items[store.currentIndex];
        if (nextItem && nextItem.status === 'queued') {
          void processItem(nextItem.taskId, nextItem.localUri);
        } else if (!nextItem) {
          setScreenStep('summary');
        }
      }
    },
    [
      jwt,
      currentItem,
      uploadMutation,
      processMutation,
      updateItemStatus,
      updateItemTags,
      advanceToNext,
    ],
  );

  useEffect(() => {
    return () => {
      unsubscribeRef.current?.();
    };
  }, []);

  const handleImagesSelected = (images: CaptureStepImage[]) => {
    const sources = images.map((image, index) => ({
      taskId: `task-${Date.now()}-${index}`,
      localUri: image.localUri,
      source: image.source,
    }));
    initBatch(sources);
    setScreenStep('processing');
    const first = sources[0];
    if (first) {
      void processItem(first.taskId, first.localUri);
    }
  };

  const handleRetryProcessing = () => {
    if (currentItem) {
      void processItem(currentItem.taskId, currentItem.localUri);
    }
  };

  const handleSkipProcessing = () => {
    if (currentItem) {
      updateItemStatus(currentItem.taskId, 'review');
      setScreenStep('review');
    }
  };

  const advanceAfterSave = () => {
    if (currentItem) {
      updateItemStatus(currentItem.taskId, 'saved');
    }
    advanceToNext();
    // getState() -- see processItem's catch-block comment for why this
    // reads live store state rather than the render-closured items/index.
    const store = useWardrobeBatchStore.getState();
    const nextItem = store.items[store.currentIndex];
    if (nextItem) {
      setScreenStep('processing');
      void processItem(nextItem.taskId, nextItem.localUri);
    } else {
      setScreenStep('summary');
    }
  };

  const handleCancel = () => {
    unsubscribeRef.current?.();
    resetBatch();
    setLimitReachedMessage(null);
    // router.back() throws an unhandled-GO_BACK dev warning (and silently
    // does nothing) when this screen was entered with no prior history in
    // the stack -- e.g. a direct URL load / page refresh while already on
    // /wardrobe/upload, which is a normal way to land here during
    // web/tunnel testing, not just via an in-app push. Falls back to an
    // explicit replace to the wardrobe grid so Cancel always returns
    // somewhere, per this ticket's own AC ("Cancel at any step discards and
    // returns to the wardrobe screen").
    if (router.canGoBack()) {
      router.back();
    } else {
      router.replace('/(tabs)/wardrobe');
    }
  };

  const handleAddAnother = () => {
    resetBatch();
    setLimitReachedMessage(null);
    setScreenStep('capture');
  };

  const [pendingCategory, setPendingCategory] = useState<
    WardrobeCategory | undefined
  >(undefined);
  const categoryPickerRef = useRef<AppBottomSheetRef>(null);

  return (
    <>
      <IconButton
        icon="close-outline"
        accessibilityLabel="Cancel"
        onPress={handleCancel}
      />

      {screenStep === 'capture' ? (
        <CaptureStep onImagesSelected={handleImagesSelected} />
      ) : null}

      {/* SS-019: the Capture step's CameraView needs full-bleed flex: 1
          layout, not a scrolling ancestor -- the ScrollView wrap is scoped
          to the other 3 steps only. Follows this repo's one existing
          precedent for this exact pattern (edit-preferences.tsx: plain
          react-native ScrollView, no KeyboardAvoidingView) -- confirmed
          against the currently-installed Expo SDK's docs, which offer
          react-native-keyboard-controller as an opt-in third-party library
          this repo doesn't depend on, not a requirement for plain
          scroll-to-reveal-inputs behaviour. */}
      {screenStep !== 'capture' ? (
        <ScrollView testID="upload-scroll-view" className="flex-1">
          {screenStep === 'processing' && currentItem ? (
            <ProcessingStep
              status={currentItem.status}
              currentIndex={currentIndex}
              totalItems={items.length}
              onRetry={handleRetryProcessing}
              onSkip={handleSkipProcessing}
            />
          ) : null}

          {screenStep === 'review' && currentItem && jwt ? (
            <>
              <ReviewStep
                itemId={currentItem.itemId ?? ''}
                jwt={jwt}
                processingStatus="bg_removed"
                initialTags={currentItem.tags ?? DEFAULT_TAGS_DRAFT}
                onOpenCategoryPicker={() => {
                  categoryPickerRef.current?.present();
                }}
                selectedCategoryOverride={pendingCategory}
                onSaved={advanceAfterSave}
              />
              <CategoryPicker
                ref={categoryPickerRef}
                onSelect={setPendingCategory}
              />
            </>
          ) : null}

          {screenStep === 'summary' ? (
            <BatchSummaryToast
              items={items}
              onAddAnother={handleAddAnother}
              limitReachedMessage={limitReachedMessage}
            />
          ) : null}
        </ScrollView>
      ) : null}
    </>
  );
}
