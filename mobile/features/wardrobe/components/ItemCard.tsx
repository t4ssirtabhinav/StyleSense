import { useQueryClient } from '@tanstack/react-query';
import { Image } from 'expo-image';
import { memo, useState } from 'react';
import { Pressable, View } from 'react-native';
import { Badge, Card, IconButton, Text } from '../../../components/ui';
import { useAuthStore } from '../../auth/auth.store';
import { WARDROBE_CATEGORIES } from '../wardrobe.constants';
import {
  useToggleWardrobeItemFavourite,
  wardrobeItemImageUrlsQueryKey,
} from '../wardrobe.queries';
import type {
  WardrobeItemImageUrlsMap,
  WardrobeItemRow,
} from '../wardrobe.types';

export interface ItemCardProps {
  item: WardrobeItemRow;
  imageUrls: WardrobeItemImageUrlsMap;
  onPress: (item: WardrobeItemRow) => void;
}

const CATEGORY_LABEL_BY_VALUE: Record<string, string> = Object.fromEntries(
  WARDROBE_CATEGORIES.map((option) => [option.value, option.label]),
);

const THUMBNAIL_HEIGHT_PX = 160;

function categoryLabel(item: WardrobeItemRow): string {
  if (!item.category) {
    return 'Uncategorized';
  }
  return CATEGORY_LABEL_BY_VALUE[item.category] ?? item.category;
}

// React.memo'd (Technical Note, literal) -- a 2-col FlashList grid can hold
// dozens of these; re-rendering every card on every unrelated filter/sort
// change would defeat FlashList's own virtualization win.
function ItemCardComponent({ item, imageUrls, onPress }: ItemCardProps) {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.session?.user.id);
  const [imageFailed, setImageFailed] = useState(false);
  const toggleFavourite = useToggleWardrobeItemFavourite();

  const imageInfo = imageUrls[item.id];
  const isProcessing =
    item.processing_status === 'uploaded' ||
    item.processing_status === 'bg_processing';
  const isBgPending = item.processing_status === 'bg_pending';

  const handleToggleFavourite = () => {
    toggleFavourite.mutate({
      itemId: item.id,
      isFavourite: !item.is_favourite,
    });
  };

  const handleRetryImage = () => {
    setImageFailed(false);
    queryClient.invalidateQueries({
      queryKey: wardrobeItemImageUrlsQueryKey(userId),
    });
  };

  return (
    // SS-014 fix pass (2026-07-27) -- manual-verification finding #7
    // (shared with SS-019, see that ticket's coordination note): the
    // favourite IconButton used to be a *child* of this Pressable's own
    // subtree, and both render with `accessibilityRole="button"` -- on web
    // that's a literal `<button>` nested inside another `<button>`, which
    // the browser (and React) rejects with a "cannot contain a nested
    // <button>" console error, plus invalid hit-testing/DOM semantics.
    // Restructured so the favourite control is a *sibling*, absolutely
    // positioned over the same visual spot instead of a descendant of the
    // card's own Pressable -- kept minimal and self-contained so it doesn't
    // collide with SS-019's separate pass over this same file.
    <View className="relative m-xs flex-1">
      <Pressable
        testID={`item-card-${item.id}`}
        accessibilityRole="button"
        accessibilityLabel={`${categoryLabel(item)} item`}
        onPress={() => onPress(item)}
      >
        <Card variant="flat">
          <View className="relative">
            {imageInfo && !imageFailed ? (
              <Image
                testID={`item-card-image-${item.id}`}
                source={{ uri: imageInfo.url }}
                style={{ width: '100%', height: THUMBNAIL_HEIGHT_PX }}
                contentFit="contain"
                cachePolicy="memory-disk"
                accessibilityLabel={categoryLabel(item)}
                onError={() => setImageFailed(true)}
              />
            ) : (
              <View
                testID={`item-card-image-fallback-${item.id}`}
                className="items-center justify-center bg-surfaceSecondary"
                style={{ width: '100%', height: THUMBNAIL_HEIGHT_PX }}
              >
                {imageFailed ? (
                  <IconButton
                    icon="refresh"
                    accessibilityLabel="Retry loading photo"
                    onPress={handleRetryImage}
                  />
                ) : null}
              </View>
            )}

            {isProcessing ? (
              <View
                testID={`item-card-processing-overlay-${item.id}`}
                className="absolute inset-0 items-center justify-center bg-textPrimary/40"
              >
                <Text variant="caption" color="secondary">
                  Processing…
                </Text>
              </View>
            ) : null}
            {isBgPending ? (
              <Text
                testID={`item-card-bg-pending-note-${item.id}`}
                variant="caption"
              >
                Background not removed
              </Text>
            ) : null}
          </View>

          <Badge label={categoryLabel(item)} />
          <Text variant="caption">{`Worn ${item.wear_count ?? 0}×`}</Text>
        </Card>
      </Pressable>

      <View className="absolute right-xs top-xs">
        <IconButton
          icon={item.is_favourite ? 'heart' : 'heart-outline'}
          accessibilityLabel={
            item.is_favourite ? 'Remove from favourites' : 'Add to favourites'
          }
          size="sm"
          onPress={handleToggleFavourite}
        />
      </View>
    </View>
  );
}

export const ItemCard = memo(ItemCardComponent);
