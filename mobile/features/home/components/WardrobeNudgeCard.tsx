import { useRouter } from 'expo-router';
import { View } from 'react-native';
import { Button, Card, Text } from '../../../components/ui';
import { useAuthStore } from '../../auth/auth.store';
import { useWardrobeItemCountQuery } from '../../wardrobe/wardrobe.queries';

// SS-014 closes BL-031's remaining half: gated on a real, cheap item-count
// query instead of always rendering. Fail-safe: renders null while loading
// and on error (never show "add your first item" to a user whose real
// count is simply unknown), and once count is known to be > 0.
export function WardrobeNudgeCard() {
  const router = useRouter();
  const userId = useAuthStore((state) => state.session?.user.id);
  const countQuery = useWardrobeItemCountQuery(userId);

  const handleAddItem = () => {
    // Bonus fix bundled in (SS-014): routes directly to /wardrobe/upload
    // now that the destination exists, skipping the redundant Wardrobe-tab
    // hop -- only reachable when count is already known to be 0.
    router.push('/wardrobe/upload');
  };

  if (countQuery.isLoading || countQuery.isError) {
    return null;
  }
  if ((countQuery.data ?? 0) > 0) {
    return null;
  }

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
