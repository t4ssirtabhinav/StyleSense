import {
  COMPRESS_QUALITY_FLOOR,
  MAX_UPLOAD_WIDTH,
} from '../../../features/wardrobe/wardrobe.constants';
import {
  compressImageForUpload,
  computeBatchDedupeHash,
  removeBackground,
  requestUploadUrl,
  subscribeToItemUpdates,
  tagItem,
  uploadToR2WithProgress,
} from '../../../features/wardrobe/wardrobe.service';

const mockManipulateAsync = jest.fn();
jest.mock('expo-image-manipulator', () => ({
  manipulateAsync: (...args: unknown[]) => mockManipulateAsync(...args),
  SaveFormat: { JPEG: 'jpeg' },
}));

const mockDigestStringAsync = jest.fn();
jest.mock('expo-crypto', () => ({
  digestStringAsync: (...args: unknown[]) => mockDigestStringAsync(...args),
  CryptoDigestAlgorithm: { SHA256: 'SHA-256' },
}));

const mockInvoke = jest.fn();
const mockOn = jest.fn();
const mockSubscribe = jest.fn();
const mockChannel = jest.fn();
const mockRemoveChannel = jest.fn();
jest.mock('../../../lib/supabase', () => ({
  supabase: {
    functions: { invoke: (...args: unknown[]) => mockInvoke(...args) },
    channel: (...args: unknown[]) => mockChannel(...args),
    removeChannel: (...args: unknown[]) => mockRemoveChannel(...args),
  },
}));

function mockBlob(size: number): Blob {
  return { size } as Blob;
}

describe('compressImageForUpload', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // biome-ignore lint/suspicious/noExplicitAny: test-only global stub
    (global as any).fetch = jest.fn();
  });

  it('calls manipulateAsync with resize.width 1200 and JPEG SaveFormat', async () => {
    mockManipulateAsync.mockResolvedValue({ uri: 'file://out.jpg' });
    (global.fetch as jest.Mock).mockResolvedValue({
      blob: () => Promise.resolve(mockBlob(500_000)),
    });

    await compressImageForUpload('file://in.jpg');

    expect(mockManipulateAsync).toHaveBeenCalledWith(
      'file://in.jpg',
      [{ resize: { width: MAX_UPLOAD_WIDTH } }],
      { compress: 0.8, format: 'jpeg' },
    );
  });

  it('re-invokes with a lower compress value when the output exceeds 2MB, stopping at the 0.5 floor', async () => {
    mockManipulateAsync.mockResolvedValue({ uri: 'file://out.jpg' });
    const bigBlob = mockBlob(3_000_000);
    const smallBlob = mockBlob(1_000_000);
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce({ blob: () => Promise.resolve(bigBlob) }) // 0.8
      .mockResolvedValueOnce({ blob: () => Promise.resolve(bigBlob) }) // 0.7
      .mockResolvedValueOnce({ blob: () => Promise.resolve(bigBlob) }) // 0.6
      .mockResolvedValueOnce({ blob: () => Promise.resolve(smallBlob) }); // 0.5 -> under 2MB, stop

    const result = await compressImageForUpload('file://in.jpg');

    expect(mockManipulateAsync).toHaveBeenCalledTimes(4);
    expect(mockManipulateAsync).toHaveBeenLastCalledWith(
      'file://in.jpg',
      [{ resize: { width: MAX_UPLOAD_WIDTH } }],
      { compress: COMPRESS_QUALITY_FLOOR, format: 'jpeg' },
    );
    expect(result.size).toBe(1_000_000);
  });

  it('stops re-invoking once the 0.5 floor is reached even if still over 2MB', async () => {
    mockManipulateAsync.mockResolvedValue({ uri: 'file://out.jpg' });
    const bigBlob = mockBlob(5_000_000);
    (global.fetch as jest.Mock).mockResolvedValue({
      blob: () => Promise.resolve(bigBlob),
    });

    const result = await compressImageForUpload('file://in.jpg');

    // 0.8, 0.7, 0.6, 0.5 -> 4 calls total, then the loop stops (quality is no
    // longer > the floor) even though the blob is still over 2MB.
    expect(mockManipulateAsync).toHaveBeenCalledTimes(4);
    expect(result.size).toBe(5_000_000);
  });
});

describe('requestUploadUrl', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("calls supabase.functions.invoke('get-upload-url', ...) and returns the typed UploadUrlResponse", async () => {
    const response = {
      uploadUrl: 'https://r2.example.com/signed',
      itemId: 'item-1',
      key: 'wardrobe/user-1/item-1/original.jpg',
      expiresAt: '2026-01-01T00:05:00.000Z',
      contentType: 'image/jpeg' as const,
      existingItemCount: 0,
    };
    mockInvoke.mockResolvedValue({ data: response, error: null });

    const result = await requestUploadUrl({});

    expect(mockInvoke).toHaveBeenCalledWith('get-upload-url', { body: {} });
    expect(result).toEqual(response);
  });

  it('maps a 403 wardrobe_limit_reached function response into a typed, non-retryable WardrobeUploadError', async () => {
    const upgradeMessage =
      "You've reached the free plan's 50-item wardrobe limit. Upgrade to premium for unlimited items.";
    mockInvoke.mockResolvedValue({
      data: null,
      error: {
        context: {
          status: 403,
          json: () =>
            Promise.resolve({
              code: 'wardrobe_limit_reached',
              message: upgradeMessage,
            }),
        },
      },
    });

    await expect(requestUploadUrl({})).rejects.toEqual({
      code: 'wardrobe_limit_reached',
      message: upgradeMessage,
      retryable: false,
    });
  });
});

class FakeXHR {
  static instances: FakeXHR[] = [];
  status = 0;
  upload: { onprogress?: (event: ProgressEvent) => void } = {};
  onload?: () => void;
  onerror?: () => void;
  open = jest.fn();
  setRequestHeader = jest.fn();
  send = jest.fn();

  constructor() {
    FakeXHR.instances.push(this);
  }
}

describe('uploadToR2WithProgress', () => {
  beforeEach(() => {
    FakeXHR.instances = [];
    // biome-ignore lint/suspicious/noExplicitAny: test-only global stub
    (global as any).XMLHttpRequest = FakeXHR;
  });

  it('opens a raw-body PUT (not a FormData POST) with the given Content-Type, resolves on 200, and reports increasing progress', async () => {
    const onProgress = jest.fn();
    const blob = { size: 1000 } as Blob;
    const promise = uploadToR2WithProgress(
      'https://r2.example.com/signed',
      blob,
      'image/jpeg',
      onProgress,
    );

    const xhr = FakeXHR.instances[0];
    expect(xhr.open).toHaveBeenCalledWith(
      'PUT',
      'https://r2.example.com/signed',
      true,
    );
    expect(xhr.setRequestHeader).toHaveBeenCalledWith(
      'Content-Type',
      'image/jpeg',
    );

    xhr.upload.onprogress?.({
      lengthComputable: true,
      loaded: 50,
      total: 100,
    } as ProgressEvent);
    xhr.upload.onprogress?.({
      lengthComputable: true,
      loaded: 100,
      total: 100,
    } as ProgressEvent);

    xhr.status = 200;
    xhr.onload?.();

    await expect(promise).resolves.toBeUndefined();
    expect(onProgress).toHaveBeenNthCalledWith(1, 50);
    expect(onProgress).toHaveBeenNthCalledWith(2, 100);
    expect(xhr.send).toHaveBeenCalledWith(blob);
  });

  it('rejects with a retryable network_error on xhr.onerror', async () => {
    const blob = { size: 1000 } as Blob;
    const promise = uploadToR2WithProgress(
      'https://r2.example.com/signed',
      blob,
      'image/jpeg',
    );
    const xhr = FakeXHR.instances[0];
    xhr.onerror?.();

    await expect(promise).rejects.toEqual(
      expect.objectContaining({ code: 'network_error', retryable: true }),
    );
  });

  it('detects HTTP 403 specifically in onload and rejects with a distinct expired-url error', async () => {
    const blob = { size: 1000 } as Blob;
    const promise = uploadToR2WithProgress(
      'https://r2.example.com/signed',
      blob,
      'image/jpeg',
    );
    const xhr = FakeXHR.instances[0];
    xhr.status = 403;
    xhr.onload?.();

    await expect(promise).rejects.toEqual(
      expect.objectContaining({ code: 'expired_url' }),
    );
  });

  it('detects a policy-violation 400 in onload and rejects with a non-retryable invalid_file error', async () => {
    const blob = { size: 1000 } as Blob;
    const promise = uploadToR2WithProgress(
      'https://r2.example.com/signed',
      blob,
      'image/jpeg',
    );
    const xhr = FakeXHR.instances[0];
    xhr.status = 400;
    xhr.onload?.();

    await expect(promise).rejects.toEqual(
      expect.objectContaining({ code: 'invalid_file', retryable: false }),
    );
  });
});

describe('computeBatchDedupeHash', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('returns identical hashes for identical compressed-image bytes', async () => {
    mockDigestStringAsync.mockImplementation((_alg: string, data: string) =>
      Promise.resolve(`hash-of-${data}`),
    );

    const first = await computeBatchDedupeHash('same-base64-bytes');
    const second = await computeBatchDedupeHash('same-base64-bytes');

    expect(first).toBe(second);
    expect(mockDigestStringAsync).toHaveBeenCalledWith(
      'SHA-256',
      'same-base64-bytes',
    );
  });
});

describe('removeBackground / tagItem', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // biome-ignore lint/suspicious/noExplicitAny: test-only global stub
    (global as any).fetch = jest.fn();
  });

  it('removeBackground POSTs to /wardrobe/remove-bg with { item_id } and the bearer token, expects 202', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({ status: 202 });

    await removeBackground('item-1', 'jwt-token');

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/wardrobe/remove-bg'),
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ Authorization: 'Bearer jwt-token' }),
        body: JSON.stringify({ item_id: 'item-1' }),
      }),
    );
  });

  it('removeBackground throws when the response is not 202', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({ status: 500 });

    await expect(removeBackground('item-1', 'jwt-token')).rejects.toEqual(
      expect.objectContaining({ code: 'unknown' }),
    );
  });

  it('tagItem POSTs to /wardrobe/tag with the same shape', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({ status: 202 });

    await tagItem('item-1', 'jwt-token');

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/wardrobe/tag'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ item_id: 'item-1' }),
      }),
    );
  });
});

describe('subscribeToItemUpdates', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockChannel.mockReturnValue({ on: mockOn });
    mockOn.mockReturnValue({ subscribe: mockSubscribe });
    mockSubscribe.mockReturnValue('the-channel');
  });

  it('subscribes with filter id=eq.{itemId} on wardrobe_items and invokes the callback on an UPDATE payload', () => {
    const onUpdate = jest.fn();
    subscribeToItemUpdates('item-1', onUpdate);

    expect(mockChannel).toHaveBeenCalledWith('wardrobe_item_item-1');
    expect(mockOn).toHaveBeenCalledWith(
      'postgres_changes',
      expect.objectContaining({
        event: 'UPDATE',
        schema: 'public',
        table: 'wardrobe_items',
        filter: 'id=eq.item-1',
      }),
      expect.any(Function),
    );

    const handler = mockOn.mock.calls[0][2];
    handler({ new: { id: 'item-1', processing_status: 'bg_removed' } });
    expect(onUpdate).toHaveBeenCalledWith({
      id: 'item-1',
      processing_status: 'bg_removed',
    });
  });

  it('returns an unsubscribe function that removes the channel', () => {
    const unsubscribe = subscribeToItemUpdates('item-1', jest.fn());
    unsubscribe();

    expect(mockRemoveChannel).toHaveBeenCalledWith('the-channel');
  });
});
