import { render } from '@testing-library/react-native';
import { Text } from 'react-native';
import { CircularProgress } from '../../../components/ui/CircularProgress';

function getFillOffset(
  getByTestId: (id: string) => { props: Record<string, unknown> },
) {
  const fill = getByTestId('circular-progress-fill');
  return Number(fill.props.strokeDashoffset);
}

describe('CircularProgress', () => {
  it('clamps a negative progress value to 0', async () => {
    const { getByTestId } = await render(<CircularProgress progress={-25} />);
    expect(getByTestId('circular-progress').props.accessibilityValue.now).toBe(
      0,
    );
  });

  it('clamps a >100 progress value to 100', async () => {
    const { getByTestId } = await render(<CircularProgress progress={150} />);
    expect(getByTestId('circular-progress').props.accessibilityValue.now).toBe(
      100,
    );
  });

  it('clamps a NaN progress value to 0', async () => {
    const { getByTestId } = await render(
      <CircularProgress progress={Number.NaN} />,
    );
    expect(getByTestId('circular-progress').props.accessibilityValue.now).toBe(
      0,
    );
  });

  it('exposes accessibilityRole="progressbar" with accessibilityValue.now equal to the clamped progress', async () => {
    const { getByTestId } = await render(<CircularProgress progress={42} />);
    const node = getByTestId('circular-progress');
    expect(node.props.accessibilityRole).toBe('progressbar');
    expect(node.props.accessibilityValue).toEqual({
      min: 0,
      max: 100,
      now: 42,
    });
  });

  it('renders its children centred in the ring', async () => {
    const { getByText } = await render(
      <CircularProgress progress={50}>
        <Text>50</Text>
      </CircularProgress>,
    );
    expect(getByText('50')).toBeTruthy();
  });

  it('renders a longer filled arc (smaller strokeDashoffset) for a higher progress value', async () => {
    const low = await render(<CircularProgress progress={10} />);
    const high = await render(<CircularProgress progress={90} />);

    const lowOffset = getFillOffset(low.getByTestId);
    const highOffset = getFillOffset(high.getByTestId);

    expect(highOffset).toBeLessThan(lowOffset);
  });

  it('uses a default testID of circular-progress and an override when provided', async () => {
    const { getByTestId } = await render(
      <CircularProgress progress={50} testID="custom-ring" />,
    );
    expect(getByTestId('custom-ring')).toBeTruthy();
  });
});
