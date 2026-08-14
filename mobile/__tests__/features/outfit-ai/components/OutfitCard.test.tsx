import { cleanup, fireEvent, render } from '@testing-library/react-native';
import { OutfitCard } from '../../../../features/outfit-ai/components/OutfitCard';
import type { PortfolioItemResponse } from '../../../../features/outfit-ai/outfit-ai.types';

const mockUseOccasionTaxonomy = jest.fn();
jest.mock('../../../../features/onboarding/onboarding.queries', () => ({
  useOccasionTaxonomy: () => mockUseOccasionTaxonomy(),
}));

// SS-024: OutfitCard now renders FootwearSection, which calls useRouter()
// (for the ADD_FOOTWEAR_CTA route) -- mocked here so every existing test in
// this file keeps rendering outside a real navigation container.
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

const mockOutfitItemStackRender = jest.fn();
jest.mock('../../../../features/outfit-ai/components/OutfitItemStack', () => ({
  OutfitItemStack: (props: unknown) => {
    mockOutfitItemStackRender(props);
    return null;
  },
}));

function item(
  overrides: Partial<PortfolioItemResponse> = {},
): PortfolioItemResponse {
  return {
    item_ids: ['item-a', 'item-b'],
    category_labels: { 'item-a': 'Top', 'item-b': 'Bottom' },
    total_score: 0.837,
    rationale: 'A clean, professional look with balanced formality.',
    rationale_language: 'en',
    is_exploration: false,
    gap_flags: [],
    rank: 1,
    outfit_fingerprint: 'a'.repeat(64),
    ...overrides,
  };
}

describe('OutfitCard', () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    jest.clearAllMocks();
    mockUseOccasionTaxonomy.mockReturnValue({
      label: (key: string) => (key === 'office' ? 'Office' : key),
      badgeColor: (key: string) => (key === 'office' ? 'office' : undefined),
    });
  });

  it('renders the score as "NN% match", never a raw float', async () => {
    const { getByTestId, queryByText } = await render(
      <OutfitCard
        item={item({ total_score: 0.837 })}
        occasionKey="office"
        onAccept={jest.fn()}
        onReject={jest.fn()}
      />,
    );

    expect(getByTestId('outfit-card-score-badge')).toBeOnTheScreen();
    expect(queryByText('0.837')).toBeNull();
  });

  it('reasoning is collapsed by default and expands on press (AC #3)', async () => {
    const rationale = 'A clean, professional look with balanced formality.';
    const { getByTestId } = await render(
      <OutfitCard
        item={item({ rationale })}
        occasionKey="office"
        onAccept={jest.fn()}
        onReject={jest.fn()}
      />,
    );

    const disclosure = getByTestId('reasoning-disclosure');
    expect(disclosure.props.accessibilityLabel).toBe('Expand styling notes');
    await fireEvent.press(disclosure);
    expect(disclosure.props.accessibilityLabel).toBe('Collapse styling notes');
  });

  it('occasion badge uses badgeColor(key) and falls back to neutral while the taxonomy loads', async () => {
    mockUseOccasionTaxonomy.mockReturnValue({
      label: (key: string) => key,
      badgeColor: () => undefined,
    });

    const { getByTestId } = await render(
      <OutfitCard
        item={item()}
        occasionKey="unknown_occasion"
        onAccept={jest.fn()}
        onReject={jest.fn()}
      />,
    );

    expect(getByTestId('outfit-card-occasion-badge')).toBeOnTheScreen();
  });

  it.each([
    ['rule-based', 'Rule-based: balanced formality.'],
    ['LLM', 'LLM: a sharp, versatile pairing.'],
  ])(
    'a %s rationale renders through the same reasoning-disclosure structure (no degraded-visual treatment)',
    async (_label, rationale) => {
      const { getByTestId, queryByTestId } = await render(
        <OutfitCard
          item={item({ rationale })}
          occasionKey="office"
          onAccept={jest.fn()}
          onReject={jest.fn()}
        />,
      );

      // Same testID/structure regardless of rationale source -- no "AI
      // unavailable" badge, no visual second-class treatment.
      expect(getByTestId('reasoning-disclosure')).toBeOnTheScreen();
      expect(queryByTestId('ai-unavailable-badge')).toBeNull();
    },
  );

  it('renders the footwear nudge when the item has gap_flags: [missing_footwear] (SS-024)', async () => {
    const { getByText } = await render(
      <OutfitCard
        item={item({ gap_flags: ['missing_footwear'] })}
        occasionKey="office"
        onAccept={jest.fn()}
        onReject={jest.fn()}
      />,
    );

    expect(getByText('No footwear in your wardrobe yet')).toBeOnTheScreen();
  });

  it('accept/reject buttons call their handlers', async () => {
    const onAccept = jest.fn();
    const onReject = jest.fn();
    const { getByLabelText } = await render(
      <OutfitCard
        item={item()}
        occasionKey="office"
        onAccept={onAccept}
        onReject={onReject}
      />,
    );

    await fireEvent.press(getByLabelText('Save this outfit'));
    await fireEvent.press(getByLabelText('Dismiss this outfit'));

    expect(onAccept).toHaveBeenCalled();
    expect(onReject).toHaveBeenCalled();
  });
});
