import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import Anthropic from "https://esm.sh/@anthropic-ai/sdk";

Deno.serve(async (_req: Request) => {
  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );

  const sevenDaysAgo = new Date(
    Date.now() - 7 * 24 * 60 * 60 * 1000,
  ).toISOString();

  const [
    { count: newUsers },
    { count: aiSessions },
    { count: outfitsCreated },
    { count: socialPosts },
    { count: premiumUsers },
  ] = await Promise.all([
    supabase
      .from("users")
      .select("*", { count: "exact", head: true })
      .gte("created_at", sevenDaysAgo),
    supabase
      .from("suggestion_sessions")
      .select("*", { count: "exact", head: true })
      .gte("created_at", sevenDaysAgo),
    supabase
      .from("outfits")
      .select("*", { count: "exact", head: true })
      .gte("created_at", sevenDaysAgo),
    supabase
      .from("social_posts")
      .select("*", { count: "exact", head: true })
      .gte("created_at", sevenDaysAgo),
    supabase
      .from("users")
      .select("*", { count: "exact", head: true })
      .neq("plan_tier", "free"),
  ]);

  const anthropic = new Anthropic({ apiKey: Deno.env.get("ANTHROPIC_API_KEY")! });

  const aiMsg = await anthropic.messages.create({
    model: "claude-haiku-4-5-20251001",
    max_tokens: 400,
    messages: [
      {
        role: "user",
        content: `Write a brief weekly health report for StyleSense (India-first AI fashion app).
Data from the past 7 days:
- New signups: ${newUsers ?? 0}
- AI outfit sessions: ${aiSessions ?? 0}
- Outfits created: ${outfitsCreated ?? 0}
- OOTD social posts: ${socialPosts ?? 0}
- Total premium users: ${premiumUsers ?? 0}

Write 3-4 sentences in a positive, founder-friendly tone. Highlight what's working and one thing to focus on next week.`,
      },
    ],
  });

  const summary = (aiMsg.content[0] as { text: string }).text;

  const dateStr = new Date().toLocaleDateString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "long",
    year: "numeric",
  });

  const row = (label: string, value: number) =>
    `<tr><td style="padding:8px;border:1px solid #ddd">${label}</td>` +
    `<td style="padding:8px;border:1px solid #ddd;font-weight:bold">${value}</td></tr>`;

  await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${Deno.env.get("RESEND_API_KEY")}`,
    },
    body: JSON.stringify({
      from: "StyleSense <reports@stylesense.app>",
      to: [Deno.env.get("REPORT_EMAIL") ?? "joshiaayu06@gmail.com"],
      subject: `StyleSense Weekly Report — ${dateStr}`,
      html: `
        <h2>StyleSense Weekly Health Report</h2>
        <p style="font-size:16px;color:#333">${summary.replace(/\n/g, "<br>")}</p>
        <hr>
        <h3>Numbers (Last 7 Days)</h3>
        <table style="border-collapse:collapse;width:100%;max-width:400px">
          ${row("New signups", newUsers ?? 0)}
          ${row("AI outfit sessions", aiSessions ?? 0)}
          ${row("Outfits created", outfitsCreated ?? 0)}
          ${row("OOTD posts", socialPosts ?? 0)}
          ${row("Total premium users", premiumUsers ?? 0)}
        </table>
        <p style="color:#999;font-size:12px;margin-top:24px">StyleSense · Automated weekly report</p>
      `,
    }),
  });

  return new Response(
    JSON.stringify({
      success: true,
      metrics: { newUsers, aiSessions, outfitsCreated, socialPosts, premiumUsers },
    }),
    { headers: { "Content-Type": "application/json" } },
  );
});
