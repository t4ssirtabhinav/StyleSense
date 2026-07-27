import { BottomSheetModal, BottomSheetView } from '@gorhom/bottom-sheet';
import {
  type ReactNode,
  forwardRef,
  useImperativeHandle,
  useMemo,
  useRef,
} from 'react';

export interface AppBottomSheetProps {
  /** Default `['30%', '60%', '90%']` per AC. */
  snapPoints?: Array<string | number>;
  children: ReactNode;
  onDismiss?: () => void;
  /** Default true. */
  enablePanDownToClose?: boolean;
  /**
   * Which `snapPoints` entry `.present()` opens to. Default `0` (the
   * smallest snap point), matching the original behaviour. SS-014 fix pass
   * (2026-07-27, manual-verification findings #3/#5): sheets with real
   * content (ItemDetailSheet/WardrobeFilterSheet) need to open to a usable
   * height without requiring the user to drag first -- passed straight
   * through to `BottomSheetModal`'s own `index` prop (confirmed via the
   * installed `@gorhom/bottom-sheet@5.2.14` source,
   * `lib/typescript/components/bottomSheet/types.d.ts`: "Initial snap point
   * index").
   */
  initialIndex?: number;
}

export interface AppBottomSheetRef {
  present: () => void;
  dismiss: () => void;
}

const DEFAULT_SNAP_POINTS = ['30%', '60%', '90%'];

// Thin wrapper around @gorhom/bottom-sheet's BottomSheetModal. Requires
// <GestureHandlerRootView> + <BottomSheetModalProvider> wrapping the app
// root (added to app/_layout.tsx in this ticket) — any usage without that
// wrapping will crash or silently fail to render at runtime.
export const AppBottomSheet = forwardRef<
  AppBottomSheetRef,
  AppBottomSheetProps
>(
  (
    {
      snapPoints = DEFAULT_SNAP_POINTS,
      children,
      onDismiss,
      enablePanDownToClose = true,
      initialIndex = 0,
    },
    ref,
  ) => {
    const modalRef = useRef<BottomSheetModal>(null);
    const resolvedSnapPoints = useMemo(() => snapPoints, [snapPoints]);

    useImperativeHandle(ref, () => ({
      present: () => modalRef.current?.present(),
      dismiss: () => modalRef.current?.dismiss(),
    }));

    return (
      <BottomSheetModal
        ref={modalRef}
        snapPoints={resolvedSnapPoints}
        index={initialIndex}
        onDismiss={onDismiss}
        enablePanDownToClose={enablePanDownToClose}
      >
        <BottomSheetView className="flex-1 p-md">{children}</BottomSheetView>
      </BottomSheetModal>
    );
  },
);

AppBottomSheet.displayName = 'AppBottomSheet';
