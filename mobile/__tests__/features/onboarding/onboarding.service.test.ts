import {
  completeOnboarding,
  fetchOnboardingProgress,
  saveStep1Profile,
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

  it('maps a saved row correctly', async () => {
    mockMaybeSingle.mockResolvedValue({
      data: {
        full_name: 'Priya Sharma',
        gender: 'woman',
        city: 'Mumbai',
        style_preferences: null,
      },
      error: null,
    });

    await expect(fetchOnboardingProgress('user-1')).resolves.toEqual({
      fullName: 'Priya Sharma',
      gender: 'woman',
      city: 'Mumbai',
      stylePreferences: null,
    });
  });

  it('resolves a missing/null row to null without throwing', async () => {
    mockMaybeSingle.mockResolvedValue({ data: null, error: null });

    await expect(fetchOnboardingProgress('user-2')).resolves.toBeNull();
  });
});
