import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SESSION_ALERT_THRESHOLD = 200;

Deno.serve(async (_req: Request) => {
  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );

  // Start of today in IST
  const nowIST = new Date(
    new Date().toLocaleString("en-US", { timeZone: "Asia/Kolkata" }),
  );
  nowIST.setHours(0, 0, 0, 0);

  const { count: sessionCount, error } = await supabase
    .from("suggestion_sessions")
    .select("*", { count: "exact", head: true })
    .gte("created_at", nowIST.toISOString());

  if (error) {
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }

  const count = sessionCount ?? 0;
  const overLimit = count > SESSION_ALERT_THRESHOLD;

  const dateStr = new Date().toLocaleDateString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    year: "numeric",
  });

  const lines = [
    `*StyleSense Cost Monitor — ${dateStr}*`,
    `${overLimit ? "🔴" : "✅"} AI sessions today: ${count}`,
  ];
  if (overLimit) {
    lines.push(
      `\n⚠️ Above threshold (${SESSION_ALERT_THRESHOLD}). Review API spend.`,
    );
  }
  const text = lines.join("\n");

  const botToken = Deno.env.get("TELEGRAM_BOT_TOKEN");
  const chatId = Deno.env.get("TELEGRAM_CHAT_ID");

  if (botToken && chatId) {
    await fetch(`https://api.telegram.org/bot${botToken}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text, parse_mode: "Markdown" }),
    });
  }

  return new Response(
    JSON.stringify({ date: dateStr, sessionCount: count, overLimit }),
    { headers: { "Content-Type": "application/json" } },
  );
});
