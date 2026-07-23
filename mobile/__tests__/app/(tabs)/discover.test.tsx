import { render } from '@testing-library/react-native';
import DiscoverScreen from '../../../app/(tabs)/discover';

describe('DiscoverScreen (app/(tabs)/discover.tsx)', () => {
  it('renders the expected EmptyState heading/subtext', async () => {
    const { getByText } = await render(<DiscoverScreen />);

    expect(getByText('Nothing here yet')).toBeOnTheScreen();
    expect(getByText('Outfit suggestions are on the way.')).toBeOnTheScreen();
  });
});
