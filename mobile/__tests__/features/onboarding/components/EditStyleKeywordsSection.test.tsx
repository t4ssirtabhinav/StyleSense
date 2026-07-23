import { cleanup, fireEvent, render } from '@testing-library/react-native';
import { EditStyleKeywordsSection } from '../../../../features/onboarding/components/EditStyleKeywordsSection';

const mockMutate = jest.fn();
const mockUseUpdateStyleKeywordsMutation = jest.fn();

jest.mock('../../../../features/onboarding/onboarding.queries', () => ({
  useUpdateStyleKeywordsMutation: () => mockUseUpdateStyleKeywordsMutation(),
}));

const THREE_STYLES = [
  { key: 'ethnic', label: 'Ethnic', sortOrder: 1 },
  { key: 'western', label: 'Western', sortOrder: 2 },
  { key: 'minimalist', label: 'Minimalist', sortOrder: 3 },
];

const TAXONOMIES = {
  styleKeywords: THREE_STYLES,
  occasionTypes: [],
  colourPalette: [],
};

function renderSection(initialStyles: string[] = []) {
  return render(
    <EditStyleKeywordsSection
      userId="user-1"
      initialStyles={initialStyles}
      taxonomies={TAXONOMIES}
      isTaxonomiesLoading={false}
      isTaxonomiesError={false}
      onRetryTaxonomies={jest.fn()}
    />,
  );
}

describe('EditStyleKeywordsSection', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseUpdateStyleKeywordsMutation.mockReturnValue({
      mutate: mockMutate,
      isPending: false,
      isError: false,
    });
  });

  afterEach(async () => {
    await cleanup();
  });

  it('renders pre-selected chips matching the passed-in styles array', async () => {
    const { getByText } = await renderSection(['ethnic']);

    expect(getByText('Ethnic').parent).toHaveProp(
      'className',
      expect.stringContaining('border-2'),
    );
    expect(getByText('Western').parent).not.toHaveProp(
      'className',
      expect.stringContaining('border-2'),
    );
  });

  it('selecting all available options succeeds (no cap); Save calls the mutation with the full selected array', async () => {
    const { getByLabelText, getByText } = await renderSection([]);

    await fireEvent.press(getByLabelText('Ethnic'));
    await fireEvent.press(getByLabelText('Western'));
    await fireEvent.press(getByLabelText('Minimalist'));

    await fireEvent.press(getByText('Save'));

    expect(mockMutate).toHaveBeenCalledWith({
      userId: 'user-1',
      styles: ['ethnic', 'western', 'minimalist'],
    });
  });

  it('renders TaxonomyChipsSkeleton while loading', async () => {
    const { getAllByTestId, queryByText } = await render(
      <EditStyleKeywordsSection
        userId="user-1"
        initialStyles={[]}
        taxonomies={undefined}
        isTaxonomiesLoading
        isTaxonomiesError={false}
        onRetryTaxonomies={jest.fn()}
      />,
    );

    expect(getAllByTestId('skeleton').length).toBeGreaterThan(0);
    expect(queryByText('Ethnic')).toBeNull();
  });

  it('renders the inline error message + Retry, calling onRetryTaxonomies', async () => {
    const mockRetry = jest.fn();
    const { getByText } = await render(
      <EditStyleKeywordsSection
        userId="user-1"
        initialStyles={[]}
        taxonomies={undefined}
        isTaxonomiesLoading={false}
        isTaxonomiesError
        onRetryTaxonomies={mockRetry}
      />,
    );

    expect(getByText("Couldn't load style options.")).toBeOnTheScreen();
    await fireEvent.press(getByText('Retry'));
    expect(mockRetry).toHaveBeenCalledTimes(1);
  });

  it('renders the empty-state message when styleKeywords is empty', async () => {
    const { getByText } = await render(
      <EditStyleKeywordsSection
        userId="user-1"
        initialStyles={[]}
        taxonomies={{ styleKeywords: [], occasionTypes: [], colourPalette: [] }}
        isTaxonomiesLoading={false}
        isTaxonomiesError={false}
        onRetryTaxonomies={jest.fn()}
      />,
    );

    expect(
      getByText('No style options available right now.'),
    ).toBeOnTheScreen();
  });
});
