import { cleanup, fireEvent, render } from '@testing-library/react-native';
import { EditFavouriteColoursSection } from '../../../../features/onboarding/components/EditFavouriteColoursSection';

const mockMutate = jest.fn();
const mockUseUpdateFavouriteColoursMutation = jest.fn();

jest.mock('../../../../features/onboarding/onboarding.queries', () => ({
  useUpdateFavouriteColoursMutation: () =>
    mockUseUpdateFavouriteColoursMutation(),
}));

const TWELVE_COLOURS = [
  { key: 'black', label: 'Black', hex: '#000000', sortOrder: 1 },
  { key: 'white', label: 'White', hex: '#FFFFFF', sortOrder: 2 },
  { key: 'maroon', label: 'Maroon', hex: '#7B241C', sortOrder: 3 },
  { key: 'navy', label: 'Navy', hex: '#1B2A4A', sortOrder: 4 },
  { key: 'royal_blue', label: 'Royal Blue', hex: '#2E5C8A', sortOrder: 5 },
  { key: 'emerald', label: 'Emerald Green', hex: '#2D6A4F', sortOrder: 6 },
  {
    key: 'marigold',
    label: 'Marigold/Mustard',
    hex: '#E8A420',
    sortOrder: 7,
  },
  { key: 'rose', label: 'Rose Pink', hex: '#C45B7C', sortOrder: 8 },
  { key: 'beige', label: 'Beige', hex: '#D9C9A3', sortOrder: 9 },
  { key: 'grey', label: 'Grey', hex: '#9A9590', sortOrder: 10 },
  { key: 'pastel_blue', label: 'Pastel Blue', hex: '#A9C6E8', sortOrder: 11 },
  { key: 'red', label: 'Red', hex: '#C0392B', sortOrder: 12 },
];

const TAXONOMIES = {
  styleKeywords: [],
  occasionTypes: [],
  colourPalette: TWELVE_COLOURS,
};

function renderSection(initialColours: string[] = []) {
  return render(
    <EditFavouriteColoursSection
      userId="user-1"
      initialColours={initialColours}
      taxonomies={TAXONOMIES}
      isTaxonomiesLoading={false}
      isTaxonomiesError={false}
      onRetryTaxonomies={jest.fn()}
    />,
  );
}

describe('EditFavouriteColoursSection', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseUpdateFavouriteColoursMutation.mockReturnValue({
      mutate: mockMutate,
      isPending: false,
      isError: false,
    });
  });

  afterEach(async () => {
    await cleanup();
  });

  it('renders pre-selected swatches (checkmark shown) matching the passed-in favourite_colours array', async () => {
    const { queryAllByTestId } = await renderSection(['#000000', '#FFFFFF']);

    expect(queryAllByTestId('colour-swatch-check')).toHaveLength(2);
  });

  it('selecting a 6th colour when 5 are already selected does not add a 6th', async () => {
    const { getByLabelText, queryAllByTestId } = await renderSection([
      '#000000',
      '#FFFFFF',
      '#7B241C',
      '#1B2A4A',
      '#2E5C8A',
    ]);

    await fireEvent.press(getByLabelText('Emerald Green'));

    expect(queryAllByTestId('colour-swatch-check')).toHaveLength(5);
  });

  it('shows "You can select up to 5 colours." only once 5 are selected', async () => {
    const { getByLabelText, getByText, queryByText } = await renderSection([
      '#000000',
      '#FFFFFF',
      '#7B241C',
      '#1B2A4A',
    ]);

    expect(queryByText('You can select up to 5 colours.')).toBeNull();

    await fireEvent.press(getByLabelText('Royal Blue'));

    expect(getByText('You can select up to 5 colours.')).toBeOnTheScreen();
  });

  it('deselecting one of 5 selected, then selecting a different one, swaps successfully', async () => {
    const { getByLabelText, queryAllByTestId } = await renderSection([
      '#000000',
      '#FFFFFF',
      '#7B241C',
      '#1B2A4A',
      '#2E5C8A',
    ]);

    await fireEvent.press(getByLabelText('Black'));
    await fireEvent.press(getByLabelText('Marigold/Mustard'));

    expect(queryAllByTestId('colour-swatch-check')).toHaveLength(5);
    expect(getByLabelText('Marigold/Mustard')).toHaveProp(
      'className',
      expect.stringContaining('border-brand'),
    );
    expect(getByLabelText('Black')).toHaveProp(
      'className',
      expect.stringContaining('border-textMuted'),
    );
  });

  it('pressing Save calls the mutation with exactly the current local selection', async () => {
    const { getByLabelText, getByText } = await renderSection(['#000000']);

    await fireEvent.press(getByLabelText('White'));
    await fireEvent.press(getByText('Save'));

    expect(mockMutate).toHaveBeenCalledWith({
      userId: 'user-1',
      colours: ['#000000', '#FFFFFF'],
    });
  });

  it('renders 12 Skeleton variant="circle" while loading', async () => {
    const { getAllByTestId } = await render(
      <EditFavouriteColoursSection
        userId="user-1"
        initialColours={[]}
        taxonomies={undefined}
        isTaxonomiesLoading
        isTaxonomiesError={false}
        onRetryTaxonomies={jest.fn()}
      />,
    );

    expect(getAllByTestId('skeleton')).toHaveLength(12);
  });

  it('renders the inline error message + Retry, calling onRetryTaxonomies', async () => {
    const mockRetry = jest.fn();
    const { getByText } = await render(
      <EditFavouriteColoursSection
        userId="user-1"
        initialColours={[]}
        taxonomies={undefined}
        isTaxonomiesLoading={false}
        isTaxonomiesError
        onRetryTaxonomies={mockRetry}
      />,
    );

    expect(getByText("Couldn't load colour options.")).toBeOnTheScreen();
    await fireEvent.press(getByText('Retry'));
    expect(mockRetry).toHaveBeenCalledTimes(1);
  });
});
