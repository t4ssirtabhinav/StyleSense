import { cleanup, fireEvent, render } from '@testing-library/react-native';
import { Step1BasicProfile } from '../../../../features/onboarding/components/Step1BasicProfile';
import { useOnboardingStore } from '../../../../features/onboarding/onboarding.store';

// Same mocking approach as CityPicker.test.tsx — Step1BasicProfile renders
// CityPicker (wrapping AppBottomSheet) directly.
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

describe('Step1BasicProfile', () => {
  afterEach(async () => {
    await cleanup();
    useOnboardingStore.getState().reset();
  });

  it('selecting each of the 4 gender chips updates the store (single-select — selecting a second deselects the first)', async () => {
    const { getByLabelText } = await render(<Step1BasicProfile />);

    await fireEvent.press(getByLabelText('Woman'));
    expect(useOnboardingStore.getState().gender).toBe('woman');

    await fireEvent.press(getByLabelText('Man'));
    expect(useOnboardingStore.getState().gender).toBe('man');

    await fireEvent.press(getByLabelText('Non-binary'));
    expect(useOnboardingStore.getState().gender).toBe('non_binary');

    await fireEvent.press(getByLabelText('Prefer not to say'));
    expect(useOnboardingStore.getState().gender).toBe('prefer_not_to_say');
  });

  it('"Other" city with empty text shows the field-level error path', async () => {
    const { getByLabelText, findByText } = await render(<Step1BasicProfile />);

    await fireEvent.press(getByLabelText('Select city'));
    await fireEvent.press(getByLabelText('Other'));

    expect(await findByText('Please enter your city name.')).toBeOnTheScreen();
  });
});
