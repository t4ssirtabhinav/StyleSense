import { render } from '@testing-library/react-native';
import { ProgressBar } from '../../../components/ui/ProgressBar';

function flattenStyle(style: unknown) {
  return Array.isArray(style) ? Object.assign({}, ...style) : style;
}

describe('ProgressBar', () => {
  it.each([
    [0, '0%'],
    [50, '50%'],
    [100, '100%'],
  ] as const)('renders the fill at %s%% width', async (value, expected) => {
    const { getByTestId } = await render(<ProgressBar progress={value} />);
    const style = flattenStyle(getByTestId('progress-bar-fill').props.style);
    expect(style.width).toBe(expected);
  });

  it('clamps a negative progress value to 0%', async () => {
    const { getByTestId } = await render(<ProgressBar progress={-25} />);
    const style = flattenStyle(getByTestId('progress-bar-fill').props.style);
    expect(style.width).toBe('0%');
  });

  it('clamps a >100 progress value to 100%', async () => {
    const { getByTestId } = await render(<ProgressBar progress={150} />);
    const style = flattenStyle(getByTestId('progress-bar-fill').props.style);
    expect(style.width).toBe('100%');
  });

  it('treats NaN as 0%', async () => {
    const { getByTestId } = await render(<ProgressBar progress={Number.NaN} />);
    const style = flattenStyle(getByTestId('progress-bar-fill').props.style);
    expect(style.width).toBe('0%');
  });
});
