import { fireEvent, render } from '@testing-library/react-native';
import { Badge } from '../../../components/ui/Badge';

describe('Badge', () => {
  it.each([
    ['wedding', 'bg-occasionWedding', 'text-textPrimary'],
    ['festival', 'bg-occasionFestival', 'text-textPrimary'],
    ['office', 'bg-occasionOffice', 'text-white'],
    ['casual', 'bg-occasionCasual', 'text-white'],
  ] as const)(
    'occasion=%s pairs %s bg with %s text',
    async (occasion, expectedBg, expectedText) => {
      const { getByTestId, getByText } = await render(
        <Badge label="Occasion" occasion={occasion} testID="badge" />,
      );
      expect(getByTestId('badge')).toHaveProp(
        'className',
        expect.stringContaining(expectedBg),
      );
      expect(getByText('Occasion')).toHaveProp(
        'className',
        expect.stringContaining(expectedText),
      );
    },
  );

  it('omitting occasion renders the neutral grey badge', async () => {
    const { getByTestId } = await render(
      <Badge label="Neutral" testID="badge" />,
    );
    expect(getByTestId('badge')).toHaveProp(
      'className',
      expect.stringContaining('bg-surfaceSecondary'),
    );
  });

  it('truncates a 25-character label to 20 chars + an ellipsis', async () => {
    const longLabel = 'a'.repeat(25);
    const expectedTruncated = `${'a'.repeat(20)}…`;
    const { getByText, queryByText } = await render(
      <Badge label={longLabel} />,
    );
    expect(expectedTruncated).toHaveLength(21);
    expect(getByText(expectedTruncated)).toBeOnTheScreen();
    expect(queryByText(longLabel)).toBeNull();
  });

  it('truncate=false renders a >20-char label verbatim (SS-022)', async () => {
    const longLabel = 'Dressing for 28°C, partly cloudy';
    const { getByText, queryByText } = await render(
      <Badge label={longLabel} truncate={false} />,
    );
    expect(getByText(longLabel)).toBeOnTheScreen();
    expect(queryByText(/…$/)).toBeNull();
  });

  it('is touchable when onPress is provided', async () => {
    const onPress = jest.fn();
    const { getByRole } = await render(
      <Badge label="Chip" onPress={onPress} />,
    );
    fireEvent.press(getByRole('button'));
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it('is not interactive when onPress is absent', async () => {
    const { queryByRole } = await render(<Badge label="Static" />);
    expect(queryByRole('button')).toBeNull();
  });
});
