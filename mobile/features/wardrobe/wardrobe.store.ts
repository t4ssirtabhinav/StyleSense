import { create } from 'zustand';
import { STALE_UPLOAD_THRESHOLD_MS } from './wardrobe.constants';
import type {
  BatchItemState,
  BatchItemStatus,
  GarmentTagsDraft,
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
}));

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
