import { create } from 'zustand';
import { registerUserStateReset } from '../auth/userStateReset';
import type {
  BudgetRangeKey,
  GenderKey,
  OccasionPriorityKey,
  StyleKeywordKey,
  StylePreferences,
  WardrobeTypeKey,
} from './onboarding.types';

// Zustand store holding all in-progress wizard answers (not yet persisted)
// plus currentStepIndex. Per docs/tickets/SS-004-design.md's "Files to
// create/modify" #6. Typed selectors only — see components for usage.
//
// Step 1's answers (fullName/gender/city) also live here transiently between
// entry and the "Next" press that calls saveStep1Profile, and are re-hydrated
// from fetchOnboardingProgress on resume/edit-preferences re-entry.

const MAX_OCCASIONS = 3;
const MAX_COLOURS = 5;

export interface OnboardingState {
  currentStepIndex: number;
  fullName: string;
  gender: GenderKey | undefined;
  city: string;
  styles: StyleKeywordKey[];
  wardrobeType: WardrobeTypeKey | undefined;
  occasionsPriority: OccasionPriorityKey[];
  budgetRange: BudgetRangeKey | undefined;
  favouriteColours: string[]; // hex codes, max 5

  setCurrentStepIndex: (index: number) => void;
  setFullName: (fullName: string) => void;
  setGender: (gender: GenderKey) => void;
  setCity: (city: string) => void;
  toggleStyle: (key: StyleKeywordKey) => void;
  setWardrobeType: (key: WardrobeTypeKey) => void;
  toggleOccasion: (key: OccasionPriorityKey) => void;
  setBudgetRange: (key: BudgetRangeKey) => void;
  toggleColour: (hex: string) => void;
  hydrateFromProgress: (progress: {
    fullName: string;
    gender: GenderKey | undefined;
    city: string;
    stylePreferences?: StylePreferences | null;
  }) => void;
  reset: () => void;
}

const INITIAL_STATE = {
  currentStepIndex: 0,
  fullName: '',
  gender: undefined as GenderKey | undefined,
  city: '',
  styles: [] as StyleKeywordKey[],
  wardrobeType: undefined as WardrobeTypeKey | undefined,
  occasionsPriority: [] as OccasionPriorityKey[],
  budgetRange: undefined as BudgetRangeKey | undefined,
  favouriteColours: [] as string[],
};

export const useOnboardingStore = create<OnboardingState>((set) => ({
  ...INITIAL_STATE,

  setCurrentStepIndex: (index) => set({ currentStepIndex: index }),
  setFullName: (fullName) => set({ fullName }),
  setGender: (gender) => set({ gender }),
  setCity: (city) => set({ city }),

  toggleStyle: (key) =>
    set((state) => ({
      styles: state.styles.includes(key)
        ? state.styles.filter((existing) => existing !== key)
        : [...state.styles, key],
    })),

  setWardrobeType: (key) => set({ wardrobeType: key }),

  // No-ops past MAX_OCCASIONS selections unless deselecting.
  toggleOccasion: (key) =>
    set((state) => {
      if (state.occasionsPriority.includes(key)) {
        return {
          occasionsPriority: state.occasionsPriority.filter(
            (existing) => existing !== key,
          ),
        };
      }
      if (state.occasionsPriority.length >= MAX_OCCASIONS) {
        return state;
      }
      return { occasionsPriority: [...state.occasionsPriority, key] };
    }),

  setBudgetRange: (key) => set({ budgetRange: key }),

  // No-ops past MAX_COLOURS selections unless deselecting.
  toggleColour: (hex) =>
    set((state) => {
      if (state.favouriteColours.includes(hex)) {
        return {
          favouriteColours: state.favouriteColours.filter(
            (existing) => existing !== hex,
          ),
        };
      }
      if (state.favouriteColours.length >= MAX_COLOURS) {
        return state;
      }
      return { favouriteColours: [...state.favouriteColours, hex] };
    }),

  // Fix pass 5, 2026-07-22 (SS-004): previously only applied
  // fullName/gender/city, silently dropping Step 2-4's answers even when
  // fetchOnboardingProgress had already fetched a complete stylePreferences
  // blob from the DB — verified live against a fully-completed test user
  // whose row had onboarding_completed: true and a correct, complete
  // style_preferences JSONB, yet Steps 2-4 rendered blank on resume. Now
  // hydrates all 6 StylePreferences fields onto the store's corresponding
  // state when present; a null/absent stylePreferences (e.g. a user who
  // saved Step 1 but never reached "Get Started") still only hydrates
  // fullName/gender/city, leaving the array/undefined fields at their
  // INITIAL_STATE defaults rather than crashing on missing keys.
  hydrateFromProgress: ({ fullName, gender, city, stylePreferences }) =>
    set({
      fullName,
      gender,
      city,
      ...(stylePreferences
        ? {
            styles: stylePreferences.styles,
            wardrobeType: stylePreferences.wardrobe_type,
            occasionsPriority: stylePreferences.occasions_priority,
            budgetRange: stylePreferences.budget_range,
            favouriteColours: stylePreferences.favourite_colours,
          }
        : {}),
    }),

  reset: () => set({ ...INITIAL_STATE }),
}));

// SS-071 AC #6 — self-registers with the sign-out reset registry so a
// wizard in progress for one user cannot survive into the next user's
// session on the same device. See features/auth/userStateReset.ts.
registerUserStateReset(() => useOnboardingStore.getState().reset());
