import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import {
  useGenerateSuggestionsMutation,
  useRecordOutcomeMutation,
} from '../../../features/outfit-ai/outfit-ai.queries';
import * as outfitAiService from '../../../features/outfit-ai/outfit-ai.service';

jest.mock('../../../features/outfit-ai/outfit-ai.service', () => ({
  generateSuggestionsPortfolio: jest.fn(),
  recordOutfitOutcome: jest.fn(),
}));
// outfit-ai.queries.ts re-exports useWardrobeItemCountQuery from
// wardrobe.queries.ts (reuse, not a second implementation) -- that module
// pulls in @sentry/react-native at import time, which isn't transformable
// under this test's minimal setup. Mocked out since this file's tests don't
// exercise that re-export.
jest.mock('../../../features/wardrobe/wardrobe.queries', () => ({
  useWardrobeItemCountQuery: jest.fn(),
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

describe('outfit-ai.queries', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('useGenerateSuggestionsMutation calls the service with the request and jwt', async () => {
    (
      outfitAiService.generateSuggestionsPortfolio as jest.Mock
    ).mockResolvedValue({
      portfolio: [],
      session_id: 'session-1',
    });

    const { result } = await renderHook(
      () => useGenerateSuggestionsMutation(),
      {
        wrapper: createWrapper(),
      },
    );

    result.current.mutate({
      request: { occasion: 'office', exclude_fingerprints: [] },
      jwt: 'jwt-token',
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(outfitAiService.generateSuggestionsPortfolio).toHaveBeenCalledWith(
      { occasion: 'office', exclude_fingerprints: [] },
      'jwt-token',
    );
  });

  it('useRecordOutcomeMutation calls the service with the request and jwt', async () => {
    (outfitAiService.recordOutfitOutcome as jest.Mock).mockResolvedValue({
      outfit_id: 'outfit-1',
      outcome_recorded: true,
      already_saved: false,
    });

    const { result } = await renderHook(() => useRecordOutcomeMutation(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({
      request: { session_id: 'session-1', rank: 1, outcome_type: 'saved' },
      jwt: 'jwt-token',
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(outfitAiService.recordOutfitOutcome).toHaveBeenCalledWith(
      { session_id: 'session-1', rank: 1, outcome_type: 'saved' },
      'jwt-token',
    );
  });

  it('a non-2xx/failed service call surfaces as a rejected mutation, never an unhandled rejection', async () => {
    (outfitAiService.recordOutfitOutcome as jest.Mock).mockRejectedValue(
      new Error('network failure'),
    );

    const { result } = await renderHook(() => useRecordOutcomeMutation(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({
      request: { session_id: 'session-1', rank: 1, outcome_type: 'saved' },
      jwt: 'jwt-token',
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(Error);
  });
});
