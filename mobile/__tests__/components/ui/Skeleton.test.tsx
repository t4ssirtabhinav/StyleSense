import { render } from '@testing-library/react-native';
import { Skeleton } from '../../../components/ui/Skeleton';

describe('Skeleton', () => {
  it.each([
    ['card', '100%', 160],
    ['listItem', '100%', 64],
    ['circle', 48, 48],
    ['text', '80%', 16],
  ] as const)(
    'variant=%s renders the expected default width/height',
    async (variant, expectedWidth, expectedHeight) => {
      const { getByTestId } = await render(<Skeleton variant={variant} />);
      const style = getByTestId('skeleton').props.style;
      const flattened = Array.isArray(style)
        ? Object.assign({}, ...style)
        : style;
      expect(flattened.width).toBe(expectedWidth);
      expect(flattened.height).toBe(expectedHeight);
    },
  );

  it('accepts explicit width/height overrides', async () => {
    const { getByTestId } = await render(
      <Skeleton variant="text" width={200} height={20} />,
    );
    const style = getByTestId('skeleton').props.style;
    const flattened = Array.isArray(style)
      ? Object.assign({}, ...style)
      : style;
    expect(flattened.width).toBe(200);
    expect(flattened.height).toBe(20);
  });

  it('does not throw when the reanimated shimmer mounts and timers advance', async () => {
    jest.useFakeTimers();
    await render(<Skeleton variant="card" />);
    jest.advanceTimersByTime(2000);
    jest.useRealTimers();
  });
});
