import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { useAuthStore } from '../../../features/auth/auth.store';
import {
  useDeleteWardrobeItem,
  useMarkWardrobeItemWorn,
  useProcessWardrobeItem,
  useSaveWardrobeItemTags,
  useToggleWardrobeItemFavourite,
  useUploadWardrobeItem,
  useWardrobeItemCountQuery,
  useWardrobeItemImageUrlsQuery,
  useWardrobeItemsQuery,
  wardrobeItemCountQueryKey,
  wardrobeItemsQueryKey,
} from '../../../features/wardrobe/wardrobe.queries';
import * as wardrobeService from '../../../features/wardrobe/wardrobe.service';
import { useWardrobeUploadStore } from '../../../features/wardrobe/wardrobe.store';

const mockTrack = jest.fn();
jest.mock('../../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({ track: mockTrack }),
}));

const mockCaptureException = jest.fn();
jest.mock('@sentry/react-native', () => ({
  captureException: (...args: unknown[]) => mockCaptureException(...args),
}));

jest.mock('../../../features/wardrobe/wardrobe.service', () => ({
  compressImageForUpload: jest.fn(),
  requestUploadUrl: jest.fn(),
  uploadToR2WithProgress: jest.fn(),
  removeBackground: jest.fn(),
  tagItem: jest.fn(),
  fetchWardrobeItems: jest.fn(),
  fetchWardrobeItemCount: jest.fn(),
  fetchWardrobeItemImageUrls: jest.fn(),
  fetchWardrobeItemImageUrl: jest.fn(),
  toggleWardrobeItemFavourite: jest.fn(),
  markWardrobeItemWorn: jest.fn(),
  deleteWardrobeItem: jest.fn(),
}));

const mockEq = jest.fn();
const mockUpdate = jest.fn((..._args: unknown[]) => ({ eq: mockEq }));
const mockFrom = jest.fn((..._args: unknown[]) => ({ update: mockUpdate }));
jest.mock('../../../lib/supabase', () => ({
  supabase: { from: (...args: unknown[]) => mockFrom(...args) },
}));

const FAKE_USER_ID = 'user-1';
function setFakeSession() {
  useAuthStore.setState({
    // biome-ignore lint/suspicious/noExplicitAny: minimal fake Session for tests
    session: { user: { id: FAKE_USER_ID } } as any,
    isSessionLoading: false,
  });
}

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

// Same as createWrapper, but also hands back the QueryClient instance so
// tests can spy on invalidateQueries.
function createWrapperWithClient() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { Wrapper, queryClient };
}

const baseUploadUrlResponse = {
  uploadUrl: 'https://r2.example.com/signed',
  itemId: 'item-1',
  key: 'wardrobe/user-1/item-1/original.jpg',
  expiresAt: '2026-01-01T00:05:00.000Z',
  contentType: 'image/jpeg' as const,
  existingItemCount: 0,
};

describe('useUploadWardrobeItem', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useWardrobeUploadStore.setState({ tasks: {} });
    (wardrobeService.compressImageForUpload as jest.Mock).mockResolvedValue({
      uri: 'file://compressed.jpg',
      blob: {},
      size: 100,
    });
  });

  it('orchestrates compress -> requestUploadUrl -> upload and resolves with { itemId, key }', async () => {
    (wardrobeService.requestUploadUrl as jest.Mock).mockResolvedValue(
      baseUploadUrlResponse,
    );
    (wardrobeService.uploadToR2WithProgress as jest.Mock).mockResolvedValue(
      undefined,
    );

    useWardrobeUploadStore
      .getState()
      .startUpload('task-1', 'file://a.jpg', 'camera');
    const { result } = await renderHook(() => useUploadWardrobeItem(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({
      taskId: 'task-1',
      localUri: 'file://a.jpg',
      source: 'camera',
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({
      itemId: 'item-1',
      key: baseUploadUrlResponse.key,
    });
  });

  it('on a 403 mid-upload, requests a fresh presigned URL (same itemId) and retries before surfacing an error', async () => {
    (wardrobeService.requestUploadUrl as jest.Mock)
      .mockResolvedValueOnce(baseUploadUrlResponse)
      .mockResolvedValueOnce({
        ...baseUploadUrlResponse,
        uploadUrl: 'https://r2.example.com/signed-2',
      });
    (wardrobeService.uploadToR2WithProgress as jest.Mock)
      .mockRejectedValueOnce({
        code: 'expired_url',
        message: 'expired',
        retryable: true,
      })
      .mockResolvedValueOnce(undefined);

    useWardrobeUploadStore
      .getState()
      .startUpload('task-1', 'file://a.jpg', 'camera');
    const { result } = await renderHook(() => useUploadWardrobeItem(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({
      taskId: 'task-1',
      localUri: 'file://a.jpg',
      source: 'camera',
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(wardrobeService.requestUploadUrl).toHaveBeenCalledTimes(2);
    expect(wardrobeService.requestUploadUrl).toHaveBeenNthCalledWith(2, {
      itemId: 'item-1',
    });
    expect(mockCaptureException).not.toHaveBeenCalled();
  });

  it('retries with exponential backoff up to the max attempt count on a generic network failure, then fails', async () => {
    jest.useFakeTimers();
    try {
      (wardrobeService.requestUploadUrl as jest.Mock).mockResolvedValue(
        baseUploadUrlResponse,
      );
      (wardrobeService.uploadToR2WithProgress as jest.Mock).mockRejectedValue({
        code: 'network_error',
        message: 'No internet connection.',
        retryable: true,
      });

      useWardrobeUploadStore
        .getState()
        .startUpload('task-1', 'file://a.jpg', 'camera');
      const { result } = await renderHook(() => useUploadWardrobeItem(), {
        wrapper: createWrapper(),
      });
      result.current.mutate({
        taskId: 'task-1',
        localUri: 'file://a.jpg',
        source: 'camera',
      });

      // 3 total attempts -> 2 backoff sleeps (1s, then 2s).
      await act(async () => {
        await jest.advanceTimersByTimeAsync(1000);
      });
      await act(async () => {
        await jest.advanceTimersByTimeAsync(2000);
      });

      await waitFor(() => expect(result.current.isError).toBe(true));
      expect(wardrobeService.uploadToR2WithProgress).toHaveBeenCalledTimes(3);
      expect(mockCaptureException).toHaveBeenCalledTimes(1);
    } finally {
      jest.useRealTimers();
    }
  });

  it('surfaces a wardrobe_limit_reached error unchanged and immediately, with no retry loop', async () => {
    (wardrobeService.requestUploadUrl as jest.Mock).mockRejectedValue({
      code: 'wardrobe_limit_reached',
      message: 'Upgrade to premium',
      retryable: false,
    });

    useWardrobeUploadStore
      .getState()
      .startUpload('task-1', 'file://a.jpg', 'camera');
    const { result } = await renderHook(() => useUploadWardrobeItem(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({
      taskId: 'task-1',
      localUri: 'file://a.jpg',
      source: 'camera',
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toEqual({
      code: 'wardrobe_limit_reached',
      message: 'Upgrade to premium',
      retryable: false,
    });
    expect(wardrobeService.uploadToR2WithProgress).not.toHaveBeenCalled();
    expect(mockCaptureException).not.toHaveBeenCalled();
  });

  it('tracks ITEM_UPLOADED exactly once with the caller-supplied source on success', async () => {
    // existingItemCount >= 1 so this test isolates ITEM_UPLOADED from the
    // separate FIRST_ITEM_ADDED behaviour covered by the tests below.
    (wardrobeService.requestUploadUrl as jest.Mock).mockResolvedValue({
      ...baseUploadUrlResponse,
      existingItemCount: 3,
    });
    (wardrobeService.uploadToR2WithProgress as jest.Mock).mockResolvedValue(
      undefined,
    );

    useWardrobeUploadStore
      .getState()
      .startUpload('task-1', 'file://a.jpg', 'gallery');
    const { result } = await renderHook(() => useUploadWardrobeItem(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({
      taskId: 'task-1',
      localUri: 'file://a.jpg',
      source: 'gallery',
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockTrack).toHaveBeenCalledWith('item_uploaded', {
      source: 'gallery',
    });
    expect(mockTrack).toHaveBeenCalledTimes(1);
  });

  it('additionally tracks FIRST_ITEM_ADDED when the pre-upload item count was 0', async () => {
    (wardrobeService.requestUploadUrl as jest.Mock).mockResolvedValue({
      ...baseUploadUrlResponse,
      existingItemCount: 0,
    });
    (wardrobeService.uploadToR2WithProgress as jest.Mock).mockResolvedValue(
      undefined,
    );

    useWardrobeUploadStore
      .getState()
      .startUpload('task-1', 'file://a.jpg', 'camera');
    const { result } = await renderHook(() => useUploadWardrobeItem(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({
      taskId: 'task-1',
      localUri: 'file://a.jpg',
      source: 'camera',
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockTrack).toHaveBeenCalledWith('first_item_added');
  });

  it('does not track FIRST_ITEM_ADDED when the pre-upload item count was >= 1', async () => {
    (wardrobeService.requestUploadUrl as jest.Mock).mockResolvedValue({
      ...baseUploadUrlResponse,
      existingItemCount: 3,
    });
    (wardrobeService.uploadToR2WithProgress as jest.Mock).mockResolvedValue(
      undefined,
    );

    useWardrobeUploadStore
      .getState()
      .startUpload('task-1', 'file://a.jpg', 'camera');
    const { result } = await renderHook(() => useUploadWardrobeItem(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({
      taskId: 'task-1',
      localUri: 'file://a.jpg',
      source: 'camera',
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockTrack).not.toHaveBeenCalledWith('first_item_added');
  });

  it('calls Sentry.captureException exactly once (tagged) on a non-retryable invalid_file error', async () => {
    (wardrobeService.requestUploadUrl as jest.Mock).mockResolvedValue(
      baseUploadUrlResponse,
    );
    (wardrobeService.uploadToR2WithProgress as jest.Mock).mockRejectedValue({
      code: 'invalid_file',
      message: "This photo couldn't be uploaded.",
      retryable: false,
    });

    useWardrobeUploadStore
      .getState()
      .startUpload('task-1', 'file://a.jpg', 'camera');
    const { result } = await renderHook(() => useUploadWardrobeItem(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({
      taskId: 'task-1',
      localUri: 'file://a.jpg',
      source: 'camera',
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(mockCaptureException).toHaveBeenCalledTimes(1);
    expect(mockCaptureException).toHaveBeenCalledWith(
      expect.objectContaining({ code: 'invalid_file' }),
      expect.objectContaining({ tags: { feature: 'wardrobe_upload' } }),
    );
  });
});

describe('useProcessWardrobeItem', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('calls removeBackground then tagItem, in that order (awaits the first before firing the second)', async () => {
    const callOrder: string[] = [];
    (wardrobeService.removeBackground as jest.Mock).mockImplementation(
      async () => {
        callOrder.push('removeBackground');
      },
    );
    (wardrobeService.tagItem as jest.Mock).mockImplementation(async () => {
      callOrder.push('tagItem');
    });

    const { result } = await renderHook(() => useProcessWardrobeItem(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({ itemId: 'item-1', jwt: 'jwt-token' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(callOrder).toEqual(['removeBackground', 'tagItem']);
    expect(wardrobeService.removeBackground).toHaveBeenCalledWith(
      'item-1',
      'jwt-token',
    );
    expect(wardrobeService.tagItem).toHaveBeenCalledWith('item-1', 'jwt-token');
  });

  it('if removeBackground rejects, tagItem is never called', async () => {
    (wardrobeService.removeBackground as jest.Mock).mockRejectedValue({
      code: 'unknown',
      message: 'failed',
      retryable: true,
    });

    const { result } = await renderHook(() => useProcessWardrobeItem(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({ itemId: 'item-1', jwt: 'jwt-token' });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(wardrobeService.tagItem).not.toHaveBeenCalled();
  });
});

describe('useSaveWardrobeItemTags', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockEq.mockResolvedValue({ error: null });
    setFakeSession();
  });

  it('invalidates wardrobeItemsQueryKey/wardrobeItemCountQueryKey on success (SS-014 retrofit)', async () => {
    const { Wrapper, queryClient } = createWrapperWithClient();
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');

    const { result } = await renderHook(() => useSaveWardrobeItemTags(), {
      wrapper: Wrapper,
    });
    result.current.mutate({
      itemId: 'item-1',
      tags: {
        category: 'ethnic_kurta',
        subcategory: null,
        colorPrimary: null,
        colorSecondary: null,
        pattern: null,
        fabric: null,
        occasionTags: [],
        seasonTags: [],
        confidence: 0.9,
        contentFlag: 'ok',
        containsPerson: false,
      },
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: wardrobeItemsQueryKey(FAKE_USER_ID),
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: wardrobeItemCountQueryKey(FAKE_USER_ID),
    });
  });

  it('issues a scoped .update() against wardrobe_items for the given itemId with exactly the edited fields', async () => {
    const tags = {
      category: 'ethnic_kurta' as const,
      subcategory: 'kurta',
      colorPrimary: 'blue',
      colorSecondary: null,
      pattern: 'solid',
      fabric: 'cotton',
      occasionTags: ['festival' as const],
      seasonTags: ['summer' as const],
      confidence: 0.9,
      contentFlag: 'ok' as const,
      containsPerson: false,
    };

    const { result } = await renderHook(() => useSaveWardrobeItemTags(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({ itemId: 'item-1', tags });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockFrom).toHaveBeenCalledWith('wardrobe_items');
    expect(mockUpdate).toHaveBeenCalledWith({
      category: 'ethnic_kurta',
      subcategory: 'kurta',
      color_primary: 'blue',
      color_secondary: null,
      pattern: 'solid',
      fabric: 'cotton',
      occasion_tags: ['festival'],
      season_tags: ['summer'],
    });
    expect(mockEq).toHaveBeenCalledWith('id', 'item-1');
  });
});

// --- SS-014 additions ---------------------------------------------------

describe('useWardrobeItemsQuery / useWardrobeItemCountQuery', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('useWardrobeItemsQuery calls fetchWardrobeItems, keyed by userId', async () => {
    (wardrobeService.fetchWardrobeItems as jest.Mock).mockResolvedValue([
      { id: 'item-1' },
    ]);

    const { result } = await renderHook(() => useWardrobeItemsQuery('user-1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(wardrobeService.fetchWardrobeItems).toHaveBeenCalled();
    expect(result.current.data).toEqual([{ id: 'item-1' }]);
  });

  it('useWardrobeItemsQuery does not fire when userId is undefined', async () => {
    const { result } = await renderHook(
      () => useWardrobeItemsQuery(undefined),
      { wrapper: createWrapper() },
    );

    expect(result.current.fetchStatus).toBe('idle');
    expect(wardrobeService.fetchWardrobeItems).not.toHaveBeenCalled();
  });

  it('useWardrobeItemCountQuery calls fetchWardrobeItemCount, keyed by userId', async () => {
    (wardrobeService.fetchWardrobeItemCount as jest.Mock).mockResolvedValue(3);

    const { result } = await renderHook(
      () => useWardrobeItemCountQuery('user-1'),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(wardrobeService.fetchWardrobeItemCount).toHaveBeenCalled();
    expect(result.current.data).toBe(3);
  });
});

describe('useWardrobeItemImageUrlsQuery', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('calls the bulk service function with all provided ids', async () => {
    const urls = {
      'item-1': { url: 'https://signed/1', source: 'thumbnail' as const },
    };
    (wardrobeService.fetchWardrobeItemImageUrls as jest.Mock).mockResolvedValue(
      urls,
    );

    const { result } = await renderHook(
      () =>
        useWardrobeItemImageUrlsQuery('user-1', ['item-1', 'item-2'], 'jwt'),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(wardrobeService.fetchWardrobeItemImageUrls).toHaveBeenCalledWith(
      ['item-1', 'item-2'],
      'jwt',
    );
    expect(result.current.data).toEqual(urls);
  });

  it('is disabled when itemIds is empty', async () => {
    const { result } = await renderHook(
      () => useWardrobeItemImageUrlsQuery('user-1', [], 'jwt'),
      { wrapper: createWrapper() },
    );

    expect(result.current.fetchStatus).toBe('idle');
    expect(wardrobeService.fetchWardrobeItemImageUrls).not.toHaveBeenCalled();
  });
});

describe('useToggleWardrobeItemFavourite / useMarkWardrobeItemWorn / useDeleteWardrobeItem', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    setFakeSession();
  });

  it('useToggleWardrobeItemFavourite calls through and invalidates the grid queries on success', async () => {
    (
      wardrobeService.toggleWardrobeItemFavourite as jest.Mock
    ).mockResolvedValue(undefined);
    const { Wrapper, queryClient } = createWrapperWithClient();
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');

    const { result } = await renderHook(
      () => useToggleWardrobeItemFavourite(),
      {
        wrapper: Wrapper,
      },
    );
    result.current.mutate({ itemId: 'item-1', isFavourite: true });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(wardrobeService.toggleWardrobeItemFavourite).toHaveBeenCalledWith(
      'item-1',
      true,
    );
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: wardrobeItemsQueryKey(FAKE_USER_ID),
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: wardrobeItemCountQueryKey(FAKE_USER_ID),
    });
  });

  it('useMarkWardrobeItemWorn calls through and invalidates the grid queries on success', async () => {
    (wardrobeService.markWardrobeItemWorn as jest.Mock).mockResolvedValue(
      undefined,
    );
    const { Wrapper, queryClient } = createWrapperWithClient();
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');

    const { result } = await renderHook(() => useMarkWardrobeItemWorn(), {
      wrapper: Wrapper,
    });
    result.current.mutate({ itemId: 'item-1', nextWearCount: 4 });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(wardrobeService.markWardrobeItemWorn).toHaveBeenCalledWith(
      'item-1',
      4,
    );
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: wardrobeItemsQueryKey(FAKE_USER_ID),
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: wardrobeItemCountQueryKey(FAKE_USER_ID),
    });
  });

  it('useDeleteWardrobeItem calls through and invalidates the grid queries on success', async () => {
    (wardrobeService.deleteWardrobeItem as jest.Mock).mockResolvedValue(
      undefined,
    );
    const { Wrapper, queryClient } = createWrapperWithClient();
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');

    const { result } = await renderHook(() => useDeleteWardrobeItem(), {
      wrapper: Wrapper,
    });
    result.current.mutate({ itemId: 'item-1' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(wardrobeService.deleteWardrobeItem).toHaveBeenCalledWith('item-1');
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: wardrobeItemsQueryKey(FAKE_USER_ID),
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: wardrobeItemCountQueryKey(FAKE_USER_ID),
    });
  });
});
