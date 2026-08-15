// SS-023 — client (Zustand) state for the Style tab's occasion → deck flow.
// Server state (the fetched portfolio itself) lives in React Query
// (outfit-ai.queries.ts), never here — this store only holds what the UI
// needs to remember BETWEEN requests: which occasion is selected, which
// card the deck is showing, and the regenerate exclusion set (design §4).

import { create } from 'zustand';
import { registerUserStateReset } from '../auth/userStateReset';
import { EXCLUDE_FINGERPRINTS_CAP } from './outfit-ai.constants';

export interface OutfitAiState {
  selectedOccasionKey: string | null;
  deckIndex: number;
  /** Every fingerprint shown OR dismissed this session — the regenerate
   * exclusion set. Capped at EXCLUDE_FINGERPRINTS_CAP, FIFO (oldest
   * dropped first). Cleared whenever selectedOccasionKey changes (a
   * different occasion legitimately re-uses the same garments). */
  dismissedFingerprints: string[];
  sessionId: string | null;

  selectOccasion: (occasionKey: string) => void;
  setSessionId: (sessionId: string | null) => void;
  addShownFingerprints: (fingerprints: string[]) => void;
  advanceDeck: () => void;
  resetDeck: () => void;
  reset: () => void;
}

function pushCapped(
  existing: string[],
  incoming: string[],
  cap: number,
): string[] {
  const merged = [...existing];
  for (const fp of incoming) {
    if (!merged.includes(fp)) {
      merged.push(fp);
    }
  }
  if (merged.length <= cap) {
    return merged;
  }
  // FIFO — drop oldest first, keep the most recently shown/dismissed.
  return merged.slice(merged.length - cap);
}

export const useOutfitAiStore = create<OutfitAiState>((set) => ({
  selectedOccasionKey: null,
  deckIndex: 0,
  dismissedFingerprints: [],
  sessionId: null,

  selectOccasion: (occasionKey) =>
    set((state) => ({
      selectedOccasionKey: occasionKey,
      // A different occasion legitimately re-uses the same garments — the
      // exclusion set and deck position are session-scoped to ONE occasion.
      dismissedFingerprints:
        state.selectedOccasionKey === occasionKey
          ? state.dismissedFingerprints
          : [],
      deckIndex:
        state.selectedOccasionKey === occasionKey ? state.deckIndex : 0,
      sessionId:
        state.selectedOccasionKey === occasionKey ? state.sessionId : null,
    })),

  setSessionId: (sessionId) => set({ sessionId }),

  addShownFingerprints: (fingerprints) =>
    set((state) => ({
      dismissedFingerprints: pushCapped(
        state.dismissedFingerprints,
        fingerprints,
        EXCLUDE_FINGERPRINTS_CAP,
      ),
    })),

  advanceDeck: () => set((state) => ({ deckIndex: state.deckIndex + 1 })),

  // Kept exactly as-is (clears deckIndex only) -- app/(tabs)/style.tsx's own
  // regenerate flow relies on this NOT touching
  // selectedOccasionKey/dismissedFingerprints/sessionId. `reset()` below is
  // the full, sign-out-scoped clear; resetDeck() is not folded into it.
  resetDeck: () => set({ deckIndex: 0 }),

  // SS-071 AC #6 — the full reset the sign-out registry needs.
  // resetDeck() above only ever clears 1 of these 4 fields by design (see
  // its own comment); a previous user's selectedOccasionKey,
  // dismissedFingerprints, and sessionId would otherwise survive into the
  // next signed-in user's session on the same device.
  reset: () =>
    set({
      selectedOccasionKey: null,
      deckIndex: 0,
      dismissedFingerprints: [],
      sessionId: null,
    }),
}));

// SS-071 AC #6 — self-registers with the sign-out reset registry. See
// features/auth/userStateReset.ts.
registerUserStateReset(() => useOutfitAiStore.getState().reset());
