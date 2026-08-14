import { useRouter } from 'expo-router';
import { useCallback } from 'react';
import { View } from 'react-native';
import { Button, Text } from '../../../components/ui';
import { CATEGORY_GROUPS } from '../../wardrobe/wardrobe.constants';
import { useWardrobeFilterStore } from '../../wardrobe/wardrobe.store';
import type { WardrobeCategory } from '../../wardrobe/wardrobe.types';
import {
  ADD_FOOTWEAR_CTA,
  FOOTWEAR_MISMATCH_HEADING,
  FOOTWEAR_MISMATCH_SUBTEXT,
  FOOTWEAR_SECTION_HEADING,
  MISSING_FOOTWEAR_HEADING,
  MISSING_FOOTWEAR_SUBTEXT,
} from '../outfit-ai.constants';
import type { PortfolioItemResponse } from '../outfit-ai.types';
import { OutfitItemStack } from './OutfitItemStack';

export interface FootwearSectionProps {
  item: PortfolioItemResponse;
  testID?: string;
}

// `category_labels` values are the raw WardrobeCategory enum string
// (engine_v2_attribute_scoring.py:332), never re-derived here -- reuses the
// already-exported CATEGORY_GROUPS mapping (SS-014), not a second
// category-classification implementation.
function isFootwearCategory(category: string): boolean {
  return (
    Object.prototype.hasOwnProperty.call(CATEGORY_GROUPS, category) &&
    CATEGORY_GROUPS[category as WardrobeCategory] === 'footwear'
  );
}

// design doc §4.2/§4.3 -- "Best footwear for this outfit". Four render
// states (CLAUDE.md's loading/error/empty-state rule, applied here as
// present/missing/mismatch/nothing):
//   1. footwear present, no gap flag -> heading + single thumbnail
//   2. gap_flags has `missing_footwear` -> nudge + CTA, no thumbnail
//   3. gap_flags has `footwear_formality_mismatch` -> thumbnail + nudge
//      (the pair is still shown -- the caveat sits with it, never suppressed)
//   4. neither flag and no resolvable footwear item (occasion with
//      footwear_required=False, or an item deleted between suggestion and
//      render) -> render nothing. An empty labelled section is the
//      "broken/empty suggestion slot" AC #4 forbids.
// Both flags present is impossible by construction on the backend (SS-024
// design §4.1); if that construction ever breaks, missing_footwear wins
// (there is no thumbnail to show), which the branch order below encodes.
export function FootwearSection({ item, testID }: FootwearSectionProps) {
  const setCategoryFilter = useWardrobeFilterStore(
    (state) => state.setCategoryFilter,
  );
  const router = useRouter();
  const sectionTestID = testID ?? 'footwear-section';

  const handleAddFootwear = useCallback(() => {
    setCategoryFilter('footwear');
    router.push('/(tabs)/wardrobe');
  }, [setCategoryFilter, router]);

  const hasMissingFlag = item.gap_flags.includes('missing_footwear');
  const hasMismatchFlag = item.gap_flags.includes(
    'footwear_formality_mismatch',
  );
  // Deterministic: the first item_ids entry whose category resolves to the
  // footwear group. The current assembler attaches at most one footwear
  // item per candidate, but this never assumes that -- it never renders a
  // second thumbnail under the singular heading either way.
  const footwearItemId = item.item_ids.find((id) => {
    const category = item.category_labels[id];
    return category !== undefined && isFootwearCategory(category);
  });

  if (hasMissingFlag) {
    return (
      <View testID={sectionTestID} className="gap-xs">
        <Text variant="heading" weight="bold">
          {MISSING_FOOTWEAR_HEADING}
        </Text>
        <Text variant="body" color="secondary">
          {MISSING_FOOTWEAR_SUBTEXT}
        </Text>
        <Button
          variant="secondary"
          accessibilityLabel={ADD_FOOTWEAR_CTA}
          onPress={handleAddFootwear}
        >
          {ADD_FOOTWEAR_CTA}
        </Button>
      </View>
    );
  }

  if (!footwearItemId) {
    return null;
  }

  return (
    <View testID={sectionTestID} className="gap-xs">
      <Text variant="heading" weight="bold">
        {FOOTWEAR_SECTION_HEADING}
      </Text>
      <OutfitItemStack itemIds={[footwearItemId]} />
      {hasMismatchFlag ? (
        <View testID="footwear-mismatch-nudge" className="gap-xs">
          <Text variant="body" weight="bold">
            {FOOTWEAR_MISMATCH_HEADING}
          </Text>
          <Text variant="caption" color="secondary">
            {FOOTWEAR_MISMATCH_SUBTEXT}
          </Text>
        </View>
      ) : null}
    </View>
  );
}
