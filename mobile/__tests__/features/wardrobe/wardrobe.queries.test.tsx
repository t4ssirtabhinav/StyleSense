import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { useUploadWardrobeItem } from '../../../features/wardrobe/wardrobe.queries';
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
}));

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
