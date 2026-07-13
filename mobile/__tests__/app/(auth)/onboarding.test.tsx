import { cleanup, fireEvent, render } from '@testing-library/react-native';
import OnboardingScreen from '../../../app/(auth)/onboarding';

const mockReplace = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({ replace: mockReplace, push: jest.fn() }),
}));

// Smoke test only — this file is a disposable placeholder (SS-004 owns the
// real onboarding flow), per docs/tickets/SS-003-design.md #10.
describe('OnboardingScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  afterEach(async () => {
    await cleanup();
  });

  it('renders without crashing and contains the placeholder copy', async () => {
    const { getByText } = await render(<OnboardingScreen />);
    expect(getByText('Welcome to StyleSense')).toBeOnTheScreen();
    expect(getByText('Onboarding coming soon.')).toBeOnTheScreen();
  });

  it('calls router.replace("/") on button press', async () => {
    const { getByText } = await render(<OnboardingScreen />);
    await fireEvent.press(getByText('Continue'));
    expect(mockReplace).toHaveBeenCalledWith('/');
  });
});
