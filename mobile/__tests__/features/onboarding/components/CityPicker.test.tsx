import { cleanup, fireEvent, render } from '@testing-library/react-native';
import { createRef } from 'react';
import type { AppBottomSheetRef } from '../../../../components/ui';
import { CityPicker } from '../../../../features/onboarding/components/CityPicker';

// Same mocking approach as components/ui/__tests__/BottomSheet.test.tsx /
// features/auth/components/CountryCodePicker.test.tsx (SS-003/SS-008's
// precedent): always renders children regardless of present/dismiss state.
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

describe('CityPicker', () => {
  afterEach(async () => {
    await cleanup();
  });

  it('typing a search query filters the 50-city list to matching names (case-insensitive)', async () => {
    const onSelect = jest.fn();
    const { getByPlaceholderText, getByText, queryByText } = await render(
      <CityPicker onSelect={onSelect} />,
    );

    expect(getByText('Mumbai')).toBeOnTheScreen();
    expect(getByText('Delhi')).toBeOnTheScreen();

    await fireEvent.changeText(getByPlaceholderText('Search city'), 'mum');

    expect(getByText('Mumbai')).toBeOnTheScreen();
    expect(queryByText('Delhi')).toBeNull();
  });

  it('selecting "Other" reveals the free-text input', async () => {
    const onSelect = jest.fn();
    const { getByLabelText, getByPlaceholderText } = await render(
      <CityPicker onSelect={onSelect} />,
    );

    await fireEvent.press(getByLabelText('Other'));

    expect(getByPlaceholderText('Enter your city')).toBeOnTheScreen();
  });

  it('selecting a real city closes the sheet and reports the city name via a callback', async () => {
    const onSelect = jest.fn();
    const ref = createRef<AppBottomSheetRef>();
    const { getByLabelText } = await render(
      <CityPicker ref={ref} onSelect={onSelect} />,
    );

    await fireEvent.press(getByLabelText('Mumbai'));

    expect(onSelect).toHaveBeenCalledWith('Mumbai');
  });
});
