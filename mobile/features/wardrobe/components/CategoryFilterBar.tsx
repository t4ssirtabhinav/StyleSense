import { ScrollView } from 'react-native';
import { Badge } from '../../../components/ui';
import { CATEGORY_FILTER_PILLS } from '../wardrobe.constants';
import { countsByCategoryFilter } from '../wardrobe.selectors';
import { useWardrobeFilterStore } from '../wardrobe.store';
import type { CategoryFilterValue, WardrobeItemRow } from '../wardrobe.types';

export interface CategoryFilterBarProps {
  items: WardrobeItemRow[];
}

// One Badge (~32px) + py-sm top/bottom (~16px) + border. A hard ceiling so
// react-native-web's `flexGrow: 1` ScrollView base style can never inflate
// this row -- see the comment on the ScrollView below.
const CATEGORY_FILTER_BAR_MAX_HEIGHT = 56;

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
    // react-native-web's ScrollView ships `flexGrow: 1` in its own base
    // style (node_modules/react-native-web/dist/exports/ScrollView/index.js's
    // `commonStyle`, applied to BOTH horizontal and vertical variants), so
    // this horizontal pill row grows to fill all remaining vertical space in
    // the screen's flex-column layout unless something stops it.
    //
    // SS-014's fix pass (2026-07-27) tried to stop it with a `flex-none`
    // *className*. Re-verified 2026-08-12 against a real browser: that does
    // NOT hold in the current bundle -- the row was still growing, with
    // `contentContainerClassName="items-center"` (cross-axis == VERTICAL for
    // a horizontal ScrollView) centering the pills inside the grown box.
    // That produced a large gap BOTH above and below the pills, pushed the
    // search bar to mid-screen, and inflated the whole screen's height
    // enough to push the tab bar and FAB off the visual viewport.
    //
    // Fixed here with the `style` prop instead of a className -- RN's merge
    // order (`[baseStyle, ..., props.style]`) gives it last-writer
    // precedence over the library's own base style -- plus an explicit
    // `maxHeight` so the row physically cannot grow regardless of how any
    // future flex default resolves. Height is a real ceiling, not a
    // heuristic: it just has to clear one Badge plus its py-sm padding.
    <ScrollView
      testID="category-filter-bar"
      horizontal
      showsHorizontalScrollIndicator={false}
      style={{
        flexGrow: 0,
        flexShrink: 0,
        flexBasis: 'auto',
        maxHeight: CATEGORY_FILTER_BAR_MAX_HEIGHT,
      }}
      className="border-b border-textMuted/40 bg-surfacePrimary py-sm"
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
