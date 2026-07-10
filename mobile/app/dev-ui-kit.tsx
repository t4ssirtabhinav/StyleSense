import { useRef, useState } from 'react';
import { ScrollView, View } from 'react-native';
import {
  AppBottomSheet,
  type AppBottomSheetRef,
  Avatar,
  Badge,
  Button,
  Card,
  IconButton,
  Input,
  Skeleton,
  Text,
} from '../components/ui';

// Storybook-style test screen rendering every component/variant combination.
// Reachable at `/dev-ui-kit` (web-first app); not linked from any tab bar or
// nav — dev-only by convention, not by build-time exclusion (BL-009,
// docs/BACKLOG.md: Expo Router has no dev-only route exclusion mechanism).
export default function DevUiKitScreen() {
  const [textValue, setTextValue] = useState('');
  const [phoneValue, setPhoneValue] = useState('');
  const [searchValue, setSearchValue] = useState('StyleSense');
  const [otpValue, setOtpValue] = useState('');
  const [otpError, setOtpError] = useState('');
  const sheetRef = useRef<AppBottomSheetRef>(null);

  return (
    <ScrollView
      className="flex-1 bg-surfacePrimary"
      contentContainerClassName="gap-md p-md"
    >
      <Text variant="display">Text variants</Text>
      <Text variant="display">Display</Text>
      <Text variant="heading">Heading</Text>
      <Text variant="body">Body</Text>
      <Text variant="caption">Caption</Text>
      <Text variant="mono">Mono</Text>
      <Text variant="body" script="devanagari">
        नमस्ते
      </Text>

      <Text variant="heading">Buttons</Text>
      <View className="gap-sm">
        <Button variant="primary" onPress={() => {}}>
          Primary
        </Button>
        <Button variant="secondary" onPress={() => {}}>
          Secondary
        </Button>
        <Button variant="ghost" onPress={() => {}}>
          Ghost
        </Button>
        <Button variant="primary" loading onPress={() => {}}>
          Loading
        </Button>
        <Button variant="primary" disabled onPress={() => {}}>
          Disabled
        </Button>
      </View>

      <Text variant="heading">Cards</Text>
      <Card variant="elevated">
        <Text variant="body">Elevated card</Text>
      </Card>
      <Card variant="flat">
        <Text variant="body">Flat card</Text>
      </Card>
      <Card variant="outlined">
        <Text variant="body">Outlined card</Text>
      </Card>

      <Text variant="heading">Badges</Text>
      <View className="flex-row flex-wrap gap-sm">
        <Badge label="Wedding" occasion="wedding" />
        <Badge label="Office" occasion="office" />
        <Badge label="Festival" occasion="festival" />
        <Badge label="Casual" occasion="casual" />
        <Badge label="Neutral" />
        <Badge label="Selected" occasion="office" selected />
      </View>

      <Text variant="heading">Avatars</Text>
      <View className="flex-row items-center gap-sm">
        <Avatar name="Aayushi Joshi" size="sm" />
        <Avatar name="Aayushi Joshi" size="md" />
        <Avatar name="Aayushi Joshi" size="lg" />
      </View>

      <Text variant="heading">Inputs</Text>
      <Input
        variant="text"
        label="Name"
        value={textValue}
        onChangeText={setTextValue}
      />
      <Input
        variant="phone"
        label="Phone"
        value={phoneValue}
        onChangeText={setPhoneValue}
      />
      <Input
        variant="search"
        value={searchValue}
        onChangeText={setSearchValue}
      />
      <Input
        variant="otp"
        label="OTP"
        value={otpValue}
        onChangeText={setOtpValue}
        error={otpError}
        onComplete={() => setOtpError('Invalid code')}
      />

      <Text variant="heading">Icon buttons</Text>
      <View className="flex-row gap-sm">
        <IconButton
          icon="heart"
          variant="filled"
          onPress={() => {}}
          accessibilityLabel="Like"
        />
        <IconButton
          icon="heart-outline"
          variant="ghost"
          onPress={() => {}}
          accessibilityLabel="Like"
        />
      </View>

      <Text variant="heading">Skeletons</Text>
      <Skeleton variant="card" />
      <Skeleton variant="listItem" />
      <Skeleton variant="circle" />
      <Skeleton variant="text" />

      <Text variant="heading">Bottom sheet</Text>
      <Button variant="secondary" onPress={() => sheetRef.current?.present()}>
        Open bottom sheet
      </Button>
      <AppBottomSheet ref={sheetRef}>
        <Text variant="body">Bottom sheet content</Text>
      </AppBottomSheet>
    </ScrollView>
  );
}
