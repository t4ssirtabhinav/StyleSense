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

// Load-bearing, not decoration (2026-08-12 investigation, verified via live
// DOM measurement against the real authenticated route, not just reasoning
// about it): react-native-screens' web `Screen` (the per-route wrapper
// expo-router/ui's <Tabs>/<TabSlot> renders this screen inside --
// node_modules/react-native-screens/lib/.../Screen.web.js) is a plain View
// with `flex: 1, position: 'relative', height: '100%'` and no exposed prop
// to add a `minHeight: 0` override. A column flex item's `min-height: auto`
// default lets its content's intrinsic size win over an explicit
// `height: 100%` when the content wants more room -- this is standard CSS
// flexbox behaviour (reproduces in Chrome, not just Safari; an earlier
// version of this fix wrongly assumed it was Safari-specific). Without
// this, this screen's grid rendered at its full natural content height
// (measured 2320px for 20 items) instead of the ~700px actually available,
// pushing CustomTabBar off the bottom of the viewport.
//
// Fix: take this screen's root out of the flex-sizing negotiation
// entirely. `position: absolute` + `inset: 0` removes it from Screen's
// in-flow content, so Screen no longer has anything to "grow to fit" --
// its own min-height:auto then resolves against nothing, letting its
// `height: 100%` (against ScreenContainer, which app/(tabs)/_layout.tsx's
// own TabSlot `style={{minHeight:0}}` fix bounds correctly) take over
// cleanly. This screen's own internal flex-1/minHeight:0 chain down to the
// grid (unchanged, already correct) then fills that now-correctly-bounded
// box and scrolls internally.
const SCREEN_FILL_STYLE = {
  position: 'absolute' as const,
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
};

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
        className="flex-row flex-wrap p-md"
        style={{ ...SCREEN_FILL_STYLE, paddingTop: insets.top }}
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
      <View style={{ ...SCREEN_FILL_STYLE, paddingTop: insets.top }}>
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
      <View style={{ ...SCREEN_FILL_STYLE, paddingTop: insets.top }}>
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
    // SCREEN_FILL_STYLE takes this screen out of Screen's flex-sizing
    // negotiation entirely (see that constant's own comment for the full
    // "why", verified via live DOM measurement). minHeight: 0 here is a
    // second, independent fix for a second, independent link in the chain
    // -- this screen's OWN internal flex-1 column (CategoryFilterBar, the
    // search row, FreeTierBanner, then the grid) still needs it so the
    // grid (not this outer box) is the thing that scrolls internally.
    <View
      className="flex-1"
      style={{ ...SCREEN_FILL_STYLE, paddingTop: insets.top, minHeight: 0 }}
    >
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
        <View className="flex-1" style={{ minHeight: 0 }}>
          <WardrobeGrid
            items={filteredItems}
            imageUrls={imageUrls}
            onItemPress={handleItemPress}
            refreshing={itemsQuery.isRefetching}
            onRefresh={handleRefresh}
          />
        </View>
      )}

      <ItemDetailSheet ref={detailSheetRef} item={selectedItem} jwt={jwt} />

      {/* Sits inside this screen's own bounded flex-1 box (a real, non-
          overlapping sibling of CustomTabBar now that global.css's html/
          body/#root height fix makes that box terminate exactly where the
          tab bar begins -- see that file's comment). No insets.bottom math
          needed here: the tab bar already reserves the true device-edge/
          home-indicator safe area for itself. `bottom-lg` is just breathing
          room off this box's own bottom edge, per the user's "slight
          margin" ask. */}
      <View className="absolute bottom-lg right-md items-end">
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
