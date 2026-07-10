import { BottomSheetModalProvider } from '@gorhom/bottom-sheet';
import * as Sentry from '@sentry/react-native';
import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import { useEffect } from 'react';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { fontAssets } from '../lib/fonts';
import '../global.css';

export default function RootLayout() {
  const [, fontError] = useFonts(fontAssets);

  // Edge case: font loading failure must fall back to the system font, not a
  // blank screen. React Native already falls back to the OS default font
  // when a requested custom fontFamily isn't registered, so the render tree
  // below is never gated on `fontsLoaded` — only the error is reported.
  useEffect(() => {
    if (fontError) {
      Sentry.captureException(fontError);
    }
  }, [fontError]);

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <BottomSheetModalProvider>
        <Stack screenOptions={{ headerShown: false }} />
      </BottomSheetModalProvider>
    </GestureHandlerRootView>
  );
}
