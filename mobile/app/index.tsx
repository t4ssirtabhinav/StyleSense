import { Card, Text } from '../components/ui';

// Disposable smoke test that the new Card/Text components render correctly
// end-to-end (see docs/tickets/SS-008-design.md's migration decision) — SS-005
// (Home Screen Shell) will replace this file's contents entirely.
export default function HomeScreen() {
  return (
    <Card
      testID="home-card"
      variant="flat"
      className="m-md flex-1 items-center justify-center"
    >
      <Text variant="heading">StyleSense</Text>
      <Text variant="body" color="peacock" className="mt-sm">
        Expo Router + NativeWind is working.
      </Text>
      <Text variant="body" color="peacock" className="mt-sm">
        Prod
      </Text>
    </Card>
  );
}
