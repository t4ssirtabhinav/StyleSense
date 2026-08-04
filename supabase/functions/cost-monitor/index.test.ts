// Deno test for the refactored cost-monitor/index.ts handleRequest seam
// (SS-033 / BL-107).
//
// NOT executed this session -- no `deno` binary is available in this
// sandbox (same gap SS-010's get-upload-url/index.test.ts already flagged;
// BL-042 tracks that CI does not run Deno tests either). Written to the
// letter of design §7.3's test list.

import { assertEquals, assertStringIncludes } from "jsr:@std/assert";
import { type HandleRequestDeps, handleRequest } from "./index.ts";

interface FakeResult {
  count: number | null;
  error: { message: string } | null;
}

interface RecordedCall {
  eq?: [string, unknown];
}

function buildFakeSupabaseClient(
  opts: { total: FakeResult; billable: FakeResult; calls: RecordedCall[] },
) {
  return {
    from(_table: string) {
      const record: RecordedCall = {};
      opts.calls.push(record);
      let filtered = false;
      // deno-lint-ignore no-explicit-any
      const builder: any = {
        select: () => builder,
        gte: () => builder,
        eq: (column: string, value: unknown) => {
          filtered = true;
          record.eq = [column, value];
          return builder;
        },
        then: (
          resolve: (v: FakeResult) => void,
        ) => resolve(filtered ? opts.billable : opts.total),
      };
      return builder;
    },
    // deno-lint-ignore no-explicit-any
  } as any;
}

function fakeDeps(
  overrides: {
    total?: FakeResult;
    billable?: FakeResult;
    alertThreshold?: number;
    calls?: RecordedCall[];
    fetchCalls?: Array<{ url: string; body: unknown }>;
  } = {},
): HandleRequestDeps {
  const calls = overrides.calls ?? [];
  const fetchCalls = overrides.fetchCalls ?? [];
  const client = buildFakeSupabaseClient({
    total: overrides.total ?? { count: 0, error: null },
    billable: overrides.billable ?? { count: 0, error: null },
    calls,
  });

  return {
    createSupabaseClient: () => client,
    alertThreshold: overrides.alertThreshold ?? 200,
    fetchImpl: ((url: string, init?: RequestInit) => {
      fetchCalls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
      return Promise.resolve(new Response("ok", { status: 200 }));
    }) as typeof fetch,
  };
}

Deno.test(
  "the daily billable count excludes a cache-hit session (AC #5's literal requirement)",
  async () => {
    // Fixture intent: 3 sessions today, one of them cost_incurred=false /
    // zero_cost_reason='cache_hit' -- the billable count must be 2, not 3.
    const res = await handleRequest(
      new Request("https://edge.local/cost-monitor"),
      fakeDeps({ total: { count: 3, error: null }, billable: { count: 2, error: null } }),
    );
    const body = await res.json();
    assertEquals(body.totalSessionCount, 3);
    assertEquals(body.billableSessionCount, 2);
  },
);

Deno.test(
  "the daily billable count also excludes a degraded_e0 session",
  async () => {
    const res = await handleRequest(
      new Request("https://edge.local/cost-monitor"),
      fakeDeps({ total: { count: 3, error: null }, billable: { count: 2, error: null } }),
    );
    const body = await res.json();
    assertEquals(body.billableSessionCount, 2);
  },
);

Deno.test(
  "the billable filter is applied as .eq('cost_incurred', true)",
  async () => {
    const calls: RecordedCall[] = [];
    await handleRequest(
      new Request("https://edge.local/cost-monitor"),
      fakeDeps({
        total: { count: 3, error: null },
        billable: { count: 2, error: null },
        calls,
      }),
    );
    const eqCalls = calls.map((c) => c.eq).filter(Boolean);
    assertEquals(eqCalls, [["cost_incurred", true]]);
  },
);

Deno.test(
  "the alert threshold compares against the billable count, not the total",
  async () => {
    // 3 total / 2 billable with threshold 2 -> NOT over limit (2 is not > 2).
    const res = await handleRequest(
      new Request("https://edge.local/cost-monitor"),
      fakeDeps({
        total: { count: 3, error: null },
        billable: { count: 2, error: null },
        alertThreshold: 2,
      }),
    );
    const body = await res.json();
    assertEquals(body.overLimit, false);
  },
);

Deno.test(
  "the Slack copy names the billable count and reports the total separately",
  async () => {
    Deno.env.set("SLACK_WEBHOOK_URL", "https://hooks.example.com/webhook");
    const fetchCalls: Array<{ url: string; body: unknown }> = [];
    try {
      await handleRequest(
        new Request("https://edge.local/cost-monitor"),
        fakeDeps({
          total: { count: 5, error: null },
          billable: { count: 2, error: null },
          alertThreshold: 1,
          fetchCalls,
        }),
      );
    } finally {
      Deno.env.delete("SLACK_WEBHOOK_URL");
    }

    assertEquals(fetchCalls.length, 1);
    const text = (fetchCalls[0].body as { text: string }).text;
    assertStringIncludes(text, "Billable AI sessions today: *2*");
    assertStringIncludes(text, "of 5 total");
  },
);

Deno.test("a Supabase error still returns 500 (regression guard)", async () => {
  const res = await handleRequest(
    new Request("https://edge.local/cost-monitor"),
    fakeDeps({ total: { count: null, error: { message: "connection refused" } } }),
  );
  assertEquals(res.status, 500);
});

Deno.test(
  "_shared/suggestionSessions.ts is the only place the predicate is defined -- " +
    'the literal string "cost_incurred" appears in neither Edge Function\'s index.ts',
  async () => {
    const costMonitorSource = await Deno.readTextFile(
      new URL("./index.ts", import.meta.url),
    );
    const weeklyReportSource = await Deno.readTextFile(
      new URL("../weekly-report/index.ts", import.meta.url),
    );

    assertEquals(costMonitorSource.includes("cost_incurred"), false);
    assertEquals(weeklyReportSource.includes("cost_incurred"), false);
    assertStringIncludes(costMonitorSource, "_shared/suggestionSessions.ts");
    assertStringIncludes(weeklyReportSource, "_shared/suggestionSessions.ts");
  },
);
