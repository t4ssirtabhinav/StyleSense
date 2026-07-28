import { fireEvent, render } from '@testing-library/react-native';
import { useAuthStore } from '../../../../features/auth/auth.store';
import { WearHistorySection } from '../../../../features/wardrobe/components/WearHistorySection';
import type { WardrobeItemWearRow } from '../../../../features/wardrobe/wardrobe.types';

const mockLogWearMutate = jest.fn();
const mockUpdateWearMutate = jest.fn();
const mockDeleteWearMutate = jest.fn();

let mockWearsQueryState: {
  isLoading: boolean;
  isError: boolean;
  isSuccess: boolean;
  data: WardrobeItemWearRow[];
} = {
  isLoading: false,
  isError: false,
  isSuccess: true,
  data: [],
};

jest.mock('../../../../features/wardrobe/wardrobe.queries', () => ({
  useWardrobeItemWearsQuery: () => mockWearsQueryState,
  useLogWardrobeItemWear: () => ({
    mutate: mockLogWearMutate,
    isPending: false,
  }),
  useUpdateWardrobeItemWear: () => ({
    mutate: mockUpdateWearMutate,
    isPending: false,
  }),
  useDeleteWardrobeItemWear: () => ({
    mutate: mockDeleteWearMutate,
    isPending: false,
  }),
}));

function makeWear(
  overrides: Partial<WardrobeItemWearRow> = {},
): WardrobeItemWearRow {
  return {
    id: 'wear-1',
    item_id: 'item-1',
    user_id: 'user-1',
    worn_on: '2026-07-20',
    created_at: '2026-07-20T00:00:00.000Z',
    ...overrides,
  };
}

describe('WearHistorySection', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useAuthStore.setState({
      // biome-ignore lint/suspicious/noExplicitAny: minimal fake Session for tests
      session: { user: { id: 'user-1' } } as any,
      isSessionLoading: false,
    });
    mockWearsQueryState = {
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: [],
    };
  });

  it('renders one row per wear, newest first, dates in en-IN', async () => {
    mockWearsQueryState = {
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: [
        makeWear({ id: 'wear-2', worn_on: '2026-07-25' }),
        makeWear({ id: 'wear-1', worn_on: '2026-07-20' }),
      ],
    };

    const { getByText, getByTestId } = await render(
      <WearHistorySection
        itemId="item-1"
        purchaseDate={null}
        onBack={jest.fn()}
      />,
    );

    expect(getByTestId('wear-row-wear-2')).toBeOnTheScreen();
    expect(getByTestId('wear-row-wear-1')).toBeOnTheScreen();
    expect(getByText('25 Jul 2026')).toBeOnTheScreen();
    expect(getByText('20 Jul 2026')).toBeOnTheScreen();
  });

  it('renders a loading state', async () => {
    mockWearsQueryState = {
      isLoading: true,
      isError: false,
      isSuccess: false,
      data: [],
    };

    const { getByTestId } = await render(
      <WearHistorySection
        itemId="item-1"
        purchaseDate={null}
        onBack={jest.fn()}
      />,
    );

    expect(getByTestId('wear-history-loading')).toBeOnTheScreen();
  });

  it('renders an error state', async () => {
    mockWearsQueryState = {
      isLoading: false,
      isError: true,
      isSuccess: false,
      data: [],
    };

    const { getByTestId } = await render(
      <WearHistorySection
        itemId="item-1"
        purchaseDate={null}
        onBack={jest.fn()}
      />,
    );

    expect(getByTestId('wear-history-error')).toBeOnTheScreen();
  });

  it('renders "Never worn" for the empty state', async () => {
    const { getByTestId, getByText } = await render(
      <WearHistorySection
        itemId="item-1"
        purchaseDate={null}
        onBack={jest.fn()}
      />,
    );

    expect(getByTestId('wear-history-empty')).toBeOnTheScreen();
    expect(getByText('Never worn')).toBeOnTheScreen();
  });

  it("editing a row's date calls useUpdateWardrobeItemWear with the new date", async () => {
    mockWearsQueryState = {
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: [makeWear({ worn_on: '2026-07-20' })],
    };

    const { getByLabelText, getByPlaceholderText } = await render(
      <WearHistorySection
        itemId="item-1"
        purchaseDate={null}
        onBack={jest.fn()}
      />,
    );

    await fireEvent.press(getByLabelText('Edit wear on 20 Jul 2026'));
    await fireEvent.changeText(
      getByPlaceholderText('DD/MM/YYYY'),
      '18/07/2026',
    );

    expect(mockUpdateWearMutate).toHaveBeenCalledWith(
      { wearId: 'wear-1', itemId: 'item-1', wornOn: '2026-07-18' },
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    );
  });

  it('first delete tap arms, second calls useDeleteWardrobeItemWear', async () => {
    mockWearsQueryState = {
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: [makeWear({ worn_on: '2026-07-20' })],
    };

    const { getByLabelText } = await render(
      <WearHistorySection
        itemId="item-1"
        purchaseDate={null}
        onBack={jest.fn()}
      />,
    );

    await fireEvent.press(getByLabelText('Delete wear on 20 Jul 2026'));
    expect(mockDeleteWearMutate).not.toHaveBeenCalled();

    await fireEvent.press(
      getByLabelText('Tap again to confirm delete of wear on 20 Jul 2026'),
    );
    expect(mockDeleteWearMutate).toHaveBeenCalledWith({
      wearId: 'wear-1',
      itemId: 'item-1',
    });
  });

  it('a duplicate-date save surfaces the friendly conflict message, not a raw Postgres error', async () => {
    mockUpdateWearMutate.mockImplementation(
      (_vars: unknown, options?: { onError?: (error: unknown) => void }) => {
        options?.onError?.({ code: '23505', message: 'duplicate key value' });
      },
    );
    mockWearsQueryState = {
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: [makeWear({ worn_on: '2026-07-20' })],
    };

    const { getByLabelText, getByPlaceholderText, getByText, queryByText } =
      await render(
        <WearHistorySection
          itemId="item-1"
          purchaseDate={null}
          onBack={jest.fn()}
        />,
      );

    await fireEvent.press(getByLabelText('Edit wear on 20 Jul 2026'));
    await fireEvent.changeText(
      getByPlaceholderText('DD/MM/YYYY'),
      '18/07/2026',
    );

    expect(
      getByText('A wear is already logged for that date'),
    ).toBeOnTheScreen();
    expect(queryByText(/duplicate key value/)).toBeNull();
  });

  it('the back button calls onBack', async () => {
    const onBack = jest.fn();
    const { getByLabelText } = await render(
      <WearHistorySection
        itemId="item-1"
        purchaseDate={null}
        onBack={onBack}
      />,
    );

    await fireEvent.press(getByLabelText('Back to item details'));

    expect(onBack).toHaveBeenCalled();
  });
});
