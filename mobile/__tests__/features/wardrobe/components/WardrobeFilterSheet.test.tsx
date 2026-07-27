import { fireEvent, render, within } from '@testing-library/react-native';
import { WardrobeFilterSheet } from '../../../../features/wardrobe/components/WardrobeFilterSheet';
import { useWardrobeFilterStore } from '../../../../features/wardrobe/wardrobe.store';
import type { WardrobeItemRow } from '../../../../features/wardrobe/wardrobe.types';

jest.mock('@gorhom/bottom-sheet', () => {
  const actual = jest.requireActual('@gorhom/bottom-sheet');
  const react = jest.requireActual('react');
  const reactNative = jest.requireActual('react-native');

  const MockBottomSheetModal = react.forwardRef(
    (props: Record<string, unknown>, ref: React.Ref<unknown>) => {
      react.useImperativeHandle(ref, () => ({
        present: jest.fn(),
        dismiss: jest.fn(),
      }));
      return react.createElement(
        reactNative.View,
        { testID: 'mock-bottom-sheet-modal' },
        props.children,
      );
    },
  );
  MockBottomSheetModal.displayName = 'MockBottomSheetModal';

  return {
    ...actual,
    BottomSheetModal: MockBottomSheetModal,
    BottomSheetView: reactNative.View,
  };
});

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

describe('WardrobeFilterSheet', () => {
  beforeEach(() => {
    useWardrobeFilterStore.getState().reset();
  });

  // SS-014 fix pass (2026-07-27) -- manual-verification finding #5: 2-panel
  // layout. Only the *active* section's options render in the right panel,
  // so tests must switch sections via the left rail (`filter-section-tab-*`)
  // before a section's own option testIDs (`filter-occasion-*`/
  // `filter-season-*`/`filter-color-*`/`filter-sort-*`) exist.

  it('occasion is the default active section on open', async () => {
    const items = [makeItem()];
    const { getByTestId, queryByTestId } = await render(
      <WardrobeFilterSheet items={items} />,
    );

    expect(getByTestId('filter-occasion-office')).toBeOnTheScreen();
    expect(queryByTestId('filter-season-winter')).toBeNull();
  });

  it('selecting the left-rail section switches which options the right panel shows', async () => {
    const items = [
      makeItem({ id: '1', color_primary: 'blue' }),
      makeItem({ id: '2', color_primary: 'red' }),
      makeItem({ id: '3', color_primary: 'blue' }),
      makeItem({ id: '4', color_primary: null }),
    ];

    const { getByTestId, queryByTestId } = await render(
      <WardrobeFilterSheet items={items} />,
    );

    await fireEvent.press(getByTestId('filter-section-tab-color'));

    expect(getByTestId('filter-color-blue')).toBeOnTheScreen();
    expect(getByTestId('filter-color-red')).toBeOnTheScreen();
    // No duplicate for the second 'blue' item, no entry for null.
    expect(queryByTestId('filter-color-null')).toBeNull();
    // Switching sections hides the previously-active section's options.
    expect(queryByTestId('filter-occasion-office')).toBeNull();
  });

  it('already-selected options are visible up front via the selected-summary row and the rail captions', async () => {
    const items = [makeItem()];
    const { getByTestId } = await render(<WardrobeFilterSheet items={items} />);

    await fireEvent.press(getByTestId('filter-occasion-office'));
    await fireEvent.press(getByTestId('filter-section-tab-season'));
    await fireEvent.press(getByTestId('filter-season-winter'));

    // Summary row (visible regardless of which section is active).
    expect(getByTestId('filter-selected-chip-occasion')).toBeOnTheScreen();
    expect(getByTestId('filter-selected-chip-season')).toBeOnTheScreen();
    // Left-rail caption under "Occasion" reflects the draft selection even
    // while a different section ("Season") is now active.
    expect(
      within(getByTestId('filter-section-tab-occasion')).getByText('office'),
    ).toBeOnTheScreen();
  });

  it('selecting an occasion/season/sort option (across sections) and pressing Apply writes to the store', async () => {
    const items = [makeItem()];

    const { getByTestId, getByLabelText } = await render(
      <WardrobeFilterSheet items={items} />,
    );

    await fireEvent.press(getByTestId('filter-occasion-office'));
    await fireEvent.press(getByTestId('filter-section-tab-season'));
    await fireEvent.press(getByTestId('filter-season-winter'));
    await fireEvent.press(getByTestId('filter-section-tab-sort'));
    await fireEvent.press(getByTestId('filter-sort-most_worn'));
    await fireEvent.press(getByLabelText('Apply filters'));

    const state = useWardrobeFilterStore.getState();
    expect(state.occasionFilter).toBe('office');
    expect(state.seasonFilter).toBe('winter');
    expect(state.sort).toBe('most_worn');
  });

  it('Clear resets the store back to defaults', async () => {
    useWardrobeFilterStore.getState().setOccasionFilter('festival');
    useWardrobeFilterStore.getState().setSeasonFilter('summer');
    useWardrobeFilterStore.getState().setSort('cost_per_wear');
    const items = [makeItem()];

    const { getByLabelText } = await render(
      <WardrobeFilterSheet items={items} />,
    );

    await fireEvent.press(getByLabelText('Clear filters'));

    const state = useWardrobeFilterStore.getState();
    expect(state.occasionFilter).toBe('all');
    expect(state.seasonFilter).toBe('all');
    expect(state.colorFilter).toBe('all');
    expect(state.sort).toBe('newest');
  });
});
