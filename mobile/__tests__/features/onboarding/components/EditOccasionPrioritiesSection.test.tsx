import { cleanup, fireEvent, render } from '@testing-library/react-native';
import { EditOccasionPrioritiesSection } from '../../../../features/onboarding/components/EditOccasionPrioritiesSection';

const mockMutate = jest.fn();
const mockUseUpdateOccasionPrioritiesMutation = jest.fn();

jest.mock('../../../../features/onboarding/onboarding.queries', () => ({
  useUpdateOccasionPrioritiesMutation: () =>
    mockUseUpdateOccasionPrioritiesMutation(),
}));

// (SS-025) 12 top-level registry rows, up from the 9 of the retired
// `occasion_types` table, each carrying a badge colour.
const TWELVE_OCCASIONS = [
  { key: 'office', label: 'Office', badgeColor: 'office' as const },
  { key: 'casual', label: 'Casual', badgeColor: 'casual' as const },
  { key: 'date_night', label: 'Date Night', badgeColor: 'wedding' as const },
  {
    key: 'wedding_guest',
    label: 'Wedding Guest',
    badgeColor: 'wedding' as const,
  },
  { key: 'festival', label: 'Festival', badgeColor: 'festival' as const },
  { key: 'puja', label: 'Puja', badgeColor: 'festival' as const },
  { key: 'party', label: 'Party', badgeColor: 'festival' as const },
  { key: 'travel', label: 'Travel', badgeColor: 'casual' as const },
  { key: 'workout', label: 'Workout', badgeColor: 'casual' as const },
  { key: 'beach', label: 'Beach', badgeColor: 'casual' as const },
  {
    key: 'formal_event',
    label: 'Formal Event',
    badgeColor: 'wedding' as const,
  },
  { key: 'college', label: 'College', badgeColor: 'casual' as const },
].map((option, index) => ({
  ...option,
  sortOrder: index + 1,
  kind: 'everyday',
  parentKey: null,
  regionScope: null,
  cultureScope: null,
}));

const TAXONOMIES = {
  styleKeywords: [],
  occasions: TWELVE_OCCASIONS,
  occasionAliases: [
    { alias: 'wedding', occasionKey: 'wedding_guest' },
    { alias: 'date', occasionKey: 'date_night' },
  ],
  colourPalette: [],
  isStale: false,
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
    const { getByText } = await renderSection(['office', 'wedding_guest']);

    expect(getByText('Office').parent).toHaveProp(
      'className',
      expect.stringContaining('border-2'),
    );
    expect(getByText('Wedding Guest').parent).toHaveProp(
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
      'wedding_guest',
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
      'wedding_guest',
    ]);

    expect(queryByText('You can select up to 3 occasions.')).toBeNull();

    await fireEvent.press(getByLabelText('Festival'));

    expect(getByText('You can select up to 3 occasions.')).toBeOnTheScreen();
  });

  it('deselecting one of 3 selected, then selecting a different one, swaps successfully', async () => {
    const { getByLabelText, getByText } = await renderSection([
      'office',
      'wedding_guest',
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

    await fireEvent.press(getByLabelText('Wedding Guest'));
    await fireEvent.press(getByText('Save'));

    expect(mockMutate).toHaveBeenCalledWith({
      userId: 'user-1',
      occasions: ['office', 'wedding_guest'],
    });
  });

  it('renders all 12 top-level registry occasions (was 9), each with a badge colour', async () => {
    const { getByTestId, getByText } = await renderSection();

    expect(TWELVE_OCCASIONS).toHaveLength(12);
    for (const option of TWELVE_OCCASIONS) {
      expect(
        getByTestId(`edit-occasion-priority-${option.key}`),
      ).toBeOnTheScreen();
      expect(getByText(option.label).parent).toHaveProp(
        'className',
        expect.stringMatching(/bg-occasion/),
      );
    }
  });

  it('renders a saved LEGACY key as selected once 009 has backfilled it (wedding -> wedding_guest)', async () => {
    // 009's alias backfill rewrites users.style_preferences.occasions_priority
    // in place, so by the time this screen loads, the stored value is already
    // canonical -- this asserts the canonical value renders selected, which is
    // what makes a re-entering user see their choice instead of a blank chip.
    const { getByText } = await renderSection(['wedding_guest']);

    expect(getByText('Wedding Guest').parent).toHaveProp(
      'className',
      expect.stringContaining('border-2'),
    );
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
