import { fireEvent, render } from '@testing-library/react-native';
import { Button } from '../../../components/ui/Button';

describe('Button', () => {
  it('variant="primary" has the marigold background and dark text classes', async () => {
    const { getByRole, getByText } = await render(
      <Button variant="primary" onPress={jest.fn()}>
        Primary
      </Button>,
    );
    expect(getByRole('button')).toHaveProp(
      'className',
      expect.stringContaining('bg-brand'),
    );
    expect(getByText('Primary')).toHaveProp(
      'className',
      expect.stringContaining('text-textPrimary'),
    );
  });

  it('variant="secondary" and variant="ghost" have visually distinct styling', async () => {
    const secondary = await render(
      <Button variant="secondary" onPress={jest.fn()}>
        Secondary
      </Button>,
    );
    const ghost = await render(
      <Button variant="ghost" onPress={jest.fn()}>
        Ghost
      </Button>,
    );

    const secondaryClassName = secondary.getByRole('button').props
      .className as string;
    const ghostClassName = ghost.getByRole('button').props.className as string;

    expect(secondaryClassName).toEqual(expect.stringContaining('border'));
    expect(ghostClassName).not.toEqual(
      expect.stringContaining('border-peacock'),
    );
  });

  it('shows a spinner when loading and does not call onPress when pressed', async () => {
    const onPress = jest.fn();
    const { getByTestId, getByRole } = await render(
      <Button variant="primary" loading onPress={onPress}>
        Loading
      </Button>,
    );

    expect(getByTestId('button-spinner')).toBeOnTheScreen();
    fireEvent.press(getByRole('button'));
    expect(onPress).not.toHaveBeenCalled();
  });

  it('does not call onPress when disabled', async () => {
    const onPress = jest.fn();
    const { getByRole } = await render(
      <Button variant="primary" disabled onPress={onPress}>
        Disabled
      </Button>,
    );

    fireEvent.press(getByRole('button'));
    expect(onPress).not.toHaveBeenCalled();
  });

  it('calls onPress when enabled and pressed', async () => {
    const onPress = jest.fn();
    const { getByRole } = await render(
      <Button variant="primary" onPress={onPress}>
        Enabled
      </Button>,
    );

    fireEvent.press(getByRole('button'));
    expect(onPress).toHaveBeenCalledTimes(1);
  });
});
