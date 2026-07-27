import { act, render, waitFor } from '@testing-library/react-native';
import { WearLoggedToast } from '../../../../features/wardrobe/components/WearLoggedToast';

describe('WearLoggedToast', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('renders the message', async () => {
    const { getByText } = await render(
      <WearLoggedToast
        message="Outfit logged! Cost per wear: ₹500"
        onDismiss={jest.fn()}
      />,
    );

    expect(getByText('Outfit logged! Cost per wear: ₹500')).toBeOnTheScreen();
  });

  it('auto-dismisses after the given duration', async () => {
    const onDismiss = jest.fn();
    await render(
      <WearLoggedToast
        message="Wear logged for 27 Jul 2026"
        onDismiss={onDismiss}
        durationMs={3000}
      />,
    );

    expect(onDismiss).not.toHaveBeenCalled();

    await act(async () => {
      jest.advanceTimersByTime(3000);
    });

    await waitFor(() => expect(onDismiss).toHaveBeenCalledTimes(1));
  });
});
