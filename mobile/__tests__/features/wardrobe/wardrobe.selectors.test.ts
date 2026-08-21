import { WARDROBE_CATEGORIES } from '../../../features/wardrobe/wardrobe.constants';
import {
  columnsForWidth,
  countsByCategoryFilter,
  groupForCategory,
  selectFilteredSortedItems,
} from '../../../features/wardrobe/wardrobe.selectors';
import type {
  CategoryGroup,
  WardrobeFilterState,
  WardrobeItemRow,
} from '../../../features/wardrobe/wardrobe.types';

const DEFAULT_FILTERS: WardrobeFilterState = {
  categoryFilter: 'all',
  occasionFilter: 'all',
  seasonFilter: 'all',
  colorFilter: 'all',
  search: '',
  sort: 'newest',
};

let idCounter = 0;
function makeItem(overrides: Partial<WardrobeItemRow> = {}): WardrobeItemRow {
  idCounter += 1;
  return {
    ai_tags: null,
    brand: null,
    category: 'western_top',
    color_primary: null,
    color_secondary: null,
    condition: null,
    cost_per_wear: null,
    created_at: '2026-01-01T00:00:00.000Z',
    custom_tags: [],
    do_not_style: false,
    fabric: null,
    id: `item-${idCounter}`,
    image_clean_url: null,
    image_url: 'wardrobe/user-1/item/original.jpg',
    is_archived: false,
    is_favourite: false,
    last_worn_at: null,
    occasion_tags: null,
    pattern: null,
    processing_status: 'bg_removed',
    purchase_date: null,
    purchase_price: null,
    render_transform: null,
    season_tags: null,
    subcategory: null,
    thumbnail_url: null,
    user_id: 'user-1',
    user_notes: null,
    wear_count: null,
    ...overrides,
  };
}

const EXPECTED_GROUPS: Record<string, CategoryGroup> = {
  western_top: 'western',
  western_bottom: 'western',
  western_dress: 'western',
  western_outerwear: 'western',
  ethnic_kurta: 'ethnic',
  ethnic_saree: 'ethnic',
  ethnic_lehenga: 'ethnic',
  ethnic_anarkali: 'ethnic',
  ethnic_salwar_kameez: 'ethnic',
  ethnic_dupatta: 'ethnic',
  ethnic_sherwani: 'ethnic',
  indo_western: 'ethnic',
  footwear_formal: 'footwear',
  footwear_casual: 'footwear',
  footwear_ethnic: 'footwear',
  footwear_sports: 'footwear',
  accessory_bag: 'accessories',
  accessory_jewellery: 'accessories',
  accessory_watch: 'accessories',
  accessory_belt: 'accessories',
  accessory_scarf: 'accessories',
};

describe('groupForCategory', () => {
  it('maps every one of the 21 WardrobeCategory values to the correct group', () => {
    expect(WARDROBE_CATEGORIES).toHaveLength(21);
    for (const { value } of WARDROBE_CATEGORIES) {
      expect(groupForCategory(value)).toBe(EXPECTED_GROUPS[value]);
    }
  });

  it('returns null for a null category', () => {
    expect(groupForCategory(null)).toBeNull();
  });
});

describe('countsByCategoryFilter', () => {
  it('returns correct per-pill counts, All=total, Favourites=is_favourite independent of category', () => {
    const items = [
      makeItem({ category: 'western_top', is_favourite: false }),
      makeItem({ category: 'ethnic_kurta', is_favourite: true }),
      makeItem({ category: 'footwear_formal', is_favourite: false }),
      makeItem({ category: 'accessory_bag', is_favourite: true }),
      makeItem({ category: null, is_favourite: true }),
    ];

    const counts = countsByCategoryFilter(items);

    expect(counts.all).toBe(5);
    expect(counts.western).toBe(1);
    expect(counts.ethnic).toBe(1);
    expect(counts.footwear).toBe(1);
    expect(counts.accessories).toBe(1);
    // 3 favourites, including the uncategorized one.
    expect(counts.favourites).toBe(3);
  });
});

describe('selectFilteredSortedItems', () => {
  it('category filter narrows to the matching group only', () => {
    const items = [
      makeItem({ category: 'western_top' }),
      makeItem({ category: 'ethnic_kurta' }),
    ];

    const result = selectFilteredSortedItems(items, {
      ...DEFAULT_FILTERS,
      categoryFilter: 'ethnic',
    });

    expect(result).toHaveLength(1);
    expect(result[0].category).toBe('ethnic_kurta');
  });

  it('favourites category filter narrows to is_favourite items regardless of category', () => {
    const items = [
      makeItem({ category: 'western_top', is_favourite: true }),
      makeItem({ category: 'ethnic_kurta', is_favourite: false }),
    ];

    const result = selectFilteredSortedItems(items, {
      ...DEFAULT_FILTERS,
      categoryFilter: 'favourites',
    });

    expect(result).toHaveLength(1);
    expect(result[0].is_favourite).toBe(true);
  });

  it('occasion filter narrows to items whose occasion_tags include the value', () => {
    const items = [
      makeItem({ occasion_tags: ['office'] }),
      makeItem({ occasion_tags: ['festival'] }),
      makeItem({ occasion_tags: null }),
    ];

    const result = selectFilteredSortedItems(items, {
      ...DEFAULT_FILTERS,
      occasionFilter: 'office',
    });

    expect(result).toHaveLength(1);
    expect(result[0].occasion_tags).toEqual(['office']);
  });

  it('season filter narrows to items whose season_tags include the value', () => {
    const items = [
      makeItem({ season_tags: ['summer'] }),
      makeItem({ season_tags: ['winter'] }),
    ];

    const result = selectFilteredSortedItems(items, {
      ...DEFAULT_FILTERS,
      seasonFilter: 'winter',
    });

    expect(result).toHaveLength(1);
    expect(result[0].season_tags).toEqual(['winter']);
  });

  it('colour filter narrows to items with a matching color_primary', () => {
    const items = [
      makeItem({ color_primary: 'blue' }),
      makeItem({ color_primary: 'red' }),
    ];

    const result = selectFilteredSortedItems(items, {
      ...DEFAULT_FILTERS,
      colorFilter: 'red',
    });

    expect(result).toHaveLength(1);
    expect(result[0].color_primary).toBe('red');
  });

  it('search matches humanized category label, raw category, brand, or user_notes (case-insensitive)', () => {
    const items = [
      makeItem({ category: 'ethnic_kurta', brand: null, user_notes: null }),
      makeItem({ category: 'western_top', brand: 'Zara', user_notes: null }),
      makeItem({
        category: 'western_top',
        brand: null,
        user_notes: 'Gift from mom',
      }),
    ];

    expect(
      selectFilteredSortedItems(items, { ...DEFAULT_FILTERS, search: 'kurta' }),
    ).toHaveLength(1);
    expect(
      selectFilteredSortedItems(items, { ...DEFAULT_FILTERS, search: 'ZARA' }),
    ).toHaveLength(1);
    expect(
      selectFilteredSortedItems(items, { ...DEFAULT_FILTERS, search: 'gift' }),
    ).toHaveLength(1);
  });

  it('combined filters AND together', () => {
    const items = [
      makeItem({
        category: 'ethnic_kurta',
        color_primary: 'blue',
        occasion_tags: ['festival'],
      }),
      makeItem({
        category: 'ethnic_kurta',
        color_primary: 'red',
        occasion_tags: ['festival'],
      }),
      makeItem({
        category: 'western_top',
        color_primary: 'blue',
        occasion_tags: ['festival'],
      }),
    ];

    const result = selectFilteredSortedItems(items, {
      ...DEFAULT_FILTERS,
      categoryFilter: 'ethnic',
      colorFilter: 'blue',
      occasionFilter: 'festival',
    });

    expect(result).toHaveLength(1);
    expect(result[0].category).toBe('ethnic_kurta');
    expect(result[0].color_primary).toBe('blue');
  });

  it("'newest' sorts by created_at descending", () => {
    const items = [
      makeItem({ id: 'old', created_at: '2026-01-01T00:00:00.000Z' }),
      makeItem({ id: 'new', created_at: '2026-02-01T00:00:00.000Z' }),
    ];

    const result = selectFilteredSortedItems(items, {
      ...DEFAULT_FILTERS,
      sort: 'newest',
    });

    expect(result.map((item) => item.id)).toEqual(['new', 'old']);
  });

  it("'most_worn' sorts by wear_count descending, treating null as 0", () => {
    const items = [
      makeItem({ id: 'a', wear_count: 3 }),
      makeItem({ id: 'b', wear_count: null }),
      makeItem({ id: 'c', wear_count: 10 }),
    ];

    const result = selectFilteredSortedItems(items, {
      ...DEFAULT_FILTERS,
      sort: 'most_worn',
    });

    expect(result.map((item) => item.id)).toEqual(['c', 'a', 'b']);
  });

  it("'least_worn' sorts by wear_count ascending -- never-worn (0/null) items surface first", () => {
    const items = [
      makeItem({ id: 'a', wear_count: 3 }),
      makeItem({ id: 'b', wear_count: null }),
      makeItem({ id: 'c', wear_count: 0 }),
    ];

    const result = selectFilteredSortedItems(items, {
      ...DEFAULT_FILTERS,
      sort: 'least_worn',
    });

    expect(result[0].wear_count === null || result[0].wear_count === 0).toBe(
      true,
    );
    expect(result[result.length - 1].id).toBe('a');
  });

  it("'cost_per_wear' sorts ascending (lowest/best-value first), with null always last", () => {
    const items = [
      makeItem({ id: 'a', cost_per_wear: 50 }),
      makeItem({ id: 'b', cost_per_wear: null }),
      makeItem({ id: 'c', cost_per_wear: 10 }),
    ];

    const result = selectFilteredSortedItems(items, {
      ...DEFAULT_FILTERS,
      sort: 'cost_per_wear',
    });

    expect(result.map((item) => item.id)).toEqual(['c', 'a', 'b']);
  });
});

// SS-014 fix pass (2026-07-27) -- manual-verification finding #1: responsive
// grid column count.
describe('columnsForWidth', () => {
  it('returns 2 columns below the smallest breakpoint (plain phone portrait)', () => {
    expect(columnsForWidth(320)).toBe(2);
    expect(columnsForWidth(479)).toBe(2);
  });

  it('returns 3 columns at/above 480px', () => {
    expect(columnsForWidth(480)).toBe(3);
    expect(columnsForWidth(700)).toBe(3);
  });

  it('returns 4 columns at/above 768px', () => {
    expect(columnsForWidth(768)).toBe(4);
    expect(columnsForWidth(1000)).toBe(4);
  });

  it('returns 5 columns at/above 1024px', () => {
    expect(columnsForWidth(1024)).toBe(5);
    expect(columnsForWidth(2000)).toBe(5);
  });
});
