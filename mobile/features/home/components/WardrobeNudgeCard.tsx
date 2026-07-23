import { useRouter } from 'expo-router';
import { View } from 'react-native';
import { Button, Card, Text } from '../../../components/ui';

// Always rendered (not conditional on an actual wardrobe_items count) — no
// Wardrobe-domain query exists yet to check against (Epic 2, unscheduled).
// Logged as BL-031 (docs/BACKLOG.md): the eventual Wardrobe epic ticket must
// close this by hiding the nudge once a user has >=1 item.
export function WardrobeNudgeCard() {
  const router = useRouter();

  const handleAddItem = () => {
    // No dedicated upload/add-item screen exists yet — routes to the
    // Wardrobe tab's own empty state (also logged under BL-031).
    router.push('/wardrobe');
  };

  return (
    <Card
      testID="wardrobe-nudge-card"
      variant="elevated"
      className="mx-md mt-md"
    >
      <Text variant="heading">Your wardrobe is empty</Text>
      <Text variant="body" color="secondary" className="mt-xs">
        Add your first item to start getting outfit suggestions.
      </Text>
      <View className="mt-sm">
        <Button
          variant="primary"
          onPress={handleAddItem}
          accessibilityLabel="Add your first item"
        >
          Add your first item
        </Button>
      </View>
    </Card>
  );
}
