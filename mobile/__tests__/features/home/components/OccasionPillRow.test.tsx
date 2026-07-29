import { fireEvent, render } from '@testing-library/react-native';
import { OccasionPillRow } from '../../../../features/home/components/OccasionPillRow';
import { OCCASION_PILLS } from '../../../../features/home/home.constants';

const mockPush = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

const mockUseOccasionTaxonomy = jest.fn();
jest.mock('../../../../features/onboarding/onboarding.queries', () => ({
  useOccasionTaxonomy: () => mockUseOccasionTaxonomy(),
}));

// (SS-025) The pills read the registry for COLOUR only — never for the list
// itself, which stays a curated hardcoded 6 with emoji (SS-005).
const BADGE_COLOR_BY_KEY: Record<string, string> = {
  office: 'office',
  casual: 'casual',
  wedding_guest: 'wedding',
  festival: 'festival',
  date_night: 'wedding',
  party: 'festival',
};

describe('OccasionPillRow', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseOccasionTaxonomy.mockReturnValue({
      badgeColor: (slug: string) => BADGE_COLOR_BY_KEY[slug],
    });
  });

  it('renders exactly 6 pills with the labels/icons from OCCASION_PILLS, in the fixed order', async () => {
    const { getByTestId } = await render(<OccasionPillRow />);

    expect(OCCASION_PILLS).toHaveLength(6);
    for (const pill of OCCASION_PILLS) {
      expect(getByTestId(`occasion-pill-${pill.key}`)).toBeOnTheScreen();
    }
  });

  it('uses canonical registry keys (SS-025 rename) with SS-005 labels/emoji/order intact', async () => {
    expect(OCCASION_PILLS.map((pill) => pill.key)).toEqual([
      'office',
      'casual',
      'wedding_guest',
      'festival',
      'date_night',
      'party',
    ]);
    expect(OCCASION_PILLS.map((pill) => pill.label)).toEqual([
      'Office',
      'Casual',
      'Wedding',
      'Festival',
      'Date',
      'Party',
    ]);
    expect(OCCASION_PILLS.map((pill) => pill.icon)).toEqual([
      '💼',
      '☀️',
      '💍',
      '🪔',
      '❤️',
      '🎉',
    ]);
  });

  it('every pill carries a badge colour once the taxonomy resolves — the BL-008 fix', async () => {
    const { toJSON } = await render(<OccasionPillRow />);
    const rendered = JSON.stringify(toJSON());

    expect(rendered).toContain('bg-occasionOffice');
    expect(rendered).toContain('bg-occasionCasual');
    expect(rendered).toContain('bg-occasionWedding');
    expect(rendered).toContain('bg-occasionFestival');
    // No pill is left on Badge's neutral style any more.
    expect(rendered).not.toContain('bg-surfaceSecondary');
  });

  it('renders every pill neutral while the taxonomy is loading — home never blocks or flashes empty', async () => {
    mockUseOccasionTaxonomy.mockReturnValue({ badgeColor: () => undefined });

    const { getByTestId, toJSON } = await render(<OccasionPillRow />);
    const rendered = JSON.stringify(toJSON());

    for (const pill of OCCASION_PILLS) {
      expect(getByTestId(`occasion-pill-${pill.key}`)).toBeOnTheScreen();
    }
    expect(rendered).toContain('bg-surfaceSecondary');
  });

  it("tapping a pill navigates to /style with that pill's canonical key as the occasion param", async () => {
    const { getByTestId } = await render(<OccasionPillRow />);

    fireEvent.press(getByTestId('occasion-pill-wedding_guest'));

    expect(mockPush).toHaveBeenCalledWith({
      pathname: '/style',
      params: { occasion: 'wedding_guest' },
    });
  });
});
