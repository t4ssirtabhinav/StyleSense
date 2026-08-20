import { render } from '@testing-library/react-native';
import type { ReactElement } from 'react';
import { Dimensions } from 'react-native';
import { ItemCard } from '../../../../features/wardrobe/components/ItemCard';
import { WardrobeGrid } from '../../../../features/wardrobe/components/WardrobeGrid';
import type {
  WardrobeItemImageUrlsMap,
  WardrobeItemRow,
} from '../../../../features/wardrobe/wardrobe.types';

// SS-014 fix pass (2026-07-27) -- numColumns is now derived from
// useWindowDimensions (finding #1), so tests must control the mocked width
// explicitly rather than relying on jest-expo's default mock width (750px,
// which is itself wide enough to land in a non-2-column breakpoint).
// Replacing the whole 'react-native' module via jest.mock() breaks
// jest-expo's own native-module mock chain (confirmed via isolated repro --
// "Cannot read properties of undefined (reading 'Component')" the moment
// any other file requires 'react-native' afterwards), so this uses RN's
// own public test seam instead: `Dimensions.set()` (Libraries/Utilities/
// Dimensions.js's documented `static set`), which useWindowDimensions reads
// via `Dimensions.get('window')` at mount and on its own 'change' listener.
function setMockWindowWidth(width: number) {
  Dimensions.set({
    window: { width, height: 800, scale: 1, fontScale: 1 },
    screen: { width, height: 800, scale: 1, fontScale: 1 },
  });
}

// Unit-tests WardrobeGrid's own contract -- what it passes to FlashList --
// rather than FlashList's internal RefreshControl/RecyclerView plumbing
// (already covered by @shopify/flash-list's own test suite). Both mocks
// render `null` and only record their received props -- no JSX/View usage
// inside these jest.mock() factories, since NativeWind's babel css-interop
// plugin injects a file-scoped helper reference that jest's module-factory
// out-of-scope-variable check then rejects.
const mockFlashList = jest.fn();
jest.mock('@shopify/flash-list', () => ({
  FlashList: (props: unknown) => {
    mockFlashList(props);
    return null;
  },
}));

jest.mock('../../../../features/wardrobe/components/ItemCard', () => ({
  ItemCard: () => null,
}));

function makeItem(overrides: Partial<WardrobeItemRow> = {}): WardrobeItemRow {
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
    id: 'item-1',
    image_clean_url: null,
    image_url: 'wardrobe/user-1/item-1/original.jpg',
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

const NO_IMAGES: WardrobeItemImageUrlsMap = {};

interface CapturedFlashListProps {
  data: WardrobeItemRow[];
  renderItem: (info: { item: WardrobeItemRow }) => ReactElement;
  keyExtractor: (item: WardrobeItemRow) => string;
  numColumns: number;
  refreshing: boolean;
  onRefresh: () => void;
}

describe('WardrobeGrid', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    setMockWindowWidth(375);
  });

  it('renders a FlashList with numColumns={2} on a phone-width viewport and one ItemCard per item', async () => {
    const items = [makeItem({ id: 'item-1' }), makeItem({ id: 'item-2' })];

    await render(
      <WardrobeGrid
        items={items}
        imageUrls={NO_IMAGES}
        onItemPress={jest.fn()}
        refreshing={false}
        onRefresh={jest.fn()}
      />,
    );

    expect(mockFlashList).toHaveBeenCalledTimes(1);
    const passedProps = mockFlashList.mock
      .calls[0][0] as CapturedFlashListProps;
    expect(passedProps.numColumns).toBe(2);
    expect(passedProps.data).toEqual(items);
    expect(passedProps.keyExtractor(items[0])).toBe('item-1');

    for (const item of items) {
      const element = passedProps.renderItem({ item });
      expect(element.type).toBe(ItemCard);
      expect((element.props as { item: WardrobeItemRow }).item).toBe(item);
    }
  });

  it('pull-to-refresh (onRefresh) triggers the combined refetch', async () => {
    const onRefresh = jest.fn();
    const items = [makeItem({ id: 'item-1' })];

    await render(
      <WardrobeGrid
        items={items}
        imageUrls={NO_IMAGES}
        onItemPress={jest.fn()}
        refreshing={false}
        onRefresh={onRefresh}
      />,
    );

    const passedProps = mockFlashList.mock
      .calls[0][0] as CapturedFlashListProps;
    expect(passedProps.refreshing).toBe(false);
    passedProps.onRefresh();

    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it.each([
    [375, 2],
    [600, 3],
    [800, 4],
    [1200, 5],
  ])(
    'a %ipx-wide viewport derives numColumns=%i (responsive grid, fix pass finding #1)',
    async (width, expectedColumns) => {
      setMockWindowWidth(width);
      const items = [makeItem({ id: 'item-1' })];

      await render(
        <WardrobeGrid
          items={items}
          imageUrls={NO_IMAGES}
          onItemPress={jest.fn()}
          refreshing={false}
          onRefresh={jest.fn()}
        />,
      );

      const passedProps = mockFlashList.mock
        .calls[0][0] as CapturedFlashListProps;
      expect(passedProps.numColumns).toBe(expectedColumns);
    },
  );
});
