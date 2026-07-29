// Pure functions only -- no React/Zustand/Supabase imports (CLAUDE.md: "no
// useEffect for derived state -- compute it directly during render"). Called
// via useMemo in app/(tabs)/wardrobe.tsx. Per
// docs/tickets/SS-014-design.md's "Files to create/modify" /
// "Concrete values" sections.

import {
  CATEGORY_GROUPS,
  GRID_COLUMN_BREAKPOINTS,
  GRID_DEFAULT_COLUMNS,
  WARDROBE_CATEGORIES,
} from './wardrobe.constants';
import type {
  CategoryFilterValue,
  CategoryGroup,
  WardrobeCategory,
  WardrobeFilterState,
  WardrobeItemRow,
  WardrobeSortOption,
} from './wardrobe.types';

// SS-014 fix pass (2026-07-27) -- manual-verification finding #1: fixed
// 2-column grid looked poor on wide/desktop viewports. Pure so it's
// unit-testable without mounting useWindowDimensions; called via useMemo
// in WardrobeGrid.tsx (CLAUDE.md: no useEffect for derived data).
export function columnsForWidth(width: number): number {
  const match = GRID_COLUMN_BREAKPOINTS.find(
    (breakpoint) => width >= breakpoint.minWidth,
  );
  return match ? match.columns : GRID_DEFAULT_COLUMNS;
}

export function groupForCategory(
  category: WardrobeCategory | null,
): CategoryGroup | null {
  if (!category) {
    return null;
  }
  return CATEGORY_GROUPS[category] ?? null;
}

const CATEGORY_LABEL_BY_VALUE: Record<string, string> = Object.fromEntries(
  WARDROBE_CATEGORIES.map((option) => [option.value, option.label]),
);

// 'all' = total item count; 'favourites' = is_favourite count, independent
// of category group (an uncategorized favourite still counts here, even
// though it's excluded from every category-group pill below).
export function countsByCategoryFilter(
  items: WardrobeItemRow[],
): Record<CategoryFilterValue, number> {
  const counts: Record<CategoryFilterValue, number> = {
    all: items.length,
    ethnic: 0,
    western: 0,
    footwear: 0,
    accessories: 0,
    favourites: 0,
  };

  for (const item of items) {
    const group = groupForCategory(item.category);
    if (group) {
      counts[group] += 1;
    }
    if (item.is_favourite) {
      counts.favourites += 1;
    }
  }

  return counts;
}

function matchesCategoryFilter(
  item: WardrobeItemRow,
  categoryFilter: CategoryFilterValue,
): boolean {
  if (categoryFilter === 'all') {
    return true;
  }
  if (categoryFilter === 'favourites') {
    return Boolean(item.is_favourite);
  }
  return groupForCategory(item.category) === categoryFilter;
}

// Search fields per the design doc's Concrete values: humanized category
// label + raw category value, brand, and user_notes -- not
// subcategory/fabric/pattern.
function matchesSearch(item: WardrobeItemRow, search: string): boolean {
  const query = search.trim().toLowerCase();
  if (!query) {
    return true;
  }

  const humanizedCategory = item.category
    ? (CATEGORY_LABEL_BY_VALUE[item.category] ?? '')
    : '';
  const haystacks = [
    humanizedCategory,
    item.category ?? '',
    item.brand ?? '',
    item.user_notes ?? '',
  ];

  return haystacks.some((value) => value.toLowerCase().includes(query));
}

// All 4 modes null-safe. cost_per_wear's null-last rule applies regardless
// of direction (Architect's call, design doc's Concrete values).
function compareBySort(
  a: WardrobeItemRow,
  b: WardrobeItemRow,
  sort: WardrobeSortOption,
): number {
  switch (sort) {
    case 'most_worn':
      return (b.wear_count ?? 0) - (a.wear_count ?? 0);
    case 'least_worn':
      return (a.wear_count ?? 0) - (b.wear_count ?? 0);
    case 'cost_per_wear': {
      const aValue = a.cost_per_wear;
      const bValue = b.cost_per_wear;
      if (aValue === null && bValue === null) {
        return 0;
      }
      if (aValue === null) {
        return 1;
      }
      if (bValue === null) {
        return -1;
      }
      return aValue - bValue;
    }
    default:
      return (
        new Date(b.created_at ?? 0).getTime() -
        new Date(a.created_at ?? 0).getTime()
      );
  }
}

export function selectFilteredSortedItems(
  items: WardrobeItemRow[],
  filters: WardrobeFilterState,
): WardrobeItemRow[] {
  const filtered = items.filter((item) => {
    if (!matchesCategoryFilter(item, filters.categoryFilter)) {
      return false;
    }
    // (SS-025) Deliberately a plain string `includes` against the stored
    // slugs, with NO registry membership check: an applied filter on an
    // occasion that has since been deactivated (or that was never in the
    // registry at all, e.g. an unknown AI-emitted slug) must keep matching
    // the items carrying it. Never orphan a user's data because of a
    // taxonomy edit (design §6.2).
    if (
      filters.occasionFilter !== 'all' &&
      !(item.occasion_tags ?? []).includes(filters.occasionFilter)
    ) {
      return false;
    }
    if (
      filters.seasonFilter !== 'all' &&
      !(item.season_tags ?? []).includes(filters.seasonFilter)
    ) {
      return false;
    }
    if (
      filters.colorFilter !== 'all' &&
      item.color_primary !== filters.colorFilter
    ) {
      return false;
    }
    if (!matchesSearch(item, filters.search)) {
      return false;
    }
    return true;
  });

  return [...filtered].sort((a, b) => compareBySort(a, b, filters.sort));
}
