import { BottomSheetModalProvider } from '@gorhom/bottom-sheet';
import * as Sentry from '@sentry/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import { useEffect, useState } from 'react';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { useAuth } from '../hooks/useAuth';
import { fontAssets } from '../lib/fonts';
import '../global.css';

export default function RootLayout() {
  const [, fontError] = useFonts(fontAssets);
  // SS-003 gap found: `@tanstack/react-query` was a dependency but nothing
  // in the app tree ever mounted a QueryClientProvider before this ticket —
  // features/auth/auth.queries.ts is the first real consumer of
  // useMutation/useQuery, and both throw at render time without a provider
  // ancestor. Not listed in docs/tickets/SS-003-design.md's "Modified"
  // section (which names only the useAuth() wiring here), but required for
  // this ticket's screens to function at all; a lazy useState initializer
  // keeps the same QueryClient instance across re-renders.
  const [queryClient] = useState(() => new QueryClient());

  // Registers the supabase.auth session listener once, before any screen
  // mounts, so app/(tabs)/_layout.tsx's Auth Guard always has up-to-date
  // session state to read from features/auth/auth.store.ts.
  useAuth();

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
      {/* SS-005 gap found: react-native-safe-area-context was a direct
          dependency but SafeAreaProvider was never mounted anywhere in the
          app tree — app/(tabs)/_layout.tsx's new CustomTabBar receives its
          safe-area insets via the tab-bar navigator (which itself needs a
          SafeAreaProvider ancestor to compute real device insets rather than
          falling back to zeroed initial metrics). Must wrap everything else
          so any current/future useSafeAreaInsets() call resolves correctly. */}
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <BottomSheetModalProvider>
            <Stack screenOptions={{ headerShown: false }} />
          </BottomSheetModalProvider>
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
