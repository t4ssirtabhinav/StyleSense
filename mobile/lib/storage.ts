// SS-025 — last-known-good taxonomy cache (design doc §6.5).
//
// `useOnboardingTaxonomiesQuery` is in-memory (`gcTime: Infinity`) and is
// therefore empty on every cold start. Once the occasion vocabulary is
// fetched at runtime instead of bundled as a TS constant, a cold start with
// no network would leave every occasion picker empty — so the last
// successful payload is persisted here and read back when the fetch fails.
//
// Deliberately NOT a bundled fallback vocabulary (design §9 open question 3,
// signed off): first-ever launch + offline + no cache renders the
// component's error/retry state, not an empty chip row. A bundled seed
// constant would reintroduce exactly the hardcoded `OCCASION_TYPES` the
// ticket's AC deletes.
//
// This is the `lib/storage.ts` slot CLAUDE.md's folder structure already
// reserves. Every function here is total — a corrupt/absent/version-mismatched
// entry is a cache MISS, never a throw. A storage failure must never be able
// to break a screen that would otherwise have rendered from the network.

import AsyncStorage from '@react-native-async-storage/async-storage';
import type { OnboardingTaxonomies } from '../features/onboarding/onboarding.types';

export const TAXONOMY_CACHE_KEY = 'stylesense.taxonomies.v1';

/** Bump when `OnboardingTaxonomies`' shape changes incompatibly. A stored
 * entry with any other version is treated as a miss (never migrated in
 * place, never partially read). */
export const TAXONOMY_CACHE_VERSION = 1;

export interface CachedTaxonomies {
  version: number;
  /** ISO 8601, so a consumer can decide how stale is too stale. */
  fetchedAt: string;
  payload: OnboardingTaxonomies;
}

function isTaxonomyPayload(value: unknown): value is OnboardingTaxonomies {
  if (typeof value !== 'object' || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    Array.isArray(candidate.styleKeywords) &&
    Array.isArray(candidate.occasions) &&
    Array.isArray(candidate.occasionAliases) &&
    Array.isArray(candidate.colourPalette)
  );
}

export async function writeCachedTaxonomies(
  payload: OnboardingTaxonomies,
): Promise<void> {
  const entry: CachedTaxonomies = {
    version: TAXONOMY_CACHE_VERSION,
    fetchedAt: new Date().toISOString(),
    // `isStale` is a per-read marker, never persisted — a cached payload is
    // by definition served as stale on the next read.
    payload: { ...payload, isStale: false },
  };
  try {
    await AsyncStorage.setItem(TAXONOMY_CACHE_KEY, JSON.stringify(entry));
  } catch {
    // A failed cache write is not a failed fetch. Swallow deliberately.
  }
}

export async function readCachedTaxonomies(): Promise<CachedTaxonomies | null> {
  let raw: string | null;
  try {
    raw = await AsyncStorage.getItem(TAXONOMY_CACHE_KEY);
  } catch {
    return null;
  }
  if (!raw) {
    return null;
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    // Corrupt JSON is a cache miss, not an error.
    return null;
  }

  if (typeof parsed !== 'object' || parsed === null) {
    return null;
  }
  const entry = parsed as Record<string, unknown>;
  if (entry.version !== TAXONOMY_CACHE_VERSION) {
    return null;
  }
  if (!isTaxonomyPayload(entry.payload)) {
    return null;
  }

  return {
    version: TAXONOMY_CACHE_VERSION,
    fetchedAt: typeof entry.fetchedAt === 'string' ? entry.fetchedAt : '',
    payload: entry.payload,
  };
}

export async function clearCachedTaxonomies(): Promise<void> {
  try {
    await AsyncStorage.removeItem(TAXONOMY_CACHE_KEY);
  } catch {
    // Same posture as writeCachedTaxonomies.
  }
}

// SS-023 — generic per-user "fire once ever" flag, backing
// first_suggestion_viewed/first_outfit_saved (design §5's "Fire-once
// semantics are per user, persisted via lib/storage.ts, not per app
// session" — a component-state guard would re-fire on every cold start).
// Deliberately total, same posture as the taxonomy cache above: a storage
// failure degrades to "not yet fired" (an event may fire again in the rare
// failure case) rather than ever throwing and breaking the screen.
function onceEventKey(userId: string, eventKey: string): string {
  return `stylesense.once.${eventKey}.${userId}`;
}

export async function hasFiredOnceEvent(
  userId: string,
  eventKey: string,
): Promise<boolean> {
  try {
    const raw = await AsyncStorage.getItem(onceEventKey(userId, eventKey));
    return raw === '1';
  } catch {
    return false;
  }
}

export async function markOnceEventFired(
  userId: string,
  eventKey: string,
): Promise<void> {
  try {
    await AsyncStorage.setItem(onceEventKey(userId, eventKey), '1');
  } catch {
    // A failed write just means this event might fire again next time —
    // acceptable, never a thrown error (same posture as writeCachedTaxonomies).
  }
}
