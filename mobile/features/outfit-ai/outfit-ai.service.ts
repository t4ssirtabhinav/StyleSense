// SS-023 — raw fetch calls to backend/routers/outfit_suggestions.py's
// /portfolio and /outcome routes. Mirrors wardrobe.service.ts's
// postWardrobeAction/fetchWardrobeItemImageUrl shape exactly: base URL from
// constants/api.ts (never a literal host), `Authorization: Bearer ${jwt}`,
// every non-2xx response mapped to a typed, user-facing error rather than
// an unhandled rejection (CLAUDE.md: "All async ops: always wrap in
// try/catch with user-facing error handling").
//
// This is the only place fetch() is called from for this domain —
// outfit-ai.queries.ts wraps these in React Query hooks and never calls
// fetch directly itself (mirrors wardrobe.service.ts/wardrobe.queries.ts's
// established split).

import { EXPO_PUBLIC_BACKEND_URL } from '../../constants/api';
import { BACKEND_UNREACHABLE_COPY } from './outfit-ai.constants';
import type {
  GeneratePortfolioRequest,
  GeneratePortfolioResponse,
  RecordOutcomeRequest,
  RecordOutcomeResponse,
} from './outfit-ai.types';

export class OutfitAiError extends Error {
  constructor(message: string = BACKEND_UNREACHABLE_COPY) {
    super(message);
    this.name = 'OutfitAiError';
  }
}

async function postJson<TResponse>(
  path: string,
  body: unknown,
  jwt: string,
): Promise<TResponse> {
  let response: Response;
  try {
    response = await fetch(`${EXPO_PUBLIC_BACKEND_URL}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${jwt}`,
      },
      body: JSON.stringify(body),
    });
  } catch {
    // Network failure (offline, DNS, timeout) — never an unhandled
    // rejection reaching the caller.
    throw new OutfitAiError();
  }

  if (!response.ok) {
    throw new OutfitAiError();
  }

  return response.json() as Promise<TResponse>;
}

export async function generateSuggestionsPortfolio(
  request: GeneratePortfolioRequest,
  jwt: string,
): Promise<GeneratePortfolioResponse> {
  return postJson<GeneratePortfolioResponse>(
    '/outfit-suggestions/portfolio',
    request,
    jwt,
  );
}

export async function recordOutfitOutcome(
  request: RecordOutcomeRequest,
  jwt: string,
): Promise<RecordOutcomeResponse> {
  return postJson<RecordOutcomeResponse>(
    '/outfit-suggestions/outcome',
    request,
    jwt,
  );
}
