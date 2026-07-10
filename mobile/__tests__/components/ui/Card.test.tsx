import { render } from '@testing-library/react-native';
import { Text as RNText } from 'react-native';
import { Card } from '../../../components/ui/Card';

describe('Card', () => {
  it.each([
    ['elevated', 'rounded-lg'],
    ['flat', 'rounded-md'],
    ['outlined', 'rounded-sm'],
  ] as const)(
    'variant=%s resolves the %s radius class',
    async (variant, expectedRadiusClass) => {
      const { getByTestId } = await render(
        <Card variant={variant} testID="card">
          <RNText>Content</RNText>
        </Card>,
      );
      expect(getByTestId('card')).toHaveProp(
        'className',
        expect.stringContaining(expectedRadiusClass),
      );
    },
  );

  it('the 3 variants resolve to different radius classes from one another', async () => {
    const radii: Array<string | undefined> = [];
    for (const variant of ['elevated', 'flat', 'outlined'] as const) {
      const { getByTestId, unmount } = await render(
        <Card variant={variant} testID="card">
          <RNText>Content</RNText>
        </Card>,
      );
      const className = getByTestId('card').props.className as string;
      radii.push(className.match(/rounded-\w+/)?.[0]);
      await unmount();
    }
    expect(new Set(radii).size).toBe(3);
  });

  it('renders children', async () => {
    const { getByText } = await render(
      <Card>
        <RNText>Card body</RNText>
      </Card>,
    );
    expect(getByText('Card body')).toBeOnTheScreen();
  });
});
