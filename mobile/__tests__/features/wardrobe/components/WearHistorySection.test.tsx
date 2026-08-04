import { fireEvent, render } from '@testing-library/react-native';
import { useAuthStore } from '../../../../features/auth/auth.store';
import { WearHistorySection } from '../../../../features/wardrobe/components/WearHistorySection';
import type { WardrobeItemWearRow } from '../../../../features/wardrobe/wardrobe.types';

const mockLogWearMutate = jest.fn();
const mockUpdateWearMutate = jest.fn();
const mockDeleteWearMutate = jest.fn();
const mockUseOccasionOptions = jest.fn();

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
  useOccasionOptions: () => mockUseOccasionOptions(),
}));

// (SS-025/SS-035) Occasion chips come from the `occasions` registry at
// runtime. `optionsIncluding` implements the UNION rule: active registry
// PLUS any slug already selected, so an unknown/deactivated occasion stays
// visible and selected instead of being silently dropped.
const REGISTRY_OCCASIONS = [
  { key: 'office', label: 'Office', badgeColor: 'office' as const },
  { key: 'puja', label: 'Puja', badgeColor: 'festival' as const },
];

function humanize(slug: string): string {
  return slug
    .split('_')
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

function occasionTaxonomy() {
  const byKey = Object.fromEntries(REGISTRY_OCCASIONS.map((o) => [o.key, o]));
  return {
    occasions: REGISTRY_OCCASIONS,
    label: (slug: string) => byKey[slug]?.label ?? humanize(slug),
    badgeColor: (slug: string) => byKey[slug]?.badgeColor,
    optionsIncluding: (tags: readonly string[]) => {
      const options = REGISTRY_OCCASIONS.map((o) => ({ ...o }));
      const seen = new Set(options.map((o) => o.key));
      for (const tag of tags) {
        if (tag && !seen.has(tag)) {
          seen.add(tag);
          options.push({
            key: tag,
            label: humanize(tag),
            badgeColor: undefined as never,
          });
        }
      }
      return options;
    },
    isLoading: false,
    isError: false,
    refetch: jest.fn(),
  };
}

function makeWear(
  overrides: Partial<WardrobeItemWearRow> = {},
): WardrobeItemWearRow {
  return {
    id: 'wear-1',
    item_id: 'item-1',
    user_id: 'user-1',
    worn_on: '2026-07-20',
    occasion_key: null,
    outfit_id: null,
    created_at: '2026-07-20T00:00:00.000Z',
    ...overrides,
  } as WardrobeItemWearRow;
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
    mockUseOccasionOptions.mockReturnValue(occasionTaxonomy());
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

  it("editing a row's date calls useUpdateWardrobeItemWear with the new date and the unchanged occasion", async () => {
    mockWearsQueryState = {
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: [makeWear({ worn_on: '2026-07-20', occasion_key: 'office' })],
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
      {
        wearId: 'wear-1',
        itemId: 'item-1',
        wornOn: '2026-07-18',
        occasionKey: 'office',
      },
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

  it('a duplicate-date save with no occasion selected surfaces the plain conflict message', async () => {
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

  it('a duplicate-date save WITH an occasion selected surfaces the occasion-specific conflict message', async () => {
    mockUpdateWearMutate.mockImplementation(
      (_vars: unknown, options?: { onError?: (error: unknown) => void }) => {
        options?.onError?.({ code: '23505', message: 'duplicate key value' });
      },
    );
    mockWearsQueryState = {
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: [makeWear({ worn_on: '2026-07-20', occasion_key: 'office' })],
    };

    const { getByLabelText, getByPlaceholderText, getByText } = await render(
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
      getByText('A wear is already logged for that date and occasion'),
    ).toBeOnTheScreen();
  });

  it('a wear with an occasion renders its label as a badge, not the raw slug', async () => {
    mockWearsQueryState = {
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: [makeWear({ occasion_key: 'office' })],
    };

    const { getByTestId, getByText } = await render(
      <WearHistorySection
        itemId="item-1"
        purchaseDate={null}
        onBack={jest.fn()}
      />,
    );

    expect(getByTestId('wear-row-occasion-wear-1')).toBeOnTheScreen();
    expect(getByText('Office')).toBeOnTheScreen();
  });

  it('a NULL-occasion wear renders the neutral "Any occasion" caption, not a badge', async () => {
    mockWearsQueryState = {
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: [makeWear({ occasion_key: null })],
    };

    const { getByTestId, queryByTestId, getByText } = await render(
      <WearHistorySection
        itemId="item-1"
        purchaseDate={null}
        onBack={jest.fn()}
      />,
    );

    expect(getByTestId('wear-row-no-occasion-wear-1')).toBeOnTheScreen();
    expect(getByText('Any occasion')).toBeOnTheScreen();
    expect(queryByTestId('wear-row-occasion-wear-1')).toBeNull();
  });

  it('adding a wear with a selected occasion passes it to the log mutation', async () => {
    const { getByLabelText, getByTestId } = await render(
      <WearHistorySection
        itemId="item-1"
        purchaseDate={null}
        onBack={jest.fn()}
      />,
    );

    await fireEvent.press(getByLabelText('Add a wear'));
    await fireEvent.press(getByTestId('wear-occasion-office'));
    await fireEvent.press(getByTestId('wear-date-today'));

    expect(mockLogWearMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        itemId: 'item-1',
        userId: 'user-1',
        occasionKey: 'office',
      }),
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it('adding a wear with no occasion selected passes occasionKey: null (the one-tap default)', async () => {
    const { getByLabelText, getByTestId } = await render(
      <WearHistorySection
        itemId="item-1"
        purchaseDate={null}
        onBack={jest.fn()}
      />,
    );

    await fireEvent.press(getByLabelText('Add a wear'));
    await fireEvent.press(getByTestId('wear-date-today'));

    expect(mockLogWearMutate).toHaveBeenCalledWith(
      expect.objectContaining({ occasionKey: null }),
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
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
