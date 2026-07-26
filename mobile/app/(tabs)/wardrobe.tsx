import { useRouter } from 'expo-router';
import { Button, EmptyState } from '../../components/ui';

// Styled empty state (SS-005). SS-013 gives its CTA a real destination
// (BL-031's "Wardrobe tab CTA has a real destination" half) -- the other
// half (Home nudge hiding once a user has >=1 item) stays SS-014's job.
export default function WardrobeScreen() {
  const router = useRouter();

  const handleAddFirstItem = () => {
    router.push('/wardrobe/upload');
  };

  return (
    <EmptyState
      testID="wardrobe-empty-state"
      icon="shirt-outline"
      heading="Your wardrobe is empty"
      subtext="Add your first item to get outfit suggestions."
    >
      <Button
        variant="primary"
        accessibilityLabel="Add your first item"
        onPress={handleAddFirstItem}
      >
        Add your first item
      </Button>
    </EmptyState>
  );
}
