import { Text, View } from 'react-native';

export default function HomeScreen() {
  return (
    <View className="flex-1 items-center justify-center bg-white">
      <Text className="text-xl font-semibold text-dark">StyleSense</Text>
      <Text className="mt-2 text-base text-peacock">Expo Router + NativeWind is working.</Text>
    </View>
  );
}
