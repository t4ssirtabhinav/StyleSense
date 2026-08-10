import { View } from 'react-native';
import { Badge, Card, IconButton, Text } from '../../../components/ui';
import { useOccasionTaxonomy } from '../../onboarding/onboarding.queries';
import { scoreBadgeLabel } from '../outfit-ai.constants';
import type { PortfolioItemResponse } from '../outfit-ai.types';
import { OutfitItemStack } from './OutfitItemStack';
import { ReasoningDisclosure } from './ReasoningDisclosure';

export interface OutfitCardProps {
  item: PortfolioItemResponse;
  occasionKey: string;
  onAccept: () => void;
  onReject: () => void;
  testID?: string;
}

// One card: item stack, occasion badge, score badge, reasoning disclosure,
// accept/reject actions. Every swipe action is ALSO reachable via a plain
// accessible IconButton pair (design edge cases: web-first, no existing
// gesture-driven component in this repo to inherit a working config from —
// the accessible-button pair is the guarantee AC #2 is satisfiable even if
// the gesture layer degrades on one platform, and it's required for
// accessibility regardless of platform).
export function OutfitCard({
  item,
  occasionKey,
  onAccept,
  onReject,
  testID,
}: OutfitCardProps) {
  const { label, badgeColor } = useOccasionTaxonomy();

  return (
    <Card
      testID={testID ?? 'outfit-card'}
      variant="elevated"
      className="gap-md"
    >
      <OutfitItemStack itemIds={item.item_ids} />

      <View className="flex-row flex-wrap gap-sm">
        <Badge
          testID="outfit-card-occasion-badge"
          label={label(occasionKey)}
          occasion={badgeColor(occasionKey)}
        />
        <Badge
          testID="outfit-card-score-badge"
          label={scoreBadgeLabel(item.total_score)}
        />
      </View>

      <ReasoningDisclosure rationale={item.rationale} />

      <View className="flex-row items-center justify-center gap-lg">
        <IconButton
          icon="close"
          accessibilityLabel="Dismiss this outfit"
          onPress={onReject}
        />
        <IconButton
          icon="checkmark"
          variant="filled"
          accessibilityLabel="Save this outfit"
          onPress={onAccept}
        />
      </View>
    </Card>
  );
}
