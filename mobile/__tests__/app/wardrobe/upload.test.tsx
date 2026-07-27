import { fireEvent, render, waitFor } from '@testing-library/react-native';
import WardrobeUploadScreen from '../../../app/wardrobe/upload';
import { useAuthStore } from '../../../features/auth/auth.store';
import * as wardrobeQueries from '../../../features/wardrobe/wardrobe.queries';
import * as wardrobeService from '../../../features/wardrobe/wardrobe.service';
import { useWardrobeBatchStore } from '../../../features/wardrobe/wardrobe.store';

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
jest.mock('../../../features/wardrobe/wardrobe.queries', () => ({
  useUploadWardrobeItem: jest.fn(),
  useProcessWardrobeItem: jest.fn(),
  useSaveWardrobeItemTags: jest.fn(),
}));

const mockSubscribeToItemUpdates = jest.fn();
jest.mock('../../../features/wardrobe/wardrobe.service', () => ({
  subscribeToItemUpdates: (...args: unknown[]) =>
    mockSubscribeToItemUpdates(...args),
  fetchWardrobeItemImageUrl: jest.fn().mockResolvedValue({
    url: 'https://r2.example.com/clean.png',
    source: 'clean',
  }),
}));

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
});
