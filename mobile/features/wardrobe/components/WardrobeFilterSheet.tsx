import { forwardRef, useMemo, useState } from 'react';
import { Pressable, View } from 'react-native';
import {
  AppBottomSheet,
  type AppBottomSheetRef,
  Badge,
  Button,
  Text,
} from '../../../components/ui';
import {
  OCCASION_BADGE_COLOR_MAP,
  OCCASION_TYPES,
  SEASON_TAGS,
  SORT_OPTIONS,
} from '../wardrobe.constants';
import { useWardrobeFilterStore } from '../wardrobe.store';
import type {
  OccasionType,
  SeasonTag,
  WardrobeItemRow,
  WardrobeSortOption,
} from '../wardrobe.types';

export interface WardrobeFilterSheetProps {
  /** Currently-loaded item set -- source of the dynamic colour row (no
   * fixed palette exists for `color_primary`, design doc's Concrete
   * values). */
  items: WardrobeItemRow[];
}

type FilterSectionKey = 'occasion' | 'season' | 'color' | 'sort';

interface FilterSectionDescriptor {
  key: FilterSectionKey;
  label: string;
}

const FILTER_SECTIONS: FilterSectionDescriptor[] = [
  { key: 'occasion', label: 'Occasion' },
  { key: 'season', label: 'Season' },
  { key: 'color', label: 'Colour' },
  { key: 'sort', label: 'Sort by' },
];

const SORT_LABEL_BY_VALUE: Record<WardrobeSortOption, string> =
  Object.fromEntries(
    SORT_OPTIONS.map((option) => [option.value, option.label]),
  ) as Record<WardrobeSortOption, string>;

// AppBottomSheet with an e-commerce-style 2-panel layout -- section headers
// in a left rail, the active section's options in a right panel. "Apply"/
// "Clear" write to useWardrobeFilterStore -- selections are staged locally
// (draft state) until Apply is pressed, per docs/tickets/
// SS-014-design.md's Files section.
//
// SS-014 fix pass (2026-07-27) -- manual-verification finding #5 (the
// ticket's own biggest finding): the previous version stacked every section
// header AND its options in one long vertical column, requiring a drag to
// even see the whole sheet. Rebuilt as a 2-panel layout:
// - `initialIndex={0}` on a taller `snapPoints` pair opens the sheet to a
//   usable height immediately, no drag required.
// - A "Selected" summary row up front (testID `filter-selected-summary`)
//   surfaces every currently-active (non-default) filter as a chip, visible
//   without switching sections -- satisfies "already-selected options must
//   be visible up front".
// - The left rail (testID `filter-section-rail`) shows each section's
//   current value as a caption under its label (also part of "visible up
//   front"), and highlights the active section.
// - The right panel (testID `filter-section-panel`) shows only the active
//   section's options, wrapped horizontally (flex-row flex-wrap) -- mixing
//   vertical (rail) and horizontal (panel/chip-wrap) rhythm instead of one
//   tall column.
export const WardrobeFilterSheet = forwardRef<
  AppBottomSheetRef,
  WardrobeFilterSheetProps
>(({ items }, ref) => {
  const storeOccasion = useWardrobeFilterStore((state) => state.occasionFilter);
  const storeSeason = useWardrobeFilterStore((state) => state.seasonFilter);
  const storeColor = useWardrobeFilterStore((state) => state.colorFilter);
  const storeSort = useWardrobeFilterStore((state) => state.sort);
  const setOccasionFilter = useWardrobeFilterStore(
    (state) => state.setOccasionFilter,
  );
  const setSeasonFilter = useWardrobeFilterStore(
    (state) => state.setSeasonFilter,
  );
  const setColorFilter = useWardrobeFilterStore(
    (state) => state.setColorFilter,
  );
  const setSort = useWardrobeFilterStore((state) => state.setSort);

  const [activeSection, setActiveSection] =
    useState<FilterSectionKey>('occasion');
  const [draftOccasion, setDraftOccasion] = useState<OccasionType | 'all'>(
    storeOccasion,
  );
  const [draftSeason, setDraftSeason] = useState<SeasonTag | 'all'>(
    storeSeason,
  );
  const [draftColor, setDraftColor] = useState<string | 'all'>(storeColor);
  const [draftSort, setDraftSort] = useState<WardrobeSortOption>(storeSort);

  // Dynamically derived -- Array.from(new Set(...)) over the currently-
  // loaded item set's non-null color_primary values (design doc's
  // Concrete values -- no controlled vocabulary for this free-text column).
  const colorOptions = useMemo(
    () =>
      Array.from(
        new Set(
          items
            .map((item) => item.color_primary)
            .filter((value): value is string => Boolean(value)),
        ),
      ),
    [items],
  );

  const sectionSummary: Record<FilterSectionKey, string> = {
    occasion: draftOccasion === 'all' ? 'All' : draftOccasion,
    season: draftSeason === 'all' ? 'All' : draftSeason,
    color: draftColor === 'all' ? 'All' : draftColor,
    sort: SORT_LABEL_BY_VALUE[draftSort],
  };

  const activeFilterChips: Array<{ key: string; label: string }> = [];
  if (draftOccasion !== 'all') {
    activeFilterChips.push({ key: 'occasion', label: draftOccasion });
  }
  if (draftSeason !== 'all') {
    activeFilterChips.push({ key: 'season', label: draftSeason });
  }
  if (draftColor !== 'all') {
    activeFilterChips.push({ key: 'color', label: draftColor });
  }
  if (draftSort !== 'newest') {
    activeFilterChips.push({
      key: 'sort',
      label: SORT_LABEL_BY_VALUE[draftSort],
    });
  }

  const handleApply = () => {
    setOccasionFilter(draftOccasion);
    setSeasonFilter(draftSeason);
    setColorFilter(draftColor);
    setSort(draftSort);
    if (ref && 'current' in ref) {
      ref.current?.dismiss();
    }
  };

  const handleClear = () => {
    setDraftOccasion('all');
    setDraftSeason('all');
    setDraftColor('all');
    setDraftSort('newest');
    setOccasionFilter('all');
    setSeasonFilter('all');
    setColorFilter('all');
    setSort('newest');
  };

  return (
    <AppBottomSheet ref={ref} snapPoints={['75%', '95%']} initialIndex={0}>
      <Text variant="heading" className="mb-sm">
        Filter &amp; sort
      </Text>

      <View
        testID="filter-selected-summary"
        className="mb-md flex-row flex-wrap gap-xs"
      >
        {activeFilterChips.length === 0 ? (
          <Text variant="caption" color="muted">
            No filters applied
          </Text>
        ) : (
          activeFilterChips.map((chip) => (
            <Badge
              key={chip.key}
              testID={`filter-selected-chip-${chip.key}`}
              label={chip.label}
              selected
            />
          ))
        )}
      </View>

      <View className="flex-1 flex-row overflow-hidden rounded-md border border-textMuted">
        <View
          testID="filter-section-rail"
          className="w-2/5 gap-xs border-r border-textMuted bg-surfaceSecondary p-md"
        >
          {FILTER_SECTIONS.map((section) => {
            const isActive = activeSection === section.key;
            return (
              <Pressable
                key={section.key}
                testID={`filter-section-tab-${section.key}`}
                accessibilityRole="button"
                accessibilityLabel={`${section.label} filter section`}
                accessibilityState={{ selected: isActive }}
                onPress={() => setActiveSection(section.key)}
                className={`rounded-md p-sm ${
                  isActive ? 'bg-surfacePrimary' : 'bg-transparent'
                }`}
              >
                <Text
                  variant="body"
                  weight={isActive ? 'bold' : 'regular'}
                  color={isActive ? 'peacock' : 'primary'}
                >
                  {section.label}
                </Text>
                <Text variant="caption" color="muted">
                  {sectionSummary[section.key]}
                </Text>
              </Pressable>
            );
          })}
        </View>

        <View
          testID="filter-section-panel"
          className="flex-1 flex-row flex-wrap content-start gap-sm bg-surfacePrimary p-sm"
        >
          {activeSection === 'occasion'
            ? OCCASION_TYPES.map((occasion) => (
                <Badge
                  key={occasion}
                  testID={`filter-occasion-${occasion}`}
                  label={occasion}
                  occasion={OCCASION_BADGE_COLOR_MAP[occasion]}
                  selected={draftOccasion === occasion}
                  onPress={() => setDraftOccasion(occasion)}
                />
              ))
            : null}
          {activeSection === 'season'
            ? SEASON_TAGS.map((season) => (
                <Badge
                  key={season}
                  testID={`filter-season-${season}`}
                  label={season}
                  selected={draftSeason === season}
                  onPress={() => setDraftSeason(season)}
                />
              ))
            : null}
          {activeSection === 'color'
            ? colorOptions.map((color) => (
                <Badge
                  key={color}
                  testID={`filter-color-${color}`}
                  label={color}
                  selected={draftColor === color}
                  onPress={() => setDraftColor(color)}
                />
              ))
            : null}
          {activeSection === 'sort'
            ? SORT_OPTIONS.map((option) => (
                <Badge
                  key={option.value}
                  testID={`filter-sort-${option.value}`}
                  label={option.label}
                  selected={draftSort === option.value}
                  onPress={() => setDraftSort(option.value)}
                />
              ))
            : null}
        </View>
      </View>

      <View className="flex-row gap-sm pt-md">
        <View className="flex-1">
          <Button
            variant="secondary"
            accessibilityLabel="Clear filters"
            fullWidth
            onPress={handleClear}
          >
            Clear
          </Button>
        </View>
        <View className="flex-1">
          <Button
            variant="primary"
            accessibilityLabel="Apply filters"
            fullWidth
            onPress={handleApply}
          >
            Apply
          </Button>
        </View>
      </View>
    </AppBottomSheet>
  );
});

WardrobeFilterSheet.displayName = 'WardrobeFilterSheet';
