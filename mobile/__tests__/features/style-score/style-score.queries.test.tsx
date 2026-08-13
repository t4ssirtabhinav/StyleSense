import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import * as authService from '../../../features/auth/auth.service';
import {
  styleScoreQueryKey,
  useStyleScoreQuery,
} from '../../../features/style-score/style-score.queries';
import * as styleScoreService from '../../../features/style-score/style-score.service';

const mockUseOccasionOptions = jest.fn();
jest.mock('../../../features/onboarding/onboarding.queries', () => ({
  useOccasionTaxonomy: (...args: unknown[]) => mockUseOccasionOptions(...args),
}));

jest.mock('../../../features/style-score/style-score.service', () => ({
  fetchStyleScoreInputs: jest.fn(),
}));

jest.mock('../../../features/auth/auth.service', () => ({
  fetchUserPlanTier: jest.fn(),
}));

const RESOLVED_OCCASIONS = [{ key: 'office' }, { key: 'casual' }];

const SAMPLE_INPUTS = {
  itemCount: 5,
  distinctCategories: 3,
  coveredOccasionKeys: ['office'],
  activeOccasionKeys: ['office', 'casual'],
  costPerWearValues: [100],
  outfitsThisMonth: 1,
  wearsThisMonth: 2,
};

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

describe('useStyleScoreQuery', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseOccasionOptions.mockReturnValue({
      occasions: RESOLVED_OCCASIONS,
      isLoading: false,
    });
    (styleScoreService.fetchStyleScoreInputs as jest.Mock).mockResolvedValue(
      SAMPLE_INPUTS,
    );
  });

  it('is disabled and issues no request when userId is undefined', async () => {
    (authService.fetchUserPlanTier as jest.Mock).mockResolvedValue('free');
    const { result } = await renderHook(() => useStyleScoreQuery(undefined), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isPending).toBe(true));
    expect(styleScoreService.fetchStyleScoreInputs).not.toHaveBeenCalled();
  });

  it('returns isPremium: true for plan_tier "premium" and "premium_annual"', async () => {
    (authService.fetchUserPlanTier as jest.Mock).mockResolvedValue('premium');
    const { result } = await renderHook(() => useStyleScoreQuery('user-1'), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.isPremium).toBe(true);

    (authService.fetchUserPlanTier as jest.Mock).mockResolvedValue(
      'premium_annual',
    );
    const { result: result2 } = await renderHook(
      () => useStyleScoreQuery('user-2'),
      {
        wrapper: createWrapper(),
      },
    );
    await waitFor(() => expect(result2.current.isSuccess).toBe(true));
    expect(result2.current.data?.isPremium).toBe(true);
  });

  it('returns isPremium: false when fetchUserPlanTier resolves null (fail-closed)', async () => {
    (authService.fetchUserPlanTier as jest.Mock).mockResolvedValue(null);
    const { result } = await renderHook(() => useStyleScoreQuery('user-1'), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.isPremium).toBe(false);
  });

  it('includes userId in the query key so two users cannot share a cache entry', () => {
    expect(styleScoreQueryKey('user-1')).toEqual([
      'style-score',
      'summary',
      'user-1',
    ]);
    expect(styleScoreQueryKey('user-1')).not.toEqual(
      styleScoreQueryKey('user-2'),
    );
  });
});
