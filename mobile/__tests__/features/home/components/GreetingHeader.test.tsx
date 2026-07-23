import { cleanup, render } from '@testing-library/react-native';
import { useAuthStore } from '../../../../features/auth/auth.store';
import { GreetingHeader } from '../../../../features/home/components/GreetingHeader';
import { useUserGreetingQuery } from '../../../../features/home/home.queries';

jest.mock('../../../../features/home/home.queries', () => ({
  useUserGreetingQuery: jest.fn(),
}));

const mockedUseUserGreetingQuery = useUserGreetingQuery as jest.Mock;

function setGreetingQuery(
  overrides: Partial<ReturnType<typeof mockQueryResult>>,
) {
  mockedUseUserGreetingQuery.mockReturnValue(mockQueryResult(overrides));
}

function mockQueryResult(
  overrides: Partial<{
    data: string | null;
    isSuccess: boolean;
    isLoading: boolean;
    isError: boolean;
  }> = {},
) {
  return {
    data: null,
    isSuccess: false,
    isLoading: false,
    isError: false,
    ...overrides,
  };
}

describe('GreetingHeader', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useAuthStore.setState({
      session: { user: { id: 'user-1' } } as never,
      isSessionLoading: false,
    });
  });

  afterEach(async () => {
    await cleanup();
    useAuthStore.setState({ session: null, isSessionLoading: true });
    jest.useRealTimers();
  });

  it('renders "Good morning, {name}!" before noon IST', async () => {
    jest.useFakeTimers().setSystemTime(new Date('2024-01-01T01:30:00.000Z')); // 07:00 IST
    setGreetingQuery({ data: 'Priya Sharma', isSuccess: true });

    const { getByText } = await render(<GreetingHeader />);

    expect(getByText('Good morning, Priya!')).toBeOnTheScreen();
  });

  it('renders "Good afternoon, {name}!" between 12:00-17:00 IST', async () => {
    jest.useFakeTimers().setSystemTime(new Date('2024-01-01T08:30:00.000Z')); // 14:00 IST
    setGreetingQuery({ data: 'Priya Sharma', isSuccess: true });

    const { getByText } = await render(<GreetingHeader />);

    expect(getByText('Good afternoon, Priya!')).toBeOnTheScreen();
  });

  it('renders "Good evening, {name}!" at/after 17:00 IST', async () => {
    jest.useFakeTimers().setSystemTime(new Date('2024-01-01T14:30:00.000Z')); // 20:00 IST
    setGreetingQuery({ data: 'Priya Sharma', isSuccess: true });

    const { getByText } = await render(<GreetingHeader />);

    expect(getByText('Good evening, Priya!')).toBeOnTheScreen();
  });

  it('renders the no-name variant when the query resolves null', async () => {
    setGreetingQuery({ data: null, isSuccess: true });

    const { getByTestId } = await render(<GreetingHeader />);

    const text = getByTestId('greeting-header');
    expect(text.props.children).not.toMatch(/undefined|null/);
    expect(text.props.children).toMatch(/^Good \w+!$/);
  });

  it('renders the no-name variant while loading', async () => {
    setGreetingQuery({ isLoading: true, isSuccess: false });

    const { getByTestId } = await render(<GreetingHeader />);

    expect(getByTestId('greeting-header').props.children).toMatch(
      /^Good \w+!$/,
    );
  });

  it('renders the no-name variant when the query errors', async () => {
    setGreetingQuery({ isError: true, isSuccess: false });

    const { getByTestId } = await render(<GreetingHeader />);

    expect(getByTestId('greeting-header').props.children).toMatch(
      /^Good \w+!$/,
    );
  });
});
