import { fireEvent, render } from '@testing-library/react-native';
import { createRef } from 'react';
import type { AppBottomSheetRef } from '../../../../components/ui';
import { CategoryPicker } from '../../../../features/wardrobe/components/CategoryPicker';
import { WARDROBE_CATEGORIES } from '../../../../features/wardrobe/wardrobe.constants';

jest.mock('@gorhom/bottom-sheet', () => {
  const actual = jest.requireActual('@gorhom/bottom-sheet');
  const react = jest.requireActual('react');
  const reactNative = jest.requireActual('react-native');

  const MockBottomSheetModal = react.forwardRef(
    (props: Record<string, unknown>, ref: React.Ref<unknown>) => {
      const dismissRef = { current: jest.fn() };
      react.useImperativeHandle(ref, () => ({
        present: jest.fn(),
        dismiss: dismissRef.current,
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

describe('CategoryPicker', () => {
  it('opens via present(), lists all 21 categories', async () => {
    const ref = createRef<AppBottomSheetRef>();
    const { getByText } = await render(
      <CategoryPicker ref={ref} onSelect={jest.fn()} />,
    );

    ref.current?.present();

    for (const option of WARDROBE_CATEGORIES) {
      expect(getByText(option.label)).toBeTruthy();
    }
    expect(WARDROBE_CATEGORIES).toHaveLength(21);
  });

  it('typing a filter string narrows the visible rows (substring match, case-insensitive)', async () => {
    const { getByPlaceholderText, findByText, queryByText } = await render(
      <CategoryPicker onSelect={jest.fn()} />,
    );

    fireEvent.changeText(getByPlaceholderText('Search categories'), 'SAREE');

    expect(await findByText('Ethnic Saree')).toBeTruthy();
    expect(queryByText('Western Top')).toBeNull();
  });

  it('selecting a row calls onSelect with the exact category value and dismisses the sheet', async () => {
    const onSelect = jest.fn();
    const ref = createRef<AppBottomSheetRef>();
    const { getByTestId } = await render(
      <CategoryPicker ref={ref} onSelect={onSelect} />,
    );

    fireEvent.press(getByTestId('category-row-ethnic_kurta'));

    expect(onSelect).toHaveBeenCalledWith('ethnic_kurta');
  });
});
