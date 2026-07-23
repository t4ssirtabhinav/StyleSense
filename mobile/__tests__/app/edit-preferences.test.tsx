import { cleanup, render } from '@testing-library/react-native';
import EditPreferencesScreen from '../../app/edit-preferences';
import { useAuthStore } from '../../features/auth/auth.store';

// Same mocking convention as __tests__/app/(auth)/onboarding.test.tsx's Auth
// Guard test — a plain stand-in that renders the target href.
jest.mock('expo-router', () => {
  const react = jest.requireActual('react');
  const reactNative = jest.requireActual('react-native');
  return {
    Redirect: ({ href }: { href: string }) =>
      react.createElement(reactNative.Text, { testID: 'redirect' }, href),
  };
});

const mockUseOnboardingProgressQuery = jest.fn();
const mockUseOnboardingTaxonomiesQuery = jest.fn();
const mockRefetchProgress = jest.fn();
const mockRefetchTaxonomies = jest.fn();

jest.mock('../../features/onboarding/onboarding.queries', () => ({
  useOnboardingProgressQuery: (userId: string | undefined) =>
    mockUseOnboardingProgressQuery(userId),
  useOnboardingTaxonomiesQuery: () => mockUseOnboardingTaxonomiesQuery(),
}));

// The 5 sections are mocked to plain testID/props-dump stand-ins — each
// section's own chip/cap/save behaviour is already covered by its own test
// file (EditStyleKeywordsSection.test.tsx etc.); this screen's test only
// needs to confirm the right initial slice of stylePreferences reaches each
// section, and the session/banner gating around them.
jest.mock(
  '../../features/onboarding/components/EditStyleKeywordsSection',
  () => ({
    EditStyleKeywordsSection: (props: { initialStyles: string[] }) => {
      const react = jest.requireActual('react');
      const reactNative = jest.requireActual('react-native');
      return react.createElement(
        reactNative.Text,
        { testID: 'mock-style-keywords' },
        JSON.stringify(props.initialStyles),
      );
    },
  }),
);

jest.mock(
  '../../features/onboarding/components/EditWardrobeTypeSection',
  () => ({
    EditWardrobeTypeSection: (props: {
      initialWardrobeType: string | undefined;
    }) => {
      const react = jest.requireActual('react');
      const reactNative = jest.requireActual('react-native');
      return react.createElement(
        reactNative.Text,
        { testID: 'mock-wardrobe-type' },
        String(props.initialWardrobeType),
      );
    },
  }),
);

jest.mock(
  '../../features/onboarding/components/EditOccasionPrioritiesSection',
  () => ({
    EditOccasionPrioritiesSection: (props: {
      initialOccasions: string[];
    }) => {
      const react = jest.requireActual('react');
      const reactNative = jest.requireActual('react-native');
      return react.createElement(
        reactNative.Text,
        { testID: 'mock-occasion-priorities' },
        JSON.stringify(props.initialOccasions),
      );
    },
  }),
);

jest.mock(
  '../../features/onboarding/components/EditBudgetRangeSection',
  () => ({
    EditBudgetRangeSection: (props: {
      initialBudgetRange: string | undefined;
    }) => {
      const react = jest.requireActual('react');
      const reactNative = jest.requireActual('react-native');
      return react.createElement(
        reactNative.Text,
        { testID: 'mock-budget-range' },
        String(props.initialBudgetRange),
      );
    },
  }),
);

jest.mock(
  '../../features/onboarding/components/EditFavouriteColoursSection',
  () => ({
    EditFavouriteColoursSection: (props: { initialColours: string[] }) => {
      const react = jest.requireActual('react');
      const reactNative = jest.requireActual('react-native');
      return react.createElement(
        reactNative.Text,
        { testID: 'mock-favourite-colours' },
        JSON.stringify(props.initialColours),
      );
    },
  }),
);

const FAKE_SESSION = { user: { id: 'user-1' } } as never;

const FULL_PROGRESS_DATA = {
  fullName: 'Priya Sharma',
  gender: 'woman' as const,
  city: 'Mumbai',
  stylePreferences: {
    styles: ['ethnic'],
    wardrobe_type: 'mostly_ethnic' as const,
    occasions_priority: ['office'],
    budget_range: '1000_3000' as const,
    favourite_colours: ['#000000'],
    gender: 'woman' as const,
  },
  onboardingCompleted: true,
};

describe('EditPreferencesScreen (app/edit-preferences.tsx)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useAuthStore.setState({ session: FAKE_SESSION, isSessionLoading: false });
    mockUseOnboardingTaxonomiesQuery.mockReturnValue({
      data: { styleKeywords: [], occasionTypes: [], colourPalette: [] },
      isLoading: false,
      isError: false,
      refetch: mockRefetchTaxonomies,
    });
  });

  afterEach(async () => {
    await cleanup();
    useAuthStore.setState({ session: null, isSessionLoading: true });
  });

  it('shows the loading Card while isSessionLoading', async () => {
    useAuthStore.setState({ session: null, isSessionLoading: true });
    mockUseOnboardingProgressQuery.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      isSuccess: false,
      refetch: mockRefetchProgress,
    });

    const { getByTestId, queryByTestId } = await render(
      <EditPreferencesScreen />,
    );

    expect(getByTestId('edit-preferences-session-loading')).toBeOnTheScreen();
    expect(queryByTestId('redirect')).toBeNull();
  });

  it('redirects to /login when there is no session', async () => {
    useAuthStore.setState({ session: null, isSessionLoading: false });
    mockUseOnboardingProgressQuery.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      isSuccess: false,
      refetch: mockRefetchProgress,
    });

    const { getByTestId } = await render(<EditPreferencesScreen />);

    expect(getByTestId('redirect')).toHaveTextContent('/login');
  });

  it('renders all 5 sections pre-filled from a mocked useOnboardingProgressQuery result', async () => {
    mockUseOnboardingProgressQuery.mockReturnValue({
      data: FULL_PROGRESS_DATA,
      isLoading: false,
      isError: false,
      isSuccess: true,
      refetch: mockRefetchProgress,
    });

    const { getByTestId } = await render(<EditPreferencesScreen />);

    expect(getByTestId('mock-style-keywords')).toHaveTextContent('["ethnic"]');
    expect(getByTestId('mock-wardrobe-type')).toHaveTextContent(
      'mostly_ethnic',
    );
    expect(getByTestId('mock-occasion-priorities')).toHaveTextContent(
      '["office"]',
    );
    expect(getByTestId('mock-budget-range')).toHaveTextContent('1000_3000');
    expect(getByTestId('mock-favourite-colours')).toHaveTextContent(
      '["#000000"]',
    );
  });

  it('shows the "finish setting up" banner when onboardingCompleted is false, and every section still renders underneath it', async () => {
    mockUseOnboardingProgressQuery.mockReturnValue({
      data: { ...FULL_PROGRESS_DATA, onboardingCompleted: false },
      isLoading: false,
      isError: false,
      isSuccess: true,
      refetch: mockRefetchProgress,
    });

    const { getByTestId } = await render(<EditPreferencesScreen />);

    expect(getByTestId('edit-preferences-incomplete-banner')).toBeOnTheScreen();
    expect(getByTestId('mock-style-keywords')).toBeOnTheScreen();
    expect(getByTestId('mock-wardrobe-type')).toBeOnTheScreen();
    expect(getByTestId('mock-occasion-priorities')).toBeOnTheScreen();
    expect(getByTestId('mock-budget-range')).toBeOnTheScreen();
    expect(getByTestId('mock-favourite-colours')).toBeOnTheScreen();
  });

  it('does not show the banner when onboardingCompleted is true', async () => {
    mockUseOnboardingProgressQuery.mockReturnValue({
      data: FULL_PROGRESS_DATA,
      isLoading: false,
      isError: false,
      isSuccess: true,
      refetch: mockRefetchProgress,
    });

    const { queryByTestId } = await render(<EditPreferencesScreen />);

    expect(queryByTestId('edit-preferences-incomplete-banner')).toBeNull();
  });
});
