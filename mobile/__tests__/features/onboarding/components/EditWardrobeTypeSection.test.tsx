import { cleanup, fireEvent, render } from '@testing-library/react-native';
import { EditWardrobeTypeSection } from '../../../../features/onboarding/components/EditWardrobeTypeSection';

const mockMutate = jest.fn();
const mockUseUpdateWardrobeTypeMutation = jest.fn();

jest.mock('../../../../features/onboarding/onboarding.queries', () => ({
  useUpdateWardrobeTypeMutation: () => mockUseUpdateWardrobeTypeMutation(),
}));

describe('EditWardrobeTypeSection', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseUpdateWardrobeTypeMutation.mockReturnValue({
      mutate: mockMutate,
      isPending: false,
      isError: false,
    });
  });

  afterEach(async () => {
    await cleanup();
  });

  it('pre-selects the initial wardrobe type', async () => {
    const { getByText } = await render(
      <EditWardrobeTypeSection
        userId="user-1"
        initialWardrobeType="mostly_ethnic"
      />,
    );

    expect(getByText('Mostly Ethnic').parent).toHaveProp(
      'className',
      expect.stringContaining('border-2'),
    );
  });

  it('selecting a new option deselects the previous one; Save calls the mutation with the new key', async () => {
    const { getByLabelText, getByText } = await render(
      <EditWardrobeTypeSection
        userId="user-1"
        initialWardrobeType="mostly_ethnic"
      />,
    );

    await fireEvent.press(getByLabelText('Mostly Western'));

    expect(getByText('Mostly Ethnic').parent).not.toHaveProp(
      'className',
      expect.stringContaining('border-2'),
    );
    expect(getByText('Mostly Western').parent).toHaveProp(
      'className',
      expect.stringContaining('border-2'),
    );

    await fireEvent.press(getByText('Save'));

    expect(mockMutate).toHaveBeenCalledWith({
      userId: 'user-1',
      wardrobeType: 'mostly_western',
    });
  });

  it('disables Save when no wardrobe type is set yet', async () => {
    const { getByLabelText } = await render(
      <EditWardrobeTypeSection
        userId="user-1"
        initialWardrobeType={undefined}
      />,
    );

    expect(getByLabelText('Save wardrobe type')).toHaveProp(
      'accessibilityState',
      expect.objectContaining({ disabled: true }),
    );
  });
});
