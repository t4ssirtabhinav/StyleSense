import {
  cleanup,
  fireEvent,
  render,
  waitFor,
} from '@testing-library/react-native';
import OnboardingScreen, {
  STEPS,
  getStepItemType,
} from '../../../app/(auth)/onboarding';
import { useAuthStore } from '../../../features/auth/auth.store';
import { useOnboardingStore } from '../../../features/onboarding/onboarding.store';

const mockReplace = jest.fn();
jest.mock('expo-router', () => {
  const react = jest.requireActual('react');
  const reactNative = jest.requireActual('react-native');
  return {
    useRouter: () => ({ replace: mockReplace, push: jest.fn() }),
    // Same mocking convention as app/(tabs)/_layout.test.tsx's Auth Guard
    // test — a plain stand-in that renders the target href so tests can
    // assert on it without pulling in real navigation.
    Redirect: ({ href }: { href: string }) =>
      react.createElement(reactNative.Text, { testID: 'redirect' }, href),
  };
});

// Same mocking approach as Step1BasicProfile.test.tsx / CityPicker.test.tsx —
// this screen renders Step1BasicProfile (-> CityPicker -> AppBottomSheet).
jest.mock('@gorhom/bottom-sheet', () => {
  const actual = jest.requireActual('@gorhom/bottom-sheet');
  const react = jest.requireActual('react');
  const reactNative = jest.requireActual('react-native');

  const MockBottomSheetModal = react.forwardRef(
    (props: Record<string, unknown>, ref: React.Ref<unknown>) => {
      react.useImperativeHandle(ref, () => ({
        present: jest.fn(),
        dismiss: jest.fn(),
      }));
      return react.createElement(
        reactNative.View,
        { testID: 'mock-bottom-sheet-modal' },
        props.children,
      );
    },
  );
  MockBottomSheetModal.displayName = 'MockBottomSheetModal';

  return {
    ...actual,
    BottomSheetModal: MockBottomSheetModal,
    BottomSheetView: reactNative.View,
  };
});

const mockSaveStep1Mutate = jest.fn();
const mockCompleteOnboardingMutate = jest.fn();
const mockUseOnboardingProgressQuery = jest.fn();
const mockUseOnboardingTaxonomiesQuery = jest.fn();

jest.mock('../../../features/onboarding/onboarding.queries', () => ({
  useSaveStep1Mutation: () => ({
    mutate: mockSaveStep1Mutate,
    isPending: false,
  }),
  useCompleteOnboardingMutation: () => ({
    mutate: mockCompleteOnboardingMutate,
    isPending: false,
  }),
  useOnboardingProgressQuery: (userId: string | undefined) =>
    mockUseOnboardingProgressQuery(userId),
  useOnboardingTaxonomiesQuery: () => mockUseOnboardingTaxonomiesQuery(),
}));

const FAKE_SESSION = { user: { id: 'user-1' } } as never;

describe('OnboardingScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useAuthStore.setState({ session: FAKE_SESSION, isSessionLoading: false });
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      isLoading: true,
      isError: false,
      isSuccess: false,
      data: undefined,
      refetch: jest.fn(),
    });
  });

  afterEach(async () => {
    await cleanup();
    useAuthStore.setState({ session: null, isSessionLoading: true });
    useOnboardingStore.getState().reset();
  });

  // Regression guard for Bug 2 (QA-blocker fix pass, 2026-07-22): /onboarding
  // is in the (auth) route group, which has no Auth Guard, so it's
  // reachable without a session by design. Previously this rendered a
  // wizard whose "Next" button silently no-op'd; now it redirects to
  // /login instead of rendering an unusable screen.
  it('renders a loading state (not the wizard, not a redirect) while isSessionLoading is true', async () => {
    useAuthStore.setState({ session: null, isSessionLoading: true });
    mockUseOnboardingProgressQuery.mockReturnValue({
      isSuccess: false,
      data: undefined,
    });

    const { getByText, queryByTestId, queryByLabelText } = await render(
      <OnboardingScreen />,
    );

    expect(getByText('Loading…')).toBeOnTheScreen();
    expect(queryByTestId('redirect')).toBeNull();
    expect(queryByLabelText('Select city')).toBeNull();
  });

  it('redirects to /login instead of rendering the wizard when there is no session', async () => {
    useAuthStore.setState({ session: null, isSessionLoading: false });
    mockUseOnboardingProgressQuery.mockReturnValue({
      isSuccess: false,
      data: undefined,
    });

    const { getByTestId, queryByLabelText } = await render(
      <OnboardingScreen />,
    );

    expect(getByTestId('redirect')).toHaveTextContent('/login');
    expect(queryByLabelText('Select city')).toBeNull();
  });

  it('brand-new user (full_name null, onboarding_completed false) renders Step 1 directly, no ResumePrompt', async () => {
    mockUseOnboardingProgressQuery.mockReturnValue({
      isSuccess: true,
      data: {
        fullName: '',
        gender: undefined,
        city: '',
        stylePreferences: null,
      },
    });

    const { queryByText, getByLabelText } = await render(<OnboardingScreen />);

    expect(queryByText('Welcome back!')).toBeNull();
    expect(getByLabelText('Select city')).toBeOnTheScreen();
  });

  it('returning incomplete user (full_name non-null, onboarding_completed false) renders ResumePrompt first; Continue Setup advances the pager and pre-fills the store', async () => {
    mockUseOnboardingProgressQuery.mockReturnValue({
      isSuccess: true,
      data: {
        fullName: 'Priya Sharma',
        gender: 'woman',
        city: 'Mumbai',
        stylePreferences: null,
      },
    });

    const { getByText, queryByText } = await render(<OnboardingScreen />);

    expect(getByText('Welcome back!')).toBeOnTheScreen();

    await fireEvent.press(getByText('Continue Setup'));

    await waitFor(() => expect(queryByText('Welcome back!')).toBeNull());
    expect(useOnboardingStore.getState().fullName).toBe('Priya Sharma');
    expect(useOnboardingStore.getState().gender).toBe('woman');
    expect(useOnboardingStore.getState().city).toBe('Mumbai');
    expect(useOnboardingStore.getState().currentStepIndex).toBe(1);
  });

  // Fix pass 5, 2026-07-22 (SS-004): regression guard for the bug where a
  // returning user's already-saved stylePreferences (fetched by
  // useOnboardingProgressQuery) were silently dropped by
  // handleContinueSetup, leaving Steps 2-4 blank despite complete DB data —
  // confirmed live against a fully-completed test user's Supabase row.
  it('returning user with a full stylePreferences blob: Continue Setup pre-fills all 6 style-preference fields into the store, not just fullName/gender/city', async () => {
    mockUseOnboardingProgressQuery.mockReturnValue({
      isSuccess: true,
      data: {
        fullName: 'Priya Sharma',
        gender: 'woman',
        city: 'Mumbai',
        stylePreferences: {
          styles: ['ethnic'],
          wardrobe_type: 'mostly_ethnic',
          occasions_priority: ['office'],
          budget_range: '1000_3000',
          favourite_colours: ['#000000'],
          gender: 'woman',
        },
      },
    });

    const { getByText, queryByText } = await render(<OnboardingScreen />);

    expect(getByText('Welcome back!')).toBeOnTheScreen();

    await fireEvent.press(getByText('Continue Setup'));

    await waitFor(() => expect(queryByText('Welcome back!')).toBeNull());
    expect(useOnboardingStore.getState()).toMatchObject({
      fullName: 'Priya Sharma',
      gender: 'woman',
      city: 'Mumbai',
      styles: ['ethnic'],
      wardrobeType: 'mostly_ethnic',
      occasionsPriority: ['office'],
      budgetRange: '1000_3000',
      favouriteColours: ['#000000'],
    });
  });

  it('pressing Skip at any step calls router.replace("/") without calling completeOnboarding', async () => {
    mockUseOnboardingProgressQuery.mockReturnValue({
      isSuccess: true,
      data: {
        fullName: '',
        gender: undefined,
        city: '',
        stylePreferences: null,
      },
    });

    const { getByLabelText } = await render(<OnboardingScreen />);

    await fireEvent.press(getByLabelText('Skip'));

    expect(mockReplace).toHaveBeenCalledWith('/');
    expect(mockCompleteOnboardingMutate).not.toHaveBeenCalled();
  });

  it('reaching Step 4 and pressing "Get Started" calls completeOnboarding with the full assembled StylePreferences object, then router.replace("/")', async () => {
    mockUseOnboardingProgressQuery.mockReturnValue({
      isSuccess: true,
      data: {
        fullName: '',
        gender: undefined,
        city: '',
        stylePreferences: null,
      },
    });
    mockCompleteOnboardingMutate.mockImplementation(
      (_vars: unknown, { onSuccess }: { onSuccess: () => void }) => {
        onSuccess();
      },
    );

    const store = useOnboardingStore.getState();
    store.setCurrentStepIndex(3);
    store.setFullName('Priya Sharma');
    store.setGender('woman');
    store.setCity('Mumbai');
    store.toggleStyle('ethnic');
    store.setWardrobeType('mostly_ethnic');
    store.toggleOccasion('office');
    store.setBudgetRange('1000_3000');
    store.toggleColour('#000000');

    const { getByText } = await render(<OnboardingScreen />);

    await fireEvent.press(getByText('Get Started'));

    expect(mockCompleteOnboardingMutate).toHaveBeenCalledWith(
      {
        userId: 'user-1',
        data: {
          styles: ['ethnic'],
          wardrobe_type: 'mostly_ethnic',
          occasions_priority: ['office'],
          budget_range: '1000_3000',
          favourite_colours: ['#000000'],
          gender: 'woman',
        },
      },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
    expect(mockReplace).toHaveBeenCalledWith('/');
  });

  // Fix pass 3, 2026-07-22 (SS-004 Fix B): regression guard for "no way to
  // go back a step" — Back is hidden on step 0, and pressing it on a later
  // step decrements currentStepIndex without resetting the store (values
  // must persist since useOnboardingStore is never reset except by the
  // explicit reset() call after "Get Started").
  it('hides the Back button on step 0', async () => {
    mockUseOnboardingProgressQuery.mockReturnValue({
      isSuccess: true,
      data: {
        fullName: '',
        gender: undefined,
        city: '',
        stylePreferences: null,
      },
    });

    const { queryByLabelText } = await render(<OnboardingScreen />);

    expect(queryByLabelText('Back')).toBeNull();
  });

  it('pressing Back after filling Step 1 and advancing to Step 2 returns to Step 1 with fullName/gender/city still populated', async () => {
    mockUseOnboardingProgressQuery.mockReturnValue({
      isSuccess: true,
      data: {
        fullName: '',
        gender: undefined,
        city: '',
        stylePreferences: null,
      },
    });
    mockSaveStep1Mutate.mockImplementation(
      (_vars: unknown, { onSuccess }: { onSuccess: () => void }) => {
        onSuccess();
      },
    );

    const store = useOnboardingStore.getState();
    store.setFullName('Priya Sharma');
    store.setGender('woman');
    store.setCity('Mumbai');

    const { getByText, getByLabelText } = await render(<OnboardingScreen />);

    await fireEvent.press(getByText('Next'));
    expect(useOnboardingStore.getState().currentStepIndex).toBe(1);

    await fireEvent.press(getByLabelText('Back'));

    expect(useOnboardingStore.getState().currentStepIndex).toBe(0);
    expect(useOnboardingStore.getState().fullName).toBe('Priya Sharma');
    expect(useOnboardingStore.getState().gender).toBe('woman');
    expect(useOnboardingStore.getState().city).toBe('Mumbai');
  });

  it('getItemType returns 4 distinct values for the 4 fixed step items', () => {
    const types = new Set(STEPS.map(getStepItemType));
    expect(types.size).toBe(4);
  });

  it('mounting with useOnboardingTaxonomiesQuery still-loading does not crash the shell; Step 1 still renders/functions normally', async () => {
    mockUseOnboardingProgressQuery.mockReturnValue({
      isSuccess: true,
      data: {
        fullName: '',
        gender: undefined,
        city: '',
        stylePreferences: null,
      },
    });

    const { getByLabelText } = await render(<OnboardingScreen />);

    expect(getByLabelText('Select city')).toBeOnTheScreen();
  });
});
