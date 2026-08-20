import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, within } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { ItemCard } from '../../../../features/wardrobe/components/ItemCard';
import type {
  WardrobeItemImageUrlsMap,
  WardrobeItemRow,
} from '../../../../features/wardrobe/wardrobe.types';

const mockMutate = jest.fn();
const mockInvalidateQueries = jest.fn();
jest.mock('@tanstack/react-query', () => {
  const actual = jest.requireActual('@tanstack/react-query');
  return {
    ...actual,
    useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }),
  };
});
jest.mock('../../../../features/wardrobe/wardrobe.queries', () => ({
  useToggleWardrobeItemFavourite: () => ({ mutate: mockMutate }),
  wardrobeItemImageUrlsQueryKey: (userId: string | undefined) =>
    ['wardrobe', 'item-image-urls', userId] as const,
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

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

describe('ItemCard', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders the humanized category chip label', async () => {
    const item = makeItem({ category: 'ethnic_kurta' });
    const { getByText } = await render(
      <ItemCard item={item} imageUrls={NO_IMAGES} onPress={jest.fn()} />,
      { wrapper: createWrapper() },
    );

    expect(getByText('Ethnic Kurta')).toBeOnTheScreen();
  });

  it('renders "Uncategorized" when category is null', async () => {
    const item = makeItem({ category: null });
    const { getByText } = await render(
      <ItemCard item={item} imageUrls={NO_IMAGES} onPress={jest.fn()} />,
      { wrapper: createWrapper() },
    );

    expect(getByText('Uncategorized')).toBeOnTheScreen();
  });

  it('renders wear-count text matching wear_count', async () => {
    const item = makeItem({ wear_count: 7 });
    const { getByText } = await render(
      <ItemCard item={item} imageUrls={NO_IMAGES} onPress={jest.fn()} />,
      { wrapper: createWrapper() },
    );

    expect(getByText('Worn 7×')).toBeOnTheScreen();
  });

  it('renders "Worn 0×" when wear_count is null', async () => {
    const item = makeItem({ wear_count: null });
    const { getByText } = await render(
      <ItemCard item={item} imageUrls={NO_IMAGES} onPress={jest.fn()} />,
      { wrapper: createWrapper() },
    );

    expect(getByText('Worn 0×')).toBeOnTheScreen();
  });

  it('tapping the favourite heart calls useToggleWardrobeItemFavourite with the toggled value', async () => {
    const item = makeItem({ is_favourite: false });
    const { getByLabelText } = await render(
      <ItemCard item={item} imageUrls={NO_IMAGES} onPress={jest.fn()} />,
      { wrapper: createWrapper() },
    );

    fireEvent.press(getByLabelText('Add to favourites'));

    expect(mockMutate).toHaveBeenCalledWith({
      itemId: 'item-1',
      isFavourite: true,
    });
  });

  it('tapping the card (not the heart) calls onPress with the item', async () => {
    const item = makeItem();
    const onPress = jest.fn();
    const { getByTestId } = await render(
      <ItemCard item={item} imageUrls={NO_IMAGES} onPress={onPress} />,
      { wrapper: createWrapper() },
    );

    fireEvent.press(getByTestId('item-card-item-1'));

    expect(onPress).toHaveBeenCalledWith(item);
  });

  it.each(['uploaded', 'bg_processing'] as const)(
    'renders the "Processing…" overlay when processing_status is %s',
    async (status) => {
      const item = makeItem({ processing_status: status });
      const { getByTestId, getByText, queryByTestId } = await render(
        <ItemCard item={item} imageUrls={NO_IMAGES} onPress={jest.fn()} />,
        { wrapper: createWrapper() },
      );

      expect(
        getByTestId('item-card-processing-overlay-item-1'),
      ).toBeOnTheScreen();
      expect(getByText('Processing…')).toBeOnTheScreen();
      expect(queryByTestId('item-card-bg-pending-note-item-1')).toBeNull();
    },
  );

  it('renders "Background not removed" (no progress copy) when processing_status is bg_pending', async () => {
    const item = makeItem({ processing_status: 'bg_pending' });
    const { getByText, queryByTestId } = await render(
      <ItemCard item={item} imageUrls={NO_IMAGES} onPress={jest.fn()} />,
      { wrapper: createWrapper() },
    );

    expect(getByText('Background not removed')).toBeOnTheScreen();
    expect(queryByTestId('item-card-processing-overlay-item-1')).toBeNull();
  });

  it('renders neither overlay when processing_status is bg_removed', async () => {
    const item = makeItem({ processing_status: 'bg_removed' });
    const { queryByTestId, queryByText } = await render(
      <ItemCard item={item} imageUrls={NO_IMAGES} onPress={jest.fn()} />,
      { wrapper: createWrapper() },
    );

    expect(queryByTestId('item-card-processing-overlay-item-1')).toBeNull();
    expect(queryByText('Background not removed')).toBeNull();
  });

  it('image onError renders the retry icon; pressing it invalidates the bulk image-urls query key', async () => {
    const item = makeItem();
    const imageUrls: WardrobeItemImageUrlsMap = {
      'item-1': { url: 'https://signed/1', source: 'thumbnail' },
    };
    const { getByTestId, findByTestId } = await render(
      <ItemCard item={item} imageUrls={imageUrls} onPress={jest.fn()} />,
      { wrapper: createWrapper() },
    );

    fireEvent(getByTestId('item-card-image-item-1'), 'onError', {
      nativeEvent: { error: 'failed to load' },
    });

    // expo-image's onError -> setState re-render doesn't flush synchronously
    // within fireEvent's own act() wrap under this native-module mock --
    // findByTestId (which polls) is required here, not a plain getByTestId.
    const retryButton = await findByTestId('item-card-image-fallback-item-1');
    expect(retryButton).toBeOnTheScreen();

    fireEvent.press(within(retryButton).getByLabelText('Retry loading photo'));

    expect(mockInvalidateQueries).toHaveBeenCalledWith({
      queryKey: ['wardrobe', 'item-image-urls', undefined],
    });
  });
});
