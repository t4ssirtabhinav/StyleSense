import { render } from '@testing-library/react-native';
import { Text } from '../../../components/ui';
import { EmptyState } from '../../../components/ui/EmptyState';

describe('EmptyState', () => {
  it('renders the given icon, heading, and subtext', async () => {
    const { getByText, getByTestId } = await render(
      <EmptyState
        icon="shirt-outline"
        heading="Your wardrobe is empty"
        subtext="Add your first item to get outfit suggestions."
      />,
    );

    expect(getByText('Your wardrobe is empty')).toBeOnTheScreen();
    expect(
      getByText('Add your first item to get outfit suggestions.'),
    ).toBeOnTheScreen();
    // @expo/vector-icons doesn't forward `name` to the underlying host node
    // (it's consumed internally to pick the glyph, same as IconButton.test.tsx's
    // precedent of not asserting exact icon identity) — presence of the
    // rendered icon element is the testable contract here.
    expect(getByTestId('empty-state-icon')).toBeOnTheScreen();
  });

  it('renders children (CTA slot) when provided', async () => {
    const { getByText } = await render(
      <EmptyState
        icon="compass-outline"
        heading="Nothing here yet"
        subtext="Coming soon."
      >
        <Text>Add item</Text>
      </EmptyState>,
    );

    expect(getByText('Add item')).toBeOnTheScreen();
  });

  it('renders no CTA slot when children are absent', async () => {
    const { queryByText } = await render(
      <EmptyState
        icon="compass-outline"
        heading="Nothing here yet"
        subtext="Coming soon."
      />,
    );

    expect(queryByText('Add item')).toBeNull();
  });
});
