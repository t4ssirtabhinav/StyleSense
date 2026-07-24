import { create } from 'zustand';
import { STALE_UPLOAD_THRESHOLD_MS } from './wardrobe.constants';
import type {
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
