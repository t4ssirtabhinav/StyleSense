import { cleanup, fireEvent, render } from '@testing-library/react-native';
import { Step2StyleWardrobe } from '../../../../features/onboarding/components/Step2StyleWardrobe';
import { useOnboardingStore } from '../../../../features/onboarding/onboarding.store';

const mockRefetch = jest.fn();
const mockUseOnboardingTaxonomiesQuery = jest.fn();

jest.mock('../../../../features/onboarding/onboarding.queries', () => ({
  useOnboardingTaxonomiesQuery: () => mockUseOnboardingTaxonomiesQuery(),
}));

const NINE_STYLE_KEYWORDS = [
  { key: 'ethnic', label: 'Ethnic', sortOrder: 1 },
  { key: 'western', label: 'Western', sortOrder: 2 },
  { key: 'indo_western', label: 'Indo-Western', sortOrder: 3 },
  { key: 'casual', label: 'Casual', sortOrder: 4 },
  { key: 'formal', label: 'Formal', sortOrder: 5 },
  { key: 'streetwear', label: 'Streetwear', sortOrder: 6 },
  { key: 'bohemian', label: 'Bohemian', sortOrder: 7 },
  { key: 'minimalist', label: 'Minimalist', sortOrder: 8 },
  { key: 'maximalist', label: 'Maximalist', sortOrder: 9 },
];

describe('Step2StyleWardrobe', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  afterEach(async () => {
    await cleanup();
    useOnboardingStore.getState().reset();
  });

  it('renders TaxonomyChipsSkeleton, not the chip row, while loading', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: true,
      isError: false,
      isSuccess: false,
      data: undefined,
      refetch: mockRefetch,
    });

    const { getAllByTestId, queryByText } = await render(
      <Step2StyleWardrobe />,
    );

    expect(getAllByTestId('skeleton').length).toBeGreaterThan(0);
    expect(queryByText('Ethnic')).toBeNull();
  });

  it('renders the inline error message + Retry button, and Retry calls refetch', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: false,
      isError: true,
      isSuccess: false,
      data: undefined,
      refetch: mockRefetch,
    });

    const { getByText } = await render(<Step2StyleWardrobe />);

    expect(getByText("Couldn't load style options.")).toBeOnTheScreen();
    await fireEvent.press(getByText('Retry'));
    expect(mockRefetch).toHaveBeenCalledTimes(1);
  });

  it('renders the empty-state message, not a blank chip row, when styleKeywords is empty', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: { styleKeywords: [], occasionTypes: [], colourPalette: [] },
      refetch: mockRefetch,
    });

    const { getByText } = await render(<Step2StyleWardrobe />);

    expect(
      getByText('No style options available right now.'),
    ).toBeOnTheScreen();
  });

  it('multiple style-keyword chips can be selected simultaneously (multi-select, no cap)', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: {
        styleKeywords: NINE_STYLE_KEYWORDS,
        occasionTypes: [],
        colourPalette: [],
      },
      refetch: mockRefetch,
    });

    const { getByLabelText } = await render(<Step2StyleWardrobe />);

    await fireEvent.press(getByLabelText('Ethnic'));
    await fireEvent.press(getByLabelText('Western'));
    await fireEvent.press(getByLabelText('Bohemian'));

    expect(useOnboardingStore.getState().styles).toEqual([
      'ethnic',
      'western',
      'bohemian',
    ]);
  });

  it('wardrobe type: selecting one chip deselects any previously-selected one (single-select), unaffected by taxonomies query state', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: true,
      isError: false,
      isSuccess: false,
      data: undefined,
      refetch: mockRefetch,
    });

    const { getByLabelText } = await render(<Step2StyleWardrobe />);

    await fireEvent.press(getByLabelText('Mostly Western'));
    expect(useOnboardingStore.getState().wardrobeType).toBe('mostly_western');

    await fireEvent.press(getByLabelText('Mostly Ethnic'));
    expect(useOnboardingStore.getState().wardrobeType).toBe('mostly_ethnic');
  });
});
