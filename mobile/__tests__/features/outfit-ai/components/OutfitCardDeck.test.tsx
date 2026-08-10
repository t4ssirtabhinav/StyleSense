import {
  act,
  cleanup,
  fireEvent,
  render,
  waitFor,
} from '@testing-library/react-native';
import { useAuthStore } from '../../../../features/auth/auth.store';
import { OutfitCardDeck } from '../../../../features/outfit-ai/components/OutfitCardDeck';
import { useOutfitAiStore } from '../../../../features/outfit-ai/outfit-ai.store';
import type { PortfolioItemResponse } from '../../../../features/outfit-ai/outfit-ai.types';

const mockUseOccasionTaxonomy = jest.fn();
jest.mock('../../../../features/onboarding/onboarding.queries', () => ({
  useOccasionTaxonomy: () => mockUseOccasionTaxonomy(),
}));

const mockRecordOutcomeMutate = jest.fn();
const mockUseRecordOutcomeMutation = jest.fn();
jest.mock('../../../../features/outfit-ai/outfit-ai.queries', () => ({
  useRecordOutcomeMutation: () => mockUseRecordOutcomeMutation(),
}));

const mockOutfitCardRender = jest.fn();
jest.mock('../../../../features/outfit-ai/components/OutfitCard', () => ({
  OutfitCard: (props: {
    onAccept: () => void;
    onReject: () => void;
    testID?: string;
  }) => {
    mockOutfitCardRender(props);
    const { View, Text, Pressable } = jest.requireActual('react-native');
    return (
      <View testID="outfit-card-stub">
        <Pressable
          accessibilityLabel="Save this outfit"
          onPress={props.onAccept}
        >
          <Text>Save</Text>
        </Pressable>
        <Pressable
          accessibilityLabel="Dismiss this outfit"
          onPress={props.onReject}
        >
          <Text>Dismiss</Text>
        </Pressable>
      </View>
    );
  },
}));

const mockAcceptedOutfitPanelRender = jest.fn();
jest.mock(
  '../../../../features/outfit-ai/components/AcceptedOutfitPanel',
  () => ({
    AcceptedOutfitPanel: (props: unknown) => {
      mockAcceptedOutfitPanelRender(props);
      return null;
    },
  }),
);

function setFakeSession() {
  useAuthStore.setState({
    session: {
      user: { id: 'user-1' },
      access_token: 'jwt-token',
      // biome-ignore lint/suspicious/noExplicitAny: minimal fake Session for tests
    } as any,
    isSessionLoading: false,
  });
}

function items(count: number): PortfolioItemResponse[] {
  return Array.from({ length: count }).map((_, i) => ({
    item_ids: [`item-${i}-a`, `item-${i}-b`],
    category_labels: {},
    total_score: 0.8,
    rationale: 'x',
    rationale_language: 'en',
    is_exploration: false,
    gap_flags: [],
    rank: i + 1,
    outfit_fingerprint: `${i}`.repeat(64).slice(0, 64),
  }));
}

describe('OutfitCardDeck', () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    jest.clearAllMocks();
    useOutfitAiStore.setState({
      selectedOccasionKey: 'office',
      deckIndex: 0,
      dismissedFingerprints: [],
      sessionId: 'session-1',
    });
    setFakeSession();
    mockUseOccasionTaxonomy.mockReturnValue({ label: (key: string) => key });
    mockUseRecordOutcomeMutation.mockReturnValue({
      mutate: mockRecordOutcomeMutate,
    });
  });

  it('accept button calls useRecordOutcomeMutation with saved and the card session_id/rank', async () => {
    const { getByLabelText } = await render(
      <OutfitCardDeck
        portfolio={items(2)}
        occasionKey="office"
        sessionId="session-1"
        limitedOptions={false}
        onRegenerate={jest.fn()}
      />,
    );

    await act(async () => {
      fireEvent.press(getByLabelText('Save this outfit'));
    });

    expect(mockRecordOutcomeMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        request: expect.objectContaining({
          session_id: 'session-1',
          rank: 1,
          outcome_type: 'saved',
        }),
        jwt: 'jwt-token',
      }),
      expect.anything(),
    );
  });

  it('reject button calls dismissed and advances the deck (no toast)', async () => {
    const { getByLabelText, getByTestId } = await render(
      <OutfitCardDeck
        portfolio={items(2)}
        occasionKey="office"
        sessionId="session-1"
        limitedOptions={false}
        onRegenerate={jest.fn()}
      />,
    );

    await act(async () => {
      fireEvent.press(getByLabelText('Dismiss this outfit'));
    });

    expect(mockRecordOutcomeMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        request: expect.objectContaining({
          outcome_type: 'dismissed',
          rank: 1,
        }),
      }),
    );
    // Deck advanced -- the second card (rank 2) is now shown.
    await waitFor(() => {
      expect(mockOutfitCardRender).toHaveBeenLastCalledWith(
        expect.objectContaining({ item: expect.objectContaining({ rank: 2 }) }),
      );
    });
    expect(getByTestId('outfit-card-stub')).toBeOnTheScreen();
  });

  it('every swipe action is reachable via an accessible button, not only a gesture', async () => {
    const { getByLabelText } = await render(
      <OutfitCardDeck
        portfolio={items(1)}
        occasionKey="office"
        sessionId="session-1"
        limitedOptions={false}
        onRegenerate={jest.fn()}
      />,
    );

    expect(getByLabelText('Save this outfit')).toBeOnTheScreen();
    expect(getByLabelText('Dismiss this outfit')).toBeOnTheScreen();
  });

  it('exhausting the deck renders the regenerate CTA', async () => {
    useOutfitAiStore.setState({ deckIndex: 1 });

    const { getByLabelText, getByTestId } = await render(
      <OutfitCardDeck
        portfolio={items(1)}
        occasionKey="office"
        sessionId="session-1"
        limitedOptions={false}
        onRegenerate={jest.fn()}
      />,
    );

    expect(getByTestId('outfit-card-deck-exhausted')).toBeOnTheScreen();
    expect(getByLabelText('Not quite right — regenerate')).toBeOnTheScreen();
  });

  it('exhausted-with-limited-options shows the "every look" copy', async () => {
    useOutfitAiStore.setState({ deckIndex: 1 });

    const { getByText } = await render(
      <OutfitCardDeck
        portfolio={items(1)}
        occasionKey="office"
        sessionId="session-1"
        limitedOptions={true}
        onRegenerate={jest.fn()}
      />,
    );

    expect(
      getByText("That's every look we can build from your wardrobe right now"),
    ).toBeOnTheScreen();
  });
});
