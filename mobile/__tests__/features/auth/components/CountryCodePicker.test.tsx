import { cleanup, fireEvent, render } from '@testing-library/react-native';
import { createRef } from 'react';
import type { AppBottomSheetRef } from '../../../../components/ui';
import { CountryCodePicker } from '../../../../features/auth/components/CountryCodePicker';

// Same mocking approach as components/ui/__tests__/BottomSheet.test.tsx
// (SS-008's own precedent): always renders children regardless of
// present/dismiss state, since @gorhom/bottom-sheet's real modal defers
// mounting via a native portal that Jest can't exercise.
jest.mock('@gorhom/bottom-sheet', () => {
  const actual = jest.requireActual('@gorhom/bottom-sheet');
  const react = jest.requireActual('react');
  const reactNative = jest.requireActual('react-native');

  const MockBottomSheetModal = react.forwardRef(
    (props: Record<string, unknown>, ref: React.Ref<unknown>) => {
      react.useImperativeHandle(ref, () => ({
        present: jest.fn(),
        dismiss: jest.fn(),
      }));
      return react.createElement(
        reactNative.View,
        { testID: 'mock-bottom-sheet-modal' },
        props.children,
      );
    },
  );
  MockBottomSheetModal.displayName = 'MockBottomSheetModal';

  return {
    ...actual,
    BottomSheetModal: MockBottomSheetModal,
    BottomSheetView: reactNative.View,
  };
});

describe('CountryCodePicker', () => {
  afterEach(async () => {
    await cleanup();
  });

  it('renders the single +91 India row', async () => {
    const { getByLabelText } = await render(<CountryCodePicker />);
    expect(getByLabelText('🇮🇳 India +91')).toBeOnTheScreen();
  });

  it('calls onSelect with +91 and dismisses the sheet on press', async () => {
    const onSelect = jest.fn();
    const ref = createRef<AppBottomSheetRef>();
    const { getByLabelText } = await render(
      <CountryCodePicker ref={ref} onSelect={onSelect} />,
    );

    await fireEvent.press(getByLabelText('🇮🇳 India +91'));

    expect(onSelect).toHaveBeenCalledWith('+91');
  });
});
