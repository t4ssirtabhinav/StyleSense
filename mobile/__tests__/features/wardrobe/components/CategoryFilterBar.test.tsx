import { fireEvent, render } from '@testing-library/react-native';
import { CategoryFilterBar } from '../../../../features/wardrobe/components/CategoryFilterBar';
import { useWardrobeFilterStore } from '../../../../features/wardrobe/wardrobe.store';
import type { WardrobeItemRow } from '../../../../features/wardrobe/wardrobe.types';

function makeItem(overrides: Partial<WardrobeItemRow> = {}): WardrobeItemRow {
  return {
    ai_tags: null,
    brand: null,
    category: 'western_top',
    color_primary: null,
    color_secondary: null,
    cost_per_wear: null,
    created_at: '2026-01-01T00:00:00.000Z',
    fabric: null,
    id: 'item-1',
    image_clean_url: null,
    image_url: 'wardrobe/user-1/item-1/original.jpg',
    is_favourite: false,
    last_worn_at: null,
    occasion_tags: null,
    pattern: null,
    processing_status: 'bg_removed',
    purchase_date: null,
    purchase_price: null,
    season_tags: null,
    subcategory: null,
    thumbnail_url: null,
    user_id: 'user-1',
    user_notes: null,
    wear_count: null,
    ...overrides,
  };
}

describe('CategoryFilterBar', () => {
  beforeEach(() => {
    useWardrobeFilterStore.getState().reset();
  });

  it('renders all 6 pills with correct live counts', async () => {
    const items = [
      makeItem({ id: '1', category: 'western_top' }),
      makeItem({ id: '2', category: 'ethnic_kurta' }),
      makeItem({ id: '3', category: 'footwear_formal' }),
      makeItem({ id: '4', category: 'accessory_bag' }),
      makeItem({ id: '5', category: null, is_favourite: true }),
    ];

    const { getByText } = await render(<CategoryFilterBar items={items} />);

    expect(getByText('All (5)')).toBeOnTheScreen();
    expect(getByText('Ethnic (1)')).toBeOnTheScreen();
    expect(getByText('Western (1)')).toBeOnTheScreen();
    expect(getByText('Footwear (1)')).toBeOnTheScreen();
    expect(getByText('Accessories (1)')).toBeOnTheScreen();
    expect(getByText('Favourites (1)')).toBeOnTheScreen();
  });

  it('selecting a pill updates useWardrobeFilterStore.categoryFilter and visually marks it selected', async () => {
    const items = [makeItem({ category: 'ethnic_kurta' })];

    const { getByTestId } = await render(<CategoryFilterBar items={items} />);

    fireEvent.press(getByTestId('category-filter-pill-ethnic'));

    expect(useWardrobeFilterStore.getState().categoryFilter).toBe('ethnic');
  });

  it('marks the currently-selected pill with the selected visual style (border-textPrimary)', async () => {
    useWardrobeFilterStore.getState().setCategoryFilter('western');
    const items = [makeItem({ category: 'western_top' })];

    const { toJSON } = await render(<CategoryFilterBar items={items} />);

    const tree = JSON.stringify(toJSON());
    // Badge's `selected` style is a distinct className (border-textPrimary)
    // applied only when selected -- present at all confirms at least one
    // pill (the selected 'western' one) rendered with it.
    expect(tree).toContain('border-textPrimary');
  });

  // SS-014 fix pass (2026-07-27) -- manual-verification finding #2's root
  // cause: react-native-web's ScrollView defaults to `flexGrow: 1` (its own
  // `commonStyle`, applied to both scroll directions), which -- unless
  // overridden -- made this horizontal tag row grow to fill all remaining
  // vertical space in the screen's flex-column layout, producing the
  // "large unexplained gap" before the search bar. `flex-none` (flex-grow:
  // 0; flex-shrink: 0) pins it back to its content height.
  // Regression pin, rewritten 2026-08-12. The previous version of this test
  // asserted the `flex-none` *className* was present -- which is why it
  // stayed green for months while the bug was live in a real browser: the
  // className never actually won against react-native-web's own
  // `flexGrow: 1` base style. Assert the real constraint (the `style` prop,
  // which has last-writer precedence in RN's style merge) rather than the
  // mechanism that was supposed to produce it.
  it('is pinned to its content height via the style prop, not left to grow and fill the column', async () => {
    const items = [makeItem()];

    const { getByTestId } = await render(<CategoryFilterBar items={items} />);

    expect(getByTestId('category-filter-bar').props.style).toEqual(
      expect.objectContaining({
        flexGrow: 0,
        flexShrink: 0,
        maxHeight: expect.any(Number),
      }),
    );
  });
});
