import { cleanup, fireEvent, render } from '@testing-library/react-native';
import { Step4BudgetColours } from '../../../../features/onboarding/components/Step4BudgetColours';
import { useOnboardingStore } from '../../../../features/onboarding/onboarding.store';

const mockRefetch = jest.fn();
const mockUseOnboardingTaxonomiesQuery = jest.fn();

jest.mock('../../../../features/onboarding/onboarding.queries', () => ({
  useOnboardingTaxonomiesQuery: () => mockUseOnboardingTaxonomiesQuery(),
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

describe('Step4BudgetColours', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  afterEach(async () => {
    await cleanup();
    useOnboardingStore.getState().reset();
  });

  it('budget: single-select across the 4 ranges', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: true,
      isError: false,
      isSuccess: false,
      data: undefined,
      refetch: mockRefetch,
    });

    const { getByText } = await render(<Step4BudgetColours />);

    await fireEvent.press(getByText('₹500–1k'));
    expect(useOnboardingStore.getState().budgetRange).toBe('500_1000');

    await fireEvent.press(getByText('₹1k–3k'));
    expect(useOnboardingStore.getState().budgetRange).toBe('1000_3000');
  });

  it('renders 12 Skeleton variant="circle" (not TaxonomyChipsSkeleton pills) while loading', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: true,
      isError: false,
      isSuccess: false,
      data: undefined,
      refetch: mockRefetch,
    });

    const { getAllByTestId } = await render(<Step4BudgetColours />);

    expect(getAllByTestId('skeleton')).toHaveLength(12);
  });

  it('renders the inline error message + Retry button, and Retry calls refetch', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: false,
      isError: true,
      isSuccess: false,
      data: undefined,
      refetch: mockRefetch,
    });

    const { getByText } = await render(<Step4BudgetColours />);

    expect(getByText("Couldn't load colour options.")).toBeOnTheScreen();
    await fireEvent.press(getByText('Retry'));
    expect(mockRefetch).toHaveBeenCalledTimes(1);
  });

  it('renders the empty-state message when colourPalette is empty', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: { styleKeywords: [], occasionTypes: [], colourPalette: [] },
      refetch: mockRefetch,
    });

    const { getByText } = await render(<Step4BudgetColours />);

    expect(getByText('No options available right now.')).toBeOnTheScreen();
  });

  it('renders all 12 swatches in the 4x3 grid without a horizontal scroll container', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: {
        styleKeywords: [],
        occasionTypes: [],
        colourPalette: TWELVE_COLOURS,
      },
      refetch: mockRefetch,
    });

    const { getByTestId, getByLabelText } = await render(
      <Step4BudgetColours />,
    );

    const grid = getByTestId('colour-palette-grid');
    expect(grid).toHaveProp('className', expect.stringContaining('flex-wrap'));
    expect(grid).not.toHaveProp(
      'className',
      expect.stringContaining('flex-nowrap'),
    );
    for (const option of TWELVE_COLOURS) {
      expect(getByLabelText(option.label)).toBeOnTheScreen();
    }
  });

  it('renders a colour-name caption under each swatch', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: {
        styleKeywords: [],
        occasionTypes: [],
        colourPalette: TWELVE_COLOURS,
      },
      refetch: mockRefetch,
    });

    const { getByText } = await render(<Step4BudgetColours />);

    for (const option of TWELVE_COLOURS) {
      expect(getByText(option.label)).toBeOnTheScreen();
    }
  });

  it('shows a checkmark overlay only on a selected swatch, and hides it again on deselect', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: {
        styleKeywords: [],
        occasionTypes: [],
        colourPalette: TWELVE_COLOURS,
      },
      refetch: mockRefetch,
    });

    const { getByLabelText, queryAllByTestId } = await render(
      <Step4BudgetColours />,
    );

    expect(queryAllByTestId('colour-swatch-check')).toHaveLength(0);

    await fireEvent.press(getByLabelText('Black'));
    expect(queryAllByTestId('colour-swatch-check')).toHaveLength(1);

    await fireEvent.press(getByLabelText('Black'));
    expect(queryAllByTestId('colour-swatch-check')).toHaveLength(0);
  });

  it('applies the shadow-md + selected-border treatment to a selected swatch', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: {
        styleKeywords: [],
        occasionTypes: [],
        colourPalette: TWELVE_COLOURS,
      },
      refetch: mockRefetch,
    });

    const { getByLabelText } = await render(<Step4BudgetColours />);

    await fireEvent.press(getByLabelText('Black'));

    expect(getByLabelText('Black')).toHaveProp(
      'className',
      expect.stringContaining('shadow-md'),
    );
  });

  it('renders each swatch as a rounded square (rounded-lg), not a pill/circle', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: {
        styleKeywords: [],
        occasionTypes: [],
        colourPalette: TWELVE_COLOURS,
      },
      refetch: mockRefetch,
    });

    const { getByLabelText } = await render(<Step4BudgetColours />);

    const swatch = getByLabelText('Black');
    expect(swatch).toHaveProp(
      'className',
      expect.stringContaining('rounded-lg'),
    );
    expect(swatch).not.toHaveProp(
      'className',
      expect.stringContaining('rounded-pill'),
    );
  });

  it('renders a visible (non-transparent) border on an unselected swatch, with the same border width as selected', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: {
        styleKeywords: [],
        occasionTypes: [],
        colourPalette: TWELVE_COLOURS,
      },
      refetch: mockRefetch,
    });

    const { getByLabelText } = await render(<Step4BudgetColours />);

    const swatch = getByLabelText('Black');
    expect(swatch).toHaveProp('className', expect.stringContaining('border-2'));
    expect(swatch).toHaveProp(
      'className',
      expect.stringContaining('border-textMuted'),
    );
    expect(swatch).not.toHaveProp(
      'className',
      expect.stringContaining('border-transparent'),
    );

    await fireEvent.press(swatch);

    // Same width both states — only the colour changes, no layout shift.
    expect(getByLabelText('Black')).toHaveProp(
      'className',
      expect.stringContaining('border-2'),
    );
    expect(getByLabelText('Black')).toHaveProp(
      'className',
      expect.stringContaining('border-brand'),
    );
  });

  it('applies no scale/transform style to a swatch, selected or not (regression guard for the removed animation)', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: {
        styleKeywords: [],
        occasionTypes: [],
        colourPalette: TWELVE_COLOURS,
      },
      refetch: mockRefetch,
    });

    const { getByLabelText } = await render(<Step4BudgetColours />);

    const unselectedStyle = getByLabelText('Black').props.style;
    expect(unselectedStyle).not.toHaveProperty('transform');

    await fireEvent.press(getByLabelText('Black'));

    const selectedStyle = getByLabelText('Black').props.style;
    expect(selectedStyle).not.toHaveProperty('transform');
  });

  it('renders the checkmark badge in a corner position (not centered) only when selected', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: {
        styleKeywords: [],
        occasionTypes: [],
        colourPalette: TWELVE_COLOURS,
      },
      refetch: mockRefetch,
    });

    const { getByLabelText, getByTestId, queryByTestId } = await render(
      <Step4BudgetColours />,
    );

    expect(queryByTestId('colour-swatch-check')).toBeNull();

    await fireEvent.press(getByLabelText('Black'));

    const badge = getByTestId('colour-swatch-check');
    expect(badge).toHaveProp('className', expect.stringContaining('absolute'));
    expect(badge.props.style).toMatchObject({ bottom: -4, right: -4 });
  });

  it('captions use numberOfLines=2 in a fixed-height container regardless of label length or selection state', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: {
        styleKeywords: [],
        occasionTypes: [],
        colourPalette: TWELVE_COLOURS,
      },
      refetch: mockRefetch,
    });

    const { getByText, getByLabelText } = await render(<Step4BudgetColours />);

    const shortCaption = getByText('Grey');
    const longCaption = getByText('Marigold/Mustard');

    expect(shortCaption).toHaveProp('numberOfLines', 2);
    expect(longCaption).toHaveProp('numberOfLines', 2);
    expect(shortCaption.parent).toHaveProp(
      'className',
      expect.stringContaining('min-h-9'),
    );
    expect(longCaption.parent).toHaveProp(
      'className',
      expect.stringContaining('min-h-9'),
    );

    // Select the "Grey" swatch — its caption's fixed-height container must
    // be identical selected or not (no drift between cells in the same row).
    await fireEvent.press(getByLabelText('Grey'));

    expect(getByText('Grey').parent).toHaveProp(
      'className',
      expect.stringContaining('min-h-9'),
    );
  });

  // Fix pass 4, 2026-07-22 (SS-004 Fix 1): regression guard for the
  // caption-overflow bug — the caption's wrapping container must be
  // constrained to the swatch's own 64px width (`w-16`), not `w-full`
  // (which resolved to the wider `w-1/4` grid column and let long labels
  // overflow past the swatch's right edge instead of wrapping at 64px).
  it('constrains the caption container to the swatch width (w-16), not w-full, so long labels wrap instead of overflowing', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: {
        styleKeywords: [],
        occasionTypes: [],
        colourPalette: TWELVE_COLOURS,
      },
      refetch: mockRefetch,
    });

    const { getByText } = await render(<Step4BudgetColours />);

    // Longest seeded label — most likely to expose the overflow bug.
    const longCaption = getByText('Marigold/Mustard');

    expect(longCaption.parent).toHaveProp(
      'className',
      expect.stringContaining('w-16'),
    );
    expect(longCaption.parent).not.toHaveProp(
      'className',
      expect.stringContaining('w-full'),
    );
  });

  it('selecting a 6th colour when 5 are already selected does not add a 6th', async () => {
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: {
        styleKeywords: [],
        occasionTypes: [],
        colourPalette: TWELVE_COLOURS,
      },
      refetch: mockRefetch,
    });

    const { getByLabelText } = await render(<Step4BudgetColours />);

    await fireEvent.press(getByLabelText('Black'));
    await fireEvent.press(getByLabelText('White'));
    await fireEvent.press(getByLabelText('Maroon'));
    await fireEvent.press(getByLabelText('Navy'));
    await fireEvent.press(getByLabelText('Royal Blue'));
    await fireEvent.press(getByLabelText('Emerald Green'));

    expect(useOnboardingStore.getState().favouriteColours).toEqual([
      '#000000',
      '#FFFFFF',
      '#7B241C',
      '#1B2A4A',
      '#2E5C8A',
    ]);
  });
});
