import { fireEvent, render } from '@testing-library/react-native';
import { IconButton } from '../../../components/ui/IconButton';

describe('IconButton', () => {
  it('fires onPress when pressed', async () => {
    const onPress = jest.fn();
    const { getByRole } = await render(
      <IconButton icon="heart" onPress={onPress} accessibilityLabel="Like" />,
    );
    fireEvent.press(getByRole('button'));
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it('does not fire onPress when disabled', async () => {
    const onPress = jest.fn();
    const { getByRole } = await render(
      <IconButton
        icon="heart"
        onPress={onPress}
        accessibilityLabel="Like"
        disabled
      />,
    );
    fireEvent.press(getByRole('button'));
    expect(onPress).not.toHaveBeenCalled();
  });

  it('passes the required accessibilityLabel through to the underlying Pressable', async () => {
    const { getByRole } = await render(
      <IconButton
        icon="heart"
        onPress={jest.fn()}
        accessibilityLabel="Like this outfit"
      />,
    );
    expect(getByRole('button')).toHaveProp(
      'accessibilityLabel',
      'Like this outfit',
    );
  });
});
