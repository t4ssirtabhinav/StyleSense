import { render } from '@testing-library/react-native';
import { Avatar } from '../../../components/ui/Avatar';

describe('Avatar', () => {
  it('renders an expo-image Image when uri is set', async () => {
    const { getByTestId } = await render(
      <Avatar uri="https://example.com/photo.jpg" name="Aayushi Joshi" />,
    );
    const image = getByTestId('avatar-image');
    expect(image).toBeOnTheScreen();
    expect(image.props.source).toEqual(
      expect.arrayContaining([{ uri: 'https://example.com/photo.jpg' }]),
    );
  });

  it('falls back to initials when no uri is provided', async () => {
    const { getByText, queryByTestId } = await render(
      <Avatar name="Aayushi Joshi" />,
    );
    expect(getByText('AJ')).toBeOnTheScreen();
    expect(queryByTestId('avatar-image')).toBeNull();
  });

  it('derives initials from a single-word name', async () => {
    const { getByText } = await render(<Avatar name="Aayushi" />);
    expect(getByText('A')).toBeOnTheScreen();
  });

  it('renders no initials text when neither uri nor name is provided', async () => {
    const { queryByTestId } = await render(<Avatar />);
    expect(queryByTestId('avatar-image')).toBeNull();
  });
});
