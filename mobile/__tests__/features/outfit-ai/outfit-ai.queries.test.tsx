import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { useAuthStore } from '../../../features/auth/auth.store';
import {
  useGenerateSuggestionsMutation,
  useRecordOutcomeMutation,
} from '../../../features/outfit-ai/outfit-ai.queries';
import * as outfitAiService from '../../../features/outfit-ai/outfit-ai.service';

const FAKE_USER_ID = 'user-1';
function setFakeSession() {
  useAuthStore.setState({
    // biome-ignore lint/suspicious/noExplicitAny: minimal fake Session for tests
    session: { user: { id: FAKE_USER_ID } } as any,
    isSessionLoading: false,
  });
}

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

// style-score.queries.ts transitively imports lib/supabase (via
// features/auth/auth.service.ts), which isn't transformable/configured
// under this test's minimal setup -- mocked out since this file's tests
// only need the pure styleScoreQueryKey.
jest.mock('../../../features/style-score/style-score.queries', () => ({
  styleScoreQueryKey: (userId: string | undefined) =>
    ['style-score', 'summary', userId] as const,
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

function createWrapperWithClient() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { Wrapper, queryClient };
}

describe('outfit-ai.queries', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    setFakeSession();
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

  it('useRecordOutcomeMutation success invalidates the style score query key (AC: score updates after an outfit is saved)', async () => {
    (outfitAiService.recordOutfitOutcome as jest.Mock).mockResolvedValue({
      outfit_id: 'outfit-1',
      outcome_recorded: true,
      already_saved: false,
    });
    const { Wrapper, queryClient } = createWrapperWithClient();
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');

    const { result } = await renderHook(() => useRecordOutcomeMutation(), {
      wrapper: Wrapper,
    });
    result.current.mutate({
      request: { session_id: 'session-1', rank: 1, outcome_type: 'saved' },
      jwt: 'jwt-token',
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['style-score', 'summary', FAKE_USER_ID],
    });
  });
});
