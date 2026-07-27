import { render } from '@testing-library/react-native';
import { FreeTierBanner } from '../../../../features/wardrobe/components/FreeTierBanner';

const EXPECTED_TEXT =
  "You're approaching the free plan's 50-item limit (45/50). Upgrade to premium for unlimited items.";

describe('FreeTierBanner', () => {
  it('is hidden below 45 items for planTier=free', async () => {
    const { queryByTestId } = await render(
      <FreeTierBanner itemCount={44} planTier="free" />,
    );

    expect(queryByTestId('free-tier-banner')).toBeNull();
  });

  it('is visible at 45+ items for planTier=free', async () => {
    const { getByTestId, getByText } = await render(
      <FreeTierBanner itemCount={45} planTier="free" />,
    );

    expect(getByTestId('free-tier-banner')).toBeOnTheScreen();
    expect(getByText(EXPECTED_TEXT)).toBeOnTheScreen();
  });

  it('is hidden at any count for planTier=premium', async () => {
    const { queryByTestId } = await render(
      <FreeTierBanner itemCount={49} planTier="premium" />,
    );

    expect(queryByTestId('free-tier-banner')).toBeNull();
  });

  it('is hidden at any count for planTier=premium_annual', async () => {
    const { queryByTestId } = await render(
      <FreeTierBanner itemCount={49} planTier="premium_annual" />,
    );

    expect(queryByTestId('free-tier-banner')).toBeNull();
  });

  it('is hidden when planTier is null/undefined and count is below threshold (fail-safe)', async () => {
    const { queryByTestId } = await render(
      <FreeTierBanner itemCount={10} planTier={null} />,
    );

    expect(queryByTestId('free-tier-banner')).toBeNull();
  });
});
