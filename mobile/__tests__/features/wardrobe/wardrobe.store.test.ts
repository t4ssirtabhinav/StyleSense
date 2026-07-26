import {
  isUploadTaskStale,
  useWardrobeBatchStore,
  useWardrobeUploadStore,
} from '../../../features/wardrobe/wardrobe.store';

describe('useWardrobeUploadStore', () => {
  beforeEach(() => {
    useWardrobeUploadStore.setState({ tasks: {} });
  });

  it("startUpload adds a new task in 'compressing' status with progress 0", () => {
    useWardrobeUploadStore
      .getState()
      .startUpload('task-1', 'file://a.jpg', 'camera');

    const task = useWardrobeUploadStore.getState().tasks['task-1'];
    expect(task.status).toBe('compressing');
    expect(task.progress).toBe(0);
    expect(task.localUri).toBe('file://a.jpg');
    expect(task.source).toBe('camera');
  });

  it("updateProgress updates only the targeted task's percent, leaving sibling tasks untouched", () => {
    const { startUpload, updateProgress } = useWardrobeUploadStore.getState();
    startUpload('task-1', 'file://a.jpg', 'camera');
    startUpload('task-2', 'file://b.jpg', 'gallery');

    updateProgress('task-1', 42);

    const tasks = useWardrobeUploadStore.getState().tasks;
    expect(tasks['task-1'].progress).toBe(42);
    expect(tasks['task-1'].status).toBe('uploading');
    expect(tasks['task-2'].progress).toBe(0);
    expect(tasks['task-2'].status).toBe('compressing');
  });

  it("setting 'error' status preserves the last-known progress percent", () => {
    const { startUpload, updateProgress, setError } =
      useWardrobeUploadStore.getState();
    startUpload('task-1', 'file://a.jpg', 'camera');
    updateProgress('task-1', 63);

    setError('task-1', {
      code: 'network_error',
      message: 'No internet connection.',
      retryable: true,
    });

    const task = useWardrobeUploadStore.getState().tasks['task-1'];
    expect(task.status).toBe('error');
    expect(task.progress).toBe(63);
    expect(task.error?.code).toBe('network_error');
  });

  it('retryUpload resets a failed task back to an in-progress status without losing its localUri', () => {
    const { startUpload, setError, retryUpload } =
      useWardrobeUploadStore.getState();
    startUpload('task-1', 'file://a.jpg', 'camera');
    setError('task-1', {
      code: 'network_error',
      message: 'No internet connection.',
      retryable: true,
    });

    retryUpload('task-1');

    const task = useWardrobeUploadStore.getState().tasks['task-1'];
    expect(task.status).not.toBe('error');
    expect(task.status).not.toBe('idle');
    expect(task.localUri).toBe('file://a.jpg');
    expect(task.error).toBeUndefined();
  });

  it('setSuccess sets status success, progress 100, and stores the returned itemId', () => {
    const { startUpload, setSuccess } = useWardrobeUploadStore.getState();
    startUpload('task-1', 'file://a.jpg', 'camera');

    setSuccess('task-1', 'item-123');

    const task = useWardrobeUploadStore.getState().tasks['task-1'];
    expect(task.status).toBe('success');
    expect(task.progress).toBe(100);
    expect(task.itemId).toBe('item-123');
  });

  it('is a no-op (does not throw) when acting on an unknown taskId', () => {
    useWardrobeUploadStore.getState().updateProgress('missing-task', 50);
    useWardrobeUploadStore.getState().retryUpload('missing-task');
    expect(useWardrobeUploadStore.getState().tasks).toEqual({});
  });
});

describe('isUploadTaskStale', () => {
  const baseTask = {
    taskId: 't1',
    localUri: 'file://a.jpg',
    source: 'camera' as const,
    progress: 10,
  };

  it('returns true when status is uploading and lastProgressAt exceeds the threshold', () => {
    const now = 1_000_000;
    expect(
      isUploadTaskStale(
        { ...baseTask, status: 'uploading', lastProgressAt: now - 40_000 },
        now,
        30_000,
      ),
    ).toBe(true);
  });

  it('returns false when still within the threshold', () => {
    const now = 1_000_000;
    expect(
      isUploadTaskStale(
        { ...baseTask, status: 'uploading', lastProgressAt: now - 5_000 },
        now,
        30_000,
      ),
    ).toBe(false);
  });

  it('returns false for a non-uploading status regardless of how old lastProgressAt is', () => {
    const now = 1_000_000;
    expect(
      isUploadTaskStale(
        { ...baseTask, status: 'success', lastProgressAt: now - 40_000 },
        now,
        30_000,
      ),
    ).toBe(false);
  });
});

describe('useWardrobeBatchStore', () => {
  beforeEach(() => {
    useWardrobeBatchStore.setState({ items: [], currentIndex: 0 });
  });

  it('initBatch seeds items from the given sources, currentIndex=0', () => {
    useWardrobeBatchStore.getState().initBatch([
      { taskId: 't1', localUri: 'file://a.jpg', source: 'camera' },
      { taskId: 't2', localUri: 'file://b.jpg', source: 'gallery' },
    ]);

    const state = useWardrobeBatchStore.getState();
    expect(state.items).toHaveLength(2);
    expect(state.items[0]).toEqual(
      expect.objectContaining({
        taskId: 't1',
        localUri: 'file://a.jpg',
        source: 'camera',
        status: 'queued',
      }),
    );
    expect(state.currentIndex).toBe(0);
  });

  it('updateItemStatus/updateItemTags mutate only the targeted item', () => {
    useWardrobeBatchStore.getState().initBatch([
      { taskId: 't1', localUri: 'file://a.jpg', source: 'camera' },
      { taskId: 't2', localUri: 'file://b.jpg', source: 'camera' },
    ]);

    useWardrobeBatchStore
      .getState()
      .updateItemStatus('t1', 'tagging', { itemId: 'item-1' });

    let state = useWardrobeBatchStore.getState();
    expect(state.items[0].status).toBe('tagging');
    expect(state.items[0].itemId).toBe('item-1');
    expect(state.items[1].status).toBe('queued');

    const tags = {
      category: 'ethnic_kurta' as const,
      subcategory: null,
      colorPrimary: null,
      colorSecondary: null,
      pattern: null,
      fabric: null,
      occasionTags: [],
      seasonTags: [],
      confidence: 0.9,
      contentFlag: 'ok' as const,
      containsPerson: false,
    };
    useWardrobeBatchStore.getState().updateItemTags('t1', tags);
    state = useWardrobeBatchStore.getState();
    expect(state.items[0].tags).toEqual(tags);
    expect(state.items[1].tags).toBeUndefined();
  });

  it('advanceToNext increments currentIndex and is a no-op past the last item', () => {
    useWardrobeBatchStore
      .getState()
      .initBatch([
        { taskId: 't1', localUri: 'file://a.jpg', source: 'camera' },
      ]);

    useWardrobeBatchStore.getState().advanceToNext();
    expect(useWardrobeBatchStore.getState().currentIndex).toBe(1);

    useWardrobeBatchStore.getState().advanceToNext();
    expect(useWardrobeBatchStore.getState().currentIndex).toBe(1);
  });

  it('reset clears items back to empty and currentIndex to 0', () => {
    useWardrobeBatchStore
      .getState()
      .initBatch([
        { taskId: 't1', localUri: 'file://a.jpg', source: 'camera' },
      ]);
    useWardrobeBatchStore.getState().advanceToNext();

    useWardrobeBatchStore.getState().reset();

    const state = useWardrobeBatchStore.getState();
    expect(state.items).toEqual([]);
    expect(state.currentIndex).toBe(0);
  });
});
