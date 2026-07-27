import { fireEvent, render } from '@testing-library/react-native';
import {
  WearDateField,
  istTodayIso,
  istYesterdayIso,
} from '../../../../features/wardrobe/components/WearDateField';

describe('WearDateField', () => {
  beforeEach(() => {
    jest.useFakeTimers().setSystemTime(new Date('2026-07-27T10:00:00.000Z'));
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('"Today" quick pick resolves to the correct IST date', async () => {
    const onChange = jest.fn();
    const { getByTestId } = await render(
      <WearDateField value={null} onChange={onChange} />,
    );

    await fireEvent.press(getByTestId('wear-date-today'));

    expect(onChange).toHaveBeenCalledWith(istTodayIso());
    // 2026-07-27T10:00:00Z is 15:30 IST -- still 2026-07-27.
    expect(onChange).toHaveBeenCalledWith('2026-07-27');
  });

  it('"Yesterday" quick pick resolves to the correct IST date', async () => {
    const onChange = jest.fn();
    const { getByTestId } = await render(
      <WearDateField value={null} onChange={onChange} />,
    );

    await fireEvent.press(getByTestId('wear-date-yesterday'));

    expect(onChange).toHaveBeenCalledWith(istYesterdayIso());
    expect(onChange).toHaveBeenCalledWith('2026-07-26');
  });

  it('rejects a future date typed manually', async () => {
    const onChange = jest.fn();
    const { getByPlaceholderText, getByText } = await render(
      <WearDateField value={null} onChange={onChange} />,
    );

    await fireEvent.changeText(
      getByPlaceholderText('DD/MM/YYYY'),
      '28/07/2026',
    );

    expect(onChange).not.toHaveBeenCalled();
    expect(getByText("You can't log a wear in the future")).toBeOnTheScreen();
  });

  it('rejects a date before the purchase date', async () => {
    const onChange = jest.fn();
    const { getByPlaceholderText, getByText } = await render(
      <WearDateField
        value={null}
        onChange={onChange}
        purchaseDate="2026-07-10"
      />,
    );

    await fireEvent.changeText(
      getByPlaceholderText('DD/MM/YYYY'),
      '01/07/2026',
    );

    expect(onChange).not.toHaveBeenCalled();
    expect(
      getByText("You can't log a wear before the item's purchase date"),
    ).toBeOnTheScreen();
  });

  it('rejects malformed input without crashing', async () => {
    const onChange = jest.fn();
    const { getByPlaceholderText, getByText } = await render(
      <WearDateField value={null} onChange={onChange} />,
    );

    await fireEvent.changeText(getByPlaceholderText('DD/MM/YYYY'), '31-02');

    expect(onChange).not.toHaveBeenCalled();
    expect(getByText('Enter a valid date as DD/MM/YYYY')).toBeOnTheScreen();
  });

  it('rejects a non-existent calendar date (31/02/2026)', async () => {
    const onChange = jest.fn();
    const { getByPlaceholderText, getByText } = await render(
      <WearDateField value={null} onChange={onChange} />,
    );

    await fireEvent.changeText(
      getByPlaceholderText('DD/MM/YYYY'),
      '31/02/2026',
    );

    expect(onChange).not.toHaveBeenCalled();
    expect(getByText('Enter a valid date as DD/MM/YYYY')).toBeOnTheScreen();
  });

  it('accepts a valid past date typed manually', async () => {
    const onChange = jest.fn();
    const { getByPlaceholderText } = await render(
      <WearDateField value={null} onChange={onChange} />,
    );

    await fireEvent.changeText(
      getByPlaceholderText('DD/MM/YYYY'),
      '15/07/2026',
    );

    expect(onChange).toHaveBeenCalledWith('2026-07-15');
  });
});
