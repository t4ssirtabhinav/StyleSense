import { fireEvent, render } from '@testing-library/react-native';
import WardrobeScreen from '../../../app/(tabs)/wardrobe';

const mockPush = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

describe('WardrobeScreen (app/(tabs)/wardrobe.tsx)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders the expected EmptyState heading/subtext', async () => {
    const { getByText } = await render(<WardrobeScreen />);

    expect(getByText('Your wardrobe is empty')).toBeOnTheScreen();
    expect(
      getByText('Add your first item to get outfit suggestions.'),
    ).toBeOnTheScreen();
  });

  it("the CTA's onPress navigates to /wardrobe/upload", async () => {
    const { getByLabelText } = await render(<WardrobeScreen />);

    await fireEvent.press(getByLabelText('Add your first item'));

    expect(mockPush).toHaveBeenCalledWith('/wardrobe/upload');
  });
});
