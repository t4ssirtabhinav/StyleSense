import { render } from '@testing-library/react-native';
import WardrobeScreen from '../../../app/(tabs)/wardrobe';

describe('WardrobeScreen (app/(tabs)/wardrobe.tsx)', () => {
  it('renders the expected EmptyState heading/subtext', async () => {
    const { getByText } = await render(<WardrobeScreen />);

    expect(getByText('Your wardrobe is empty')).toBeOnTheScreen();
    expect(
      getByText('Add your first item to get outfit suggestions.'),
    ).toBeOnTheScreen();
  });
});
