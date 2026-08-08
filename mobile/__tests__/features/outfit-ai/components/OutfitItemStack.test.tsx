import { render } from '@testing-library/react-native';
import { useAuthStore } from '../../../../features/auth/auth.store';
import { OutfitItemStack } from '../../../../features/outfit-ai/components/OutfitItemStack';

const mockUseWardrobeItemImageUrlsQuery = jest.fn();
jest.mock('../../../../features/wardrobe/wardrobe.queries', () => ({
  useWardrobeItemImageUrlsQuery: (...args: unknown[]) =>
    mockUseWardrobeItemImageUrlsQuery(...args),
}));

function setFakeSession() {
  useAuthStore.setState({
    session: {
      user: { id: 'user-1' },
      access_token: 'jwt-token',
      // biome-ignore lint/suspicious/noExplicitAny: minimal fake Session for tests
    } as any,
    isSessionLoading: false,
  });
}

describe('OutfitItemStack', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    setFakeSession();
  });

  it('renders one thumbnail per item_ids entry', async () => {
    mockUseWardrobeItemImageUrlsQuery.mockReturnValue({
      data: {
        'item-a': { url: 'https://example.com/a.jpg', source: 'thumbnail' },
        'item-b': { url: 'https://example.com/b.jpg', source: 'thumbnail' },
      },
    });

    const { getByTestId } = await render(
      <OutfitItemStack itemIds={['item-a', 'item-b']} />,
    );

    expect(getByTestId('outfit-item-image-item-a')).toBeOnTheScreen();
    expect(getByTestId('outfit-item-image-item-b')).toBeOnTheScreen();
  });

  it('an item id with no resolved image renders the "no longer in your wardrobe" placeholder', async () => {
    mockUseWardrobeItemImageUrlsQuery.mockReturnValue({
      data: {
        'item-a': { url: 'https://example.com/a.jpg', source: 'thumbnail' },
      },
    });

    const { getByTestId, getByText, queryByTestId } = await render(
      <OutfitItemStack itemIds={['item-a', 'item-deleted']} />,
    );

    expect(getByTestId('outfit-item-image-item-a')).toBeOnTheScreen();
    expect(queryByTestId('outfit-item-image-item-deleted')).toBeNull();
    expect(getByTestId('outfit-item-missing-item-deleted')).toBeOnTheScreen();
    expect(getByText('No longer in your wardrobe')).toBeOnTheScreen();
  });

  it('never crashes when the image-urls query has no data yet', async () => {
    mockUseWardrobeItemImageUrlsQuery.mockReturnValue({ data: undefined });

    const { getByTestId } = await render(
      <OutfitItemStack itemIds={['item-a']} />,
    );

    expect(getByTestId('outfit-item-missing-item-a')).toBeOnTheScreen();
  });
});
