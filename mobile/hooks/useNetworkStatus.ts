import { useNetworkState } from 'expo-network';

// SS-014: general-purpose, not wardrobe-specific (see
// docs/tickets/SS-014-design.md's Open questions #2). Live-verified against
// the installed `expo-network@56.0.5` (matches this repo's `expo@~56.0.12`)
// package source (`src/Network.ts`/`src/Network.types.ts`) rather than
// assumed from training data: `expo-network` already ships its own
// `useNetworkState()` hook -- `{ type, isConnected, isInternetReachable }`,
// polling `getNetworkStateAsync()` on mount and subscribing to
// `addNetworkStateListener` for change events, with a web implementation
// backed by `navigator.onLine` + the `online`/`offline` window events (this
// app is web-first per CLAUDE.md, and `expo-network`'s web module covers
// that platform too, not just native). No need to add
// `@react-native-community/netinfo` as a new dependency.
//
// `isOffline` reads `isConnected` specifically (not `isInternetReachable`):
// `isInternetReachable` starts `undefined` until the first native check
// resolves, and on iOS is defined to always equal `isConnected` anyway (see
// the package's own `NetworkState.isInternetReachable` doc comment) -- using
// it here would only add a same-value indirection on iOS/web while adding a
// slower-to-settle false-negative window on Android.
//
// Before the first `getNetworkStateAsync()` resolves, `isConnected` is
// `undefined` -- treated as "online" (not offline) so the floating add-item
// button isn't disabled for a flash on cold start.
export interface NetworkStatus {
  isOffline: boolean;
}

export function useNetworkStatus(): NetworkStatus {
  const networkState = useNetworkState();
  return { isOffline: networkState.isConnected === false };
}
