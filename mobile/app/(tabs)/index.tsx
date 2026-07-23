import { ScrollView } from 'react-native';
import { GreetingHeader } from '../../features/home/components/GreetingHeader';
import { OccasionPillRow } from '../../features/home/components/OccasionPillRow';
import { TrendingPicksPlaceholder } from '../../features/home/components/TrendingPicksPlaceholder';
import { WardrobeNudgeCard } from '../../features/home/components/WardrobeNudgeCard';

// SS-005 (Home Screen Shell + Bottom Tab Navigation): full rewrite, replacing
// SS-008's disposable Card/Text smoke test (see app/(tabs)/_layout.test.tsx's
// history). ScrollView wraps the composition since the screen has more
// content than one viewport on small devices.
export default function HomeScreen() {
  return (
    <ScrollView testID="home-screen" className="flex-1 bg-surfacePrimary">
      <GreetingHeader />
      <OccasionPillRow />
      <WardrobeNudgeCard />
      <TrendingPicksPlaceholder />
    </ScrollView>
  );
}
