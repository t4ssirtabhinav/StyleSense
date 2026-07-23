import { Card, Text } from '../../../components/ui';

// Static placeholder, no data fetch — Epic 6 (Trending Picks) hasn't
// started. Reserved section so the Home layout doesn't need to be
// restructured once that epic lands.
export function TrendingPicksPlaceholder() {
  return (
    <Card
      testID="trending-picks-placeholder"
      variant="flat"
      className="mx-md mb-md mt-md"
    >
      <Text variant="heading">Trending Picks</Text>
      <Text variant="caption" color="muted" className="mt-xs">
        Personalized picks are coming soon.
      </Text>
    </Card>
  );
}
