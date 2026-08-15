import { create } from 'zustand';
import { registerUserStateReset } from '../auth/userStateReset';
import { STALE_UPLOAD_THRESHOLD_MS } from './wardrobe.constants';
import type {
  BatchItemState,
  BatchItemStatus,
  CategoryFilterValue,
  GarmentTagsDraft,
  OccasionSlug,
  SeasonTag,
  WardrobeFilterState,
  WardrobeSortOption,
  WardrobeUploadError,
  WardrobeUploadSource,
  WardrobeUploadStatus,
  WardrobeUploadTask,
} from './wardrobe.types';

// Per-task upload progress/status/retry state, keyed by a client-generated
// task id (not the same as R2's itemId until the upload actually starts --
// see wardrobe.types.ts). SS-013's UI is the intended consumer; this ticket
// only makes the state observable (see Edge Cases' "stale" upload note).

export interface WardrobeUploadState {
  tasks: Record<string, WardrobeUploadTask>;
  startUpload: (
    taskId: string,
    localUri: string,
    source: WardrobeUploadSource,
  ) => void;
  setStatus: (taskId: string, status: WardrobeUploadStatus) => void;
  updateProgress: (taskId: string, progress: number) => void;
  setSuccess: (taskId: string, itemId: string) => void;
  setError: (taskId: string, error: WardrobeUploadError) => void;
  retryUpload: (taskId: string) => void;
  removeTask: (taskId: string) => void;
  reset: () => void;
}

export const useWardrobeUploadStore = create<WardrobeUploadState>((set) => ({
  tasks: {},

  startUpload: (taskId, localUri, source) =>
    set((state) => ({
      tasks: {
        ...state.tasks,
        [taskId]: {
          taskId,
          localUri,
          source,
          status: 'compressing',
          progress: 0,
          lastProgressAt: Date.now(),
        },
      },
    })),

  setStatus: (taskId, status) =>
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) {
        return state;
      }
      return { tasks: { ...state.tasks, [taskId]: { ...task, status } } };
    }),

  updateProgress: (taskId, progress) =>
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) {
        return state;
      }
      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            status: 'uploading',
            progress,
            lastProgressAt: Date.now(),
          },
        },
      };
    }),

  setSuccess: (taskId, itemId) =>
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) {
        return state;
      }
      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            status: 'success',
            progress: 100,
            itemId,
            error: undefined,
          },
        },
      };
    }),

  // Preserves the last-known progress percent (not reset to 0) so a
  // retry-button UI can show where it stalled.
  setError: (taskId, error) =>
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) {
        return state;
      }
      return {
        tasks: {
          ...state.tasks,
          [taskId]: { ...task, status: 'error', error },
        },
      };
    }),

  // Resets a failed task back to an in-progress status without losing its
  // localUri -- a fresh presigned URL is requested next (wardrobe.queries.ts),
  // hence 'requesting_url' rather than restarting compression.
  retryUpload: (taskId) =>
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) {
        return state;
      }
      return {
        tasks: {
          ...state.tasks,
          [taskId]: { ...task, status: 'requesting_url', error: undefined },
        },
      };
    }),

  removeTask: (taskId) =>
    set((state) => {
      if (!(taskId in state.tasks)) {
        return state;
      }
      const nextTasks = { ...state.tasks };
      delete nextTasks[taskId];
      return { tasks: nextTasks };
    }),

  // SS-071 AC #6 — this store previously had no reset() at all, a silent
  // cross-user-bleed source: a signed-out user's in-flight upload tasks
  // (with local URIs pointing at THEIR device photos) would otherwise
  // survive into the next signed-in user's session on the same device.
  reset: () => set({ tasks: {} }),
}));

// SS-071 AC #6 — self-registers with the sign-out reset registry. See
// features/auth/userStateReset.ts.
registerUserStateReset(() => useWardrobeUploadStore.getState().reset());

// --- SS-013: useWardrobeBatchStore ---
// Kept separate from useWardrobeUploadStore above (per the design doc's
// "Files to create/modify" note): the upload store's tasks end at
// 'uploaded'/'success'; this store's tasks continue through
// BG-removal/tagging/review/save -- a different lifecycle, not folded in.

export interface WardrobeBatchSource {
  taskId: string;
  localUri: string;
  source: WardrobeUploadSource;
}

export interface WardrobeBatchState {
  items: BatchItemState[];
  currentIndex: number;
  initBatch: (sources: WardrobeBatchSource[]) => void;
  updateItemStatus: (
    taskId: string,
    status: BatchItemStatus,
    extra?: { itemId?: string; error?: string },
  ) => void;
  updateItemTags: (taskId: string, tags: GarmentTagsDraft) => void;
  advanceToNext: () => void;
  reset: () => void;
}

export const useWardrobeBatchStore = create<WardrobeBatchState>((set) => ({
  items: [],
  currentIndex: 0,

  initBatch: (sources) =>
    set({
      items: sources.map((source) => ({
        taskId: source.taskId,
        localUri: source.localUri,
        source: source.source,
        status: 'queued' as BatchItemStatus,
      })),
      currentIndex: 0,
    }),

  updateItemStatus: (taskId, status, extra) =>
    set((state) => ({
      items: state.items.map((item) =>
        item.taskId === taskId
          ? {
              ...item,
              status,
              itemId: extra?.itemId ?? item.itemId,
              error: extra?.error,
            }
          : item,
      ),
    })),

  updateItemTags: (taskId, tags) =>
    set((state) => ({
      items: state.items.map((item) =>
        item.taskId === taskId ? { ...item, tags } : item,
      ),
    })),

  // No-op past the last item -- batch-summary is a separate signal (see
  // BatchSummaryToast), not an out-of-bounds index.
  advanceToNext: () =>
    set((state) => ({
      currentIndex: Math.min(state.currentIndex + 1, state.items.length),
    })),

  reset: () => set({ items: [], currentIndex: 0 }),
}));

// SS-071 AC #6 — self-registers with the sign-out reset registry.
registerUserStateReset(() => useWardrobeBatchStore.getState().reset());

// --- SS-014: useWardrobeFilterStore ---
// Kept separate from useWardrobeUploadStore/useWardrobeBatchStore above (per
// the design doc's "Files to create/modify" note): this store's state
// persists across the whole grid-viewing session, not per-upload-task -- a
// different lifecycle, not folded in.

const DEFAULT_FILTER_STATE: WardrobeFilterState = {
  categoryFilter: 'all',
  occasionFilter: 'all',
  seasonFilter: 'all',
  colorFilter: 'all',
  search: '',
  sort: 'newest',
};

export interface WardrobeFilterStoreState extends WardrobeFilterState {
  setCategoryFilter: (value: CategoryFilterValue) => void;
  setOccasionFilter: (value: OccasionSlug | 'all') => void;
  setSeasonFilter: (value: SeasonTag | 'all') => void;
  setColorFilter: (value: string | 'all') => void;
  setSearch: (value: string) => void;
  setSort: (value: WardrobeSortOption) => void;
  reset: () => void;
}

export const useWardrobeFilterStore = create<WardrobeFilterStoreState>(
  (set) => ({
    ...DEFAULT_FILTER_STATE,
    setCategoryFilter: (categoryFilter) => set({ categoryFilter }),
    setOccasionFilter: (occasionFilter) => set({ occasionFilter }),
    setSeasonFilter: (seasonFilter) => set({ seasonFilter }),
    setColorFilter: (colorFilter) => set({ colorFilter }),
    setSearch: (search) => set({ search }),
    setSort: (sort) => set({ sort }),
    reset: () => set({ ...DEFAULT_FILTER_STATE }),
  }),
);

// SS-071 AC #6 — self-registers with the sign-out reset registry. Filters
// are weakly user-scoped (design doc's store table), but a stale search
// term/sort left over from a previous user is still worth clearing rather
// than assuming it is harmless.
registerUserStateReset(() => useWardrobeFilterStore.getState().reset());

// Derived "stale" check (Edge Cases: app backgrounded/closed mid-upload) --
// exposed as a standalone helper rather than store state since it depends on
// the current time, not anything that should trigger a re-render on its own.
export function isUploadTaskStale(
  task: WardrobeUploadTask,
  now: number = Date.now(),
  thresholdMs: number = STALE_UPLOAD_THRESHOLD_MS,
): boolean {
  return task.status === 'uploading' && now - task.lastProgressAt > thresholdMs;
}
