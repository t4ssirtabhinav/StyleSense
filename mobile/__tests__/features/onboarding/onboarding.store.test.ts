import { act, cleanup, renderHook } from '@testing-library/react-native';
import { useOnboardingStore } from '../../../features/onboarding/onboarding.store';

describe('useOnboardingStore', () => {
  afterEach(async () => {
    await cleanup();
    useOnboardingStore.getState().reset();
  });

  describe('toggleOccasion', () => {
    it('selects up to 3, a 4th call when 3 are already selected is a no-op', async () => {
      const { toggleOccasion } = useOnboardingStore.getState();

      await act(async () => {
        toggleOccasion('office');
        toggleOccasion('wedding');
        toggleOccasion('festival');
        toggleOccasion('casual');
      });

      expect(useOnboardingStore.getState().occasionsPriority).toEqual([
        'office',
        'wedding',
        'festival',
      ]);
    });

    it('deselecting an already-selected one always works regardless of count', async () => {
      const { toggleOccasion } = useOnboardingStore.getState();

      await act(async () => {
        toggleOccasion('office');
        toggleOccasion('wedding');
        toggleOccasion('festival');
        toggleOccasion('wedding');
      });

      expect(useOnboardingStore.getState().occasionsPriority).toEqual([
        'office',
        'festival',
      ]);
    });
  });

  describe('toggleColour', () => {
    it('selects up to 5, a 6th call when 5 are already selected is a no-op', async () => {
      const { toggleColour } = useOnboardingStore.getState();

      await act(async () => {
        toggleColour('#000000');
        toggleColour('#FFFFFF');
        toggleColour('#7B241C');
        toggleColour('#1B2A4A');
        toggleColour('#2E5C8A');
        toggleColour('#E8A420');
      });

      expect(useOnboardingStore.getState().favouriteColours).toEqual([
        '#000000',
        '#FFFFFF',
        '#7B241C',
        '#1B2A4A',
        '#2E5C8A',
      ]);
    });
  });

  it('setCurrentStepIndex updates state and a typed selector returns the updated value', async () => {
    const { result } = await renderHook(() =>
      useOnboardingStore((state) => state.currentStepIndex),
    );

    await act(async () => {
      useOnboardingStore.getState().setCurrentStepIndex(2);
    });

    expect(result.current).toBe(2);
  });

  it('wizard-answer setters update state and a typed selector reflects it', async () => {
    const { result } = await renderHook(() =>
      useOnboardingStore((state) => state.fullName),
    );

    await act(async () => {
      useOnboardingStore.getState().setFullName('Priya Sharma');
    });

    expect(result.current).toBe('Priya Sharma');
  });

  describe('hydrateFromProgress', () => {
    // Fix pass 5, 2026-07-22 (SS-004): regression guard for the bug where
    // a fetched stylePreferences blob was silently dropped, leaving
    // Steps 2-4 blank on resume despite complete DB data.
    it('with a full stylePreferences object, populates all 6 corresponding store fields', async () => {
      await act(async () => {
        useOnboardingStore.getState().hydrateFromProgress({
          fullName: 'Priya Sharma',
          gender: 'woman',
          city: 'Mumbai',
          stylePreferences: {
            styles: ['ethnic', 'western'],
            wardrobe_type: 'mostly_ethnic',
            occasions_priority: ['office', 'wedding'],
            budget_range: '1000_3000',
            favourite_colours: ['#000000', '#FFFFFF'],
            gender: 'woman',
          },
        });
      });

      expect(useOnboardingStore.getState()).toMatchObject({
        fullName: 'Priya Sharma',
        gender: 'woman',
        city: 'Mumbai',
        styles: ['ethnic', 'western'],
        wardrobeType: 'mostly_ethnic',
        occasionsPriority: ['office', 'wedding'],
        budgetRange: '1000_3000',
        favouriteColours: ['#000000', '#FFFFFF'],
      });
    });

    it('with stylePreferences: null, only sets fullName/gender/city and leaves array/undefined fields at initial defaults, no crash', async () => {
      await act(async () => {
        useOnboardingStore.getState().hydrateFromProgress({
          fullName: 'Priya Sharma',
          gender: 'woman',
          city: 'Mumbai',
          stylePreferences: null,
        });
      });

      expect(useOnboardingStore.getState()).toMatchObject({
        fullName: 'Priya Sharma',
        gender: 'woman',
        city: 'Mumbai',
        styles: [],
        wardrobeType: undefined,
        occasionsPriority: [],
        budgetRange: undefined,
        favouriteColours: [],
      });
    });

    it('with stylePreferences absent entirely, only sets fullName/gender/city and leaves array/undefined fields at initial defaults, no crash', async () => {
      await act(async () => {
        useOnboardingStore.getState().hydrateFromProgress({
          fullName: 'Priya Sharma',
          gender: 'woman',
          city: 'Mumbai',
        });
      });

      expect(useOnboardingStore.getState()).toMatchObject({
        fullName: 'Priya Sharma',
        gender: 'woman',
        city: 'Mumbai',
        styles: [],
        wardrobeType: undefined,
        occasionsPriority: [],
        budgetRange: undefined,
        favouriteColours: [],
      });
    });
  });

  it('reset() clears all wizard-answer fields back to initial', async () => {
    const store = useOnboardingStore.getState();

    await act(async () => {
      store.setFullName('Priya Sharma');
      store.setGender('woman');
      store.setCity('Mumbai');
      store.toggleStyle('ethnic');
      store.setWardrobeType('mostly_ethnic');
      store.toggleOccasion('office');
      store.setBudgetRange('1000_3000');
      store.toggleColour('#000000');
      store.setCurrentStepIndex(3);
      store.reset();
    });

    expect(useOnboardingStore.getState()).toMatchObject({
      currentStepIndex: 0,
      fullName: '',
      gender: undefined,
      city: '',
      styles: [],
      wardrobeType: undefined,
      occasionsPriority: [],
      budgetRange: undefined,
      favouriteColours: [],
    });
  });
});
