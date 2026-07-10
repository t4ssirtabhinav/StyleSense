import { render } from '@testing-library/react-native';
import HomeScreen from '../../app/index';

// Smoke test for the SS-008 migration off raw View/Text (see
// docs/tickets/SS-008-design.md's migration decision): asserts the rendered
// tree is built from the token-driven Card/Text components, not the
// pre-migration literal `bg-white`/`text-dark` raw RN primitives.
describe('HomeScreen (app/index.tsx)', () => {
  it('renders inside a Card using the flat variant', async () => {
    const { getByTestId } = await render(<HomeScreen />);
    // Card has no accessibilityRole; assert via its computed variant classes
    // rather than the file's raw JSX, since that's what actually renders.
    const root = getByTestId('home-card');
    expect(root).toHaveProp('className', expect.stringContaining('rounded-md'));
    expect(root).toHaveProp(
      'className',
      expect.stringContaining('bg-surfaceSecondary'),
    );
  });

  it('renders the StyleSense heading via the Text component (font-heading class)', async () => {
    const { getByText } = await render(<HomeScreen />);
    const heading = getByText('StyleSense');
    expect(heading).toHaveProp(
      'className',
      expect.stringContaining('font-heading'),
    );
  });

  it('renders the two status lines via the Text component (font-body class)', async () => {
    const { getByText } = await render(<HomeScreen />);
    expect(getByText('Expo Router + NativeWind is working.')).toHaveProp(
      'className',
      expect.stringContaining('font-body'),
    );
    expect(getByText('Prod')).toHaveProp(
      'className',
      expect.stringContaining('font-body'),
    );
  });
});
