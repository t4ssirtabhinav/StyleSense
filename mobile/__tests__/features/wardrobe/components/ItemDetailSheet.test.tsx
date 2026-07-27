import { fireEvent, render } from '@testing-library/react-native';
import { createRef } from 'react';
import type { AppBottomSheetRef } from '../../../../components/ui';
import { ItemDetailSheet } from '../../../../features/wardrobe/components/ItemDetailSheet';
import type { WardrobeItemRow } from '../../../../features/wardrobe/wardrobe.types';

let mockCapturedProps: Record<string, unknown> = {};

jest.mock('@gorhom/bottom-sheet', () => {
  const actual = jest.requireActual('@gorhom/bottom-sheet');
  const react = jest.requireActual('react');
  const reactNative = jest.requireActual('react-native');

  const MockBottomSheetModal = react.forwardRef(
    (props: Record<string, unknown>, ref: React.Ref<unknown>) => {
      mockCapturedProps = props;
      react.useImperativeHandle(ref, () => ({
        present: jest.fn(),
        dismiss: mockDismiss,
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

const mockDismiss = jest.fn();
const mockToggleFavouriteMutate = jest.fn();
const mockMarkWornMutate = jest.fn();
const mockDeleteMutate = jest.fn(
  (_vars: unknown, options?: { onSuccess?: () => void }) => {
    options?.onSuccess?.();
  },
);
const mockSaveTagsMutate = jest.fn();

jest.mock('../../../../features/wardrobe/wardrobe.queries', () => ({
  useWardrobeItemImageUrlQuery: () => ({
    data: { url: 'https://signed/full.png', source: 'clean' },
  }),
  useToggleWardrobeItemFavourite: () => ({
    mutate: mockToggleFavouriteMutate,
    isPending: false,
  }),
  useMarkWardrobeItemWorn: () => ({
    mutate: mockMarkWornMutate,
    isPending: false,
  }),
  useDeleteWardrobeItem: () => ({
    mutate: mockDeleteMutate,
    isPending: false,
  }),
  useSaveWardrobeItemTags: () => ({
    mutate: mockSaveTagsMutate,
    isPending: false,
  }),
}));

function makeItem(overrides: Partial<WardrobeItemRow> = {}): WardrobeItemRow {
  return {
    ai_tags: null,
    brand: null,
    category: 'ethnic_kurta',
    color_primary: 'blue',
    color_secondary: null,
    cost_per_wear: null,
    created_at: '2026-01-01T00:00:00.000Z',
    fabric: 'cotton',
    id: 'item-1',
    image_clean_url: 'wardrobe/user-1/item-1/clean.png',
    image_url: 'wardrobe/user-1/item-1/original.jpg',
    is_favourite: false,
    last_worn_at: '2026-01-15T00:00:00.000Z',
    occasion_tags: ['festival'],
    pattern: 'solid',
    processing_status: 'bg_removed',
    purchase_date: null,
    purchase_price: null,
    season_tags: ['summer'],
    subcategory: 'Straight-fit',
    thumbnail_url: 'wardrobe/user-1/item-1/thumbnail.jpg',
    user_id: 'user-1',
    user_notes: null,
    wear_count: 3,
    ...overrides,
  };
}

describe('ItemDetailSheet', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockCapturedProps = {};
  });

  // SS-014 fix pass (2026-07-27) -- manual-verification findings #3/#4.
  it('renders a header (handle + title) and opens to a usable height (initialIndex=1) instead of requiring a drag', async () => {
    const item = makeItem();
    const { getByTestId, getByText } = await render(
      <ItemDetailSheet item={item} jwt="jwt-token" />,
    );

    expect(getByTestId('item-detail-sheet-header')).toBeOnTheScreen();
    expect(getByText('Ethnic Kurta')).toBeOnTheScreen();
    expect(mockCapturedProps.index).toBe(1);
  });

  it('the favourite action\'s visible label never flips to "Favourited" -- only the icon/accessibilityLabel change', async () => {
    const { getByText, queryByText, getByLabelText } = await render(
      <ItemDetailSheet
        item={makeItem({ is_favourite: true })}
        jwt="jwt-token"
      />,
    );

    expect(getByText('Favourite')).toBeOnTheScreen();
    expect(queryByText('Favourited')).toBeNull();
    expect(getByLabelText('Remove from favourites')).toBeOnTheScreen();
  });

  it('renders the full tag set read-only in view mode; fetches the full image via useWardrobeItemImageUrlQuery', async () => {
    const item = makeItem();
    const { getByText, getByTestId } = await render(
      <ItemDetailSheet item={item} jwt="jwt-token" />,
    );

    expect(getByText('Ethnic Kurta')).toBeOnTheScreen();
    expect(getByText('Straight-fit')).toBeOnTheScreen();
    expect(getByText('Worn 3×')).toBeOnTheScreen();
    const image = getByTestId('item-detail-image');
    // expo-image's Image wrapper resolves `source` through resolveSources
    // (always an array form), so the deepest host node's `source` prop
    // isn't the raw `{ uri }` object passed in -- assert via JSON search
    // instead of a direct shape match.
    expect(JSON.stringify(image.props.source)).toContain(
      'https://signed/full.png',
    );
  });

  it('"Edit" swaps to EditItemTagsForm', async () => {
    const item = makeItem();
    const { getByLabelText, getByText } = await render(
      <ItemDetailSheet item={item} jwt="jwt-token" />,
    );

    await fireEvent.press(getByLabelText('Edit'));

    // EditItemTagsForm's own Save button, distinct from the view mode's
    // action row.
    expect(getByLabelText('Save')).toBeOnTheScreen();
    expect(getByText('ethnic_kurta')).toBeOnTheScreen();
  });

  it('"Mark Worn" calls useMarkWardrobeItemWorn with wear_count + 1', async () => {
    const item = makeItem({ wear_count: 3 });
    const { getByLabelText } = await render(
      <ItemDetailSheet item={item} jwt="jwt-token" />,
    );

    await fireEvent.press(getByLabelText('Mark Worn'));

    expect(mockMarkWornMutate).toHaveBeenCalledWith({
      itemId: 'item-1',
      nextWearCount: 4,
    });
  });

  it('first Delete tap arms the confirm state without deleting; second tap calls useDeleteWardrobeItem and dismisses', async () => {
    const item = makeItem();
    const { getByLabelText } = await render(
      <ItemDetailSheet item={item} jwt="jwt-token" />,
    );

    await fireEvent.press(getByLabelText('Delete'));
    expect(mockDeleteMutate).not.toHaveBeenCalled();
    expect(getByLabelText('Tap again to confirm delete')).toBeOnTheScreen();

    await fireEvent.press(getByLabelText('Tap again to confirm delete'));

    expect(mockDeleteMutate).toHaveBeenCalledWith(
      { itemId: 'item-1' },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it('favourite toggle here uses the same mutation ItemCard uses', async () => {
    const item = makeItem({ is_favourite: false });
    const { getByLabelText } = await render(
      <ItemDetailSheet item={item} jwt="jwt-token" />,
    );

    await fireEvent.press(getByLabelText('Add to favourites'));

    expect(mockToggleFavouriteMutate).toHaveBeenCalledWith({
      itemId: 'item-1',
      isFavourite: true,
    });
  });
});
