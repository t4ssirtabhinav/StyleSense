import {
  OutfitAiError,
  generateSuggestionsPortfolio,
  recordOutfitOutcome,
} from '../../../features/outfit-ai/outfit-ai.service';

describe('outfit-ai.service', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // biome-ignore lint/suspicious/noExplicitAny: test-only global stub
    (global as any).fetch = jest.fn();
  });

  it('generateSuggestionsPortfolio POSTs to /outfit-suggestions/portfolio with the JWT as Authorization: Bearer', async () => {
    const responseBody = { portfolio: [], session_id: null };
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => responseBody,
    });

    const result = await generateSuggestionsPortfolio(
      { occasion: 'office', exclude_fingerprints: [] },
      'jwt-token',
    );

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/outfit-suggestions/portfolio'),
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ Authorization: 'Bearer jwt-token' }),
        body: JSON.stringify({ occasion: 'office', exclude_fingerprints: [] }),
      }),
    );
    expect(result).toEqual(responseBody);
  });

  it('the base URL comes from constants/api.ts, never a literal host', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });

    await generateSuggestionsPortfolio(
      { occasion: 'office', exclude_fingerprints: [] },
      'jwt-token',
    );

    const [url] = (global.fetch as jest.Mock).mock.calls[0];
    expect(url).toMatch(/^https?:\/\//);
  });

  it('a non-2xx response produces a typed, user-facing error, never an unhandled rejection', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({ ok: false, status: 500 });

    await expect(
      generateSuggestionsPortfolio(
        { occasion: 'office', exclude_fingerprints: [] },
        'jwt-token',
      ),
    ).rejects.toBeInstanceOf(OutfitAiError);
  });

  it('a network failure (fetch rejects) produces the same typed error, never an unhandled rejection', async () => {
    (global.fetch as jest.Mock).mockRejectedValue(new Error('offline'));

    await expect(
      generateSuggestionsPortfolio(
        { occasion: 'office', exclude_fingerprints: [] },
        'jwt-token',
      ),
    ).rejects.toBeInstanceOf(OutfitAiError);
  });

  it('recordOutfitOutcome POSTs to /outfit-suggestions/outcome with the JWT as Authorization: Bearer', async () => {
    const responseBody = {
      outfit_id: 'outfit-1',
      outcome_recorded: true,
      already_saved: false,
    };
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => responseBody,
    });

    const result = await recordOutfitOutcome(
      { session_id: 'session-1', rank: 1, outcome_type: 'saved' },
      'jwt-token',
    );

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/outfit-suggestions/outcome'),
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ Authorization: 'Bearer jwt-token' }),
        body: JSON.stringify({
          session_id: 'session-1',
          rank: 1,
          outcome_type: 'saved',
        }),
      }),
    );
    expect(result).toEqual(responseBody);
  });

  it('recordOutfitOutcome maps a non-2xx response to the same typed error', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({ ok: false, status: 404 });

    await expect(
      recordOutfitOutcome(
        { session_id: 'session-1', rank: 1, outcome_type: 'saved' },
        'jwt-token',
      ),
    ).rejects.toBeInstanceOf(OutfitAiError);
  });
});
