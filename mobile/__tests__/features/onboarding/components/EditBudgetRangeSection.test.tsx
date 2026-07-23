import { cleanup, fireEvent, render } from '@testing-library/react-native';
import { EditBudgetRangeSection } from '../../../../features/onboarding/components/EditBudgetRangeSection';

const mockMutate = jest.fn();
const mockUseUpdateBudgetRangeMutation = jest.fn();

jest.mock('../../../../features/onboarding/onboarding.queries', () => ({
  useUpdateBudgetRangeMutation: () => mockUseUpdateBudgetRangeMutation(),
}));

describe('EditBudgetRangeSection', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseUpdateBudgetRangeMutation.mockReturnValue({
      mutate: mockMutate,
      isPending: false,
      isError: false,
    });
  });

  afterEach(async () => {
    await cleanup();
  });

  it('pre-selects the initial budget range', async () => {
    const { getByText } = await render(
      <EditBudgetRangeSection userId="user-1" initialBudgetRange="1000_3000" />,
    );

    expect(getByText('₹1k–3k').parent).toHaveProp(
      'className',
      expect.stringContaining('border-2'),
    );
  });

  it('selecting a new option deselects the previous one; Save calls the mutation with the new key', async () => {
    const { getByText } = await render(
      <EditBudgetRangeSection userId="user-1" initialBudgetRange="1000_3000" />,
    );

    await fireEvent.press(getByText('₹500–1k'));

    expect(getByText('₹1k–3k').parent).not.toHaveProp(
      'className',
      expect.stringContaining('border-2'),
    );
    expect(getByText('₹500–1k').parent).toHaveProp(
      'className',
      expect.stringContaining('border-2'),
    );

    await fireEvent.press(getByText('Save'));

    expect(mockMutate).toHaveBeenCalledWith({
      userId: 'user-1',
      budgetRange: '500_1000',
    });
  });

  it('disables Save when no budget range is set yet', async () => {
    const { getByLabelText } = await render(
      <EditBudgetRangeSection userId="user-1" initialBudgetRange={undefined} />,
    );

    expect(getByLabelText('Save budget range')).toHaveProp(
      'accessibilityState',
      expect.objectContaining({ disabled: true }),
    );
  });
});
