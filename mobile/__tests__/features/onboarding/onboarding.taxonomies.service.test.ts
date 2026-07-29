import { fetchOnboardingTaxonomies } from '../../../features/onboarding/onboarding.taxonomies.service';
import * as storage from '../../../lib/storage';

// Four parallel queries now (SS-025): style_keywords, occasions,
// occasion_aliases, colour_palette. `occasion_aliases` has no .eq()/.order()
// chain, so the builder must resolve at whichever link the caller stops at.
const mockOrder = jest.fn();
const mockEq = jest.fn(() => ({ order: mockOrder }));
// `then: undefined` makes the resolved shape non-thenable-shaped for
// callers that (correctly) never await this builder link directly; biome's
// noThenProperty doesn't know that, hence the ignore.
// biome-ignore lint/suspicious/noThenProperty: deliberately non-thenable marker, not a real Promise-like.
const mockSelect = jest.fn(() => ({ eq: mockEq, then: undefined }));
// jest.Mock's bare (default-generic) form, not an explicit `any` -- the
// mock's return shape varies per test (see primeQueries below), and
// jest.Mock's inference from the initial implementation is too narrow for
// that.
const mockFrom: jest.Mock = jest.fn((_table: string) => ({
  select: mockSelect,
}));

jest.mock('../../../lib/supabase', () => ({
  supabase: {
    from: (arg: string) => mockFrom(arg),
  },
}));

jest.mock('../../../lib/storage', () => ({
  readCachedTaxonomies: jest.fn(),
  writeCachedTaxonomies: jest.fn(),
}));

const mockRead = storage.readCachedTaxonomies as jest.Mock;
const mockWrite = storage.writeCachedTaxonomies as jest.Mock;

const OCCASION_ROW = {
  key: 'office',
  label: 'Office',
  badge_color: 'office',
  kind: 'professional',
  parent_key: null,
  sort_order: 1,
  region_scope: null,
  culture_scope: null,
};

// `occasion_aliases` is the one query with no .eq()/.order() — it awaits the
// select() result directly, so that builder link must be thenable.
function aliasResult(data: unknown, error: unknown = null) {
  return Promise.resolve({ data, error });
}

interface QueryResult {
  data: unknown;
  error: unknown;
}

function primeQueries({
  styleKeywords = { data: [], error: null } as QueryResult,
  occasions = { data: [OCCASION_ROW], error: null } as QueryResult,
  aliases = {
    data: [{ alias: 'wedding', occasion_key: 'wedding_guest' }],
    error: null,
  } as QueryResult,
  colourPalette = { data: [], error: null } as QueryResult,
} = {}) {
  mockFrom.mockImplementation((table: string) => {
    if (table === 'occasion_aliases') {
      return {
        select: () => aliasResult(aliases.data, aliases.error),
      };
    }
    return {
      select: () => ({
        eq: () => ({
          order: () =>
            Promise.resolve(
              table === 'style_keywords'
                ? styleKeywords
                : table === 'occasions'
                  ? occasions
                  : colourPalette,
            ),
        }),
      }),
    };
  });
}

describe('fetchOnboardingTaxonomies', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockWrite.mockResolvedValue(undefined);
    mockRead.mockResolvedValue(null);
  });

  it('queries occasions + occasion_aliases (not the retired occasion_types table)', async () => {
    primeQueries();

    await fetchOnboardingTaxonomies();

    const tables = mockFrom.mock.calls.map((call) => call[0]);
    expect(tables).toContain('style_keywords');
    expect(tables).toContain('occasions');
    expect(tables).toContain('occasion_aliases');
    expect(tables).toContain('colour_palette');
    expect(tables).not.toContain('occasion_types');
  });

  it('requests only is_active rows, ordered by sort_order ascending', async () => {
    const eq = jest.fn(() => ({
      order: jest.fn(() =>
        Promise.resolve({ data: [OCCASION_ROW], error: null }),
      ),
    }));
    mockFrom.mockImplementation((table: string) => {
      if (table === 'occasion_aliases') {
        return { select: () => aliasResult([]) };
      }
      if (table === 'occasions') {
        return { select: () => ({ eq }) };
      }
      return {
        select: () => ({
          eq: () => ({
            order: () => Promise.resolve({ data: [], error: null }),
          }),
        }),
      };
    });

    await fetchOnboardingTaxonomies();

    expect(eq).toHaveBeenCalledWith('is_active', true);
  });

  it('maps occasion rows into OccasionOption, including hierarchy and scopes', async () => {
    primeQueries();

    const result = await fetchOnboardingTaxonomies();

    expect(result.occasions).toEqual([
      {
        key: 'office',
        label: 'Office',
        badgeColor: 'office',
        kind: 'professional',
        parentKey: null,
        sortOrder: 1,
        regionScope: null,
        cultureScope: null,
      },
    ]);
    expect(result.occasionAliases).toEqual([
      { alias: 'wedding', occasionKey: 'wedding_guest' },
    ]);
    expect(result.isStale).toBe(false);
  });

  it('writes the whole payload to the last-known-good cache on success', async () => {
    primeQueries();

    const result = await fetchOnboardingTaxonomies();

    expect(mockWrite).toHaveBeenCalledTimes(1);
    expect(mockWrite).toHaveBeenCalledWith(result);
  });

  it('resolves a zero-row result to empty arrays, not a thrown error', async () => {
    primeQueries({
      occasions: { data: [], error: null },
      aliases: { data: [], error: null },
    });

    await expect(fetchOnboardingTaxonomies()).resolves.toEqual({
      styleKeywords: [],
      occasions: [],
      occasionAliases: [],
      colourPalette: [],
      isStale: false,
    });
  });

  it('falls back to the cached payload and marks it stale when a query errors', async () => {
    primeQueries({ occasions: { data: null, error: new Error('RLS denied') } });
    mockRead.mockResolvedValue({
      version: 1,
      fetchedAt: '2026-07-27T00:00:00.000Z',
      payload: {
        styleKeywords: [],
        occasions: [
          {
            key: 'casual',
            label: 'Casual',
            badgeColor: 'casual',
            kind: 'everyday',
            parentKey: null,
            sortOrder: 2,
            regionScope: null,
            cultureScope: null,
          },
        ],
        occasionAliases: [],
        colourPalette: [],
        isStale: false,
      },
    });

    const result = await fetchOnboardingTaxonomies();

    expect(result.isStale).toBe(true);
    expect(result.occasions[0].key).toBe('casual');
  });

  it('falls back to cache when the network rejects outright', async () => {
    mockFrom.mockImplementation((table: string) => {
      if (table === 'occasion_aliases') {
        return { select: () => Promise.reject(new Error('network error')) };
      }
      return {
        select: () => ({
          eq: () => ({
            order: () => Promise.resolve({ data: [], error: null }),
          }),
        }),
      };
    });
    mockRead.mockResolvedValue({
      version: 1,
      fetchedAt: '2026-07-27T00:00:00.000Z',
      payload: {
        styleKeywords: [],
        occasions: [],
        occasionAliases: [],
        colourPalette: [],
        isStale: false,
      },
    });

    await expect(fetchOnboardingTaxonomies()).resolves.toMatchObject({
      isStale: true,
    });
  });

  it('rejects when a query fails and there is NO cache, so the hook renders isError', async () => {
    // Cold start, offline, first ever launch: an error/retry state, NOT an
    // empty picker and NOT a bundled fallback vocabulary (design §6.5).
    primeQueries({ occasions: { data: null, error: new Error('RLS denied') } });
    mockRead.mockResolvedValue(null);

    await expect(fetchOnboardingTaxonomies()).rejects.toThrow('RLS denied');
  });

  it('does not write the cache when the fetch failed', async () => {
    primeQueries({ occasions: { data: null, error: new Error('RLS denied') } });
    mockRead.mockResolvedValue(null);

    await expect(fetchOnboardingTaxonomies()).rejects.toThrow();
    expect(mockWrite).not.toHaveBeenCalled();
  });
});
