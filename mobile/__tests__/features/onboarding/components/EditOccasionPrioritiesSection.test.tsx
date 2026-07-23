import { cleanup, fireEvent, render } from '@testing-library/react-native';
import { EditOccasionPrioritiesSection } from '../../../../features/onboarding/components/EditOccasionPrioritiesSection';

const mockMutate = jest.fn();
const mockUseUpdateOccasionPrioritiesMutation = jest.fn();

jest.mock('../../../../features/onboarding/onboarding.queries', () => ({
  useUpdateOccasionPrioritiesMutation: () =>
    mockUseUpdateOccasionPrioritiesMutation(),
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

const TAXONOMIES = {
  styleKeywords: [],
  occasionTypes: NINE_OCCASIONS,
  colourPalette: [],
};

function renderSection(initialOccasions: string[] = []) {
  return render(
    <EditOccasionPrioritiesSection
      userId="user-1"
      initialOccasions={initialOccasions}
      taxonomies={TAXONOMIES}
      isTaxonomiesLoading={false}
      isTaxonomiesError={false}
      onRetryTaxonomies={jest.fn()}
    />,
  );
}

describe('EditOccasionPrioritiesSection', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseUpdateOccasionPrioritiesMutation.mockReturnValue({
      mutate: mockMutate,
      isPending: false,
      isError: false,
    });
  });

  afterEach(async () => {
    await cleanup();
  });

  it('renders pre-selected chips matching the passed-in occasions_priority array', async () => {
    const { getByText } = await renderSection(['office', 'wedding']);

    expect(getByText('Office').parent).toHaveProp(
      'className',
      expect.stringContaining('border-2'),
    );
    expect(getByText('Wedding').parent).toHaveProp(
      'className',
      expect.stringContaining('border-2'),
    );
    expect(getByText('Festival').parent).not.toHaveProp(
      'className',
      expect.stringContaining('border-2'),
    );
  });

  it('selecting a 4th occasion when 3 are already selected does not add a 4th', async () => {
    const { getByLabelText, getByText } = await renderSection([
      'office',
      'wedding',
      'festival',
    ]);

    await fireEvent.press(getByLabelText('Casual'));

    expect(getByText('Casual').parent).not.toHaveProp(
      'className',
      expect.stringContaining('border-2'),
    );
  });

  it('shows "You can select up to 3 occasions." only once 3 are selected', async () => {
    const { getByLabelText, getByText, queryByText } = await renderSection([
      'office',
      'wedding',
    ]);

    expect(queryByText('You can select up to 3 occasions.')).toBeNull();

    await fireEvent.press(getByLabelText('Festival'));

    expect(getByText('You can select up to 3 occasions.')).toBeOnTheScreen();
  });

  it('deselecting one of 3 selected, then selecting a different one, swaps successfully', async () => {
    const { getByLabelText, getByText } = await renderSection([
      'office',
      'wedding',
      'festival',
    ]);

    await fireEvent.press(getByLabelText('Office'));
    await fireEvent.press(getByLabelText('Casual'));

    expect(getByText('Office').parent).not.toHaveProp(
      'className',
      expect.stringContaining('border-2'),
    );
    expect(getByText('Casual').parent).toHaveProp(
      'className',
      expect.stringContaining('border-2'),
    );
  });

  it('pressing Save calls the mutation with exactly the current local selection', async () => {
    const { getByLabelText, getByText } = await renderSection(['office']);

    await fireEvent.press(getByLabelText('Wedding'));
    await fireEvent.press(getByText('Save'));

    expect(mockMutate).toHaveBeenCalledWith({
      userId: 'user-1',
      occasions: ['office', 'wedding'],
    });
  });

  it('renders TaxonomyChipsSkeleton while loading', async () => {
    const { getAllByTestId, queryByText } = await render(
      <EditOccasionPrioritiesSection
        userId="user-1"
        initialOccasions={[]}
        taxonomies={undefined}
        isTaxonomiesLoading
        isTaxonomiesError={false}
        onRetryTaxonomies={jest.fn()}
      />,
    );

    expect(getAllByTestId('skeleton').length).toBeGreaterThan(0);
    expect(queryByText('Office')).toBeNull();
  });

  it('renders the inline error message + Retry, calling onRetryTaxonomies', async () => {
    const mockRetry = jest.fn();
    const { getByText } = await render(
      <EditOccasionPrioritiesSection
        userId="user-1"
        initialOccasions={[]}
        taxonomies={undefined}
        isTaxonomiesLoading={false}
        isTaxonomiesError
        onRetryTaxonomies={mockRetry}
      />,
    );

    expect(getByText("Couldn't load occasion options.")).toBeOnTheScreen();
    await fireEvent.press(getByText('Retry'));
    expect(mockRetry).toHaveBeenCalledTimes(1);
  });
});
