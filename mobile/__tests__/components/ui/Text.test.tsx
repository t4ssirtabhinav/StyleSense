import { render } from '@testing-library/react-native';
import { Text } from '../../../components/ui/Text';

describe('Text', () => {
  it.each([
    ['display', 'font-display'],
    ['heading', 'font-heading'],
    ['body', 'font-body'],
    ['caption', 'font-body'],
    ['mono', 'font-mono'],
  ] as const)(
    'variant=%s resolves the %s font-family class',
    async (variant, expectedFontClass) => {
      const { getByText } = await render(<Text variant={variant}>Hello</Text>);
      const node = getByText('Hello');
      expect(node).toHaveProp(
        'className',
        expect.stringContaining(expectedFontClass),
      );
    },
  );

  it('script="devanagari" overrides to the Noto Sans Devanagari family regardless of variant', async () => {
    const { getByText } = await render(
      <Text variant="display" script="devanagari">
        नमस्ते
      </Text>,
    );
    const node = getByText('नमस्ते');
    expect(node).toHaveProp('className', expect.stringContaining('font-hindi'));
    expect(node.props.className).not.toEqual(
      expect.stringContaining('font-display'),
    );
  });

  it('defaults to body variant and primary color', async () => {
    const { getByText } = await render(<Text>Default</Text>);
    const node = getByText('Default');
    expect(node).toHaveProp('className', expect.stringContaining('font-body'));
    expect(node).toHaveProp(
      'className',
      expect.stringContaining('text-textPrimary'),
    );
  });

  it('caption variant defaults to muted color', async () => {
    const { getByText } = await render(<Text variant="caption">Muted</Text>);
    const node = getByText('Muted');
    expect(node).toHaveProp(
      'className',
      expect.stringContaining('text-textMuted'),
    );
  });

  it('renders provided children text', async () => {
    const { getByText } = await render(<Text>Hello world</Text>);
    expect(getByText('Hello world')).toBeOnTheScreen();
  });
});
