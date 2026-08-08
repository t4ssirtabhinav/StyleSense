import { EXCLUDE_FINGERPRINTS_CAP } from '../../../features/outfit-ai/outfit-ai.constants';
import { useOutfitAiStore } from '../../../features/outfit-ai/outfit-ai.store';

function resetStore() {
  useOutfitAiStore.setState({
    selectedOccasionKey: null,
    deckIndex: 0,
    dismissedFingerprints: [],
    sessionId: null,
  });
}

describe('outfit-ai.store', () => {
  beforeEach(() => {
    resetStore();
  });

  it('dismissedFingerprints accumulates shown AND dismissed fingerprints', () => {
    useOutfitAiStore.getState().selectOccasion('office');
    useOutfitAiStore.getState().addShownFingerprints(['a', 'b']);
    useOutfitAiStore.getState().addShownFingerprints(['c']);

    expect(useOutfitAiStore.getState().dismissedFingerprints).toEqual([
      'a',
      'b',
      'c',
    ]);
  });

  it('caps at EXCLUDE_FINGERPRINTS_CAP, FIFO (oldest dropped first)', () => {
    useOutfitAiStore.getState().selectOccasion('office');
    const many = Array.from({ length: EXCLUDE_FINGERPRINTS_CAP + 10 }).map(
      (_, i) => `fp-${i}`,
    );
    useOutfitAiStore.getState().addShownFingerprints(many);

    const result = useOutfitAiStore.getState().dismissedFingerprints;
    expect(result.length).toBe(EXCLUDE_FINGERPRINTS_CAP);
    // The oldest 10 ('fp-0'..'fp-9') were dropped; the most recent ones survive.
    expect(result[0]).toBe('fp-10');
    expect(result[result.length - 1]).toBe(
      `fp-${EXCLUDE_FINGERPRINTS_CAP + 9}`,
    );
  });

  it('does not duplicate an already-present fingerprint', () => {
    useOutfitAiStore.getState().selectOccasion('office');
    useOutfitAiStore.getState().addShownFingerprints(['a', 'b']);
    useOutfitAiStore.getState().addShownFingerprints(['a', 'c']);

    expect(useOutfitAiStore.getState().dismissedFingerprints).toEqual([
      'a',
      'b',
      'c',
    ]);
  });

  it('clears dismissedFingerprints and deckIndex when selectedOccasionKey changes', () => {
    useOutfitAiStore.getState().selectOccasion('office');
    useOutfitAiStore.getState().addShownFingerprints(['a', 'b']);
    useOutfitAiStore.getState().advanceDeck();
    useOutfitAiStore.getState().setSessionId('session-1');

    useOutfitAiStore.getState().selectOccasion('festival');

    const state = useOutfitAiStore.getState();
    expect(state.dismissedFingerprints).toEqual([]);
    expect(state.deckIndex).toBe(0);
    expect(state.sessionId).toBeNull();
    expect(state.selectedOccasionKey).toBe('festival');
  });

  it('re-selecting the SAME occasion key preserves the exclusion set (a regenerate, not a switch)', () => {
    useOutfitAiStore.getState().selectOccasion('office');
    useOutfitAiStore.getState().addShownFingerprints(['a']);
    useOutfitAiStore.getState().advanceDeck();

    useOutfitAiStore.getState().selectOccasion('office');

    const state = useOutfitAiStore.getState();
    expect(state.dismissedFingerprints).toEqual(['a']);
    expect(state.deckIndex).toBe(1);
  });

  it('advanceDeck increments deckIndex; resetDeck zeroes it', () => {
    useOutfitAiStore.getState().advanceDeck();
    useOutfitAiStore.getState().advanceDeck();
    expect(useOutfitAiStore.getState().deckIndex).toBe(2);

    useOutfitAiStore.getState().resetDeck();
    expect(useOutfitAiStore.getState().deckIndex).toBe(0);
  });
});
