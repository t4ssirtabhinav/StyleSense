import {
  completeOnboarding,
  fetchOnboardingProgress,
  saveStep1Profile,
  updateOccasionPriorities,
} from '../../../features/onboarding/onboarding.service';
import type { StylePreferences } from '../../../features/onboarding/onboarding.types';

const mockMaybeSingle = jest.fn();
const mockEq = jest.fn();
const mockSelect = jest.fn();
const mockUpdate = jest.fn();
const mockFrom = jest.fn();

mockEq.mockReturnValue({ maybeSingle: mockMaybeSingle });
mockSelect.mockReturnValue({ eq: mockEq });
mockUpdate.mockReturnValue({ eq: mockEq });
mockFrom.mockReturnValue({ select: mockSelect, update: mockUpdate });

jest.mock('../../../lib/supabase', () => ({
  supabase: {
    from: (arg: unknown) => mockFrom(arg),
  },
}));

describe('saveStep1Profile', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockEq.mockReturnValue({ maybeSingle: mockMaybeSingle });
    mockSelect.mockReturnValue({ eq: mockEq });
    mockUpdate.mockReturnValue({ eq: mockEq });
    mockFrom.mockReturnValue({ select: mockSelect, update: mockUpdate });
  });

  it('updates exactly full_name/gender/city (no style_preferences touched) and eq(id, userId)', async () => {
    mockEq.mockResolvedValue({ error: null });

    await saveStep1Profile('user-1', {
      fullName: 'Priya Sharma',
      gender: 'woman',
      city: 'Mumbai',
    });

    expect(mockFrom).toHaveBeenCalledWith('users');
    expect(mockUpdate).toHaveBeenCalledWith({
      full_name: 'Priya Sharma',
      gender: 'woman',
      city: 'Mumbai',
    });
    expect(mockEq).toHaveBeenCalledWith('id', 'user-1');
  });

  it('throws when the update errors', async () => {
    mockEq.mockResolvedValue({ error: new Error('network error') });

    await expect(
      saveStep1Profile('user-1', {
        fullName: 'Priya Sharma',
        gender: 'woman',
        city: 'Mumbai',
      }),
    ).rejects.toThrow('network error');
  });
});

describe('completeOnboarding', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockEq.mockReturnValue({ maybeSingle: mockMaybeSingle });
    mockSelect.mockReturnValue({ eq: mockEq });
    mockUpdate.mockReturnValue({ eq: mockEq });
    mockFrom.mockReturnValue({ select: mockSelect, update: mockUpdate });
  });

  it('includes the full style_preferences object (all 6 keys incl. duplicated gender) and onboarding_completed: true', async () => {
    mockEq.mockResolvedValue({ error: null });

    const stylePreferences: StylePreferences = {
      styles: ['ethnic', 'western'],
      wardrobe_type: 'mostly_ethnic',
      occasions_priority: ['office', 'wedding'],
      budget_range: '1000_3000',
      favourite_colours: ['#000000', '#FFFFFF'],
      gender: 'woman',
    };

    await completeOnboarding('user-1', stylePreferences);

    expect(mockUpdate).toHaveBeenCalledWith({
      style_preferences: stylePreferences,
      onboarding_completed: true,
    });
    expect(mockEq).toHaveBeenCalledWith('id', 'user-1');
  });
});

describe('fetchOnboardingProgress', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockEq.mockReturnValue({ maybeSingle: mockMaybeSingle });
    mockSelect.mockReturnValue({ eq: mockEq });
    mockUpdate.mockReturnValue({ eq: mockEq });
    mockFrom.mockReturnValue({ select: mockSelect, update: mockUpdate });
  });

  it('maps a saved row correctly, including onboarding_completed', async () => {
    mockMaybeSingle.mockResolvedValue({
      data: {
        full_name: 'Priya Sharma',
        gender: 'woman',
        city: 'Mumbai',
        style_preferences: null,
        onboarding_completed: true,
      },
      error: null,
    });

    await expect(fetchOnboardingProgress('user-1')).resolves.toEqual({
      fullName: 'Priya Sharma',
      gender: 'woman',
      city: 'Mumbai',
      stylePreferences: null,
      onboardingCompleted: true,
    });
  });

  // (SS-007) regression guard: onboardingCompleted must correctly reflect a
  // `false` DB value too, not just default to true/false regardless of the
  // column's real value.
  it('maps onboarding_completed: false correctly', async () => {
    mockMaybeSingle.mockResolvedValue({
      data: {
        full_name: 'Priya Sharma',
        gender: 'woman',
        city: 'Mumbai',
        style_preferences: null,
        onboarding_completed: false,
      },
      error: null,
    });

    await expect(fetchOnboardingProgress('user-1')).resolves.toMatchObject({
      onboardingCompleted: false,
    });
  });

  it('resolves a missing/null row to null without throwing', async () => {
    mockMaybeSingle.mockResolvedValue({ data: null, error: null });

    await expect(fetchOnboardingProgress('user-2')).resolves.toBeNull();
  });
});

// (SS-007) Granular Preferences Editor — patchStylePreferences is private,
// exercised indirectly via updateOccasionPriorities (the design doc's own
// named example). Its read-merge-write behaviour is identical across all 5
// exported wrappers (patchStylePreferences is the only thing they call), so
// this single wrapper's coverage stands in for all 5 per the design doc's
// Test plan.
describe('updateOccasionPriorities (via patchStylePreferences)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockEq.mockReturnValue({ maybeSingle: mockMaybeSingle });
    mockSelect.mockReturnValue({ eq: mockEq });
    mockUpdate.mockReturnValue({ eq: mockEq });
    mockFrom.mockReturnValue({ select: mockSelect, update: mockUpdate });
  });

  it('merges the patch into an existing non-null style_preferences, preserving every other key untouched', async () => {
    mockMaybeSingle.mockResolvedValue({
      data: {
        style_preferences: {
          styles: ['ethnic'],
          wardrobe_type: 'mostly_ethnic',
          occasions_priority: ['office'],
          budget_range: '1000_3000',
          favourite_colours: ['#000000'],
          gender: 'woman',
        },
      },
      error: null,
    });
    mockEq
      .mockReturnValueOnce({ maybeSingle: mockMaybeSingle })
      .mockResolvedValueOnce({ error: null });

    await updateOccasionPriorities('user-1', ['wedding', 'festival']);

    expect(mockFrom).toHaveBeenCalledWith('users');
    expect(mockSelect).toHaveBeenCalledWith('style_preferences');
    expect(mockUpdate).toHaveBeenCalledWith({
      style_preferences: {
        styles: ['ethnic'],
        wardrobe_type: 'mostly_ethnic',
        occasions_priority: ['wedding', 'festival'],
        budget_range: '1000_3000',
        favourite_colours: ['#000000'],
        gender: 'woman',
      },
    });
  });

  it('when current style_preferences is null, writes an object containing only the patched key(s), without throwing on the missing-required-fields shape', async () => {
    mockMaybeSingle.mockResolvedValue({
      data: { style_preferences: null },
      error: null,
    });
    mockEq
      .mockReturnValueOnce({ maybeSingle: mockMaybeSingle })
      .mockResolvedValueOnce({ error: null });

    await expect(
      updateOccasionPriorities('user-2', ['wedding']),
    ).resolves.toBeUndefined();

    expect(mockUpdate).toHaveBeenCalledWith({
      style_preferences: { occasions_priority: ['wedding'] },
    });
  });

  it('propagates a read error before any write is attempted', async () => {
    mockMaybeSingle.mockResolvedValue({
      data: null,
      error: new Error('read error'),
    });

    await expect(
      updateOccasionPriorities('user-1', ['wedding']),
    ).rejects.toThrow('read error');
    expect(mockUpdate).not.toHaveBeenCalled();
  });

  it('propagates a write error', async () => {
    mockMaybeSingle.mockResolvedValue({
      data: { style_preferences: null },
      error: null,
    });
    mockEq
      .mockReturnValueOnce({ maybeSingle: mockMaybeSingle })
      .mockResolvedValueOnce({ error: new Error('write error') });

    await expect(
      updateOccasionPriorities('user-1', ['wedding']),
    ).rejects.toThrow('write error');
  });
});
