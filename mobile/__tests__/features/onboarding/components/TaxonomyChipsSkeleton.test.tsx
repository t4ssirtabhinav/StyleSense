import { cleanup, render } from '@testing-library/react-native';
import { TaxonomyChipsSkeleton } from '../../../../features/onboarding/components/TaxonomyChipsSkeleton';

describe('TaxonomyChipsSkeleton', () => {
  afterEach(async () => {
    await cleanup();
  });

  it('renders exactly `count` Skeleton instances for a given count prop', async () => {
    const { getAllByTestId } = await render(
      <TaxonomyChipsSkeleton count={9} />,
    );

    expect(getAllByTestId('skeleton')).toHaveLength(9);
  });

  it('renders a different count when count changes', async () => {
    const { getAllByTestId } = await render(
      <TaxonomyChipsSkeleton count={3} />,
    );

    expect(getAllByTestId('skeleton')).toHaveLength(3);
  });
});
