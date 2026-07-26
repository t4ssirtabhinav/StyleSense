import { render } from '@testing-library/react-native';
import { act } from 'react-test-renderer';
import { ProcessingStep } from '../../../../features/wardrobe/components/ProcessingStep';
import { SLOW_NETWORK_HINT_DELAY_MS } from '../../../../features/wardrobe/wardrobe.constants';

describe('ProcessingStep', () => {
  it("renders 'Removing background...' when status='removing_bg'", async () => {
    const { getByTestId } = await render(
      <ProcessingStep status="removing_bg" />,
    );
    expect(getByTestId('processing-status-text').props.children).toBe(
      'Removing background...',
    );
  });

  it("renders 'Analysing your item...' when status='tagging'", async () => {
    const { getByTestId } = await render(<ProcessingStep status="tagging" />);
    expect(getByTestId('processing-status-text').props.children).toBe(
      'Analysing your item...',
    );
  });

  it('batch mode renders "{n}/{total}" progress text matching currentIndex/items.length', async () => {
    const { getByTestId } = await render(
      <ProcessingStep status="tagging" currentIndex={1} totalItems={3} />,
    );
    expect(getByTestId('batch-progress-text').props.children).toBe('2/3');
  });

  it('after SLOW_NETWORK_HINT_DELAY_MS elapses without a status change, renders the slow-network hint; not before the delay', async () => {
    jest.useFakeTimers();
    try {
      const { queryByTestId } = await render(
        <ProcessingStep status="removing_bg" />,
      );
      expect(queryByTestId('slow-network-hint')).toBeNull();

      await act(async () => {
        jest.advanceTimersByTime(SLOW_NETWORK_HINT_DELAY_MS - 1);
      });
      expect(queryByTestId('slow-network-hint')).toBeNull();

      await act(async () => {
        jest.advanceTimersByTime(2);
      });
      expect(queryByTestId('slow-network-hint')).toBeTruthy();
    } finally {
      jest.useRealTimers();
    }
  });

  it("status='failed' renders a retry button and a 'skip, tag manually' option", async () => {
    const onRetry = jest.fn();
    const onSkip = jest.fn();
    const { getByLabelText } = await render(
      <ProcessingStep status="failed" onRetry={onRetry} onSkip={onSkip} />,
    );

    expect(getByLabelText('Retry')).toBeTruthy();
    expect(getByLabelText('Skip, tag manually')).toBeTruthy();
  });
});
