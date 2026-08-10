import { Image } from 'expo-image';
import { View } from 'react-native';
import { Text } from '../../../components/ui';
import { useAuthStore } from '../../auth/auth.store';
import { useWardrobeItemImageUrlsQuery } from '../../wardrobe/wardrobe.queries';
import { ITEM_NO_LONGER_IN_WARDROBE_COPY } from '../outfit-ai.constants';

export interface OutfitItemStackProps {
  itemIds: string[];
  testID?: string;
}

const THUMBNAIL_SIZE_PX = 72;

// Stacked expo-image thumbnails driven by the existing bulk image-URL hook
// (useWardrobeItemImageUrlsQuery, SS-014) — never a second bulk-fetch
// implementation. An item id with no resolved image (deleted between
// suggestion and swipe, or between save and a later render) renders the
// "no longer in your wardrobe" placeholder rather than a broken image or a
// crash (the SS-014/SS-015 deleted-item edge case, at the UI layer).
export function OutfitItemStack({ itemIds, testID }: OutfitItemStackProps) {
  const userId = useAuthStore((state) => state.session?.user.id);
  const jwt = useAuthStore((state) => state.session?.access_token);
  const imageUrlsQuery = useWardrobeItemImageUrlsQuery(userId, itemIds, jwt);
  const imageUrls = imageUrlsQuery.data ?? {};

  return (
    <View
      testID={testID ?? 'outfit-item-stack'}
      className="flex-row flex-wrap gap-sm"
    >
      {itemIds.map((itemId) => {
        const info = imageUrls[itemId];
        return (
          <View
            key={itemId}
            testID={`outfit-item-thumbnail-${itemId}`}
            className="items-center justify-center overflow-hidden rounded-md bg-surfaceSecondary"
            style={{ width: THUMBNAIL_SIZE_PX, height: THUMBNAIL_SIZE_PX }}
          >
            {info ? (
              <Image
                testID={`outfit-item-image-${itemId}`}
                source={{ uri: info.url }}
                style={{ width: THUMBNAIL_SIZE_PX, height: THUMBNAIL_SIZE_PX }}
                contentFit="cover"
              />
            ) : (
              <View
                testID={`outfit-item-missing-${itemId}`}
                className="items-center justify-center p-xs"
              >
                <Text
                  variant="caption"
                  color="secondary"
                  className="text-center"
                >
                  {ITEM_NO_LONGER_IN_WARDROBE_COPY}
                </Text>
              </View>
            )}
          </View>
        );
      })}
    </View>
  );
}
