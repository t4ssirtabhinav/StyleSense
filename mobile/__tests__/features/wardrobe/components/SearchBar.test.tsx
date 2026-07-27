import { act, fireEvent, render } from '@testing-library/react-native';
import { SearchBar } from '../../../../features/wardrobe/components/SearchBar';
import { SEARCH_DEBOUNCE_MS } from '../../../../features/wardrobe/wardrobe.constants';
import { useWardrobeFilterStore } from '../../../../features/wardrobe/wardrobe.store';

describe('SearchBar', () => {
  beforeEach(() => {
    useWardrobeFilterStore.getState().reset();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('debounces typed input (SEARCH_DEBOUNCE_MS) before writing to the store', async () => {
    jest.useFakeTimers();
    const { getByLabelText } = await render(<SearchBar />);

    await fireEvent.changeText(getByLabelText('Search'), 'kurta');

    expect(useWardrobeFilterStore.getState().search).toBe('');

    await act(async () => {
      jest.advanceTimersByTime(SEARCH_DEBOUNCE_MS - 1);
    });
    expect(useWardrobeFilterStore.getState().search).toBe('');

    await act(async () => {
      jest.advanceTimersByTime(1);
    });
    expect(useWardrobeFilterStore.getState().search).toBe('kurta');
  });

  it('resets both local text and store state immediately (not debounced) on Clear', async () => {
    const { getByLabelText } = await render(<SearchBar />);

    await fireEvent.changeText(getByLabelText('Search'), 'kurta');
    await fireEvent.press(getByLabelText('Clear search'));

    expect(useWardrobeFilterStore.getState().search).toBe('');
    expect(getByLabelText('Search').props.value).toBe('');
  });

  it('the earlier debounced write never lands after Clear', async () => {
    jest.useFakeTimers();
    const { getByLabelText } = await render(<SearchBar />);

    await fireEvent.changeText(getByLabelText('Search'), 'kurta');
    await act(async () => {
      jest.advanceTimersByTime(1);
    });
    await fireEvent.press(getByLabelText('Clear search'));

    await act(async () => {
      jest.advanceTimersByTime(SEARCH_DEBOUNCE_MS);
    });
    expect(useWardrobeFilterStore.getState().search).toBe('');
  });
});
