import { cleanup, render } from '@testing-library/react-native';
import { StepIndicatorDots } from '../../../../features/onboarding/components/StepIndicatorDots';

describe('StepIndicatorDots', () => {
  afterEach(async () => {
    await cleanup();
  });

  it('renders 4 dots; the dot at currentIndex has the active (marigold) style, the rest do not', async () => {
    const { getByTestId } = await render(
      <StepIndicatorDots currentIndex={2} total={4} />,
    );

    for (let index = 0; index < 4; index += 1) {
      const dot = getByTestId(`step-dot-${index}`);
      if (index === 2) {
        expect(dot).toHaveProp(
          'className',
          expect.stringContaining('bg-brand'),
        );
      } else {
        expect(dot).toHaveProp(
          'className',
          expect.stringContaining('bg-textMuted'),
        );
      }
    }
  });
});
