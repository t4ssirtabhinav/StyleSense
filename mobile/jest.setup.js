// (SS-025) AsyncStorage's official Jest mock.
//
// `lib/storage.ts` (the last-known-good taxonomy cache) imports
// @react-native-async-storage/async-storage at module scope, and
// features/wardrobe/wardrobe.service.ts imports lib/storage.ts — so without
// this, every suite that transitively touches the wardrobe service fails at
// import time with "NativeModule: AsyncStorage is null" (there is no native
// runtime under Jest).
//
// This is the package's own documented Jest integration:
// https://react-native-async-storage.github.io/async-storage/docs/advanced/jest
// Individual suites that need to assert on storage calls still mock the
// module themselves (see __tests__/lib/storage.test.ts); this is only the
// baseline so imports resolve.
jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);
