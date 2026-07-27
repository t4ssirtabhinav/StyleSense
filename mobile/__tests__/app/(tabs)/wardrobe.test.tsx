import { fireEvent, render } from '@testing-library/react-native';
import WardrobeScreen from '../../../app/(tabs)/wardrobe';
import { useAuthStore } from '../../../features/auth/auth.store';
import { useWardrobeFilterStore } from '../../../features/wardrobe/wardrobe.store';
import type { WardrobeItemRow } from '../../../features/wardrobe/wardrobe.types';

// All mocked child components below return `null` and only record their
// received props via a spy -- no JSX/createElement inside these
// jest.mock() factories, since NativeWind's babel css-interop plugin
// injects a file-scoped helper reference that jest's module-factory
// out-of-scope-variable check then rejects (see WardrobeGrid.test.tsx for
// the same pattern/finding).

const mockPush = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

// SS-014 fix pass (2026-07-27) -- manual-verification finding #2: the
// screen now reads top safe-area insets (useSafeAreaInsets) directly.
// react-native-safe-area-context throws ("No safe area value available")
// without a real <SafeAreaProvider> ancestor and jest-expo doesn't
// auto-mock it -- same pattern already used by CustomTabBar.test.tsx.
jest.mock('react-native-safe-area-context', () => ({
  ...jest.requireActual('react-native-safe-area-context'),
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));

const mockUseNetworkStatus = jest.fn();
jest.mock('../../../hooks/useNetworkStatus', () => ({
  useNetworkStatus: () => mockUseNetworkStatus(),
}));

const mockUsePlanTierQuery = jest.fn();
jest.mock('../../../features/auth/auth.queries', () => ({
  usePlanTierQuery: (...args: unknown[]) => mockUsePlanTierQuery(...args),
}));

const mockRefetchItems = jest.fn();
const mockRefetchCount = jest.fn();
const mockRefetchImageUrls = jest.fn();
const mockUseWardrobeItemsQuery = jest.fn();
const mockUseWardrobeItemCountQuery = jest.fn();
const mockUseWardrobeItemImageUrlsQuery = jest.fn();
jest.mock('../../../features/wardrobe/wardrobe.queries', () => ({
  useWardrobeItemsQuery: (...args: unknown[]) =>
    mockUseWardrobeItemsQuery(...args),
  useWardrobeItemCountQuery: (...args: unknown[]) =>
    mockUseWardrobeItemCountQuery(...args),
  useWardrobeItemImageUrlsQuery: (...args: unknown[]) =>
    mockUseWardrobeItemImageUrlsQuery(...args),
}));

const mockCategoryFilterBarRender = jest.fn();
jest.mock('../../../features/wardrobe/components/CategoryFilterBar', () => ({
  CategoryFilterBar: (props: unknown) => {
    mockCategoryFilterBarRender(props);
    return null;
  },
}));

const mockSearchBarRender = jest.fn();
jest.mock('../../../features/wardrobe/components/SearchBar', () => ({
  SearchBar: () => {
    mockSearchBarRender();
    return null;
  },
}));

const mockWardrobeFilterSheetRender = jest.fn();
jest.mock('../../../features/wardrobe/components/WardrobeFilterSheet', () => ({
  WardrobeFilterSheet: (props: unknown) => {
    mockWardrobeFilterSheetRender(props);
    return null;
  },
}));

const mockWardrobeGridRender = jest.fn();
jest.mock('../../../features/wardrobe/components/WardrobeGrid', () => ({
  WardrobeGrid: (props: unknown) => {
    mockWardrobeGridRender(props);
    return null;
  },
}));

const mockItemDetailSheetRender = jest.fn();
jest.mock('../../../features/wardrobe/components/ItemDetailSheet', () => ({
  ItemDetailSheet: (props: unknown) => {
    mockItemDetailSheetRender(props);
    return null;
  },
}));

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

function setFakeSession() {
  useAuthStore.setState({
    session: {
      user: { id: 'user-1' },
      access_token: 'jwt-token',
      // biome-ignore lint/suspicious/noExplicitAny: minimal fake Session for tests
    } as any,
    isSessionLoading: false,
  });
}

describe('WardrobeScreen (app/(tabs)/wardrobe.tsx)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useWardrobeFilterStore.getState().reset();
    setFakeSession();
    mockUseNetworkStatus.mockReturnValue({ isOffline: false });
    mockUsePlanTierQuery.mockReturnValue({ data: 'free' });
    mockUseWardrobeItemImageUrlsQuery.mockReturnValue({
      data: {},
      refetch: mockRefetchImageUrls,
    });
    mockUseWardrobeItemCountQuery.mockReturnValue({
      data: 0,
      refetch: mockRefetchCount,
    });
  });

  it('loading state renders skeletons, not the grid or empty state', async () => {
    mockUseWardrobeItemsQuery.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      isRefetching: false,
      refetch: mockRefetchItems,
    });

    const { getByTestId, queryByTestId, getAllByTestId } = await render(
      <WardrobeScreen />,
    );

    expect(getByTestId('wardrobe-loading')).toBeOnTheScreen();
    expect(getAllByTestId('skeleton').length).toBeGreaterThan(0);
    expect(queryByTestId('wardrobe-empty-state')).toBeNull();
    expect(mockWardrobeGridRender).not.toHaveBeenCalled();
  });

  it('error state renders a Retry button that calls refetch()', async () => {
    mockUseWardrobeItemsQuery.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      isRefetching: false,
      refetch: mockRefetchItems,
    });

    const { getByLabelText } = await render(<WardrobeScreen />);

    await fireEvent.press(getByLabelText('Retry'));

    expect(mockRefetchItems).toHaveBeenCalled();
  });

  it('items.length === 0 renders the fully-empty EmptyState (heading/subtext/CTA unchanged)', async () => {
    mockUseWardrobeItemsQuery.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
      isRefetching: false,
      refetch: mockRefetchItems,
    });

    const { getByText, getByLabelText } = await render(<WardrobeScreen />);

    expect(getByText('Your wardrobe is empty')).toBeOnTheScreen();
    expect(
      getByText('Add your first item to get outfit suggestions.'),
    ).toBeOnTheScreen();

    await fireEvent.press(getByLabelText('Add your first item'));
    expect(mockPush).toHaveBeenCalledWith('/wardrobe/upload');
  });

  it('non-empty items but empty filteredItems renders the filtered-empty state with distinct copy', async () => {
    const items = [makeItem({ category: 'western_top', brand: 'Zara' })];
    mockUseWardrobeItemsQuery.mockReturnValue({
      data: items,
      isLoading: false,
      isError: false,
      isRefetching: false,
      refetch: mockRefetchItems,
    });
    useWardrobeFilterStore.getState().setSearch('nonexistent-query-xyz');

    const { getByText } = await render(<WardrobeScreen />);

    expect(getByText('No items in this category')).toBeOnTheScreen();
    expect(mockWardrobeGridRender).not.toHaveBeenCalled();
  });

  it('populated state renders CategoryFilterBar + WardrobeGrid', async () => {
    const items = [makeItem()];
    mockUseWardrobeItemsQuery.mockReturnValue({
      data: items,
      isLoading: false,
      isError: false,
      isRefetching: false,
      refetch: mockRefetchItems,
    });

    await render(<WardrobeScreen />);

    expect(mockCategoryFilterBarRender).toHaveBeenCalled();
    expect(mockWardrobeGridRender).toHaveBeenCalledWith(
      expect.objectContaining({ items }),
    );
  });

  it('FreeTierBanner appears at 45+ items for planTier=free, disappears for premium', async () => {
    const items = [makeItem()];
    mockUseWardrobeItemsQuery.mockReturnValue({
      data: items,
      isLoading: false,
      isError: false,
      isRefetching: false,
      refetch: mockRefetchItems,
    });
    mockUseWardrobeItemCountQuery.mockReturnValue({
      data: 45,
      refetch: mockRefetchCount,
    });
    mockUsePlanTierQuery.mockReturnValue({ data: 'free' });

    const { getByTestId, rerender } = await render(<WardrobeScreen />);
    expect(getByTestId('free-tier-banner')).toBeOnTheScreen();

    mockUsePlanTierQuery.mockReturnValue({ data: 'premium' });
    await rerender(<WardrobeScreen />);
    expect(() => getByTestId('free-tier-banner')).toThrow();
  });

  it('floating add-button is disabled + captioned when offline', async () => {
    const items = [makeItem()];
    mockUseWardrobeItemsQuery.mockReturnValue({
      data: items,
      isLoading: false,
      isError: false,
      isRefetching: false,
      refetch: mockRefetchItems,
    });
    mockUseNetworkStatus.mockReturnValue({ isOffline: true });

    const { getByLabelText, getByText } = await render(<WardrobeScreen />);

    const addButton = getByLabelText('Add new item');
    expect(addButton.props.accessibilityState.disabled).toBe(true);
    expect(getByText('No connection')).toBeOnTheScreen();
  });

  it('floating add-button is enabled and routes to /wardrobe/upload when online', async () => {
    const items = [makeItem()];
    mockUseWardrobeItemsQuery.mockReturnValue({
      data: items,
      isLoading: false,
      isError: false,
      isRefetching: false,
      refetch: mockRefetchItems,
    });

    const { getByLabelText } = await render(<WardrobeScreen />);

    await fireEvent.press(getByLabelText('Add new item'));
    expect(mockPush).toHaveBeenCalledWith('/wardrobe/upload');
  });
});
