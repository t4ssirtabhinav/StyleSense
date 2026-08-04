// SS-033 -- The ONE place the "costed session" predicate and the
// zero-cost-reason vocabulary are defined. Both cost-monitor/index.ts and
// weekly-report/index.ts import from here rather than re-deriving the
// filter, per design §7.3's
// `test_shared_helper_is_the_only_place_the_predicate_is_defined` -- the
// literal string "cost_incurred" must appear in neither Edge Function's
// index.ts.
//
// Fixes BL-107: before 013_suggestion_impressions.sql, `suggestion_sessions`
// had no code path writing it at all, so counting every row as "one paid AI
// call" was harmless. The moment cache hits and E0/degraded (₹0) requests
// start being logged (design §6.1/§6.2/§6.3), that assumption silently
// over-counts spend. `cost_incurred` is the DB's own marker for "did this
// session's request actually incur provider cost" (see
// 013_suggestion_impressions.sql §3.1) -- this module is the single place
// that predicate is expressed as a query filter.

// Transcribed verbatim from
// 013_suggestion_impressions.sql's suggestion_sessions_zero_cost_reason_check
// -- kept in sync manually (no single source of truth spans SQL and two
// runtimes in this codebase).
export const ZERO_COST_REASONS = [
  "cache_hit",
  "degraded_e0",
  "rules_only",
  "budget_denied",
  "no_provider_call",
] as const;

export type ZeroCostReason = (typeof ZERO_COST_REASONS)[number];

const COST_INCURRED_COLUMN = "cost_incurred";

/**
 * Narrows a `suggestion_sessions` PostgREST query to rows that actually
 * incurred provider cost. A function (not an inlined `.eq()` call at each
 * call site) so the filter is unit-testable in isolation and cannot
 * silently drift between the two Edge Functions that need it.
 */
export function applyBillableFilter<
  T extends { eq: (column: string, value: unknown) => T },
>(query: T): T {
  return query.eq(COST_INCURRED_COLUMN, true);
}
