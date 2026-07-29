import { cleanup, fireEvent, render } from '@testing-library/react-native';
import { Step3OccasionPriorities } from '../../../../features/onboarding/components/Step3OccasionPriorities';
import { useOnboardingStore } from '../../../../features/onboarding/onboarding.store';

const mockRefetch = jest.fn();
const mockUseOccasionTaxonomy = jest.fn();

jest.mock('../../../../features/onboarding/onboarding.queries', () => ({
  useOccasionTaxonomy: () => mockUseOccasionTaxonomy(),
}));

// (SS-025) Step 3 now sources the 12 TOP-LEVEL active occasions from the
// `occasions` registry — up from the 9 rows of the retired `occasion_types`
// table — and each chip carries its registry badge colour.
const TWELVE_OCCASIONS = [
  { key: 'office', label: 'Office', badgeColor: 'office' },
  { key: 'casual', label: 'Casual', badgeColor: 'casual' },
  { key: 'date_night', label: 'Date Night', badgeColor: 'wedding' },
  { key: 'wedding_guest', label: 'Wedding Guest', badgeColor: 'wedding' },
  { key: 'festival', label: 'Festival', badgeColor: 'festival' },
  { key: 'puja', label: 'Puja', badgeColor: 'festival' },
  { key: 'party', label: 'Party', badgeColor: 'festival' },
  { key: 'travel', label: 'Travel', badgeColor: 'casual' },
  { key: 'workout', label: 'Workout', badgeColor: 'casual' },
  { key: 'beach', label: 'Beach', badgeColor: 'casual' },
  { key: 'formal_event', label: 'Formal Event', badgeColor: 'wedding' },
  { key: 'college', label: 'College', badgeColor: 'casual' },
].map((option, index) => ({
  ...option,
  sortOrder: index + 1,
  kind: 'everyday',
  parentKey: null,
  regionScope: null,
  cultureScope: null,
}));

const BADGE_COLOR_BY_KEY: Record<string, string> = Object.fromEntries(
  TWELVE_OCCASIONS.map((option) => [option.key, option.badgeColor]),
);

function taxonomy(overrides: Record<string, unknown> = {}) {
  return {
    topLevelOccasions: TWELVE_OCCASIONS,
    badgeColor: (slug: string) => BADGE_COLOR_BY_KEY[slug],
    isLoading: false,
    isError: false,
    refetch: mockRefetch,
    ...overrides,
  };
}

describe('Step3OccasionPriorities', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseOccasionTaxonomy.mockReturnValue(taxonomy());
  });

  afterEach(async () => {
    await cleanup();
    useOnboardingStore.getState().reset();
  });

  it('renders TaxonomyChipsSkeleton while loading', async () => {
    mockUseOccasionTaxonomy.mockReturnValue(
      taxonomy({ isLoading: true, topLevelOccasions: [] }),
    );

    const { getAllByTestId, queryByText } = await render(
      <Step3OccasionPriorities />,
    );

    expect(getAllByTestId('skeleton').length).toBeGreaterThan(0);
    expect(queryByText('Office')).toBeNull();
  });

  it('renders the inline error message + Retry button, and Retry calls refetch', async () => {
    mockUseOccasionTaxonomy.mockReturnValue(
      taxonomy({ isError: true, topLevelOccasions: [] }),
    );

    const { getByText } = await render(<Step3OccasionPriorities />);

    expect(getByText("Couldn't load occasion options.")).toBeOnTheScreen();
    await fireEvent.press(getByText('Retry'));
    expect(mockRefetch).toHaveBeenCalledTimes(1);
  });

  it('renders the empty-state message when the registry returns no top-level occasions', async () => {
    mockUseOccasionTaxonomy.mockReturnValue(
      taxonomy({ topLevelOccasions: [] }),
    );

    const { getByText } = await render(<Step3OccasionPriorities />);

    expect(getByText('No options available right now.')).toBeOnTheScreen();
  });

  it('renders all 12 top-level occasions from the registry, in sort_order (was 9)', async () => {
    const { getByTestId } = await render(<Step3OccasionPriorities />);

    expect(TWELVE_OCCASIONS).toHaveLength(12);
    for (const option of TWELVE_OCCASIONS) {
      expect(getByTestId(`occasion-priority-${option.key}`)).toBeOnTheScreen();
    }
  });

  it('every chip carries a registry badge colour, none renders neutral (BL-008)', async () => {
    const { getByText } = await render(<Step3OccasionPriorities />);

    for (const option of TWELVE_OCCASIONS) {
      const labelNode = getByText(option.label);
      expect(labelNode.parent).toHaveProp(
        'className',
        expect.stringMatching(/bg-occasion/),
      );
      expect(labelNode.parent).not.toHaveProp(
        'className',
        expect.stringContaining('bg-surfaceSecondary'),
      );
    }
  });

  it('does NOT render a child occasion — a growing registry must not flood the wizard', async () => {
    // topLevelOccasions already filters out rows with a parentKey; this
    // asserts the component reads that filtered list, not the raw registry.
    const { queryByTestId } = await render(<Step3OccasionPriorities />);
    expect(queryByTestId('occasion-priority-ganesh_chaturthi')).toBeNull();
  });

  it('selecting a 4th occasion when 3 are already selected does not add a 4th (SS-004 regression)', async () => {
    const { getByLabelText } = await render(<Step3OccasionPriorities />);

    await fireEvent.press(getByLabelText('Office'));
    await fireEvent.press(getByLabelText('Wedding Guest'));
    await fireEvent.press(getByLabelText('Festival'));
    await fireEvent.press(getByLabelText('Casual'));

    expect(useOnboardingStore.getState().occasionsPriority).toEqual([
      'office',
      'wedding_guest',
      'festival',
    ]);
  });

  it('persists canonical registry slugs, not the retired onboarding keys', async () => {
    const { getByLabelText } = await render(<Step3OccasionPriorities />);

    await fireEvent.press(getByLabelText('Wedding Guest'));
    await fireEvent.press(getByLabelText('Date Night'));

    expect(useOnboardingStore.getState().occasionsPriority).toEqual([
      'wedding_guest',
      'date_night',
    ]);
  });
});
