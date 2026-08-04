import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {
  createClient,
  type SupabaseClient,
} from "https://esm.sh/@supabase/supabase-js@2";
import { applyBillableFilter } from "../_shared/suggestionSessions.ts";

// SS-033 / BL-107 fix: before 013_suggestion_impressions.sql, nothing wrote
// suggestion_sessions at all, so counting every row as "one paid AI call"
// was harmless. Once cache hits and E0/degraded (₹0) requests start being
// logged, that assumption silently over-counts spend -- this now reports a
// BILLABLE count (cost_incurred = true, via the shared
// _shared/suggestionSessions.ts predicate) alongside the total, and alerts
// on the billable figure. See design §3.1/§7.2.
export const SESSION_ALERT_THRESHOLD = 200;

// Dependency-injection seam purely for index.test.ts (Deno's module system
// has no jest.mock()-style interception, so the real supabase-js client and
// global fetch are swapped for test doubles via this params object instead)
// -- the get-upload-url/index.ts precedent (SS-010).
export interface HandleRequestDeps {
  createSupabaseClient: () => SupabaseClient;
  fetchImpl: typeof fetch;
  alertThreshold: number;
}

const defaultDeps: HandleRequestDeps = {
  createSupabaseClient: () =>
    createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    ),
  fetchImpl: fetch,
  alertThreshold: SESSION_ALERT_THRESHOLD,
};

export async function handleRequest(
  _req: Request,
  deps: HandleRequestDeps = defaultDeps,
): Promise<Response> {
  const supabase = deps.createSupabaseClient();

  // Start of today in IST
  const nowIST = new Date(
    new Date().toLocaleString("en-US", { timeZone: "Asia/Kolkata" }),
  );
  nowIST.setHours(0, 0, 0, 0);

  const { count: totalSessionCount, error: totalError } = await supabase
    .from("suggestion_sessions")
    .select("*", { count: "exact", head: true })
    .gte("created_at", nowIST.toISOString());

  if (totalError) {
    return new Response(JSON.stringify({ error: totalError.message }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }

  const { count: billableSessionCount, error: billableError } =
    await applyBillableFilter(
      supabase
        .from("suggestion_sessions")
        .select("*", { count: "exact", head: true })
        .gte("created_at", nowIST.toISOString()),
    );

  if (billableError) {
    return new Response(JSON.stringify({ error: billableError.message }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }

  const total = totalSessionCount ?? 0;
  const billable = billableSessionCount ?? 0;
  const overLimit = billable > deps.alertThreshold;

  const dateStr = new Date().toLocaleDateString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    year: "numeric",
  });

  const statusEmoji = overLimit ? "🔴" : "✅";
  // Names the BILLABLE count explicitly and reports the total separately --
  // this copy must never be misreadable as "all sessions" (design §7.2's
  // test_slack_copy_names_the_billable_count_and_reports_the_total_separately).
  const slackText = overLimit
    ? `${statusEmoji} *StyleSense Cost Monitor — ${dateStr}*\nBillable AI sessions today: *${billable}* (of ${total} total; threshold: ${deps.alertThreshold})\n⚠️ Above threshold — review API spend.`
    : `${statusEmoji} *StyleSense Cost Monitor — ${dateStr}*\nBillable AI sessions today: *${billable}* (of ${total} total) — all good.`;

  const webhookUrl = Deno.env.get("SLACK_WEBHOOK_URL");
  if (webhookUrl) {
    await deps.fetchImpl(webhookUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: slackText }),
    });
  }

  return new Response(
    JSON.stringify({
      date: dateStr,
      billableSessionCount: billable,
      totalSessionCount: total,
      overLimit,
    }),
    { headers: { "Content-Type": "application/json" } },
  );
}

Deno.serve((req: Request) => handleRequest(req));
