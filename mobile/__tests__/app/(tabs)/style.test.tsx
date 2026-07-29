import { render } from '@testing-library/react-native';
import StyleScreen from '../../../app/(tabs)/style';

let mockParams: { occasion?: string } = {};
jest.mock('expo-router', () => ({
  useLocalSearchParams: () => mockParams,
}));

// (SS-025) The screen resolves the incoming param through the registry's
// alias map before matching OCCASION_PILLS, so links minted before the key
// rename keep working.
const ALIASES: Record<string, string> = {
  wedding: 'wedding_guest',
  date: 'date_night',
};

const mockUseOccasionTaxonomy = jest.fn();
jest.mock('../../../features/onboarding/onboarding.queries', () => ({
  useOccasionTaxonomy: () => mockUseOccasionTaxonomy(),
}));

describe('StyleScreen (app/(tabs)/style.tsx)', () => {
  beforeEach(() => {
    mockParams = {};
    jest.clearAllMocks();
    mockUseOccasionTaxonomy.mockReturnValue({
      resolveOccasion: (raw: string) => ALIASES[raw] ?? raw,
    });
  });

  it('renders "{Label} looks — coming soon" with a canonical occasion param', async () => {
    mockParams = { occasion: 'wedding_guest' };
    const { getByText } = await render(<StyleScreen />);

    expect(getByText('Wedding looks — coming soon')).toBeOnTheScreen();
  });

  it('still resolves a LEGACY deep link (?occasion=wedding) after the SS-025 key rename', async () => {
    mockParams = { occasion: 'wedding' };
    const { getByText } = await render(<StyleScreen />);

    expect(getByText('Wedding looks — coming soon')).toBeOnTheScreen();
  });

  it('still resolves the legacy ?occasion=date link', async () => {
    mockParams = { occasion: 'date' };
    const { getByText } = await render(<StyleScreen />);

    expect(getByText('Date looks — coming soon')).toBeOnTheScreen();
  });

  it('falls back to the raw param when the taxonomy has not resolved yet', async () => {
    mockUseOccasionTaxonomy.mockReturnValue({
      resolveOccasion: (raw: string) => raw,
    });
    mockParams = { occasion: 'festival' };
    const { getByText } = await render(<StyleScreen />);

    expect(getByText('Festival looks — coming soon')).toBeOnTheScreen();
  });

  it('renders the generic empty-state copy with no param', async () => {
    mockParams = {};
    const { getByText } = await render(<StyleScreen />);

    expect(getByText('Nothing here yet')).toBeOnTheScreen();
  });

  it('renders the generic empty-state copy (not "undefined looks…") with an unrecognized param', async () => {
    mockParams = { occasion: 'xyz' };
    const { getByText, queryByText } = await render(<StyleScreen />);

    expect(getByText('Nothing here yet')).toBeOnTheScreen();
    expect(queryByText(/undefined looks/)).toBeNull();
  });
});
