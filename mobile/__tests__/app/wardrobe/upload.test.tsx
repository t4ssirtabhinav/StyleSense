import { fireEvent, render, waitFor } from '@testing-library/react-native';
import WardrobeUploadScreen from '../../../app/wardrobe/upload';
import { useAuthStore } from '../../../features/auth/auth.store';
import * as wardrobeQueries from '../../../features/wardrobe/wardrobe.queries';
import * as wardrobeService from '../../../features/wardrobe/wardrobe.service';
import { useWardrobeBatchStore } from '../../../features/wardrobe/wardrobe.store';

// SS-019: wardrobe.service.ts is partially requireActual'd below (for a real
// mapRealtimeRowToTagsDraft) which pulls in its `lib/supabase` import
// transitively -- stubbed here so that side effect doesn't try to build a
// real Supabase client from missing env vars in this test environment.
jest.mock('../../../lib/supabase', () => ({ supabase: {} }));

const mockPush = jest.fn();
const mockBack = jest.fn();
const mockReplace = jest.fn();
const mockCanGoBack = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({
    push: mockPush,
    back: mockBack,
    replace: mockReplace,
    canGoBack: mockCanGoBack,
  }),
}));

jest.mock('expo-camera', () => {
  const React = require('react');
  return {
    CameraView: React.forwardRef(
      (
        props: Record<string, unknown>,
        ref: React.Ref<{ takePictureAsync: () => Promise<never> }>,
      ) => {
        const { View } = require('react-native');
        React.useImperativeHandle(ref, () => ({
          takePictureAsync: jest.fn(),
        }));
        return <View testID={props.testID as string} />;
      },
    ),
    useCameraPermissions: () => [
      { granted: true, canAskAgain: true },
      jest.fn(),
    ],
  };
});

const mockLaunchImageLibraryAsync = jest.fn();
jest.mock('expo-image-picker', () => ({
  useMediaLibraryPermissions: () => [
    { granted: true, canAskAgain: true },
    jest.fn().mockResolvedValue({ granted: true }),
  ],
  launchImageLibraryAsync: (...args: unknown[]) =>
    mockLaunchImageLibraryAsync(...args),
}));

jest.mock('@gorhom/bottom-sheet', () => {
  const actual = jest.requireActual('@gorhom/bottom-sheet');
  const react = jest.requireActual('react');
  const reactNative = jest.requireActual('react-native');
  const MockBottomSheetModal = react.forwardRef(
    (props: Record<string, unknown>, ref: React.Ref<unknown>) => {
      react.useImperativeHandle(ref, () => ({
        present: jest.fn(),
        dismiss: jest.fn(),
      }));
      return react.createElement(
        reactNative.View,
        { testID: 'mock-bottom-sheet-modal' },
        props.children,
      );
    },
  );
  MockBottomSheetModal.displayName = 'MockBottomSheetModal';
  return {
    ...actual,
    BottomSheetModal: MockBottomSheetModal,
    BottomSheetView: reactNative.View,
  };
});

const mockUploadMutateAsync = jest.fn();
const mockProcessMutateAsync = jest.fn();
// (SS-025) ReviewStep (reached once Realtime marks an item tagged/failed)
// sources its occasion chips from useOccasionOptions -- this integration
// test only needs it to render without crashing; occasion-specific
// behaviour is covered by ReviewStep.test.tsx directly.
jest.mock('../../../features/wardrobe/wardrobe.queries', () => ({
  useUploadWardrobeItem: jest.fn(),
  useProcessWardrobeItem: jest.fn(),
  useSaveWardrobeItemTags: jest.fn(),
  useOccasionOptions: () => ({
    occasions: [
      { key: 'casual', label: 'Casual', badgeColor: 'casual' },
      { key: 'office', label: 'Office', badgeColor: 'office' },
      { key: 'festival', label: 'Festival', badgeColor: 'festival' },
    ],
    label: (slug: string) => slug,
    badgeColor: () => undefined,
    optionsIncluding: (tags: readonly string[]) => [
      { key: 'casual', label: 'Casual', badgeColor: 'casual' },
      { key: 'office', label: 'Office', badgeColor: 'office' },
      { key: 'festival', label: 'Festival', badgeColor: 'festival' },
      ...tags
        .filter((t) => !['casual', 'office', 'festival'].includes(t))
        .map((t) => ({ key: t, label: t, badgeColor: undefined })),
    ],
    isLoading: false,
    isError: false,
    refetch: jest.fn(),
  }),
}));

const mockSubscribeToItemUpdates = jest.fn();
jest.mock('../../../features/wardrobe/wardrobe.service', () => {
  const actual = jest.requireActual(
    '../../../features/wardrobe/wardrobe.service',
  );
  return {
    // mapRealtimeRowToTagsDraft is kept real (not mocked) -- this file's
    // integration tests assert on ReviewStep's actually-rendered fields, not
    // on a call-was-made assertion (see docs/tickets/SS-019-design.md's
    // Test plan note on why the latter is exactly the shallow coverage that
    // let this ship).
    mapRealtimeRowToTagsDraft: actual.mapRealtimeRowToTagsDraft,
    subscribeToItemUpdates: (...args: unknown[]) =>
      mockSubscribeToItemUpdates(...args),
    fetchWardrobeItemImageUrl: jest.fn().mockResolvedValue({
      url: 'https://r2.example.com/clean.png',
      source: 'clean',
    }),
  };
});

describe('WardrobeUploadScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockCanGoBack.mockReturnValue(true);
    useWardrobeBatchStore.setState({ items: [], currentIndex: 0 });
    useAuthStore.setState({
      session: { access_token: 'jwt-token', user: { id: 'user-1' } } as never,
      isSessionLoading: false,
    });
    (wardrobeQueries.useUploadWardrobeItem as jest.Mock).mockReturnValue({
      mutateAsync: mockUploadMutateAsync,
    });
    (wardrobeQueries.useProcessWardrobeItem as jest.Mock).mockReturnValue({
      mutateAsync: mockProcessMutateAsync,
    });
    (wardrobeQueries.useSaveWardrobeItemTags as jest.Mock).mockReturnValue({
      mutate: (input: unknown, options?: { onSuccess?: () => void }) => {
        options?.onSuccess?.();
      },
      isPending: false,
    });
    mockSubscribeToItemUpdates.mockReturnValue(jest.fn());
  });

  it('starts on Capture; after a single-item capture, transitions to Processing, then (Realtime ready) to Review', async () => {
    mockLaunchImageLibraryAsync.mockResolvedValue({
      canceled: false,
      assets: [{ uri: 'file://a.jpg' }],
    });
    mockUploadMutateAsync.mockResolvedValue({ itemId: 'item-1', key: 'k' });
    mockProcessMutateAsync.mockResolvedValue(undefined);

    const { getByTestId, getByLabelText, findByTestId } = await render(
      <WardrobeUploadScreen />,
    );

    expect(getByTestId('camera-view')).toBeTruthy();

    await fireEvent.press(getByLabelText('Gallery'));

    await waitFor(() =>
      expect(mockSubscribeToItemUpdates).toHaveBeenCalledWith(
        'item-1',
        expect.any(Function),
      ),
    );

    expect(await findByTestId('processing-status-text')).toBeTruthy();

    const onUpdate = mockSubscribeToItemUpdates.mock.calls[0][1];
    await waitFor(() =>
      onUpdate({
        id: 'item-1',
        processing_status: 'bg_removed',
        ai_tags: { tagging: { status: 'tagged' } },
      }),
    );

    expect(await findByTestId('review-step')).toBeTruthy();
  });

  it('tapping "Choose category" opens the CategoryPicker and selecting a category updates the review draft', async () => {
    mockLaunchImageLibraryAsync.mockResolvedValue({
      canceled: false,
      assets: [{ uri: 'file://a.jpg' }],
    });
    mockUploadMutateAsync.mockResolvedValue({ itemId: 'item-1', key: 'k' });
    mockProcessMutateAsync.mockResolvedValue(undefined);

    const { getByLabelText, findByTestId, getByTestId, getByText } =
      await render(<WardrobeUploadScreen />);

    await fireEvent.press(getByLabelText('Gallery'));

    await waitFor(() =>
      expect(mockSubscribeToItemUpdates).toHaveBeenCalledWith(
        'item-1',
        expect.any(Function),
      ),
    );

    const onUpdate = mockSubscribeToItemUpdates.mock.calls[0][1];
    await waitFor(() =>
      onUpdate({
        id: 'item-1',
        processing_status: 'bg_removed',
        ai_tags: { tagging: { status: 'tagged' } },
      }),
    );
    await findByTestId('review-step');

    // Before opening: button shows placeholder label.
    expect(getByText('Choose category')).toBeTruthy();

    await fireEvent.press(getByLabelText('Choose category'));

    // CategoryPicker's rows (all 21 wardrobe_category values) are reachable.
    const rowForWesternTop = await findByTestId('category-row-western_top');
    expect(rowForWesternTop).toBeTruthy();

    await fireEvent.press(getByTestId('category-row-ethnic_saree'));

    await waitFor(() => expect(getByText('ethnic_saree')).toBeTruthy());
  });

  it('Cancel calls reset() and navigates back on the Capture step', async () => {
    mockCanGoBack.mockReturnValue(true);
    const { getByLabelText } = await render(<WardrobeUploadScreen />);

    await fireEvent.press(getByLabelText('Cancel'));

    expect(mockBack).toHaveBeenCalled();
    expect(mockReplace).not.toHaveBeenCalled();
    expect(useWardrobeBatchStore.getState().items).toEqual([]);
  });

  it('Cancel falls back to replacing with the wardrobe grid when there is no back history (e.g. a direct/refreshed load on this route)', async () => {
    mockCanGoBack.mockReturnValue(false);
    const { getByLabelText } = await render(<WardrobeUploadScreen />);

    await fireEvent.press(getByLabelText('Cancel'));

    expect(mockBack).not.toHaveBeenCalled();
    expect(mockReplace).toHaveBeenCalledWith('/(tabs)/wardrobe');
    expect(useWardrobeBatchStore.getState().items).toEqual([]);
  });

  it('a batch of 3 (2 succeed, 1 fails) ends on BatchSummaryToast with counts 2/1', async () => {
    mockLaunchImageLibraryAsync.mockResolvedValue({
      canceled: false,
      assets: [
        { uri: 'file://a.jpg' },
        { uri: 'file://b.jpg' },
        { uri: 'file://c.jpg' },
      ],
    });
    mockUploadMutateAsync
      .mockResolvedValueOnce({ itemId: 'item-1', key: 'k1' })
      .mockResolvedValueOnce({ itemId: 'item-2', key: 'k2' })
      .mockRejectedValueOnce(new Error('upload failed'));
    mockProcessMutateAsync.mockResolvedValue(undefined);

    const { getByLabelText, findByTestId } = await render(
      <WardrobeUploadScreen />,
    );

    await fireEvent.press(getByLabelText('Gallery'));

    // Item 1: drive to review, save.
    await waitFor(() =>
      expect(mockSubscribeToItemUpdates).toHaveBeenCalledTimes(1),
    );
    let onUpdate = mockSubscribeToItemUpdates.mock.calls[0][1];
    await waitFor(() =>
      onUpdate({
        id: 'item-1',
        processing_status: 'bg_removed',
        ai_tags: { tagging: { status: 'tagged' } },
      }),
    );
    await findByTestId('review-step');
    await fireEvent.press(getByLabelText('Looks Good!'));

    // Item 2: drive to review, save.
    await waitFor(() =>
      expect(mockSubscribeToItemUpdates).toHaveBeenCalledTimes(2),
    );
    onUpdate = mockSubscribeToItemUpdates.mock.calls[1][1];
    await waitFor(() =>
      onUpdate({
        id: 'item-2',
        processing_status: 'bg_removed',
        ai_tags: { tagging: { status: 'tagged' } },
      }),
    );
    await findByTestId('review-step');
    await fireEvent.press(getByLabelText('Looks Good!'));

    // Item 3: upload rejects -> marked failed, batch ends.
    expect(await findByTestId('batch-summary-toast')).toBeTruthy();
    expect((await findByTestId('batch-summary-counts')).props.children).toBe(
      '2 added, 1 failed',
    );
  });

  // --- SS-019 additions ---------------------------------------------------

  it('a Realtime tagged update prefills ReviewStep with the row values, not blank defaults', async () => {
    mockLaunchImageLibraryAsync.mockResolvedValue({
      canceled: false,
      assets: [{ uri: 'file://a.jpg' }],
    });
    mockUploadMutateAsync.mockResolvedValue({ itemId: 'item-1', key: 'k' });
    mockProcessMutateAsync.mockResolvedValue(undefined);

    const {
      getByLabelText,
      findByTestId,
      getByText,
      getByDisplayValue,
      getByTestId,
    } = await render(<WardrobeUploadScreen />);

    await fireEvent.press(getByLabelText('Gallery'));

    await waitFor(() =>
      expect(mockSubscribeToItemUpdates).toHaveBeenCalledWith(
        'item-1',
        expect.any(Function),
      ),
    );
    const onUpdate = mockSubscribeToItemUpdates.mock.calls[0][1];
    await waitFor(() =>
      onUpdate({
        id: 'item-1',
        processing_status: 'bg_removed',
        category: 'ethnic_saree',
        subcategory: 'silk saree',
        color_primary: 'red',
        color_secondary: 'gold',
        pattern: 'floral',
        fabric: 'silk',
        occasion_tags: ['festival'],
        season_tags: ['winter'],
        ai_tags: {
          tagging: {
            status: 'tagged',
            confidence: 0.95,
            moderation: { content_flag: 'ok', contains_person: false },
          },
        },
      }),
    );

    await findByTestId('review-step');

    expect(getByText('ethnic_saree')).toBeTruthy();
    expect(getByDisplayValue('silk saree')).toBeTruthy();
    expect(getByDisplayValue('red')).toBeTruthy();
    expect(getByDisplayValue('gold')).toBeTruthy();
    expect(getByDisplayValue('floral')).toBeTruthy();
    expect(getByDisplayValue('silk')).toBeTruthy();
    // Badge itself doesn't expose a `selected` prop on its rendered
    // Pressable -- selection is styling-only (border-2 border-textPrimary on
    // the inner View, see components/ui/Badge.tsx). Asserting on the
    // rendered className tree, not a mocked call, per the design doc's "real
    // rendered output" instruction.
    expect(
      JSON.stringify(getByTestId('occasion-badge-festival').toJSON()),
    ).toContain('border-2 border-textPrimary');
    expect(
      JSON.stringify(getByTestId('season-badge-winter').toJSON()),
    ).toContain('border-2 border-textPrimary');
  });

  it('a Realtime flagged update with low confidence still prefills tag fields and shows the low-confidence banner', async () => {
    mockLaunchImageLibraryAsync.mockResolvedValue({
      canceled: false,
      assets: [{ uri: 'file://a.jpg' }],
    });
    mockUploadMutateAsync.mockResolvedValue({ itemId: 'item-1', key: 'k' });
    mockProcessMutateAsync.mockResolvedValue(undefined);

    const { getByLabelText, findByTestId, getByDisplayValue } = await render(
      <WardrobeUploadScreen />,
    );

    await fireEvent.press(getByLabelText('Gallery'));
    await waitFor(() =>
      expect(mockSubscribeToItemUpdates).toHaveBeenCalledTimes(1),
    );
    const onUpdate = mockSubscribeToItemUpdates.mock.calls[0][1];
    await waitFor(() =>
      onUpdate({
        id: 'item-1',
        processing_status: 'bg_removed',
        category: 'western_top',
        subcategory: 'blouse',
        color_primary: 'blue',
        color_secondary: null,
        pattern: null,
        fabric: null,
        occasion_tags: [],
        season_tags: [],
        ai_tags: { tagging: { status: 'flagged', confidence: 0.4 } },
      }),
    );

    await findByTestId('review-step');
    expect(getByDisplayValue('blouse')).toBeTruthy();
    expect(await findByTestId('low-confidence-banner')).toBeTruthy();
  });

  it('a Realtime failed tagging update transitions to Review (not stuck on Processing) with blank defaults, no crash', async () => {
    mockLaunchImageLibraryAsync.mockResolvedValue({
      canceled: false,
      assets: [{ uri: 'file://a.jpg' }],
    });
    mockUploadMutateAsync.mockResolvedValue({ itemId: 'item-1', key: 'k' });
    mockProcessMutateAsync.mockResolvedValue(undefined);

    const { getByLabelText, findByTestId, getByText } = await render(
      <WardrobeUploadScreen />,
    );

    await fireEvent.press(getByLabelText('Gallery'));
    await waitFor(() =>
      expect(mockSubscribeToItemUpdates).toHaveBeenCalledTimes(1),
    );
    const onUpdate = mockSubscribeToItemUpdates.mock.calls[0][1];
    await waitFor(() =>
      onUpdate({
        id: 'item-1',
        processing_status: 'bg_removed',
        category: null,
        subcategory: null,
        color_primary: null,
        color_secondary: null,
        pattern: null,
        fabric: null,
        occasion_tags: null,
        season_tags: null,
        ai_tags: { tagging: { status: 'failed' } },
      }),
    );

    expect(await findByTestId('review-step')).toBeTruthy();
    expect(getByText('Choose category')).toBeTruthy();
  });

  it('a wardrobe_limit_reached upload rejection stops the batch after the first item, marks every item failed, shows the limit message, and calls uploadMutation exactly once', async () => {
    mockLaunchImageLibraryAsync.mockResolvedValue({
      canceled: false,
      assets: [
        { uri: 'file://a.jpg' },
        { uri: 'file://b.jpg' },
        { uri: 'file://c.jpg' },
      ],
    });
    const limitMessage =
      "You've reached the free plan's 50-item wardrobe limit. Upgrade to premium for unlimited items.";
    mockUploadMutateAsync.mockRejectedValue({
      code: 'wardrobe_limit_reached',
      message: limitMessage,
      retryable: false,
    });

    const { getByLabelText, findByTestId } = await render(
      <WardrobeUploadScreen />,
    );

    await fireEvent.press(getByLabelText('Gallery'));

    expect(await findByTestId('batch-summary-toast')).toBeTruthy();
    expect((await findByTestId('batch-summary-counts')).props.children).toBe(
      '0 added, 3 failed',
    );
    expect(await findByTestId('limit-reached-message')).toBeTruthy();
    expect(mockUploadMutateAsync).toHaveBeenCalledTimes(1);
  });
});
