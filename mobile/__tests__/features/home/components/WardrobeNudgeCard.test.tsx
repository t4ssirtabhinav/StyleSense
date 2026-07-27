import { fireEvent, render } from '@testing-library/react-native';
import { useAuthStore } from '../../../../features/auth/auth.store';
import { WardrobeNudgeCard } from '../../../../features/home/components/WardrobeNudgeCard';

const mockPush = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

const mockUseWardrobeItemCountQuery = jest.fn();
jest.mock('../../../../features/wardrobe/wardrobe.queries', () => ({
  useWardrobeItemCountQuery: (userId: string | undefined) =>
    mockUseWardrobeItemCountQuery(userId),
}));

describe('WardrobeNudgeCard', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useAuthStore.setState({
      // biome-ignore lint/suspicious/noExplicitAny: minimal fake Session for tests
      session: { user: { id: 'user-1' } } as any,
      isSessionLoading: false,
    });
  });

  it('renders null while loading', async () => {
    mockUseWardrobeItemCountQuery.mockReturnValue({
      isLoading: true,
      isError: false,
      data: undefined,
    });

    const { toJSON } = await render(<WardrobeNudgeCard />);

    expect(toJSON()).toBeNull();
  });

  it('renders null on error (fail-safe)', async () => {
    mockUseWardrobeItemCountQuery.mockReturnValue({
      isLoading: false,
      isError: true,
      data: undefined,
    });

    const { toJSON } = await render(<WardrobeNudgeCard />);

    expect(toJSON()).toBeNull();
  });

  it('count=0 renders the card, CTA routes to /wardrobe/upload', async () => {
    mockUseWardrobeItemCountQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      data: 0,
    });

    const { getByText, getByLabelText } = await render(<WardrobeNudgeCard />);

    expect(getByText('Your wardrobe is empty')).toBeOnTheScreen();
    fireEvent.press(getByLabelText('Add your first item'));
    expect(mockPush).toHaveBeenCalledWith('/wardrobe/upload');
  });

  it('count>0 renders null', async () => {
    mockUseWardrobeItemCountQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      data: 5,
    });

    const { toJSON } = await render(<WardrobeNudgeCard />);

    expect(toJSON()).toBeNull();
  });
});
