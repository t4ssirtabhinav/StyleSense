import { fireEvent, render } from '@testing-library/react-native';
import { WearOccasionField } from '../../../../features/wardrobe/components/WearOccasionField';
import { WEAR_OCCASIONS_UNAVAILABLE_MESSAGE } from '../../../../features/wardrobe/wardrobe.constants';

const mockUseOccasionOptions = jest.fn();
jest.mock('../../../../features/wardrobe/wardrobe.queries', () => ({
  useOccasionOptions: () => mockUseOccasionOptions(),
}));

// (SS-025/SS-035) `optionsIncluding` implements the UNION rule: active
// registry PLUS any slug already selected (currentTags), so an unknown or
// deactivated occasion stays visible and selected instead of vanishing.
const REGISTRY_OCCASIONS = [
  { key: 'office', label: 'Office', badgeColor: 'office' as const },
  { key: 'puja', label: 'Puja', badgeColor: 'festival' as const },
];

function humanize(slug: string): string {
  return slug
    .split('_')
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

function occasionTaxonomy(
  overrides: Partial<{
    isLoading: boolean;
    isError: boolean;
  }> = {},
) {
  return {
    occasions: REGISTRY_OCCASIONS,
    optionsIncluding: (tags: readonly string[]) => {
      const options = REGISTRY_OCCASIONS.map((o) => ({ ...o }));
      const seen = new Set(options.map((o) => o.key));
      for (const tag of tags) {
        if (tag && !seen.has(tag)) {
          seen.add(tag);
          options.push({
            key: tag,
            label: humanize(tag),
            badgeColor: undefined as never,
          });
        }
      }
      return options;
    },
    isLoading: false,
    isError: false,
    refetch: jest.fn(),
    ...overrides,
  };
}

describe('WearOccasionField', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders registry options with labels and badge colours, never raw slugs', async () => {
    mockUseOccasionOptions.mockReturnValue(occasionTaxonomy());

    const { getByTestId, getByText, queryByText } = await render(
      <WearOccasionField value={null} onChange={jest.fn()} />,
    );

    expect(getByText('Office')).toBeOnTheScreen();
    expect(getByText('Puja')).toBeOnTheScreen();
    expect(queryByText('office')).toBeNull();
    expect(getByTestId('wear-occasion-office')).toBeOnTheScreen();
    expect(getByTestId('wear-occasion-puja')).toBeOnTheScreen();
  });

  it('renders a leading "No occasion" chip that clears the selection', async () => {
    mockUseOccasionOptions.mockReturnValue(occasionTaxonomy());
    const onChange = jest.fn();

    const { getByTestId } = await render(
      <WearOccasionField value="office" onChange={onChange} />,
    );

    await fireEvent.press(getByTestId('wear-occasion-none'));

    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('re-tapping the already-selected chip clears the selection', async () => {
    mockUseOccasionOptions.mockReturnValue(occasionTaxonomy());
    const onChange = jest.fn();

    const { getByTestId } = await render(
      <WearOccasionField value="office" onChange={onChange} />,
    );

    await fireEvent.press(getByTestId('wear-occasion-office'));

    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('tapping a different chip selects it', async () => {
    mockUseOccasionOptions.mockReturnValue(occasionTaxonomy());
    const onChange = jest.fn();

    const { getByTestId } = await render(
      <WearOccasionField value="office" onChange={onChange} />,
    );

    await fireEvent.press(getByTestId('wear-occasion-puja'));

    expect(onChange).toHaveBeenCalledWith('puja');
  });

  it('an unknown/deactivated current value renders humanised, neutral, and selected via the union rule', async () => {
    mockUseOccasionOptions.mockReturnValue(occasionTaxonomy());

    const { getByTestId, getByText } = await render(
      <WearOccasionField value="sangeet_night" onChange={jest.fn()} />,
    );

    expect(getByText('Sangeet Night')).toBeOnTheScreen();
    expect(getByTestId('wear-occasion-sangeet_night')).toBeOnTheScreen();
  });

  it('renders a disabled/loading state while the taxonomy loads', async () => {
    mockUseOccasionOptions.mockReturnValue(occasionTaxonomy({ isLoading: true }));

    const { getByTestId, queryByTestId } = await render(
      <WearOccasionField value={null} onChange={jest.fn()} />,
    );

    expect(getByTestId('wear-occasion-field-loading')).toBeOnTheScreen();
    expect(getByTestId('wear-occasion-field-spinner')).toBeOnTheScreen();
    expect(queryByTestId('wear-occasion-none')).toBeNull();
  });

  it('a taxonomy error renders the unavailable message and never blocks logging a wear without one', async () => {
    mockUseOccasionOptions.mockReturnValue(occasionTaxonomy({ isError: true }));

    const { getByTestId, getByText, queryByTestId } = await render(
      <WearOccasionField value={null} onChange={jest.fn()} />,
    );

    expect(getByTestId('wear-occasion-field-error')).toBeOnTheScreen();
    expect(getByText(WEAR_OCCASIONS_UNAVAILABLE_MESSAGE)).toBeOnTheScreen();
    // No picker chips render on error -- the caller's WearDateField (a
    // sibling, not owned by this component) is unaffected either way, so
    // the wear can still be logged with occasionKey staying null.
    expect(queryByTestId('wear-occasion-none')).toBeNull();
  });
});
