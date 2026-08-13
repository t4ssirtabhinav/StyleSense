import { FlashList, type ListRenderItemInfo } from '@shopify/flash-list';
import { useCallback, useMemo } from 'react';
import { useWindowDimensions } from 'react-native';
import { columnsForWidth } from '../wardrobe.selectors';
import type {
  WardrobeItemImageUrlsMap,
  WardrobeItemRow,
} from '../wardrobe.types';
import { ItemCard } from './ItemCard';

export interface WardrobeGridProps {
  items: WardrobeItemRow[];
  imageUrls: WardrobeItemImageUrlsMap;
  onItemPress: (item: WardrobeItemRow) => void;
  refreshing: boolean;
  onRefresh: () => void;
}

// Thin FlashList wrapper (CLAUDE.md: FlashList, not FlatList, for lists that
// can grow). Loading/error/empty states are the *screen*'s job
// (app/(tabs)/wardrobe.tsx), not this component's -- this only renders once
// there's a non-empty filtered array to show (design doc's Files section).
//
// SS-014 fix pass (2026-07-27) -- manual-verification finding #1: numColumns
// is now derived from the current window width (columnsForWidth, computed
// during render via useMemo, not useEffect -- CLAUDE.md) instead of a fixed
// `2`. Verified against the installed @shopify/flash-list@2.3.2 source
// (dist/recyclerview/RecyclerViewManager.js's `get numColumns()` reads
// `this.propsRef.numColumns` live off the current props on every layout
// pass, not a value captured once at mount) -- unlike FlashList v1, this
// version does not need a `key` remount trick to pick up a changed
// numColumns at runtime.
export function WardrobeGrid({
  items,
  imageUrls,
  onItemPress,
  refreshing,
  onRefresh,
}: WardrobeGridProps) {
  const { width } = useWindowDimensions();
  const numColumns = useMemo(() => columnsForWidth(width), [width]);

  const renderItem = useCallback(
    ({ item }: ListRenderItemInfo<WardrobeItemRow>) => (
      <ItemCard item={item} imageUrls={imageUrls} onPress={onItemPress} />
    ),
    [imageUrls, onItemPress],
  );

  return (
    // flex: 1 alone reproduces the WardrobeGrid.tsx-class bug fixed here,
    // but is NOT sufficient by itself on WebKit/Safari: a nested flex child
    // defaults to `min-height: auto`, which lets it refuse to shrink below
    // its own intrinsic content height regardless of `flex: 1` — a classic
    // cross-browser flexbox gotcha (Chrome is more forgiving; Safari is
    // spec-strict here). minHeight: 0 overrides that default explicitly.
    // Every ancestor in this screen's flex-1 chain
    // (app/(tabs)/wardrobe.tsx) needs the same override, not just this
    // component — see that file's matching comment.
    <FlashList
      testID="wardrobe-grid"
      style={{ flex: 1, minHeight: 0 }}
      data={items}
      renderItem={renderItem}
      keyExtractor={(item) => item.id}
      numColumns={numColumns}
      refreshing={refreshing}
      onRefresh={onRefresh}
    />
  );
}
