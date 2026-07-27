import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient, type SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";
// Deno's native `npm:` specifier, tried first per docs/tickets/SS-010-design.md's
// instruction ("Developer should try npm: first ... and fall back to
// esm.sh/@aws-sdk/client-s3 if it doesn't resolve, noting whichever actually
// works"). NOT executed against a real Supabase Edge Runtime this session (no
// `deno` binary available in this sandbox) -- this resolution path remains
// [trained-knowledge, not verified this session], same label the design doc
// already carried. If `npm:@aws-sdk/client-s3` / `npm:@aws-sdk/s3-request-presigner`
// fail to resolve under `supabase functions serve`/deploy, fall back to
// `https://esm.sh/@aws-sdk/client-s3` / `https://esm.sh/@aws-sdk/s3-request-presigner`
// instead (same API surface).
import { PutObjectCommand, S3Client } from "npm:@aws-sdk/client-s3";
import { getSignedUrl } from "npm:@aws-sdk/s3-request-presigner";

// SS-010 -- Cloudflare R2 Presigned Upload Infrastructure.
//
// NOTE (post-review amendment, live-verified 2026-07-24 against the real
// CLOUDFLARE_R2_* credentials now in the repo's root .env): the design's
// originally-amended plan called for an S3-compatible presigned POST policy
// (`@aws-sdk/s3-presigned-post`'s createPresignedPost) with a
// `content-length-range` condition, to enforce both Content-Type and a size
// range server-side. Live-tested directly against the real R2 bucket this
// session -- R2 rejects presigned POST entirely:
//   501 NotImplemented: "Presigned post requests are not yet implemented"
// This overturns that plan's [trained-knowledge, not verified] assumption.
// Per the design's own documented fallback, this reverts to a presigned PUT.
// A second live finding while implementing that fallback: a plain pinned
// `ContentType` on the PutObjectCommand is NOT enforced by R2 against the
// actual request unless `content-type` is forced into the *signed* headers
// via `signableHeaders` below -- without it, R2 accepts a PUT whose real
// Content-Type header doesn't match what was "pinned" at all (verified: 200,
// not rejected). With `signableHeaders`, a mismatched header correctly fails
// R2's own signature check (403 SignatureDoesNotMatch, verified live).
// There is no PUT-based equivalent for `content-length-range` -- the size
// gap the amendment set out to close stays open (flagged, not silently
// dropped -- see this ticket's worklog/report).

export const R2_BUCKET = Deno.env.get("CLOUDFLARE_R2_BUCKET") ?? "stylesense-media";
export const PRESIGNED_URL_EXPIRY_SECONDS = 300;
export const FREE_TIER_WARDROBE_CAP = 50;
export const CONTENT_TYPE = "image/jpeg";

// Keep in sync with mobile/features/wardrobe/wardrobe.constants.ts's
// WARDROBE_LIMIT_MESSAGE -- duplicated, not shared, since this Deno runtime
// cannot import from mobile/.
export const WARDROBE_LIMIT_MESSAGE =
  "You've reached the free plan's 50-item wardrobe limit. Upgrade to premium for unlimited items.";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// Bearer-token API (no cookies), so a wildcard origin doesn't expose ambient
// credentials the way it would for a cookie-authenticated endpoint -- same
// posture as Supabase's own documented CORS example. Required because the
// platform-level `verify_jwt` gate (see config.toml) would otherwise reject
// the browser's unauthenticated OPTIONS preflight before this code ever
// runs -- [VERIFIED 2026-07-26, supabase.com/docs/guides/functions/cors +
// github.com/orgs/supabase/discussions/38832] -- so `verify_jwt` was set to
// `false` for this function and this file now does its own full CORS +
// auth handling (auth.getUser() below was already the real security
// boundary; the platform gate was redundant, not the only check).
//
// Allow-Headers matches the exact set the installed supabase-js SDK attaches
// via `supabase.functions.invoke()` (the mobile client's real call path, not
// a raw fetch) -- [VERIFIED 2026-07-26 against the installed
// mobile/node_modules/@supabase/supabase-js/src/cors.ts's own
// `SUPABASE_HEADERS`/`corsHeaders` export] -- copied verbatim rather than
// hand-picking a subset, since a first attempt with only
// authorization/content-type still 2nd-round-failed on a missing
// `x-client-info` (the SDK also sends `apikey`/`x-retry-count`).
const CORS_HEADERS: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type, x-retry-count",
  "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}

function buildR2Client(): S3Client {
  const accountId = Deno.env.get("CLOUDFLARE_R2_ACCOUNT_ID")!;
  return new S3Client({
    region: "auto",
    endpoint: `https://${accountId}.r2.cloudflarestorage.com`,
    credentials: {
      accessKeyId: Deno.env.get("CLOUDFLARE_R2_ACCESS_KEY")!,
      secretAccessKey: Deno.env.get("CLOUDFLARE_R2_SECRET_KEY")!,
    },
    // Disables the AWS SDK's default "flexible checksums" behaviour, which
    // (since ~v3.729) auto-adds a CRC32 to every PutObject. For a *presigned*
    // URL that is actively harmful: the checksum is computed at signing time,
    // when there is no body yet, so the signed URL carries
    // `x-amz-checksum-crc32=AAAAAA==` -- the CRC32 of zero bytes -- which then
    // cannot match the real bytes the browser PUTs. Observed live in a real
    // signed URL 2026-07-27; a known AWS SDK issue for presigned PUTs
    // ([VERIFIED 2026-07-27, github.com/aws/aws-sdk-js-v3 issues #4849/#6810 --
    // "integrity protections can be disabled by setting the config flag to
    // WHEN_REQUIRED"]). R2 also lists checksum algorithms as an unimplemented
    // PutBucketCors/PutObject feature, so nothing here relies on them.
    requestChecksumCalculation: "WHEN_REQUIRED",
  });
}

// Dependency-injection seam purely for index.test.ts (Deno's module system
// has no jest.mock()-style interception, so the real supabase-js/S3 clients
// are swapped for test doubles via this params object instead). Production
// use (the Deno.serve call at the bottom) always uses the real defaults.
export interface HandleRequestDeps {
  createSupabaseClient: (authHeader: string) => SupabaseClient;
  createR2Client: () => S3Client;
  getSignedUrl: typeof getSignedUrl;
}

const defaultDeps: HandleRequestDeps = {
  createSupabaseClient: (authHeader) =>
    createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_ANON_KEY")!,
      { global: { headers: { Authorization: authHeader } } },
    ),
  createR2Client: buildR2Client,
  getSignedUrl,
};

export async function handleRequest(
  req: Request,
  deps: HandleRequestDeps = defaultDeps,
): Promise<Response> {
  // Preflight must be answered before any auth check -- browsers never send
  // Authorization (or any app header) on the OPTIONS preflight itself.
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: CORS_HEADERS });
  }

  try {
    const authHeader = req.headers.get("Authorization");
    if (!authHeader) {
      return jsonResponse(
        { code: "unauthorized", message: "Missing Authorization header." },
        401,
      );
    }

    // Scoped to the caller's own JWT (not the service role) so RLS's
    // user_owns_wardrobe/user_owns_profile policies restrict every query
    // below to the caller's own rows -- defense in depth alongside
    // config.toml's verify_jwt = true and this explicit auth.getUser() call
    // (see docs/tickets/SS-010-design.md's Concrete values, §E-flagged note
    // on config.toml's verify_jwt default not being verified this session).
    const supabase = deps.createSupabaseClient(authHeader);

    const {
      data: { user },
      error: userError,
    } = await supabase.auth.getUser();

    if (userError || !user) {
      return jsonResponse(
        { code: "unauthorized", message: "Invalid or expired session." },
        401,
      );
    }

    let body: { itemId?: string } = {};
    try {
      body = await req.json();
    } catch {
      // No body / empty body is fine -- itemId is optional (first request).
    }

    const { data: profile } = await supabase
      .from("users")
      .select("plan_tier")
      .eq("id", user.id)
      .maybeSingle();

    const isPremium =
      profile?.plan_tier === "premium" || profile?.plan_tier === "premium_annual";

    // Queried unconditionally (not just for free users) -- besides the
    // free-tier cap check below, this same count feeds the mobile client's
    // FIRST_ITEM_ADDED analytics funnel step (existingItemCount === 0) for
    // every plan tier, not only free.
    const { count } = await supabase
      .from("wardrobe_items")
      .select("*", { count: "exact", head: true });
    const existingItemCount = count ?? 0;

    if (!isPremium && existingItemCount >= FREE_TIER_WARDROBE_CAP) {
      return jsonResponse(
        { code: "wardrobe_limit_reached", message: WARDROBE_LIMIT_MESSAGE },
        403,
      );
    }

    // Reuse the caller-supplied itemId on a retry (same R2 key, freshly
    // re-signed uploadUrl) if it looks like a real UUID; otherwise mint a
    // new one. No DB lookup/ownership check is possible or needed here --
    // this ticket creates no wardrobe_items row for this itemId to belong to
    // yet (see the design doc's hand-off contract for SS-011/012/013).
    const itemId =
      typeof body.itemId === "string" && UUID_RE.test(body.itemId)
        ? body.itemId
        : crypto.randomUUID();

    const key = `wardrobe/${user.id}/${itemId}/original.jpg`;

    const s3 = deps.createR2Client();
    const uploadUrl = await deps.getSignedUrl(
      s3,
      new PutObjectCommand({
        Bucket: R2_BUCKET,
        Key: key,
        ContentType: CONTENT_TYPE,
      }),
      {
        expiresIn: PRESIGNED_URL_EXPIRY_SECONDS,
        // See the file-level comment above -- forces Content-Type into the
        // *signed* headers so R2 actually rejects a mismatched upload
        // (verified live), not just a header the client can freely swap out.
        signableHeaders: new Set(["content-type"]),
      },
    );

    const expiresAt = new Date(
      Date.now() + PRESIGNED_URL_EXPIRY_SECONDS * 1000,
    ).toISOString();

    return jsonResponse({
      uploadUrl,
      itemId,
      key,
      expiresAt,
      contentType: CONTENT_TYPE,
      existingItemCount,
    });
  } catch (error) {
    return jsonResponse(
      {
        code: "internal_error",
        message: error instanceof Error ? error.message : "Unknown error",
      },
      500,
    );
  }
}

Deno.serve((req: Request) => handleRequest(req));
