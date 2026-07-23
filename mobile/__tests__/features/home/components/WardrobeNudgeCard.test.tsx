import { fireEvent, render } from '@testing-library/react-native';
import { WardrobeNudgeCard } from '../../../../features/home/components/WardrobeNudgeCard';

const mockPush = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

describe('WardrobeNudgeCard', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders the "Add your first item" CTA', async () => {
    const { getByText } = await render(<WardrobeNudgeCard />);
    expect(getByText('Add your first item')).toBeOnTheScreen();
  });

  it('tapping the CTA navigates to /wardrobe', async () => {
    const { getByLabelText } = await render(<WardrobeNudgeCard />);
    fireEvent.press(getByLabelText('Add your first item'));
    expect(mockPush).toHaveBeenCalledWith('/wardrobe');
  });
});
