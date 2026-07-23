import { fireEvent, render } from '@testing-library/react-native';
import { OccasionPillRow } from '../../../../features/home/components/OccasionPillRow';
import { OCCASION_PILLS } from '../../../../features/home/home.constants';

const mockPush = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

describe('OccasionPillRow', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders exactly 6 pills with the labels/icons from OCCASION_PILLS, in the fixed order', async () => {
    const { getByTestId } = await render(<OccasionPillRow />);

    expect(OCCASION_PILLS).toHaveLength(6);
    OCCASION_PILLS.forEach((pill) => {
      expect(getByTestId(`occasion-pill-${pill.key}`)).toBeOnTheScreen();
    });
  });

  it("every pill renders via Badge's neutral style (no occasion prop) — BL-008 regression guard", async () => {
    const { toJSON } = await render(<OccasionPillRow />);
    const rendered = JSON.stringify(toJSON());

    // Neutral style = bg-surfaceSecondary (Badge.tsx's NEUTRAL_STYLE). Any of
    // the 4 colour-coded occasion classes appearing would indicate an
    // `occasion` prop was passed to some pill, which this design explicitly
    // avoids for all 6 (date/party have no defined colour at all).
    expect(rendered).toContain('bg-surfaceSecondary');
    expect(rendered).not.toContain('bg-occasionWedding');
    expect(rendered).not.toContain('bg-occasionOffice');
    expect(rendered).not.toContain('bg-occasionFestival');
    expect(rendered).not.toContain('bg-occasionCasual');
  });

  it("tapping a pill navigates to /style with that pill's key as the occasion param", async () => {
    const { getByTestId } = await render(<OccasionPillRow />);

    fireEvent.press(getByTestId('occasion-pill-wedding'));

    expect(mockPush).toHaveBeenCalledWith({
      pathname: '/style',
      params: { occasion: 'wedding' },
    });
  });
});
