import { fireEvent, render } from '@testing-library/react-native';
import { EditItemTagsForm } from '../../../../features/wardrobe/components/EditItemTagsForm';
import { WARDROBE_CATEGORIES } from '../../../../features/wardrobe/wardrobe.constants';
import type {
  GarmentTagsDraft,
  WardrobeItemDetailsDraft,
} from '../../../../features/wardrobe/wardrobe.types';

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

const mockMutate = jest.fn(
  (_vars: unknown, options?: { onSuccess?: () => void }) => {
    options?.onSuccess?.();
  },
);
const mockSaveDetailsMutate = jest.fn(
  (
    _vars: unknown,
    options?: { onSuccess?: () => void; onError?: () => void },
  ) => {
    options?.onSuccess?.();
  },
);
jest.mock('../../../../features/wardrobe/wardrobe.queries', () => ({
  useSaveWardrobeItemTags: () => ({ mutate: mockMutate, isPending: false }),
  useSaveWardrobeItemDetails: () => ({
    mutate: mockSaveDetailsMutate,
    isPending: false,
  }),
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

const BASE_DETAILS: WardrobeItemDetailsDraft = {
  brand: "Levi's",
  purchasePrice: 2500,
  purchaseDate: '2026-01-01',
  userNotes: 'A gift',
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
        initialDetails={BASE_DETAILS}
        onSaved={jest.fn()}
        onCancel={jest.fn()}
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

  // SS-015 additions.
  it('prefills brand/purchase price (en-IN grouping)/purchase date/notes from the item', async () => {
    const { getByDisplayValue } = await render(
      <EditItemTagsForm
        itemId="item-1"
        initialTags={BASE_TAGS}
        initialDetails={BASE_DETAILS}
        onSaved={jest.fn()}
        onCancel={jest.fn()}
      />,
    );

    expect(getByDisplayValue("Levi's")).toBeOnTheScreen();
    expect(getByDisplayValue('2,500')).toBeOnTheScreen();
    expect(getByDisplayValue('01/01/2026')).toBeOnTheScreen();
    expect(getByDisplayValue('A gift')).toBeOnTheScreen();
  });

  it('the notes counter tracks length and hard-stops at 500 via maxLength', async () => {
    const { getByText, getByDisplayValue } = await render(
      <EditItemTagsForm
        itemId="item-1"
        initialTags={BASE_TAGS}
        initialDetails={BASE_DETAILS}
        onSaved={jest.fn()}
        onCancel={jest.fn()}
      />,
    );

    expect(getByText('6/500')).toBeOnTheScreen();

    const longNote = 'x'.repeat(500);
    await fireEvent.changeText(getByDisplayValue('A gift'), longNote);

    expect(getByText('500/500')).toBeOnTheScreen();
    expect(getByDisplayValue(longNote).props.maxLength).toBe(500);
  });

  it('Save calls useSaveWardrobeItemTags with the edited draft', async () => {
    const { getByLabelText, getByDisplayValue } = await render(
      <EditItemTagsForm
        itemId="item-1"
        initialTags={BASE_TAGS}
        initialDetails={BASE_DETAILS}
        onSaved={jest.fn()}
        onCancel={jest.fn()}
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

  it('Save calls both useSaveWardrobeItemTags and useSaveWardrobeItemDetails; onSaved only fires once both succeed', async () => {
    const onSaved = jest.fn();
    const { getByLabelText } = await render(
      <EditItemTagsForm
        itemId="item-1"
        initialTags={BASE_TAGS}
        initialDetails={BASE_DETAILS}
        onSaved={onSaved}
        onCancel={jest.fn()}
      />,
    );

    await fireEvent.press(getByLabelText('Save'));

    expect(mockMutate).toHaveBeenCalled();
    expect(mockSaveDetailsMutate).toHaveBeenCalledWith(
      { itemId: 'item-1', details: BASE_DETAILS },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
    expect(onSaved).toHaveBeenCalled();
  });

  it('stays open with a retryable error if the details save fails after tags saved', async () => {
    mockSaveDetailsMutate.mockImplementationOnce(
      (_vars: unknown, options?: { onError?: () => void }) => {
        options?.onError?.();
      },
    );
    const onSaved = jest.fn();
    const { getByLabelText, getByTestId } = await render(
      <EditItemTagsForm
        itemId="item-1"
        initialTags={BASE_TAGS}
        initialDetails={BASE_DETAILS}
        onSaved={onSaved}
        onCancel={jest.fn()}
      />,
    );

    await fireEvent.press(getByLabelText('Save'));

    expect(onSaved).not.toHaveBeenCalled();
    expect(getByTestId('edit-item-save-error')).toBeOnTheScreen();
  });

  it('the back button calls onCancel without saving', async () => {
    const onCancel = jest.fn();
    const { getByLabelText } = await render(
      <EditItemTagsForm
        itemId="item-1"
        initialTags={BASE_TAGS}
        initialDetails={BASE_DETAILS}
        onSaved={jest.fn()}
        onCancel={onCancel}
      />,
    );

    await fireEvent.press(getByLabelText('Back to item details'));

    expect(onCancel).toHaveBeenCalled();
    expect(mockMutate).not.toHaveBeenCalled();
  });
});
