import { ScrollView } from 'react-native';
import { Badge } from '../../../components/ui';
import { CATEGORY_FILTER_PILLS } from '../wardrobe.constants';
import { countsByCategoryFilter } from '../wardrobe.selectors';
import { useWardrobeFilterStore } from '../wardrobe.store';
import type { CategoryFilterValue, WardrobeItemRow } from '../wardrobe.types';

export interface CategoryFilterBarProps {
  items: WardrobeItemRow[];
}

// Sticky horizontal row of Badge chips, one per CATEGORY_FILTER_PILLS entry,
// label suffixed with the live count from countsByCategoryFilter (e.g.
// "Ethnic (12)") -- per docs/tickets/SS-014-design.md.
export function CategoryFilterBar({ items }: CategoryFilterBarProps) {
  const categoryFilter = useWardrobeFilterStore(
    (state) => state.categoryFilter,
  );
  const setCategoryFilter = useWardrobeFilterStore(
    (state) => state.setCategoryFilter,
  );
  const counts = countsByCategoryFilter(items);

  const handleSelect = (value: CategoryFilterValue) => {
    setCategoryFilter(value);
  };

  return (
    // SS-014 fix pass (2026-07-27) -- manual-verification finding #2 (root
    // cause, not a cosmetic patch): react-native-web's ScrollView ships
    // `flexGrow: 1` in its own base style (node_modules/react-native-web/
    // dist/exports/ScrollView/index.js's `commonStyle`, applied to BOTH
    // horizontal and vertical variants), and RN's own array-style merge
    // order (`[baseStyle, ..., this.props.style]`) lets our className
    // override it -- verified by reading that source directly. Without
    // `flex-none` here, this horizontal tag row was growing to fill all
    // remaining vertical space in the screen's flex-column layout (its
    // parent is `flex-1`), which is what produced the "large unexplained
    // gap" between the tag row and the search bar below it. `py-sm` +
    // `border-b` are the bundled visual-treatment polish (also flagged in
    // the same finding) -- a little breathing room and a hairline
    // separation from the search bar underneath.
    <ScrollView
      testID="category-filter-bar"
      horizontal
      showsHorizontalScrollIndicator={false}
      className="flex-none border-b border-textMuted/20 py-sm"
      contentContainerClassName="items-center gap-sm px-md"
    >
      {CATEGORY_FILTER_PILLS.map((pill) => (
        <Badge
          key={pill.value}
          testID={`category-filter-pill-${pill.value}`}
          label={`${pill.label} (${counts[pill.value]})`}
          selected={categoryFilter === pill.value}
          onPress={() => handleSelect(pill.value)}
        />
      ))}
    </ScrollView>
  );
}
