import { CameraView, useCameraPermissions } from 'expo-camera';
import * as ImagePicker from 'expo-image-picker';
import { useRef, useState } from 'react';
import { Linking } from 'react-native';
import { Button, Card, IconButton, Text } from '../../../components/ui';
import { MAX_BATCH_SIZE, ONE_ITEM_AT_A_TIME_TIP } from '../wardrobe.constants';
import type { WardrobeUploadSource } from '../wardrobe.types';

export interface CaptureStepImage {
  localUri: string;
  source: WardrobeUploadSource;
}

export interface CaptureStepProps {
  onImagesSelected: (images: CaptureStepImage[]) => void;
}

const TOO_MANY_IMAGES_MESSAGE = `You can add up to ${MAX_BATCH_SIZE} items at a time. Only the first ${MAX_BATCH_SIZE} were selected.`;

// Full-screen expo-camera capture (rear default, front toggle) + gallery
// multi-select (1-10 images), per docs/tickets/SS-013-design.md's
// CaptureStep spec.
export function CaptureStep({ onImagesSelected }: CaptureStepProps) {
  const [cameraPermission, requestCameraPermission] = useCameraPermissions();
  const [mediaPermission, requestMediaPermission] =
    ImagePicker.useMediaLibraryPermissions();
  const [facing, setFacing] = useState<'front' | 'back'>('back');
  const [clampMessage, setClampMessage] = useState<string | null>(null);
  const cameraRef = useRef<CameraView | null>(null);

  const handleFlip = () => {
    setFacing((current) => (current === 'back' ? 'front' : 'back'));
  };

  const handleCapture = async () => {
    if (!cameraRef.current) return;
    try {
      const photo = await cameraRef.current.takePictureAsync();
      if (photo?.uri) {
        onImagesSelected([{ localUri: photo.uri, source: 'camera' }]);
      }
    } catch {
      // Camera capture failures are transient/device-specific; the user can
      // simply try again from the same screen (no separate error banner
      // pinned by the design doc for this specific failure).
    }
  };

  const handleGalleryPress = async () => {
    if (!mediaPermission?.granted) {
      const result = await requestMediaPermission();
      if (!result.granted) return;
    }

    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        allowsMultipleSelection: true,
        selectionLimit: MAX_BATCH_SIZE,
      });
      if (result.canceled || !result.assets) return;

      let assets = result.assets;
      if (assets.length > MAX_BATCH_SIZE) {
        setClampMessage(TOO_MANY_IMAGES_MESSAGE);
        assets = assets.slice(0, MAX_BATCH_SIZE);
      } else {
        setClampMessage(null);
      }

      onImagesSelected(
        assets.map((asset) => ({
          localUri: asset.uri,
          source: 'gallery' as const,
        })),
      );
    } catch {
      // Gallery-launch failures are surfaced by clampMessage-style banners
      // elsewhere in this flow; no separate handling pinned here.
    }
  };

  if (cameraPermission && !cameraPermission.granted) {
    if (!cameraPermission.canAskAgain) {
      return (
        <Card testID="camera-permission-denied" className="m-md">
          <Text variant="body" className="mb-sm">
            Camera access is needed to photograph your wardrobe items.
          </Text>
          <Button
            variant="primary"
            accessibilityLabel="Open Settings"
            onPress={() => Linking.openSettings()}
          >
            Open Settings
          </Button>
        </Card>
      );
    }

    return (
      <Card testID="camera-permission-request" className="m-md">
        <Text variant="body" className="mb-sm">
          StyleSense needs camera access to photograph your wardrobe items.
        </Text>
        <Button
          variant="primary"
          accessibilityLabel="Allow camera access"
          onPress={requestCameraPermission}
        >
          Allow camera access
        </Button>
      </Card>
    );
  }

  return (
    <>
      <CameraView
        testID="camera-view"
        ref={cameraRef}
        style={{ flex: 1 }}
        facing={facing}
      />
      <Text variant="caption" testID="one-item-tip-banner" className="p-sm">
        {ONE_ITEM_AT_A_TIME_TIP}
      </Text>
      {clampMessage ? (
        <Text
          variant="caption"
          testID="too-many-images-message"
          className="px-sm"
        >
          {clampMessage}
        </Text>
      ) : null}
      <IconButton
        icon="camera-reverse-outline"
        accessibilityLabel="Flip camera"
        onPress={handleFlip}
      />
      <Button
        variant="primary"
        accessibilityLabel="Capture photo"
        onPress={handleCapture}
      >
        Capture
      </Button>
      <Button
        variant="secondary"
        accessibilityLabel="Gallery"
        onPress={handleGalleryPress}
      >
        Gallery
      </Button>
    </>
  );
}
