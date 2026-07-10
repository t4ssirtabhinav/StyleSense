import { Image } from 'expo-image';
import { Text as RNText, View } from 'react-native';

export type AvatarSize = 'sm' | 'md' | 'lg';

export interface AvatarProps {
  /** Rendered via expo-image; if absent, falls back to initials. */
  uri?: string;
  /** Used to derive up to 2 initials when `uri` is absent. */
  name?: string;
  size?: AvatarSize;
}

const SIZE_PX: Record<AvatarSize, number> = { sm: 32, md: 48, lg: 64 };
const SIZE_CLASS: Record<AvatarSize, string> = {
  sm: 'h-8 w-8',
  md: 'h-12 w-12',
  lg: 'h-16 w-16',
};
const INITIALS_TEXT_SIZE: Record<AvatarSize, string> = {
  sm: 'text-xs',
  md: 'text-base',
  lg: 'text-xl',
};

function getInitials(name?: string): string {
  if (!name) return '';
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const initials = parts
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
  return initials;
}

export function Avatar({ uri, name, size = 'md' }: AvatarProps) {
  const containerClassName = `${SIZE_CLASS[size]} items-center justify-center overflow-hidden rounded-pill bg-surfaceSecondary`;

  if (uri) {
    return (
      <View className={containerClassName}>
        <Image
          testID="avatar-image"
          source={{ uri }}
          accessibilityLabel={name ? `${name}'s avatar` : 'Avatar'}
          style={{ width: SIZE_PX[size], height: SIZE_PX[size] }}
          contentFit="cover"
        />
      </View>
    );
  }

  return (
    <View className={containerClassName}>
      <RNText
        className={`font-heading-semibold ${INITIALS_TEXT_SIZE[size]} text-textSecondary`}
      >
        {getInitials(name)}
      </RNText>
    </View>
  );
}
