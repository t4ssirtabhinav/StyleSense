// Deno test for _shared/suggestionSessions.ts (SS-033).
//
// NOT executed this session -- no `deno` binary is available in this
// sandbox (same gap SS-010's get-upload-url/index.test.ts already flagged;
// BL-042 tracks that CI does not run Deno tests either). Written to the
// letter of design §7.3's test list.

import { assertEquals } from "jsr:@std/assert";
import { applyBillableFilter, ZERO_COST_REASONS } from "./suggestionSessions.ts";

interface FixtureRow {
  id: string;
  cost_incurred: boolean;
  zero_cost_reason: string | null;
}

function makeArrayQuery(rows: FixtureRow[]) {
  return {
    // deno-lint-ignore no-explicit-any
    eq(column: string, value: unknown) {
      // deno-lint-ignore no-explicit-any
      const filtered = rows.filter((row) => (row as any)[column] === value);
      return makeArrayQuery(filtered);
    },
    rows,
  };
}

// AC #5's literal requirement: a fixture containing a cache-hit session
// must be excluded from the billable count.
Deno.test(
  "applyBillableFilter excludes a cache-hit session from a fixture of three",
  () => {
    const fixture: FixtureRow[] = [
      { id: "1", cost_incurred: true, zero_cost_reason: null },
      { id: "2", cost_incurred: true, zero_cost_reason: null },
      { id: "3", cost_incurred: false, zero_cost_reason: "cache_hit" },
    ];

    const filtered = applyBillableFilter(makeArrayQuery(fixture));

    assertEquals(filtered.rows.length, 2);
    assertEquals(
      filtered.rows.some((row) => row.zero_cost_reason === "cache_hit"),
      false,
    );
  },
);

Deno.test(
  "applyBillableFilter also excludes a degraded_e0 (rules-only, no provider call) session",
  () => {
    const fixture: FixtureRow[] = [
      { id: "1", cost_incurred: true, zero_cost_reason: null },
      { id: "2", cost_incurred: false, zero_cost_reason: "degraded_e0" },
    ];

    const filtered = applyBillableFilter(makeArrayQuery(fixture));

    assertEquals(filtered.rows.length, 1);
    assertEquals(filtered.rows[0].id, "1");
  },
);

Deno.test("applyBillableFilter calls eq with the exact column/value pair", () => {
  let captured: [string, unknown] | undefined;
  const query = {
    eq(column: string, value: unknown) {
      captured = [column, value];
      return query;
    },
  };

  applyBillableFilter(query);

  assertEquals(captured, ["cost_incurred", true]);
});

Deno.test(
  "ZERO_COST_REASONS matches the DB CHECK constraint's enumerated set, verbatim",
  () => {
    // Transcribed from 013_suggestion_impressions.sql's
    // suggestion_sessions_zero_cost_reason_check -- a drift guard between
    // the SQL enum and this runtime's vocabulary.
    assertEquals(ZERO_COST_REASONS, [
      "cache_hit",
      "degraded_e0",
      "rules_only",
      "budget_denied",
      "no_provider_call",
    ]);
  },
);
