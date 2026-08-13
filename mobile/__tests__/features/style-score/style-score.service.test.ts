import { fetchStyleScoreInputs } from '../../../features/style-score/style-score.service';

function makeQueryBuilder(resolvedValue: unknown) {
  const builder: Record<string, unknown> = {};
  builder.select = jest.fn(() => builder);
  builder.limit = jest.fn(() => builder);
  builder.gte = jest.fn(() => builder);
  // biome-ignore lint/suspicious/noThenProperty: mimics the real Supabase PostgrestFilterBuilder, itself a thenable.
  builder.then = (
    resolve: (value: unknown) => unknown,
    reject: (reason: unknown) => unknown,
  ) => Promise.resolve(resolvedValue).then(resolve, reject);
  return builder;
}

let itemsBuilder: ReturnType<typeof makeQueryBuilder>;
let outfitsBuilder: ReturnType<typeof makeQueryBuilder>;
let wearsBuilder: ReturnType<typeof makeQueryBuilder>;
const mockFrom = jest.fn((table: string) => {
  if (table === 'wardrobe_items') return itemsBuilder;
  if (table === 'outfits') return outfitsBuilder;
  if (table === 'wardrobe_item_wears') return wearsBuilder;
  throw new Error(`unexpected table: ${table}`);
});

jest.mock('../../../lib/supabase', () => ({
  supabase: { from: (...args: unknown[]) => mockFrom(...(args as [string])) },
}));

const NOW = new Date('2026-08-10T12:00:00.000Z');
const ACTIVE_OCCASION_KEYS = ['office', 'casual'];

const ITEM_ROWS = [
  {
    category: 'ethnic_kurta',
    occasion_tags: ['office', 'unknown_slug'],
    cost_per_wear: 50,
    purchase_price: 500,
    wear_count: 10,
  },
  {
    category: 'ethnic_kurta',
    occasion_tags: ['casual'],
    cost_per_wear: null,
    purchase_price: null,
    wear_count: 0,
  },
  {
    category: 'footwear',
    occasion_tags: [],
    cost_per_wear: 0,
    purchase_price: 0,
    wear_count: 5,
  },
  {
    category: 'accessory',
    occasion_tags: null,
    cost_per_wear: null,
    purchase_price: 1000,
    wear_count: 0,
  },
];

describe('fetchStyleScoreInputs', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    itemsBuilder = makeQueryBuilder({ data: ITEM_ROWS, error: null });
    outfitsBuilder = makeQueryBuilder({ count: 3, error: null });
    wearsBuilder = makeQueryBuilder({ count: 7, error: null });
  });

  it('issues exactly three Supabase queries and selects only the five named wardrobe_items columns', async () => {
    await fetchStyleScoreInputs('user-1', NOW, ACTIVE_OCCASION_KEYS);
    expect(mockFrom).toHaveBeenCalledTimes(3);
    expect(mockFrom).toHaveBeenCalledWith('wardrobe_items');
    expect(mockFrom).toHaveBeenCalledWith('outfits');
    expect(mockFrom).toHaveBeenCalledWith('wardrobe_item_wears');
    expect(itemsBuilder.select).toHaveBeenCalledWith(
      'category, occasion_tags, cost_per_wear, purchase_price, wear_count',
    );
  });

  it('filters the outfits count by created_at >= istMonthStart.isoTimestamp and the wears count by worn_on >= istMonthStart.isoDate', async () => {
    await fetchStyleScoreInputs('user-1', NOW, ACTIVE_OCCASION_KEYS);
    expect(outfitsBuilder.gte).toHaveBeenCalledWith(
      'created_at',
      '2026-07-31T18:30:00.000Z',
    );
    expect(wearsBuilder.gte).toHaveBeenCalledWith('worn_on', '2026-08-01');
  });

  it('adds no client-side user_id filter to any of the three queries', async () => {
    await fetchStyleScoreInputs('user-1', NOW, ACTIVE_OCCASION_KEYS);
    for (const builder of [itemsBuilder, outfitsBuilder, wearsBuilder]) {
      expect(builder).not.toHaveProperty('eq');
    }
  });

  it('derives distinctCategories and coveredOccasionKeys correctly from a mixed item fixture', async () => {
    const result = await fetchStyleScoreInputs(
      'user-1',
      NOW,
      ACTIVE_OCCASION_KEYS,
    );
    expect(result.itemCount).toBe(4);
    expect(result.distinctCategories).toBe(3); // ethnic_kurta, footwear, accessory
    expect(new Set(result.coveredOccasionKeys)).toEqual(
      new Set(['office', 'unknown_slug', 'casual']),
    );
    expect(result.outfitsThisMonth).toBe(3);
    expect(result.wearsThisMonth).toBe(7);
    expect(result.activeOccasionKeys).toEqual(ACTIVE_OCCASION_KEYS);
  });

  it('excludes items with purchase_price null, 0, or wear_count 0 from costPerWearValues', async () => {
    const result = await fetchStyleScoreInputs(
      'user-1',
      NOW,
      ACTIVE_OCCASION_KEYS,
    );
    // Only the first row qualifies (purchase_price 500 > 0, wear_count 10 >= 1, cost_per_wear 50 !== null).
    expect(result.costPerWearValues).toEqual([50]);
  });

  it('propagates a Supabase error by rejecting rather than returning zeroed inputs', async () => {
    itemsBuilder = makeQueryBuilder({
      data: null,
      error: new Error('network failure'),
    });
    await expect(
      fetchStyleScoreInputs('user-1', NOW, ACTIVE_OCCASION_KEYS),
    ).rejects.toThrow('network failure');
  });
});
