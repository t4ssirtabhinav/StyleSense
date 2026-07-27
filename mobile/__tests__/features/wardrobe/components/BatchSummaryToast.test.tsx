import { fireEvent, render } from '@testing-library/react-native';
import { BatchSummaryToast } from '../../../../features/wardrobe/components/BatchSummaryToast';
import type { BatchItemState } from '../../../../features/wardrobe/wardrobe.types';

const mockPush = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

function makeItem(
  taskId: string,
  status: BatchItemState['status'],
): BatchItemState {
  return { taskId, localUri: `file://${taskId}.jpg`, source: 'camera', status };
}

describe('BatchSummaryToast', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders correct success/failure counts from a mixed batch', async () => {
    const items = [
      makeItem('t1', 'saved'),
      makeItem('t2', 'saved'),
      makeItem('t3', 'failed'),
    ];
    const { getByTestId } = await render(
      <BatchSummaryToast items={items} onAddAnother={jest.fn()} />,
    );

    expect(getByTestId('batch-summary-counts').props.children).toBe(
      '2 added, 1 failed',
    );
  });

  it('"Add another" calls reset() and navigates back to Capture', async () => {
    const onAddAnother = jest.fn();
    const { getByLabelText } = await render(
      <BatchSummaryToast items={[]} onAddAnother={onAddAnother} />,
    );

    fireEvent.press(getByLabelText('Add another'));

    expect(onAddAnother).toHaveBeenCalled();
  });

  it('"View wardrobe" navigates to /(tabs)/wardrobe', async () => {
    const { getByLabelText } = await render(
      <BatchSummaryToast items={[]} onAddAnother={jest.fn()} />,
    );

    fireEvent.press(getByLabelText('View wardrobe'));

    expect(mockPush).toHaveBeenCalledWith('/(tabs)/wardrobe');
  });

  // --- SS-019 addition -------------------------------------------------

  it('renders limitReachedMessage text when the prop is present; renders nothing extra when absent', async () => {
    const withMessage = await render(
      <BatchSummaryToast
        items={[]}
        onAddAnother={jest.fn()}
        limitReachedMessage="You've reached the free plan's 50-item wardrobe limit."
      />,
    );
    expect(
      await withMessage.findByTestId('limit-reached-message'),
    ).toBeTruthy();

    const without = await render(
      <BatchSummaryToast items={[]} onAddAnother={jest.fn()} />,
    );
    expect(without.queryByTestId('limit-reached-message')).toBeNull();
  });
});
