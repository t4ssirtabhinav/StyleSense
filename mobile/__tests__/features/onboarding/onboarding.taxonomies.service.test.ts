import { fetchOnboardingTaxonomies } from '../../../features/onboarding/onboarding.taxonomies.service';

const mockOrder = jest.fn();
const mockEq = jest.fn(() => ({ order: mockOrder }));
const mockSelect = jest.fn(() => ({ eq: mockEq }));
const mockFrom = jest.fn((_table: string) => ({ select: mockSelect }));

jest.mock('../../../lib/supabase', () => ({
  supabase: {
    from: (arg: string) => mockFrom(arg),
  },
}));

describe('fetchOnboardingTaxonomies', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('queries all three tables (active=true, sort_order ascending) and maps rows into OnboardingTaxonomies', async () => {
    mockOrder
      .mockResolvedValueOnce({
        data: [{ key: 'ethnic', label: 'Ethnic', sort_order: 1 }],
        error: null,
      })
      .mockResolvedValueOnce({
        data: [{ key: 'office', label: 'Office', sort_order: 1 }],
        error: null,
      })
      .mockResolvedValueOnce({
        data: [{ key: 'black', label: 'Black', hex: '#000000', sort_order: 1 }],
        error: null,
      });

    const result = await fetchOnboardingTaxonomies();

    expect(mockFrom).toHaveBeenCalledWith('style_keywords');
    expect(mockFrom).toHaveBeenCalledWith('occasion_types');
    expect(mockFrom).toHaveBeenCalledWith('colour_palette');
    expect(mockEq).toHaveBeenCalledWith('active', true);
    expect(mockOrder).toHaveBeenCalledWith('sort_order', { ascending: true });

    expect(result).toEqual({
      styleKeywords: [{ key: 'ethnic', label: 'Ethnic', sortOrder: 1 }],
      occasionTypes: [{ key: 'office', label: 'Office', sortOrder: 1 }],
      colourPalette: [
        { key: 'black', label: 'Black', hex: '#000000', sortOrder: 1 },
      ],
    });
  });

  it('returns rows in DB sort_order-ascending order without a client-side re-sort', async () => {
    mockOrder
      .mockResolvedValueOnce({
        data: [
          { key: 'ethnic', label: 'Ethnic', sort_order: 1 },
          { key: 'western', label: 'Western', sort_order: 2 },
        ],
        error: null,
      })
      .mockResolvedValueOnce({ data: [], error: null })
      .mockResolvedValueOnce({ data: [], error: null });

    const result = await fetchOnboardingTaxonomies();

    expect(result.styleKeywords.map((option) => option.key)).toEqual([
      'ethnic',
      'western',
    ]);
  });

  it('resolves a zero-row result for any one table to an empty array, not a thrown error', async () => {
    mockOrder
      .mockResolvedValueOnce({ data: [], error: null })
      .mockResolvedValueOnce({ data: [], error: null })
      .mockResolvedValueOnce({ data: [], error: null });

    await expect(fetchOnboardingTaxonomies()).resolves.toEqual({
      styleKeywords: [],
      occasionTypes: [],
      colourPalette: [],
    });
  });

  it('rejects the whole function when any of the three queries rejects', async () => {
    mockOrder
      .mockResolvedValueOnce({ data: [], error: null })
      .mockRejectedValueOnce(new Error('network error'))
      .mockResolvedValueOnce({ data: [], error: null });

    await expect(fetchOnboardingTaxonomies()).rejects.toThrow('network error');
  });

  it('rejects the whole function when any of the three queries returns an error', async () => {
    mockOrder
      .mockResolvedValueOnce({ data: [], error: null })
      .mockResolvedValueOnce({ data: [], error: null })
      .mockResolvedValueOnce({ data: null, error: new Error('RLS denied') });

    await expect(fetchOnboardingTaxonomies()).rejects.toThrow('RLS denied');
  });
});
