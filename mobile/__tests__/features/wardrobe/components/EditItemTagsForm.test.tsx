import { fireEvent, render } from '@testing-library/react-native';
import { EditItemTagsForm } from '../../../../features/wardrobe/components/EditItemTagsForm';
import { WARDROBE_CATEGORIES } from '../../../../features/wardrobe/wardrobe.constants';
import type { GarmentTagsDraft } from '../../../../features/wardrobe/wardrobe.types';

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

const mockMutate = jest.fn();
jest.mock('../../../../features/wardrobe/wardrobe.queries', () => ({
  useSaveWardrobeItemTags: () => ({ mutate: mockMutate, isPending: false }),
}));

const BASE_TAGS: GarmentTagsDraft = {
  category: 'ethnic_kurta',
  subcategory: 'Straight-fit',
  colorPrimary: 'blue',
  colorSecondary: 'white',
  pattern: 'solid',
  fabric: 'cotton',
  occasionTags: ['festival'],
  seasonTags: ['summer'],
  confidence: 0.9,
  contentFlag: 'ok',
  containsPerson: false,
};

describe('EditItemTagsForm', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders CategoryPicker (imported from SS-013) and editable fields pre-filled from the item current tags', async () => {
    const { getByText, getByDisplayValue } = await render(
      <EditItemTagsForm
        itemId="item-1"
        initialTags={BASE_TAGS}
        onSaved={jest.fn()}
      />,
    );

    // Category button pre-filled with the humanized-ish raw category value.
    expect(getByText('ethnic_kurta')).toBeOnTheScreen();
    // CategoryPicker's own rows are present (proves it's the real,
    // unduplicated SS-013 component, not a re-implementation).
    for (const option of WARDROBE_CATEGORIES) {
      expect(getByText(option.label)).toBeOnTheScreen();
    }

    expect(getByDisplayValue('Straight-fit')).toBeOnTheScreen();
    expect(getByDisplayValue('blue')).toBeOnTheScreen();
    expect(getByDisplayValue('white')).toBeOnTheScreen();
    expect(getByDisplayValue('solid')).toBeOnTheScreen();
    expect(getByDisplayValue('cotton')).toBeOnTheScreen();
  });

  it('Save calls useSaveWardrobeItemTags with the edited draft', async () => {
    const { getByLabelText, getByDisplayValue } = await render(
      <EditItemTagsForm
        itemId="item-1"
        initialTags={BASE_TAGS}
        onSaved={jest.fn()}
      />,
    );

    await fireEvent.changeText(getByDisplayValue('Straight-fit'), 'A-line');
    await fireEvent.press(getByLabelText('Save'));

    expect(mockMutate).toHaveBeenCalledWith(
      {
        itemId: 'item-1',
        tags: expect.objectContaining({ subcategory: 'A-line' }),
      },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });
});
