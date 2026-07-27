import { useRouter } from 'expo-router';
import { useMemo, useRef, useState } from 'react';
import { View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import {
  type AppBottomSheetRef,
  Button,
  EmptyState,
  IconButton,
  Skeleton,
  Text,
} from '../../components/ui';
import { usePlanTierQuery } from '../../features/auth/auth.queries';
import { useAuthStore } from '../../features/auth/auth.store';
import { CategoryFilterBar } from '../../features/wardrobe/components/CategoryFilterBar';
import { FreeTierBanner } from '../../features/wardrobe/components/FreeTierBanner';
import { ItemDetailSheet } from '../../features/wardrobe/components/ItemDetailSheet';
import { SearchBar } from '../../features/wardrobe/components/SearchBar';
import { WardrobeFilterSheet } from '../../features/wardrobe/components/WardrobeFilterSheet';
import { WardrobeGrid } from '../../features/wardrobe/components/WardrobeGrid';
import {
  NO_ITEMS_IN_CATEGORY_HEADING,
  NO_ITEMS_IN_CATEGORY_SUBTEXT,
  OFFLINE_UPLOAD_DISABLED_MESSAGE,
} from '../../features/wardrobe/wardrobe.constants';
import {
  useWardrobeItemCountQuery,
  useWardrobeItemImageUrlsQuery,
  useWardrobeItemsQuery,
} from '../../features/wardrobe/wardrobe.queries';
import { selectFilteredSortedItems } from '../../features/wardrobe/wardrobe.selectors';
import { useWardrobeFilterStore } from '../../features/wardrobe/wardrobe.store';
import type { WardrobeItemRow } from '../../features/wardrobe/wardrobe.types';
import { useNetworkStatus } from '../../hooks/useNetworkStatus';

const LOADING_SKELETON_COUNT = 6;

// SS-005/SS-013's placeholder EmptyState now becomes the real 2-column
// FlashList catalogue -- per docs/tickets/SS-014-design.md, this ticket's
// core deliverable.
export default function WardrobeScreen() {
  const router = useRouter();
  const userId = useAuthStore((state) => state.session?.user.id);
  const jwt = useAuthStore((state) => state.session?.access_token);
  const { isOffline } = useNetworkStatus();
  // SS-014 fix pass (2026-07-27) -- manual-verification finding #2: this
  // screen has no navigator header (per app/(tabs)/_layout.tsx's headless
  // expo-router/ui Tabs), so its own content was rendering flush against
  // the device's top safe-area/notch with no margin. Same
  // useSafeAreaInsets() already used for the bottom inset in
  // CustomTabBar.tsx.
  const insets = useSafeAreaInsets();

  const itemsQuery = useWardrobeItemsQuery(userId);
  const countQuery = useWardrobeItemCountQuery(userId);
  const planTierQuery = usePlanTierQuery(userId);

  const items = useMemo<WardrobeItemRow[]>(
    () => itemsQuery.data ?? [],
    [itemsQuery.data],
  );
  const itemIds = useMemo(() => items.map((item) => item.id), [items]);
  const imageUrlsQuery = useWardrobeItemImageUrlsQuery(userId, itemIds, jwt);
  const imageUrls = imageUrlsQuery.data ?? {};

  // Individually-selected typed selectors (CLAUDE.md: "Zustand stores:
  // always use typed selectors") -- a selector returning a freshly-built
  // object literal every call (as opposed to a primitive field) makes
  // Zustand's useSyncExternalStore see a "changed" snapshot on every
  // render, which re-triggers the same selector call indefinitely
  // ("Maximum update depth exceeded").
  const categoryFilter = useWardrobeFilterStore(
    (state) => state.categoryFilter,
  );
  const occasionFilter = useWardrobeFilterStore(
    (state) => state.occasionFilter,
  );
  const seasonFilter = useWardrobeFilterStore((state) => state.seasonFilter);
  const colorFilter = useWardrobeFilterStore((state) => state.colorFilter);
  const search = useWardrobeFilterStore((state) => state.search);
  const sort = useWardrobeFilterStore((state) => state.sort);

  const filteredItems = useMemo(
    () =>
      selectFilteredSortedItems(items, {
        categoryFilter,
        occasionFilter,
        seasonFilter,
        colorFilter,
        search,
        sort,
      }),
    [
      items,
      categoryFilter,
      occasionFilter,
      seasonFilter,
      colorFilter,
      search,
      sort,
    ],
  );

  // Holds only the id, not a snapshot of the row itself -- found 2026-07-27:
  // a captured-at-tap-time WardrobeItemRow object never picks up a later
  // cache update (e.g. tagging finishing asynchronously after the grid's
  // list was first fetched, or `staleTime: 5min` simply not having elapsed
  // yet), so a still-open sheet kept showing stale/blank tag fields even
  // after the DB row had real data. Deriving the item live from
  // `itemsQuery.data` below means the sheet always reflects whatever the
  // query cache currently holds for that id.
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const selectedItem = useMemo(
    () => items.find((item) => item.id === selectedItemId) ?? null,
    [items, selectedItemId],
  );
  const filterSheetRef = useRef<AppBottomSheetRef>(null);
  const detailSheetRef = useRef<AppBottomSheetRef>(null);

  const handleRefresh = () => {
    itemsQuery.refetch();
    countQuery.refetch();
    imageUrlsQuery.refetch();
  };

  const handleAddFirstItem = () => {
    router.push('/wardrobe/upload');
  };

  const handleItemPress = (item: WardrobeItemRow) => {
    setSelectedItemId(item.id);
    detailSheetRef.current?.present();
    // Forces a fresh pull the moment the sheet opens, rather than trusting
    // whatever the cache happened to hold (see the state comment above) --
    // cheap (one query, RLS-scoped to the user's own rows) and removes any
    // dependency on staleTime timing for correctness here.
    void itemsQuery.refetch();
  };

  if (itemsQuery.isLoading) {
    return (
      <View
        className="flex-1 flex-row flex-wrap p-md"
        style={{ paddingTop: insets.top }}
        testID="wardrobe-loading"
      >
        {Array.from({ length: LOADING_SKELETON_COUNT }).map((_, index) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: fixed-length skeleton placeholders, not a reorderable list
          <View key={index} className="w-1/2 p-xs">
            <Skeleton variant="card" />
          </View>
        ))}
      </View>
    );
  }

  if (itemsQuery.isError) {
    return (
      <View className="flex-1" style={{ paddingTop: insets.top }}>
        <EmptyState
          testID="wardrobe-error-state"
          icon="alert-circle-outline"
          heading="Couldn't load your wardrobe"
          subtext="Something went wrong. Please try again."
        >
          <Button
            variant="primary"
            accessibilityLabel="Retry"
            onPress={() => itemsQuery.refetch()}
          >
            Retry
          </Button>
        </EmptyState>
      </View>
    );
  }

  if (items.length === 0) {
    return (
      <View className="flex-1" style={{ paddingTop: insets.top }}>
        <EmptyState
          testID="wardrobe-empty-state"
          icon="shirt-outline"
          heading="Your wardrobe is empty"
          subtext="Add your first item to get outfit suggestions."
        >
          <Button
            variant="primary"
            accessibilityLabel="Add your first item"
            onPress={handleAddFirstItem}
          >
            Add your first item
          </Button>
        </EmptyState>
      </View>
    );
  }

  return (
    <View className="flex-1" style={{ paddingTop: insets.top }}>
      <CategoryFilterBar items={items} />
      <View className="flex-row items-center gap-sm px-md">
        <View className="flex-1">
          <SearchBar />
        </View>
        <IconButton
          icon="options"
          accessibilityLabel="Filter and sort"
          onPress={() => filterSheetRef.current?.present()}
        />
      </View>
      <WardrobeFilterSheet ref={filterSheetRef} items={items} />

      <FreeTierBanner
        itemCount={countQuery.data ?? items.length}
        planTier={planTierQuery.data}
      />

      {filteredItems.length === 0 ? (
        <EmptyState
          testID="wardrobe-filtered-empty-state"
          icon="search-outline"
          heading={NO_ITEMS_IN_CATEGORY_HEADING}
          subtext={NO_ITEMS_IN_CATEGORY_SUBTEXT}
        >
          <Button
            variant="primary"
            accessibilityLabel="Add item"
            onPress={handleAddFirstItem}
          >
            Add item
          </Button>
        </EmptyState>
      ) : (
        <WardrobeGrid
          items={filteredItems}
          imageUrls={imageUrls}
          onItemPress={handleItemPress}
          refreshing={itemsQuery.isRefetching}
          onRefresh={handleRefresh}
        />
      )}

      <ItemDetailSheet ref={detailSheetRef} item={selectedItem} jwt={jwt} />

      <View className="absolute bottom-md right-md items-end">
        <IconButton
          icon="add"
          variant="filled"
          accessibilityLabel="Add new item"
          disabled={isOffline}
          onPress={handleAddFirstItem}
        />
        {isOffline ? (
          <Text variant="caption" color="secondary">
            {OFFLINE_UPLOAD_DISABLED_MESSAGE}
          </Text>
        ) : null}
      </View>
    </View>
  );
}
