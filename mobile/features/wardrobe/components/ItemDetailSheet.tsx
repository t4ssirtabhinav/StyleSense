import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { forwardRef, useState } from 'react';
import type { ComponentProps } from 'react';
import { ActivityIndicator, Pressable, View } from 'react-native';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withSequence,
  withTiming,
} from 'react-native-reanimated';
import {
  AppBottomSheet,
  type AppBottomSheetRef,
  Badge,
  Card,
  Text,
} from '../../../components/ui';
import { useAuthStore } from '../../auth/auth.store';
import {
  WARDROBE_CATEGORIES,
  WEAR_LOGGED_NO_PRICE_PREFIX,
  WEAR_LOGGED_TODAY_MESSAGE,
  WEAR_LOGGED_WITH_COST_PREFIX,
} from '../wardrobe.constants';
import {
  useDeleteWardrobeItem,
  useLogWardrobeItemWear,
  useOccasionOptions,
  useToggleWardrobeItemFavourite,
  useWardrobeItemImageUrlQuery,
} from '../wardrobe.queries';
import type {
  GarmentTagsDraft,
  OccasionSlug,
  SeasonTag,
  WardrobeItemDetailsDraft,
  WardrobeItemRow,
} from '../wardrobe.types';
import { EditItemTagsForm } from './EditItemTagsForm';
import { istTodayIso } from './WearDateField';
import { WearHistorySection } from './WearHistorySection';
import { WearLoggedToast } from './WearLoggedToast';

export interface ItemDetailSheetProps {
  item: WardrobeItemRow | null;
  jwt: string | undefined;
  onDismiss?: () => void;
}

type ItemDetailSheetMode = 'view' | 'edit' | 'wears';

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
    occasionTags: (item.occasion_tags ?? []) as OccasionSlug[],
    seasonTags: (item.season_tags ?? []) as SeasonTag[],
    confidence: 1,
    contentFlag: 'ok',
    containsPerson: false,
  };
}

// SS-015: brand/purchase_price/purchase_date/user_notes -- the fields
// SS-014's EditItemTagsForm never built.
function toEditableDetailsDraft(
  item: WardrobeItemRow,
): WardrobeItemDetailsDraft {
  return {
    brand: item.brand,
    purchasePrice: item.purchase_price,
    purchaseDate: item.purchase_date,
    userNotes: item.user_notes,
  };
}

// Wear-logged toast copy (design doc's "Concrete values"): never renders
// ₹null/₹NaN when cost_per_wear is null (purchase_price unset).
function buildWearLoggedMessage(
  costPerWear: number | null,
  wornOn: string,
): string {
  if (costPerWear == null) {
    const dateLabel = formatLastWornDate(wornOn) ?? wornOn;
    return `${WEAR_LOGGED_NO_PRICE_PREFIX} ${dateLabel}`;
  }
  return `${WEAR_LOGGED_WITH_COST_PREFIX} ${formatIndianCurrency(costPerWear)}`;
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
  /** SS-015: optional reanimated style applied to the icon (the favourite
   * tile's heart-bounce) -- undefined for every other tile. */
  animatedIconStyle?: ReturnType<typeof useAnimatedStyle>;
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
  animatedIconStyle,
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
      ) : animatedIconStyle ? (
        <Animated.View style={animatedIconStyle}>
          <Ionicons name={icon} size={20} color={iconColor} />
        </Animated.View>
      ) : (
        <Ionicons name={icon} size={20} color={iconColor} />
      )}
      <Text variant="caption" weight="bold" className={textClassName}>
        {label}
      </Text>
    </Pressable>
  );
}

// AppBottomSheet, view/edit/wears mode toggle -- per docs/tickets/
// SS-014-design.md's + SS-015-design.md's Files sections. Fetches the full
// clean/original image via useWardrobeItemImageUrlQuery only when the sheet
// actually opens (an item is set), not the grid's bulk thumbnail.
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
//
// SS-015:
// - "Mark Worn" now logs a dated wear row (useLogWardrobeItemWear) instead
//   of a client-computed wear_count + 1 -- see BL-071. Shows an in-sheet
//   toast with the trigger-recomputed cost per wear.
// - The "Worn N× / Last worn: …" stats block is now a pressable row that
//   opens the new 'wears' mode (WearHistorySection).
// - Delete passes jwt through to useDeleteWardrobeItem (now routed via
//   DELETE /wardrobe/items/{id}, not a direct Supabase delete).
// - Favourite toggle gains a heart-bounce animation on press.
export const ItemDetailSheet = forwardRef<
  AppBottomSheetRef,
  ItemDetailSheetProps
>(({ item, jwt, onDismiss }, ref) => {
  const [mode, setMode] = useState<ItemDetailSheetMode>('view');
  const [deleteArmed, setDeleteArmed] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const userId = useAuthStore((state) => state.session?.user.id);

  const imageUrlQuery = useWardrobeItemImageUrlQuery(item?.id, jwt);
  const toggleFavourite = useToggleWardrobeItemFavourite();
  const logWear = useLogWardrobeItemWear();
  const deleteItem = useDeleteWardrobeItem();
  // (SS-025) Must be called before the `if (!item)` early return below --
  // hooks are unconditional.
  const occasionTaxonomy = useOccasionOptions();

  const heartScale = useSharedValue(1);
  const heartAnimatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: heartScale.value }],
  }));

  if (!item) {
    return (
      <AppBottomSheet ref={ref} onDismiss={onDismiss}>
        {null}
      </AppBottomSheet>
    );
  }

  const handleToggleFavourite = () => {
    heartScale.value = withSequence(
      withTiming(1.35, { duration: 100 }),
      withTiming(1, { duration: 120 }),
    );
    toggleFavourite.mutate({
      itemId: item.id,
      isFavourite: !item.is_favourite,
    });
  };

  const handleMarkWorn = () => {
    if (!userId) {
      return;
    }
    logWear.mutate(
      { itemId: item.id, userId, wornOn: istTodayIso() },
      {
        onSuccess: (result) => {
          setToastMessage(
            result.alreadyLogged
              ? WEAR_LOGGED_TODAY_MESSAGE
              : buildWearLoggedMessage(result.costPerWear, result.wornOn),
          );
        },
      },
    );
  };

  const handleDelete = () => {
    if (!jwt) {
      return;
    }
    if (!deleteArmed) {
      setDeleteArmed(true);
      return;
    }
    deleteItem.mutate(
      { itemId: item.id, jwt },
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
        setToastMessage(null);
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

      {toastMessage ? (
        <WearLoggedToast
          message={toastMessage}
          onDismiss={() => setToastMessage(null)}
        />
      ) : null}

      {mode === 'edit' ? (
        <EditItemTagsForm
          itemId={item.id}
          initialTags={toEditableDraft(item)}
          initialDetails={toEditableDetailsDraft(item)}
          onSaved={handleSaved}
          onCancel={() => setMode('view')}
        />
      ) : mode === 'wears' ? (
        <WearHistorySection
          itemId={item.id}
          purchaseDate={item.purchase_date}
          onBack={() => setMode('view')}
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
            {item.brand ? (
              <Text variant="caption">{`Brand: ${item.brand}`}</Text>
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
            {item.user_notes ? (
              <Text variant="caption">{item.user_notes}</Text>
            ) : null}
          </View>

          <View className="mb-md flex-row flex-wrap gap-xs">
            {/* (SS-025) Always renders a label, even for a slug the active
             * registry no longer contains (deactivated) or never did
             * (unknown AI output) -- `label()` falls back to the humanised
             * slug, so a chip is never blank. Never orphan a user's data
             * because of a taxonomy edit. */}
            {(item.occasion_tags ?? []).map((occasion) => (
              <Badge
                key={occasion}
                testID={`item-detail-occasion-${occasion}`}
                label={occasionTaxonomy.label(occasion)}
                occasion={occasionTaxonomy.badgeColor(occasion)}
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

          <Pressable
            testID="item-detail-wear-stats"
            accessibilityRole="button"
            accessibilityLabel="View wear history"
            onPress={() => setMode('wears')}
            className="mb-md gap-xs"
          >
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
          </Pressable>

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
                animatedIconStyle={heartAnimatedStyle}
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
                loading={logWear.isPending}
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
