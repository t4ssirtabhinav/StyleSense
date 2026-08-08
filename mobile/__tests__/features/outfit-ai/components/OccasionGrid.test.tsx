import { cleanup, fireEvent, render } from '@testing-library/react-native';
import { OccasionGrid } from '../../../../features/outfit-ai/components/OccasionGrid';

const mockUseOccasionTaxonomy = jest.fn();
jest.mock('../../../../features/onboarding/onboarding.queries', () => ({
  useOccasionTaxonomy: () => mockUseOccasionTaxonomy(),
}));

describe('OccasionGrid', () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('tiles come from the registry hook, not OCCASION_PILLS', async () => {
    mockUseOccasionTaxonomy.mockReturnValue({
      topLevelOccasions: [
        { key: 'office', label: 'Office', sortOrder: 1 },
        { key: 'ganesh_chaturthi', label: 'Ganesh Chaturthi', sortOrder: 2 },
      ],
      badgeColor: () => 'office',
      isLoading: false,
      isError: false,
      isStale: false,
    });

    const { getByTestId, getByText } = await render(
      <OccasionGrid selectedKey={null} onSelect={jest.fn()} />,
    );

    expect(getByTestId('occasion-tile-office')).toBeOnTheScreen();
    expect(getByTestId('occasion-tile-ganesh_chaturthi')).toBeOnTheScreen();
    // A registry occasion with no curated emoji still renders (unlike
    // OCCASION_PILLS's hardcoded 6-item list).
    expect(getByText('Ganesh Chaturthi')).toBeOnTheScreen();
  });

  it('labels are occasion.label (English) with no i18n lookup', async () => {
    mockUseOccasionTaxonomy.mockReturnValue({
      topLevelOccasions: [
        { key: 'wedding_guest', label: 'Wedding', sortOrder: 1 },
      ],
      badgeColor: () => 'wedding',
      isLoading: false,
      isError: false,
      isStale: false,
    });

    const { getByText } = await render(
      <OccasionGrid selectedKey={null} onSelect={jest.fn()} />,
    );

    expect(getByText('Wedding')).toBeOnTheScreen();
  });

  it('loading state renders something, not a blank screen', async () => {
    mockUseOccasionTaxonomy.mockReturnValue({
      topLevelOccasions: [],
      badgeColor: () => undefined,
      isLoading: true,
      isError: false,
      isStale: false,
    });

    const { getByTestId } = await render(
      <OccasionGrid selectedKey={null} onSelect={jest.fn()} />,
    );

    expect(getByTestId('occasion-grid-loading')).toBeOnTheScreen();
  });

  it('error state renders something, not a blank screen', async () => {
    mockUseOccasionTaxonomy.mockReturnValue({
      topLevelOccasions: [],
      badgeColor: () => undefined,
      isLoading: false,
      isError: true,
      isStale: false,
    });

    const { getByTestId } = await render(
      <OccasionGrid selectedKey={null} onSelect={jest.fn()} />,
    );

    expect(getByTestId('occasion-grid-error')).toBeOnTheScreen();
  });

  it('stale state renders a quiet notice, not a blocker', async () => {
    mockUseOccasionTaxonomy.mockReturnValue({
      topLevelOccasions: [{ key: 'office', label: 'Office', sortOrder: 1 }],
      badgeColor: () => 'office',
      isLoading: false,
      isError: false,
      isStale: true,
    });

    const { getByTestId } = await render(
      <OccasionGrid selectedKey={null} onSelect={jest.fn()} />,
    );

    expect(getByTestId('occasion-grid-stale-notice')).toBeOnTheScreen();
    expect(getByTestId('occasion-tile-office')).toBeOnTheScreen();
  });

  it('two occasions sharing a badge colour both render (BL-088 accepted visual constraint)', async () => {
    mockUseOccasionTaxonomy.mockReturnValue({
      topLevelOccasions: [
        { key: 'festival', label: 'Festival', sortOrder: 1 },
        { key: 'party', label: 'Party', sortOrder: 2 },
      ],
      badgeColor: () => 'festival',
      isLoading: false,
      isError: false,
      isStale: false,
    });

    const { getByTestId } = await render(
      <OccasionGrid selectedKey={null} onSelect={jest.fn()} />,
    );

    expect(getByTestId('occasion-tile-festival')).toBeOnTheScreen();
    expect(getByTestId('occasion-tile-party')).toBeOnTheScreen();
  });

  it('tapping a tile calls onSelect with the occasion key', async () => {
    mockUseOccasionTaxonomy.mockReturnValue({
      topLevelOccasions: [{ key: 'office', label: 'Office', sortOrder: 1 }],
      badgeColor: () => 'office',
      isLoading: false,
      isError: false,
      isStale: false,
    });
    const onSelect = jest.fn();

    const { getByTestId } = await render(
      <OccasionGrid selectedKey={null} onSelect={onSelect} />,
    );

    await fireEvent.press(getByTestId('occasion-tile-office'));
    expect(onSelect).toHaveBeenCalledWith('office');
  });
});
