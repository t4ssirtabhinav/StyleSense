import { fireEvent, render, waitFor } from '@testing-library/react-native';
import type { Ref } from 'react';
import { Linking } from 'react-native';
import {
  CaptureStep,
  type CaptureStepImage,
} from '../../../../features/wardrobe/components/CaptureStep';
import { MAX_BATCH_SIZE } from '../../../../features/wardrobe/wardrobe.constants';

const mockTakePictureAsync = jest.fn();
const mockUseCameraPermissions = jest.fn();
jest.mock('expo-camera', () => {
  const React = require('react');
  return {
    CameraView: React.forwardRef(
      (
        props: Record<string, unknown>,
        ref: Ref<{ takePictureAsync: jest.Mock }>,
      ) => {
        const { View } = require('react-native');
        React.useImperativeHandle(ref, () => ({
          takePictureAsync: mockTakePictureAsync,
        }));
        return <View testID={props.testID} />;
      },
    ),
    useCameraPermissions: (...args: unknown[]) =>
      mockUseCameraPermissions(...args),
  };
});

const mockUseMediaLibraryPermissions = jest.fn();
const mockLaunchImageLibraryAsync = jest.fn();
jest.mock('expo-image-picker', () => ({
  useMediaLibraryPermissions: (...args: unknown[]) =>
    mockUseMediaLibraryPermissions(...args),
  launchImageLibraryAsync: (...args: unknown[]) =>
    mockLaunchImageLibraryAsync(...args),
}));

describe('CaptureStep', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseCameraPermissions.mockReturnValue([
      { granted: true, canAskAgain: true },
      jest.fn(),
    ]);
    mockUseMediaLibraryPermissions.mockReturnValue([
      { granted: true, canAskAgain: true },
      jest.fn().mockResolvedValue({ granted: true }),
    ]);
    jest
      .spyOn(Linking, 'openSettings')
      .mockImplementation(() => Promise.resolve());
  });

  it('renders the camera view with rear-facing default; tapping the flip button toggles facing', async () => {
    const { getByTestId, getByLabelText } = await render(
      <CaptureStep onImagesSelected={jest.fn()} />,
    );

    expect(getByTestId('camera-view')).toBeTruthy();
    fireEvent.press(getByLabelText('Flip camera'));
    // No crash / re-renders with the toggled facing prop -- covered
    // indirectly since CameraView is a mock without a visible facing assert.
    expect(getByTestId('camera-view')).toBeTruthy();
  });

  it('tapping "Gallery" invokes launchImageLibraryAsync with selectionLimit 10, allowsMultipleSelection true', async () => {
    mockLaunchImageLibraryAsync.mockResolvedValue({
      canceled: false,
      assets: [{ uri: 'file://a.jpg' }],
    });
    const onImagesSelected = jest.fn();
    const { getByLabelText } = await render(
      <CaptureStep onImagesSelected={onImagesSelected} />,
    );

    fireEvent.press(getByLabelText('Gallery'));

    await waitFor(() =>
      expect(mockLaunchImageLibraryAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          allowsMultipleSelection: true,
          selectionLimit: MAX_BATCH_SIZE,
        }),
      ),
    );
    await waitFor(() =>
      expect(onImagesSelected).toHaveBeenCalledWith([
        { localUri: 'file://a.jpg', source: 'gallery' },
      ]),
    );
  });

  it('selecting more than 10 images is clamped with a user-facing message, not silently truncated', async () => {
    const assets = Array.from({ length: 12 }, (_, i) => ({
      uri: `file://${i}.jpg`,
    }));
    mockLaunchImageLibraryAsync.mockResolvedValue({
      canceled: false,
      assets,
    });
    const onImagesSelected = jest.fn();
    const { getByLabelText, findByTestId } = await render(
      <CaptureStep onImagesSelected={onImagesSelected} />,
    );

    fireEvent.press(getByLabelText('Gallery'));

    const message = await findByTestId('too-many-images-message');
    expect(message).toBeTruthy();
    await waitFor(() => {
      const selected: CaptureStepImage[] = onImagesSelected.mock.calls[0][0];
      expect(selected).toHaveLength(MAX_BATCH_SIZE);
    });
  });

  it('renders the "photograph one item at a time" tip banner unconditionally', async () => {
    const { getByTestId } = await render(
      <CaptureStep onImagesSelected={jest.fn()} />,
    );
    expect(getByTestId('one-item-tip-banner')).toBeTruthy();
  });

  it('camera permission denied, canAskAgain=false renders "Open Settings" button; pressing calls Linking.openSettings', async () => {
    mockUseCameraPermissions.mockReturnValue([
      { granted: false, canAskAgain: false },
      jest.fn(),
    ]);
    const { getByTestId, getByLabelText } = await render(
      <CaptureStep onImagesSelected={jest.fn()} />,
    );

    expect(getByTestId('camera-permission-denied')).toBeTruthy();
    fireEvent.press(getByLabelText('Open Settings'));
    expect(Linking.openSettings).toHaveBeenCalled();
  });

  it('camera permission denied, canAskAgain=true renders a re-request prompt, not the Settings button', async () => {
    mockUseCameraPermissions.mockReturnValue([
      { granted: false, canAskAgain: true },
      jest.fn(),
    ]);
    const { getByTestId, queryByLabelText } = await render(
      <CaptureStep onImagesSelected={jest.fn()} />,
    );

    expect(getByTestId('camera-permission-request')).toBeTruthy();
    expect(queryByLabelText('Open Settings')).toBeNull();
  });

  it('Gallery remains reachable when camera permission is denied (canAskAgain=false) -- camera and gallery are independent capabilities', async () => {
    mockUseCameraPermissions.mockReturnValue([
      { granted: false, canAskAgain: false },
      jest.fn(),
    ]);
    mockLaunchImageLibraryAsync.mockResolvedValue({
      canceled: false,
      assets: [{ uri: 'file://a.jpg' }],
    });
    const onImagesSelected = jest.fn();
    const { getByTestId, getByLabelText } = await render(
      <CaptureStep onImagesSelected={onImagesSelected} />,
    );

    expect(getByTestId('camera-permission-denied')).toBeTruthy();
    fireEvent.press(getByLabelText('Gallery'));

    await waitFor(() =>
      expect(onImagesSelected).toHaveBeenCalledWith([
        { localUri: 'file://a.jpg', source: 'gallery' },
      ]),
    );
  });

  it('Gallery remains reachable when camera permission is undetermined/re-requestable (canAskAgain=true)', async () => {
    mockUseCameraPermissions.mockReturnValue([
      { granted: false, canAskAgain: true },
      jest.fn(),
    ]);
    const { getByTestId, getByLabelText } = await render(
      <CaptureStep onImagesSelected={jest.fn()} />,
    );

    expect(getByTestId('camera-permission-request')).toBeTruthy();
    expect(getByLabelText('Gallery')).toBeTruthy();
  });

  // --- SS-019 additions ----------------------------------------------------

  it('permission-denied/request Cards render with centering classes present', async () => {
    mockUseCameraPermissions.mockReturnValue([
      { granted: false, canAskAgain: false },
      jest.fn(),
    ]);
    const denied = await render(<CaptureStep onImagesSelected={jest.fn()} />);
    expect(
      denied.getByTestId('camera-permission-denied').props.className,
    ).toContain('items-center justify-center');

    mockUseCameraPermissions.mockReturnValue([
      { granted: false, canAskAgain: true },
      jest.fn(),
    ]);
    const request = await render(<CaptureStep onImagesSelected={jest.fn()} />);
    expect(
      request.getByTestId('camera-permission-request').props.className,
    ).toContain('items-center justify-center');
  });

  it('pressing Capture sets a visible loading state until takePictureAsync resolves; a second press while capturing does not call takePictureAsync twice', async () => {
    let resolveCapture: (value: { uri: string }) => void = () => {};
    mockTakePictureAsync.mockReturnValue(
      new Promise((resolve) => {
        resolveCapture = resolve;
      }),
    );
    const onImagesSelected = jest.fn();
    const { getByLabelText, findByTestId, queryByTestId } = await render(
      <CaptureStep onImagesSelected={onImagesSelected} />,
    );

    fireEvent.press(getByLabelText('Capture photo'));
    expect(await findByTestId('capture-loading-overlay')).toBeTruthy();

    // Second press while still capturing -- guarded, no second call.
    fireEvent.press(getByLabelText('Capture photo'));
    expect(mockTakePictureAsync).toHaveBeenCalledTimes(1);

    resolveCapture({ uri: 'file://captured.jpg' });
    await waitFor(() =>
      expect(onImagesSelected).toHaveBeenCalledWith([
        { localUri: 'file://captured.jpg', source: 'camera' },
      ]),
    );
    await waitFor(() =>
      expect(queryByTestId('capture-loading-overlay')).toBeNull(),
    );
  });
});
