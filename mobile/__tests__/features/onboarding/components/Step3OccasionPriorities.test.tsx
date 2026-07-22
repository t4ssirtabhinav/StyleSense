import { cleanup, fireEvent, render } from '@testing-library/react-native';
import { Step3OccasionPriorities } from '../../../../features/onboarding/components/Step3OccasionPriorities';
import { useOnboardingStore } from '../../../../features/onboarding/onboarding.store';

const mockRefetch = jest.fn();
const mockUseOnboardingTaxonomiesQuery = jest.fn();

jest.mock('../../../../features/onboarding/onboarding.queries', () => ({
  useOnboardingTaxonomiesQuery: () => mockUseOnboardingTaxonomiesQuery(),
}));

const NINE_OCCASIONS = [
  { key: 'office', label: 'Office', sortOrder: 1 },
  { key: 'wedding', label: 'Wedding', sortOrder: 2 },
  { key: 'festival', label: 'Festival', sortOrder: 3 },
  { key: 'casual', label: 'Casual', sortOrder: 4 },
  { key: 'date', label: 'Date', sortOrder: 5 },
  { key: 'party', label: 'Party', sortOrder: 6 },
  { key: 'college', label: 'College', sortOrder: 7 },
  { key: 'travel', label: 'Travel', sortOrder: 8 },
  { key: 'puja', label: 'Puja', sortOrder: 9 },
];

describe('Step3OccasionPriorities', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  afterEach(async () => {
    await cleanup();
    useOnboardingStore.getState().reset();
  });

  it('renders TaxonomyChipsSkeleton while loading', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: true,
      isError: false,
      isSuccess: false,
      data: undefined,
      refetch: mockRefetch,
    });

    const { getAllByTestId, queryByText } = await render(
      <Step3OccasionPriorities />,
    );

    expect(getAllByTestId('skeleton').length).toBeGreaterThan(0);
    expect(queryByText('Office')).toBeNull();
  });

  it('renders the inline error message + Retry button, and Retry calls refetch', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: false,
      isError: true,
      isSuccess: false,
      data: undefined,
      refetch: mockRefetch,
    });

    const { getByText } = await render(<Step3OccasionPriorities />);

    expect(getByText("Couldn't load occasion options.")).toBeOnTheScreen();
    await fireEvent.press(getByText('Retry'));
    expect(mockRefetch).toHaveBeenCalledTimes(1);
  });

  it('renders the empty-state message when occasionTypes is empty', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: { styleKeywords: [], occasionTypes: [], colourPalette: [] },
      refetch: mockRefetch,
    });

    const { getByText } = await render(<Step3OccasionPriorities />);

    expect(getByText('No options available right now.')).toBeOnTheScreen();
  });

  it('all 9 chips render with the neutral (non-occasion-coloured) Badge style', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: {
        styleKeywords: [],
        occasionTypes: NINE_OCCASIONS,
        colourPalette: [],
      },
      refetch: mockRefetch,
    });

    const { getByText } = await render(<Step3OccasionPriorities />);

    for (const option of NINE_OCCASIONS) {
      const labelNode = getByText(option.label);
      expect(labelNode.parent).toHaveProp(
        'className',
        expect.stringContaining('bg-surfaceSecondary'),
      );
      expect(labelNode.parent).not.toHaveProp(
        'className',
        expect.stringMatching(/bg-occasion/),
      );
    }
  });

  it('selecting a 4th occasion when 3 are already selected does not add a 4th', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: {
        styleKeywords: [],
        occasionTypes: NINE_OCCASIONS,
        colourPalette: [],
      },
      refetch: mockRefetch,
    });

    const { getByLabelText } = await render(<Step3OccasionPriorities />);

    await fireEvent.press(getByLabelText('Office'));
    await fireEvent.press(getByLabelText('Wedding'));
    await fireEvent.press(getByLabelText('Festival'));
    await fireEvent.press(getByLabelText('Casual'));

    expect(useOnboardingStore.getState().occasionsPriority).toEqual([
      'office',
      'wedding',
      'festival',
    ]);
  });
});
