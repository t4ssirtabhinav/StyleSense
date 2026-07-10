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
  setupFiles: ['react-native-gesture-handler/jestSetup.js'],
};
