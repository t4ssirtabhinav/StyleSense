import {
  COMPRESS_QUALITY_FLOOR,
  MAX_UPLOAD_WIDTH,
} from '../../../features/wardrobe/wardrobe.constants';
import {
  compressImageForUpload,
  computeBatchDedupeHash,
  deleteWardrobeItem,
  deleteWardrobeItemWear,
  fetchWardrobeItemCount,
  fetchWardrobeItemImageUrls,
  fetchWardrobeItemWearStats,
  fetchWardrobeItemWears,
  fetchWardrobeItems,
  logWardrobeItemWear,
  mapRealtimeRowToTagsDraft,
  normalizeOccasionTagsForWrite,
  removeBackground,
  requestUploadUrl,
  saveWardrobeItemDetails,
  saveWardrobeItemTags,
  subscribeToItemUpdates,
  tagItem,
  toggleWardrobeItemFavourite,
  updateWardrobeItemWear,
  uploadToR2WithProgress,
} from '../../../features/wardrobe/wardrobe.service';
import type { WardrobeItemRealtimeRow } from '../../../features/wardrobe/wardrobe.types';

// (SS-025) The occasion vocabulary the write path normalises against comes
// from lib/storage.ts's last-known-good cache, not a network call.
const mockReadCachedTaxonomies = jest.fn();
jest.mock('../../../lib/storage', () => ({
  readCachedTaxonomies: () => mockReadCachedTaxonomies(),
  writeCachedTaxonomies: jest.fn(),
}));

const CACHED_TAXONOMIES = {
  styleKeywords: [],
  colourPalette: [],
  isStale: false,
  occasionAliases: [
    { alias: 'wedding', occasionKey: 'wedding_guest' },
    { alias: 'date', occasionKey: 'date_night' },
  ],
  occasions: [
    'casual',
    'festival',
    'puja',
    'travel',
    'wedding_guest',
    'date_night',
  ].map((key, index) => ({
    key,
    label: key,
    sortOrder: index + 1,
    badgeColor: 'casual' as const,
    kind: 'everyday',
    parentKey: null,
    regionScope: null,
    cultureScope: null,
  })),
};

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
const mockOrder = jest.fn();
const mockSelect = jest.fn();
const mockEq = jest.fn();
const mockSingle = jest.fn();
const mockUpsertSelect = jest.fn();
const mockUpdate = jest.fn((..._args: unknown[]) => ({ eq: mockEq }));
const mockDelete = jest.fn((..._args: unknown[]) => ({ eq: mockEq }));
const mockUpsert = jest.fn((..._args: unknown[]) => ({
  select: mockUpsertSelect,
}));
const mockFrom = jest.fn((..._args: unknown[]) => ({
  select: mockSelect,
  update: mockUpdate,
  delete: mockDelete,
  upsert: mockUpsert,
}));
jest.mock('../../../lib/supabase', () => ({
  supabase: {
    functions: { invoke: (...args: unknown[]) => mockInvoke(...args) },
    channel: (...args: unknown[]) => mockChannel(...args),
    removeChannel: (...args: unknown[]) => mockRemoveChannel(...args),
    from: (...args: unknown[]) => mockFrom(...args),
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

describe('mapRealtimeRowToTagsDraft', () => {
  it('maps every tag column plus confidence/alternatives/contentFlag/containsPerson from a fully-populated row', () => {
    const row: WardrobeItemRealtimeRow = {
      id: 'item-1',
      processing_status: 'bg_removed',
      category: 'ethnic_saree',
      subcategory: 'silk saree',
      color_primary: 'red',
      color_secondary: 'gold',
      pattern: 'floral',
      fabric: 'silk',
      occasion_tags: ['festival', 'wedding_guest'],
      season_tags: ['winter'],
      ai_tags: {
        tagging: {
          status: 'tagged',
          confidence: 0.92,
          alternatives: ['ethnic_lehenga'],
          moderation: { content_flag: 'ok', contains_person: true },
        },
      },
    };

    expect(mapRealtimeRowToTagsDraft(row)).toEqual({
      category: 'ethnic_saree',
      subcategory: 'silk saree',
      colorPrimary: 'red',
      colorSecondary: 'gold',
      pattern: 'floral',
      fabric: 'silk',
      occasionTags: ['festival', 'wedding_guest'],
      seasonTags: ['winter'],
      confidence: 0.92,
      alternatives: ['ethnic_lehenga'],
      contentFlag: 'ok',
      containsPerson: true,
    });
  });

  it('defaults occasionTags/seasonTags to [] and confidence/contentFlag/containsPerson to DEFAULT_TAGS_DRAFT-equivalent values when ai_tags.tagging is absent', () => {
    const row: WardrobeItemRealtimeRow = {
      id: 'item-1',
      processing_status: 'bg_removed',
      category: null,
      subcategory: null,
      color_primary: null,
      color_secondary: null,
      pattern: null,
      fabric: null,
      occasion_tags: null,
      season_tags: null,
      ai_tags: null,
    };

    expect(mapRealtimeRowToTagsDraft(row)).toEqual({
      category: null,
      subcategory: null,
      colorPrimary: null,
      colorSecondary: null,
      pattern: null,
      fabric: null,
      occasionTags: [],
      seasonTags: [],
      confidence: 1,
      alternatives: undefined,
      contentFlag: 'ok',
      containsPerson: false,
    });
  });
});

// --- SS-014 additions --------------------------------------------------

describe('fetchWardrobeItems', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('selects * from wardrobe_items ordered by created_at descending', async () => {
    const rows = [{ id: 'item-1' }, { id: 'item-2' }];
    mockSelect.mockReturnValue({ order: mockOrder });
    mockOrder.mockResolvedValue({ data: rows, error: null });

    const result = await fetchWardrobeItems();

    expect(mockFrom).toHaveBeenCalledWith('wardrobe_items');
    expect(mockSelect).toHaveBeenCalledWith('*');
    expect(mockOrder).toHaveBeenCalledWith('created_at', { ascending: false });
    expect(result).toEqual(rows);
  });

  it('throws the raw Supabase error on failure', async () => {
    mockSelect.mockReturnValue({ order: mockOrder });
    mockOrder.mockResolvedValue({ data: null, error: new Error('boom') });

    await expect(fetchWardrobeItems()).rejects.toThrow('boom');
  });
});

describe('fetchWardrobeItemCount', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('selects id with count:exact, head:true from wardrobe_items', async () => {
    mockSelect.mockResolvedValue({ count: 7, error: null });

    const result = await fetchWardrobeItemCount();

    expect(mockFrom).toHaveBeenCalledWith('wardrobe_items');
    expect(mockSelect).toHaveBeenCalledWith('id', {
      count: 'exact',
      head: true,
    });
    expect(result).toBe(7);
  });

  it('returns 0 when count is null', async () => {
    mockSelect.mockResolvedValue({ count: null, error: null });

    const result = await fetchWardrobeItemCount();

    expect(result).toBe(0);
  });
});

describe('fetchWardrobeItemImageUrls', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // biome-ignore lint/suspicious/noExplicitAny: test-only global stub
    (global as any).fetch = jest.fn();
  });

  it('POSTs to /wardrobe/items/image-urls with { item_ids } and returns the urls map', async () => {
    const urls = {
      'item-1': { url: 'https://signed/1', source: 'thumbnail' as const },
    };
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ urls }),
    });

    const result = await fetchWardrobeItemImageUrls(['item-1'], 'jwt-token');

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/wardrobe/items/image-urls'),
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ Authorization: 'Bearer jwt-token' }),
        body: JSON.stringify({ item_ids: ['item-1'] }),
      }),
    );
    expect(result).toEqual(urls);
  });

  it('throws when the response is not ok', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({ ok: false });

    await expect(
      fetchWardrobeItemImageUrls(['item-1'], 'jwt-token'),
    ).rejects.toEqual(expect.objectContaining({ code: 'unknown' }));
  });
});

describe('toggleWardrobeItemFavourite', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockEq.mockResolvedValue({ error: null });
  });

  it('updates is_favourite for the given item id', async () => {
    await toggleWardrobeItemFavourite('item-1', true);

    expect(mockFrom).toHaveBeenCalledWith('wardrobe_items');
    expect(mockUpdate).toHaveBeenCalledWith({ is_favourite: true });
    expect(mockEq).toHaveBeenCalledWith('id', 'item-1');
  });
});

// --- SS-015 additions -------------------------------------------------

describe('deleteWardrobeItem', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // biome-ignore lint/suspicious/noExplicitAny: test-only global stub
    (global as any).fetch = jest.fn();
  });

  it('DELETEs to /wardrobe/items/{id} with the bearer token', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({ ok: true });

    await deleteWardrobeItem('item-1', 'jwt-token');

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/wardrobe/items/item-1'),
      expect.objectContaining({
        method: 'DELETE',
        headers: expect.objectContaining({ Authorization: 'Bearer jwt-token' }),
      }),
    );
  });

  it('throws when the response is not ok', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({ ok: false });

    await expect(deleteWardrobeItem('item-1', 'jwt-token')).rejects.toEqual(
      expect.objectContaining({ code: 'unknown' }),
    );
  });
});

describe('fetchWardrobeItemWears', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('selects * from wardrobe_item_wears for the item, newest first', async () => {
    const rows = [{ id: 'wear-2' }, { id: 'wear-1' }];
    mockSelect.mockReturnValue({ eq: mockEq });
    mockEq.mockReturnValue({ order: mockOrder });
    mockOrder.mockResolvedValue({ data: rows, error: null });

    const result = await fetchWardrobeItemWears('item-1');

    expect(mockFrom).toHaveBeenCalledWith('wardrobe_item_wears');
    expect(mockSelect).toHaveBeenCalledWith('*');
    expect(mockEq).toHaveBeenCalledWith('item_id', 'item-1');
    expect(mockOrder).toHaveBeenCalledWith('worn_on', { ascending: false });
    expect(result).toEqual(rows);
  });

  it('throws the raw Supabase error on failure', async () => {
    mockSelect.mockReturnValue({ eq: mockEq });
    mockEq.mockReturnValue({ order: mockOrder });
    mockOrder.mockResolvedValue({ data: null, error: new Error('boom') });

    await expect(fetchWardrobeItemWears('item-1')).rejects.toThrow('boom');
  });
});

describe('logWardrobeItemWear', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('upserts item_id/user_id/worn_on with ignoreDuplicates on the (item_id, worn_on) unique index', async () => {
    mockUpsertSelect.mockResolvedValue({
      data: [{ id: 'wear-1' }],
      error: null,
    });

    const result = await logWardrobeItemWear('item-1', 'user-1', '2026-07-27');

    expect(mockFrom).toHaveBeenCalledWith('wardrobe_item_wears');
    expect(mockUpsert).toHaveBeenCalledWith(
      { item_id: 'item-1', user_id: 'user-1', worn_on: '2026-07-27' },
      { onConflict: 'item_id,worn_on', ignoreDuplicates: true },
    );
    expect(result).toEqual({ alreadyLogged: false });
  });

  it('reports alreadyLogged=true when the conflict was ignored (empty returned data)', async () => {
    mockUpsertSelect.mockResolvedValue({ data: [], error: null });

    const result = await logWardrobeItemWear('item-1', 'user-1', '2026-07-27');

    expect(result).toEqual({ alreadyLogged: true });
  });

  it('throws the raw Supabase error on failure', async () => {
    mockUpsertSelect.mockResolvedValue({
      data: null,
      error: new Error('boom'),
    });

    await expect(
      logWardrobeItemWear('item-1', 'user-1', '2026-07-27'),
    ).rejects.toThrow('boom');
  });
});

describe('updateWardrobeItemWear', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockEq.mockResolvedValue({ error: null });
  });

  it('updates worn_on for the given wear id', async () => {
    await updateWardrobeItemWear('wear-1', '2026-07-20');

    expect(mockFrom).toHaveBeenCalledWith('wardrobe_item_wears');
    expect(mockUpdate).toHaveBeenCalledWith({ worn_on: '2026-07-20' });
    expect(mockEq).toHaveBeenCalledWith('id', 'wear-1');
  });
});

describe('deleteWardrobeItemWear', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockEq.mockResolvedValue({ error: null });
  });

  it('deletes the row scoped to the given wear id', async () => {
    await deleteWardrobeItemWear('wear-1');

    expect(mockFrom).toHaveBeenCalledWith('wardrobe_item_wears');
    expect(mockDelete).toHaveBeenCalled();
    expect(mockEq).toHaveBeenCalledWith('id', 'wear-1');
  });
});

describe('fetchWardrobeItemWearStats', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('reads back wear_count/cost_per_wear for the given item id', async () => {
    mockSelect.mockReturnValue({ eq: mockEq });
    mockEq.mockReturnValue({ single: mockSingle });
    mockSingle.mockResolvedValue({
      data: { wear_count: 4, cost_per_wear: 250 },
      error: null,
    });

    const result = await fetchWardrobeItemWearStats('item-1');

    expect(mockFrom).toHaveBeenCalledWith('wardrobe_items');
    expect(mockSelect).toHaveBeenCalledWith('wear_count, cost_per_wear');
    expect(mockEq).toHaveBeenCalledWith('id', 'item-1');
    expect(result).toEqual({ wearCount: 4, costPerWear: 250 });
  });

  it('throws the raw Supabase error on failure', async () => {
    mockSelect.mockReturnValue({ eq: mockEq });
    mockEq.mockReturnValue({ single: mockSingle });
    mockSingle.mockResolvedValue({ data: null, error: new Error('boom') });

    await expect(fetchWardrobeItemWearStats('item-1')).rejects.toThrow('boom');
  });
});

describe('saveWardrobeItemDetails', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockEq.mockResolvedValue({ error: null });
  });

  it('updates exactly brand/purchase_price/purchase_date/user_notes', async () => {
    await saveWardrobeItemDetails('item-1', {
      brand: "Levi's",
      purchasePrice: 2500,
      purchaseDate: '2026-01-01',
      userNotes: 'Gift from mom',
    });

    expect(mockFrom).toHaveBeenCalledWith('wardrobe_items');
    expect(mockUpdate).toHaveBeenCalledWith({
      brand: "Levi's",
      purchase_price: 2500,
      purchase_date: '2026-01-01',
      user_notes: 'Gift from mom',
    });
    expect(mockEq).toHaveBeenCalledWith('id', 'item-1');
  });
});

// --- SS-025 (Occasion Taxonomy & Extensibility Migration) -----------------

describe('saveWardrobeItemTags — occasion normalisation at the write boundary', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockEq.mockResolvedValue({ error: null });
    mockReadCachedTaxonomies.mockResolvedValue({
      version: 1,
      fetchedAt: '2026-07-28T00:00:00.000Z',
      payload: CACHED_TAXONOMIES,
    });
  });

  function draft(occasionTags: string[]) {
    return {
      category: 'ethnic_kurta' as const,
      subcategory: 'kurta',
      colorPrimary: 'blue',
      colorSecondary: null,
      pattern: 'solid',
      fabric: 'cotton',
      occasionTags,
      seasonTags: ['summer' as const],
      confidence: 0.9,
      contentFlag: 'ok' as const,
      containsPerson: false,
    };
  }

  it('writes exactly the 8 tag columns, scoped to the item id', async () => {
    await saveWardrobeItemTags('item-1', draft(['festival']));

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

  it('normalises and dedupes occasion slugs BEFORE the Supabase call', async () => {
    await saveWardrobeItemTags(
      'item-1',
      draft(['  Wedding Guest ', 'wedding', 'Travel', 'travel']),
    );

    // 'wedding' aliases onto wedding_guest and dedupes away; first-occurrence
    // order preserved, never sorted.
    expect(
      (mockUpdate.mock.calls[0][0] as { occasion_tags: string[] })
        .occasion_tags,
    ).toEqual(['wedding_guest', 'travel']);
  });

  it('keeps an unknown slug rather than dropping it on save', async () => {
    await saveWardrobeItemTags('item-1', draft(['Ganesh Chaturthi', 'puja']));

    expect(
      (mockUpdate.mock.calls[0][0] as { occasion_tags: string[] })
        .occasion_tags,
    ).toEqual(['ganesh_chaturthi', 'puja']);
  });

  it('degrades to shape-only normalisation when the taxonomy cache is empty', async () => {
    mockReadCachedTaxonomies.mockResolvedValue(null);

    await saveWardrobeItemTags('item-1', draft(['  Wedding Guest ']));

    // The DB trigger completes the alias mapping; the write still happens.
    expect(
      (mockUpdate.mock.calls[0][0] as { occasion_tags: string[] })
        .occasion_tags,
    ).toEqual(['wedding_guest']);
  });

  it('throws the raw Supabase error on failure', async () => {
    mockEq.mockResolvedValue({ error: new Error('boom') });

    await expect(
      saveWardrobeItemTags('item-1', draft(['casual'])),
    ).rejects.toThrow('boom');
  });
});

describe('normalizeOccasionTagsForWrite', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockReadCachedTaxonomies.mockResolvedValue({
      version: 1,
      fetchedAt: '2026-07-28T00:00:00.000Z',
      payload: CACHED_TAXONOMIES,
    });
  });

  it('returns an empty array for an empty input', async () => {
    await expect(normalizeOccasionTagsForWrite([])).resolves.toEqual([]);
  });

  it('drops entries that normalise to nothing', async () => {
    await expect(
      normalizeOccasionTagsForWrite(['', '   ', '!!!', 'casual']),
    ).resolves.toEqual(['casual']);
  });
});
