import { render } from '@testing-library/react-native';
import { forwardRef, useImperativeHandle } from 'react';
import { createRef } from 'react';
import { View } from 'react-native';
import {
  AppBottomSheet,
  type AppBottomSheetRef,
} from '../../../components/ui/BottomSheet';

let mockCapturedProps: Record<string, unknown> = {};

jest.mock('@gorhom/bottom-sheet', () => {
  const actual = jest.requireActual('@gorhom/bottom-sheet');
  const react = jest.requireActual('react');
  const reactNative = jest.requireActual('react-native');

  const MockBottomSheetModal = react.forwardRef(
    (props: Record<string, unknown>, ref: React.Ref<unknown>) => {
      mockCapturedProps = props;
      react.useImperativeHandle(ref, () => ({
        present: jest.fn(),
        dismiss: jest.fn(),
      }));
      return reactNative.View
        ? react.createElement(
            reactNative.View,
            { testID: 'mock-bottom-sheet-modal' },
            props.children,
          )
        : null;
    },
  );
  MockBottomSheetModal.displayName = 'MockBottomSheetModal';

  return {
    ...actual,
    BottomSheetModal: MockBottomSheetModal,
    BottomSheetView: reactNative.View,
  };
});

describe('AppBottomSheet', () => {
  beforeEach(() => {
    mockCapturedProps = {};
  });

  it('defaults snapPoints to [30%, 60%, 90%] when not overridden', async () => {
    await render(
      <AppBottomSheet>
        <View />
      </AppBottomSheet>,
    );
    expect(mockCapturedProps.snapPoints).toEqual(['30%', '60%', '90%']);
  });

  it('forwards a custom snapPoints array when provided', async () => {
    await render(
      <AppBottomSheet snapPoints={['50%']}>
        <View />
      </AppBottomSheet>,
    );
    expect(mockCapturedProps.snapPoints).toEqual(['50%']);
  });

  it('defaults initialIndex to 0 (SS-014 fix pass, findings #3/#5)', async () => {
    await render(
      <AppBottomSheet>
        <View />
      </AppBottomSheet>,
    );
    expect(mockCapturedProps.index).toBe(0);
  });

  it("forwards a custom initialIndex through to BottomSheetModal's index prop", async () => {
    await render(
      <AppBottomSheet initialIndex={1}>
        <View />
      </AppBottomSheet>,
    );
    expect(mockCapturedProps.index).toBe(1);
  });

  it('calling ref.current.present() / .dismiss() does not throw', async () => {
    const ref = createRef<AppBottomSheetRef>();
    await render(
      <AppBottomSheet ref={ref}>
        <View />
      </AppBottomSheet>,
    );

    expect(() => ref.current?.present()).not.toThrow();
    expect(() => ref.current?.dismiss()).not.toThrow();
  });
});
