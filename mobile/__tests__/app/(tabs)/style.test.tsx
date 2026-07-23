import { render } from '@testing-library/react-native';
import StyleScreen from '../../../app/(tabs)/style';

let mockParams: { occasion?: string } = {};
jest.mock('expo-router', () => ({
  useLocalSearchParams: () => mockParams,
}));

describe('StyleScreen (app/(tabs)/style.tsx)', () => {
  beforeEach(() => {
    mockParams = {};
  });

  it('renders "{Label} looks — coming soon" with a valid occasion param', async () => {
    mockParams = { occasion: 'wedding' };
    const { getByText } = await render(<StyleScreen />);

    expect(getByText('Wedding looks — coming soon')).toBeOnTheScreen();
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
