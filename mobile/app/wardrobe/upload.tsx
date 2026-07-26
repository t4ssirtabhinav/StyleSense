import { useRouter } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
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
import { subscribeToItemUpdates } from '../../features/wardrobe/wardrobe.service';
import { useWardrobeBatchStore } from '../../features/wardrobe/wardrobe.store';
import type {
  GarmentTagsDraft,
  WardrobeCategory,
  WardrobeItemRealtimeRow,
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
  const advanceToNext = useWardrobeBatchStore((state) => state.advanceToNext);
  const resetBatch = useWardrobeBatchStore((state) => state.reset);

  const [screenStep, setScreenStep] = useState<ScreenStep>('capture');
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
              updateItemStatus(taskId, 'review', {
                itemId: uploadResult.itemId,
              });
              setScreenStep('review');
            }
          },
        );

        await processMutation.mutateAsync({ itemId: uploadResult.itemId, jwt });
      } catch {
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
    router.back();
  };

  const handleAddAnother = () => {
    resetBatch();
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
        <BatchSummaryToast items={items} onAddAnother={handleAddAnother} />
      ) : null}
    </>
  );
}
