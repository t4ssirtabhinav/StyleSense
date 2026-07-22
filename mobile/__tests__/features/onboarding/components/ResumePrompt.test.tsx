import { cleanup, fireEvent, render } from '@testing-library/react-native';
import { ResumePrompt } from '../../../../features/onboarding/components/ResumePrompt';

describe('ResumePrompt', () => {
  afterEach(async () => {
    await cleanup();
  });

  it('"Continue Setup" calls the provided onContinue callback', async () => {
    const onContinue = jest.fn();
    const onSkip = jest.fn();
    const { getByText } = await render(
      <ResumePrompt onContinue={onContinue} onSkip={onSkip} />,
    );

    fireEvent.press(getByText('Continue Setup'));

    expect(onContinue).toHaveBeenCalledTimes(1);
    expect(onSkip).not.toHaveBeenCalled();
  });

  it('"Skip for now" calls onSkip', async () => {
    const onContinue = jest.fn();
    const onSkip = jest.fn();
    const { getByText } = await render(
      <ResumePrompt onContinue={onContinue} onSkip={onSkip} />,
    );

    fireEvent.press(getByText('Skip for now'));

    expect(onSkip).toHaveBeenCalledTimes(1);
    expect(onContinue).not.toHaveBeenCalled();
  });
});
