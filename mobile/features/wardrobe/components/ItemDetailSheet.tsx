import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { forwardRef, useState } from 'react';
import type { ComponentProps } from 'react';
import { ActivityIndicator, Pressable, View } from 'react-native';
import {
  AppBottomSheet,
  type AppBottomSheetRef,
  Badge,
  Card,
  Text,
} from '../../../components/ui';
import {
  OCCASION_BADGE_COLOR_MAP,
  WARDROBE_CATEGORIES,
} from '../wardrobe.constants';
import {
  useDeleteWardrobeItem,
  useMarkWardrobeItemWorn,
  useToggleWardrobeItemFavourite,
  useWardrobeItemImageUrlQuery,
} from '../wardrobe.queries';
import type {
  GarmentTagsDraft,
  OccasionType,
  SeasonTag,
  WardrobeItemRow,
} from '../wardrobe.types';
import { EditItemTagsForm } from './EditItemTagsForm';

export interface ItemDetailSheetProps {
  item: WardrobeItemRow | null;
  jwt: string | undefined;
  onDismiss?: () => void;
}

const CATEGORY_LABEL_BY_VALUE: Record<string, string> = Object.fromEntries(
  WARDROBE_CATEGORIES.map((option) => [option.value, option.label]),
);

function categoryLabel(item: WardrobeItemRow): string {
  if (!item.category) {
    return 'Uncategorized';
  }
  return CATEGORY_LABEL_BY_VALUE[item.category] ?? item.category;
}

// 'en-IN' locale, IST timezone -- CLAUDE.md's India-specific date rule.
function formatLastWornDate(iso: string | null): string | null {
  if (!iso) {
    return null;
  }
  return new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(new Date(iso));
}

// ALWAYS ₹1,23,456 Indian numbering -- CLAUDE.md's India-specific currency
// rule.
function formatIndianCurrency(amount: number): string {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount);
}

function toEditableDraft(item: WardrobeItemRow): GarmentTagsDraft {
  return {
    category: item.category,
    subcategory: item.subcategory,
    colorPrimary: item.color_primary,
    colorSecondary: item.color_secondary,
    pattern: item.pattern,
    fabric: item.fabric,
    occasionTags: (item.occasion_tags ?? []) as OccasionType[],
    seasonTags: (item.season_tags ?? []) as SeasonTag[],
    confidence: 1,
    contentFlag: 'ok',
    containsPerson: false,
  };
}

interface ActionTileProps {
  icon: ComponentProps<typeof Ionicons>['name'];
  label: string;
  accessibilityLabel: string;
  onPress: () => void;
  loading?: boolean;
  /** NativeWind bg-* class -- one of this design system's existing accent
   * tokens (tailwind.config.js), never an invented colour. */
  bgClassName: string;
  /** 'text-white' for the darker accents (peacock/emerald/rose/textPrimary),
   * 'text-textPrimary' for the lighter marigold -- same pairing rule
   * Button.tsx already uses for its own variants. */
  textClassName: string;
  iconColor: string;
}

// SS-014 fix pass (2026-07-27) -- manual-verification finding #3: the 2x2
// action grid (Favourite/Edit/Mark Worn/Delete), each tile with both an
// icon *and* a text label, real spacing, and a distinct background colour
// with some visual character -- reusing this design system's existing
// accent tokens (bg-rose/bg-peacock/bg-emerald/bg-textPrimary, all already
// mirrored in tailwind.config.js), not new ones. Deliberately not built as
// a new components/ui primitive (this ticket's own established precedent,
// design doc's Files section) -- local to this one sheet.
function ActionTile({
  icon,
  label,
  accessibilityLabel,
  onPress,
  loading = false,
  bgClassName,
  textClassName,
  iconColor,
}: ActionTileProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      accessibilityState={{ disabled: loading }}
      disabled={loading}
      onPress={onPress}
      className={`flex-1 flex-row items-center justify-center gap-xs rounded-md p-sm ${bgClassName} ${
        loading ? 'opacity-70' : ''
      }`}
    >
      {loading ? (
        <ActivityIndicator testID="action-tile-spinner" color={iconColor} />
      ) : (
        <Ionicons name={icon} size={20} color={iconColor} />
      )}
      <Text variant="caption" weight="bold" className={textClassName}>
        {label}
      </Text>
    </Pressable>
  );
}

// AppBottomSheet, view/edit mode toggle -- per docs/tickets/
// SS-014-design.md's Files section. Fetches the full clean/original image
// via useWardrobeItemImageUrlQuery only when the sheet actually opens (an
// item is set), not the grid's bulk thumbnail.
//
// SS-014 fix pass (2026-07-27), manual-verification findings #3/#4:
// - Added a header (handle + item title) so the sheet always identifies
//   itself, even at its smallest snap point, and opens at `initialIndex={1}`
//   (60%) so a usable height is visible without the user having to drag
//   first.
// - The image is now framed in a Card instead of sitting frameless against
//   the tags below it.
// - Tags wrap horizontally (flex-row flex-wrap) instead of stacking
//   one-per-row.
// - The 4 actions are a 2x2 grid of icon+label ActionTiles (see above)
//   instead of 4 stacked plain Buttons.
// - The favourite action's visible label no longer flips to "Favourited"
//   (finding #4) -- the heart icon's fill state alone carries the meaning;
//   the label stays the neutral "Favourite" in both states (only the
//   accessibilityLabel toggles, for screen readers).
export const ItemDetailSheet = forwardRef<
  AppBottomSheetRef,
  ItemDetailSheetProps
>(({ item, jwt, onDismiss }, ref) => {
  const [mode, setMode] = useState<'view' | 'edit'>('view');
  const [deleteArmed, setDeleteArmed] = useState(false);

  const imageUrlQuery = useWardrobeItemImageUrlQuery(item?.id, jwt);
  const toggleFavourite = useToggleWardrobeItemFavourite();
  const markWorn = useMarkWardrobeItemWorn();
  const deleteItem = useDeleteWardrobeItem();

  if (!item) {
    return (
      <AppBottomSheet ref={ref} onDismiss={onDismiss}>
        {null}
      </AppBottomSheet>
    );
  }

  const handleToggleFavourite = () => {
    toggleFavourite.mutate({
      itemId: item.id,
      isFavourite: !item.is_favourite,
    });
  };

  const handleMarkWorn = () => {
    markWorn.mutate({
      itemId: item.id,
      nextWearCount: (item.wear_count ?? 0) + 1,
    });
  };

  const handleDelete = () => {
    if (!deleteArmed) {
      setDeleteArmed(true);
      return;
    }
    deleteItem.mutate(
      { itemId: item.id },
      {
        onSuccess: () => {
          setDeleteArmed(false);
          if (ref && 'current' in ref) {
            ref.current?.dismiss();
          }
        },
      },
    );
  };

  const handleSaved = () => {
    setMode('view');
  };

  const lastWornDate = formatLastWornDate(item.last_worn_at);

  return (
    <AppBottomSheet
      ref={ref}
      initialIndex={1}
      scrollable
      onDismiss={() => {
        setMode('view');
        setDeleteArmed(false);
        onDismiss?.();
      }}
    >
      <View
        testID="item-detail-sheet-header"
        className="mb-md items-center gap-xs"
      >
        <View className="h-1 w-10 rounded-pill bg-textMuted" />
        <Text variant="heading">{categoryLabel(item)}</Text>
      </View>

      {mode === 'edit' ? (
        <EditItemTagsForm
          itemId={item.id}
          initialTags={toEditableDraft(item)}
          onSaved={handleSaved}
          onCancel={() => setMode('view')}
        />
      ) : (
        <>
          <Card
            variant="outlined"
            className="mb-md items-center justify-center overflow-hidden"
          >
            {imageUrlQuery.data ? (
              <Image
                testID="item-detail-image"
                source={{ uri: imageUrlQuery.data.url }}
                style={{ width: '100%', height: 300 }}
                contentFit="contain"
                accessibilityLabel={categoryLabel(item)}
              />
            ) : null}
          </Card>

          <View className="mb-md gap-xs">
            {item.subcategory ? (
              <Text variant="body">{item.subcategory}</Text>
            ) : null}
            {item.color_primary ? (
              <Text variant="caption">{`Colour: ${item.color_primary}${
                item.color_secondary ? `, ${item.color_secondary}` : ''
              }`}</Text>
            ) : null}
            {item.pattern ? (
              <Text variant="caption">{`Pattern: ${item.pattern}`}</Text>
            ) : null}
            {item.fabric ? (
              <Text variant="caption">{`Fabric: ${item.fabric}`}</Text>
            ) : null}
          </View>

          <View className="mb-md flex-row flex-wrap gap-xs">
            {(item.occasion_tags ?? []).map((occasion) => (
              <Badge
                key={occasion}
                testID={`item-detail-occasion-${occasion}`}
                label={occasion}
                occasion={OCCASION_BADGE_COLOR_MAP[occasion as OccasionType]}
              />
            ))}
            {(item.season_tags ?? []).map((season) => (
              <Badge
                key={season}
                testID={`item-detail-season-${season}`}
                label={season}
              />
            ))}
          </View>

          <View className="mb-md gap-xs">
            <Text variant="caption">{`Worn ${item.wear_count ?? 0}×`}</Text>
            {lastWornDate ? (
              <Text variant="caption">{`Last worn: ${lastWornDate}`}</Text>
            ) : null}
            {item.purchase_price != null ? (
              <Text variant="caption">
                {`Purchased for ${formatIndianCurrency(item.purchase_price)}${
                  item.purchase_date
                    ? ` on ${formatLastWornDate(item.purchase_date)}`
                    : ''
                }`}
              </Text>
            ) : null}
          </View>

          <View className="gap-sm">
            <View className="flex-row gap-sm">
              <ActionTile
                icon={item.is_favourite ? 'heart' : 'heart-outline'}
                label="Favourite"
                accessibilityLabel={
                  item.is_favourite
                    ? 'Remove from favourites'
                    : 'Add to favourites'
                }
                onPress={handleToggleFavourite}
                loading={toggleFavourite.isPending}
                bgClassName="bg-rose"
                textClassName="text-white"
                iconColor="#FFFFFF"
              />
              <ActionTile
                icon="create-outline"
                label="Edit"
                accessibilityLabel="Edit"
                onPress={() => setMode('edit')}
                bgClassName="bg-peacock"
                textClassName="text-white"
                iconColor="#FFFFFF"
              />
            </View>
            <View className="flex-row gap-sm">
              <ActionTile
                icon="checkmark-done-outline"
                label="Mark Worn"
                accessibilityLabel="Mark Worn"
                onPress={handleMarkWorn}
                loading={markWorn.isPending}
                bgClassName="bg-emerald"
                textClassName="text-white"
                iconColor="#FFFFFF"
              />
              <ActionTile
                icon="trash-outline"
                label={deleteArmed ? 'Confirm delete' : 'Delete'}
                accessibilityLabel={
                  deleteArmed ? 'Tap again to confirm delete' : 'Delete'
                }
                onPress={handleDelete}
                loading={deleteItem.isPending}
                bgClassName={deleteArmed ? 'bg-rose' : 'bg-textPrimary'}
                textClassName="text-white"
                iconColor="#FFFFFF"
              />
            </View>
          </View>
        </>
      )}
    </AppBottomSheet>
  );
});

ItemDetailSheet.displayName = 'ItemDetailSheet';
