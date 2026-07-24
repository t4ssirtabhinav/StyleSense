import { BottomSheetModalProvider } from '@gorhom/bottom-sheet';
import * as Sentry from '@sentry/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import { useEffect, useState } from 'react';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { ANALYTICS_EVENTS } from '../constants/analyticsEvents';
import { useAnalytics } from '../hooks/useAnalytics';
import { useAuth } from '../hooks/useAuth';
import { initAnalytics } from '../lib/analytics';
import { fontAssets } from '../lib/fonts';
import { initSentry } from '../lib/sentry';
import '../global.css';

// SS-009: both initialised at module scope, before any user-interaction
// code runs — mirrors lib/supabase.ts's existing module-scope createClient()
// side effect. Each init*() function is itself idempotent/no-op-safe, so
// this also tolerates a fast-refresh remount of this module in dev.
initSentry();
initAnalytics();

function RootLayout() {
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

  const { track } = useAnalytics();

  // Edge case: font loading failure must fall back to the system font, not a
  // blank screen. React Native already falls back to the OS default font
  // when a requested custom fontFamily isn't registered, so the render tree
  // below is never gated on `fontsLoaded` — only the error is reported.
  useEffect(() => {
    if (fontError) {
      Sentry.captureException(fontError);
    }
  }, [fontError]);

  // SS-009 AC: "PostHog records an app_opened event on launch." A real side
  // effect (fires exactly once per app launch, not derived render state) —
  // the empty dependency array is intentional, matching `track`'s stable
  // useCallback identity.
  useEffect(() => {
    track(ANALYTICS_EVENTS.APP_OPENED);
  }, [track]);

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

// Standard @sentry/react-native pattern: wraps the root component to also
// capture React render-tree errors, not just the manually-reported
// font-load exception above.
export default Sentry.wrap(RootLayout);
