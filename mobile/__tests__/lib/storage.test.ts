/**
 * SS-025 — last-known-good taxonomy cache (design doc §6.5).
 *
 * Every function here must be TOTAL: a corrupt, absent or version-mismatched
 * entry is a cache MISS, never a throw. A storage failure must not be able to
 * break a screen that would otherwise have rendered from the network.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import type { OnboardingTaxonomies } from '../../features/onboarding/onboarding.types';
import {
  TAXONOMY_CACHE_KEY,
  TAXONOMY_CACHE_VERSION,
  clearCachedTaxonomies,
  readCachedTaxonomies,
  writeCachedTaxonomies,
} from '../../lib/storage';

jest.mock('@react-native-async-storage/async-storage', () => ({
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn(),
}));

const mockGetItem = AsyncStorage.getItem as jest.Mock;
const mockSetItem = AsyncStorage.setItem as jest.Mock;
const mockRemoveItem = AsyncStorage.removeItem as jest.Mock;

const PAYLOAD: OnboardingTaxonomies = {
  styleKeywords: [{ key: 'ethnic', label: 'Ethnic', sortOrder: 1 }],
  occasions: [
    {
      key: 'office',
      label: 'Office',
      sortOrder: 1,
      badgeColor: 'office',
      kind: 'professional',
      parentKey: null,
      regionScope: null,
      cultureScope: null,
    },
  ],
  occasionAliases: [{ alias: 'wedding', occasionKey: 'wedding_guest' }],
  colourPalette: [
    { key: 'black', label: 'Black', hex: '#000000', sortOrder: 1 },
  ],
  isStale: false,
};

describe('taxonomy cache', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSetItem.mockResolvedValue(undefined);
    mockRemoveItem.mockResolvedValue(undefined);
  });

  it('round-trips a payload under the versioned key', async () => {
    await writeCachedTaxonomies(PAYLOAD);

    expect(mockSetItem).toHaveBeenCalledTimes(1);
    const [key, serialised] = mockSetItem.mock.calls[0];
    expect(key).toBe(TAXONOMY_CACHE_KEY);

    const entry = JSON.parse(serialised);
    expect(entry.version).toBe(TAXONOMY_CACHE_VERSION);
    expect(typeof entry.fetchedAt).toBe('string');

    mockGetItem.mockResolvedValue(serialised);
    const cached = await readCachedTaxonomies();
    expect(cached?.payload.occasions[0].key).toBe('office');
    expect(cached?.payload.occasionAliases[0].alias).toBe('wedding');
  });

  it('never persists isStale=true (staleness is a per-read marker)', async () => {
    await writeCachedTaxonomies({ ...PAYLOAD, isStale: true });
    const entry = JSON.parse(mockSetItem.mock.calls[0][1]);
    expect(entry.payload.isStale).toBe(false);
  });

  it('treats an absent entry as a miss', async () => {
    mockGetItem.mockResolvedValue(null);
    await expect(readCachedTaxonomies()).resolves.toBeNull();
  });

  it('treats a version mismatch as a miss, never a partial read', async () => {
    mockGetItem.mockResolvedValue(
      JSON.stringify({ version: 99, fetchedAt: 'x', payload: PAYLOAD }),
    );
    await expect(readCachedTaxonomies()).resolves.toBeNull();
  });

  it('treats corrupt JSON as a miss and never throws', async () => {
    mockGetItem.mockResolvedValue('{not json at all');
    await expect(readCachedTaxonomies()).resolves.toBeNull();
  });

  it('treats a structurally wrong payload as a miss', async () => {
    mockGetItem.mockResolvedValue(
      JSON.stringify({
        version: TAXONOMY_CACHE_VERSION,
        fetchedAt: 'x',
        payload: { styleKeywords: [] },
      }),
    );
    await expect(readCachedTaxonomies()).resolves.toBeNull();
  });

  it('treats a storage read failure as a miss and never throws', async () => {
    mockGetItem.mockRejectedValue(new Error('storage unavailable'));
    await expect(readCachedTaxonomies()).resolves.toBeNull();
  });

  it('swallows a storage write failure — a failed cache write is not a failed fetch', async () => {
    mockSetItem.mockRejectedValue(new Error('quota exceeded'));
    await expect(writeCachedTaxonomies(PAYLOAD)).resolves.toBeUndefined();
  });

  it('clears the entry and swallows a clear failure', async () => {
    await clearCachedTaxonomies();
    expect(mockRemoveItem).toHaveBeenCalledWith(TAXONOMY_CACHE_KEY);

    mockRemoveItem.mockRejectedValue(new Error('nope'));
    await expect(clearCachedTaxonomies()).resolves.toBeUndefined();
  });
});
