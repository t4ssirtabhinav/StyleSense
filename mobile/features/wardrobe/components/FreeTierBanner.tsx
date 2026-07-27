import { Card, Text } from '../../../components/ui';
import type { PlanTier } from '../../auth/auth.types';
import { FREE_TIER_WARNING_THRESHOLD } from '../wardrobe.constants';

export interface FreeTierBannerProps {
  itemCount: number;
  planTier: PlanTier | null | undefined;
}

const PREMIUM_TIERS: PlanTier[] = ['premium', 'premium_annual'];

// Card shown only when !isPremium && itemCount >= FREE_TIER_WARNING_THRESHOLD
// -- per docs/tickets/SS-014-design.md's Concrete values (literal copy).
export function FreeTierBanner({ itemCount, planTier }: FreeTierBannerProps) {
  const isPremium = Boolean(planTier && PREMIUM_TIERS.includes(planTier));

  if (isPremium || itemCount < FREE_TIER_WARNING_THRESHOLD) {
    return null;
  }

  return (
    <Card testID="free-tier-banner" variant="outlined" className="mx-md mt-sm">
      <Text variant="body">
        {`You're approaching the free plan's 50-item limit (${itemCount}/50). Upgrade to premium for unlimited items.`}
      </Text>
    </Card>
  );
}
