import {
  _clearRegisteredResetsForTests,
  registerUserStateReset,
  resetAllUserState,
} from '../../../features/auth/userStateReset';
import { useOnboardingStore } from '../../../features/onboarding/onboarding.store';
import { useOutfitAiStore } from '../../../features/outfit-ai/outfit-ai.store';
import {
  useWardrobeBatchStore,
  useWardrobeFilterStore,
  useWardrobeUploadStore,
} from '../../../features/wardrobe/wardrobe.store';

// Importing the four *.store.ts modules above means each self-registers
// its reset with the real registry at module load (production behaviour) —
// so by the time this file's tests run, resetFns already contains the six
// real store resets in addition to whatever a given test registers. The
// first describe block below only asserts on its OWN fnA/fnB mocks, so
// that is harmless; _clearRegisteredResetsForTests() between its two tests
// only needs to undo what that describe block itself added.

describe('resetAllUserState', () => {
  afterEach(() => {
    _clearRegisteredResetsForTests();
  });

  it('invokes every registered fn exactly once', () => {
    const fnA = jest.fn();
    const fnB = jest.fn();
    registerUserStateReset(fnA);
    registerUserStateReset(fnB);

    resetAllUserState();

    expect(fnA).toHaveBeenCalledTimes(1);
    expect(fnB).toHaveBeenCalledTimes(1);
  });

  it('a registered fn that throws does not prevent the others from running (partial-clear prevention)', () => {
    const throwing = jest.fn(() => {
      throw new Error('boom');
    });
    const after = jest.fn();
    registerUserStateReset(throwing);
    registerUserStateReset(after);

    expect(() => resetAllUserState()).not.toThrow();
    expect(throwing).toHaveBeenCalledTimes(1);
    expect(after).toHaveBeenCalledTimes(1);
  });
});

// SS-071 AC #6 coverage guard — calling resetAllUserState() with all four
// *.store.ts modules' real self-registrations in effect must leave each of
// the six stores at its initial state. This is the test that catches a
// store whose reset() is incomplete, the way useOutfitAiStore's
// resetDeck() was before this ticket (it cleared 1 of 4 fields).
describe('resetAllUserState — coverage guard across all six user-scoped stores', () => {
  beforeEach(() => {
    // The previous describe block's afterEach wipes the WHOLE registry
    // (including the real registrations these store modules made at
    // import time), so it's re-seeded here, before each test, rather than
    // relied on as still-present from module load.
    _clearRegisteredResetsForTests();
    registerUserStateReset(() => useOnboardingStore.getState().reset());
    registerUserStateReset(() => useWardrobeUploadStore.getState().reset());
    registerUserStateReset(() => useWardrobeBatchStore.getState().reset());
    registerUserStateReset(() => useWardrobeFilterStore.getState().reset());
    registerUserStateReset(() => useOutfitAiStore.getState().reset());
  });

  it('resets useOnboardingStore, all three wardrobe stores, and useOutfitAiStore to their initial state', () => {
    const onboardingInitial = useOnboardingStore.getState();
    const uploadInitial = useWardrobeUploadStore.getState();
    const batchInitial = useWardrobeBatchStore.getState();
    const filterInitial = useWardrobeFilterStore.getState();
    const outfitAiInitial = useOutfitAiStore.getState();

    // Seed non-default values into every store.
    useOnboardingStore.setState({
      currentStepIndex: 2,
      fullName: 'Priya Sharma',
      gender: 'woman',
      city: 'Mumbai',
      styles: ['minimalist'],
    });
    useWardrobeUploadStore.setState({
      tasks: {
        t1: {
          taskId: 't1',
          localUri: 'file:///a.jpg',
          source: 'camera',
          status: 'compressing',
          progress: 0,
          lastProgressAt: Date.now(),
        },
      },
    });
    useWardrobeBatchStore.setState({
      items: [
        {
          taskId: 't1',
          localUri: 'file:///a.jpg',
          source: 'camera',
          status: 'queued',
        },
      ],
      currentIndex: 1,
    });
    useWardrobeFilterStore.setState({
      categoryFilter: 'western',
      search: 'blue shirt',
      sort: 'most_worn',
    });
    useOutfitAiStore.setState({
      selectedOccasionKey: 'wedding_guest',
      deckIndex: 3,
      dismissedFingerprints: ['fp1', 'fp2'],
      sessionId: 'session-1',
    });

    resetAllUserState();

    expect(useOnboardingStore.getState()).toMatchObject({
      currentStepIndex: onboardingInitial.currentStepIndex,
      fullName: onboardingInitial.fullName,
      gender: onboardingInitial.gender,
      city: onboardingInitial.city,
      styles: onboardingInitial.styles,
    });
    expect(useWardrobeUploadStore.getState().tasks).toEqual(
      uploadInitial.tasks,
    );
    expect(useWardrobeBatchStore.getState()).toMatchObject({
      items: batchInitial.items,
      currentIndex: batchInitial.currentIndex,
    });
    expect(useWardrobeFilterStore.getState()).toMatchObject({
      categoryFilter: filterInitial.categoryFilter,
      search: filterInitial.search,
      sort: filterInitial.sort,
    });
    expect(useOutfitAiStore.getState()).toMatchObject({
      selectedOccasionKey: outfitAiInitial.selectedOccasionKey,
      deckIndex: outfitAiInitial.deckIndex,
      dismissedFingerprints: outfitAiInitial.dismissedFingerprints,
      sessionId: outfitAiInitial.sessionId,
    });
  });
});
