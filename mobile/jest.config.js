module.exports = {
  preset: 'jest-expo',
  collectCoverageFrom: [
    'features/**/*.{ts,tsx}',
    'components/ui/**/*.{ts,tsx}',
  ],
  // react-native-reanimated v4 (via react-native-worklets) requires a native
  // module that isn't initialised under plain Jest — use reanimated's own
  // official test mock (Skeleton's shimmer, Input's shake) so components
  // that call useSharedValue/useAnimatedStyle/withTiming/withRepeat can
  // render in tests without a native runtime. `react-native-worklets`'s own
  // jest resolver steers its internal requires away from the `.native.ts`
  // entry points (which call into the native module) toward its plain-JS
  // fallback, per https://docs.swmansion.com/react-native-worklets/docs/guides/troubleshooting.
  moduleNameMapper: {
    '^react-native-reanimated$': 'react-native-reanimated/mock',
  },
  resolver: 'react-native-worklets/jest/resolver.js',
  // react-native-gesture-handler's own official jest setup (mocks its native
  // module) — BottomSheet.tsx and app/_layout.tsx's GestureHandlerRootView
  // otherwise schedule a native binding install that fails under Jest.
  //
  // @shopify/flash-list's own official jest setup (SS-004) — mocks its
  // internal measureLayout helpers with fixed dimensions so v2's
  // RecyclerView-based engine can actually measure/render items under Jest
  // (no real native layout pass exists in this environment). Without this,
  // app/(auth)/onboarding.tsx's 4-item step pager renders zero items in
  // tests.
  setupFiles: [
    'react-native-gesture-handler/jestSetup.js',
    '@shopify/flash-list/jestSetup.js',
  ],
  // jest-expo's own default transformIgnorePatterns (jest-preset.js) doesn't
  // include @shopify/flash-list, whose dist/index.js ships untranspiled ESM
  // `import` syntax — without this override, any file importing FlashList
  // fails with "Cannot use import statement outside a module". Same base
  // pattern as jest-expo's default, with @shopify/flash-list added (SS-004).
  transformIgnorePatterns: [
    '/node_modules/(?!(.pnpm|react-native|@react-native|@react-native-community|expo|@expo|@expo-google-fonts|react-navigation|@react-navigation|@sentry/react-native|native-base|standard-navigation|@shopify/flash-list))',
    '/node_modules/react-native-reanimated/plugin/',
    '/node_modules/@react-native/babel-preset/',
  ],
};
