// Deno test (see docs/tickets/SS-010-design.md's Test Plan).
//
// NOT executed this session -- no `deno` binary is available in this
// sandbox (verified: `which deno` finds nothing, no `.deno/bin` present).
// This file is written to the letter of the design's Test Plan (adjusted
// where the plan itself was overtaken by a live finding -- see below) but
// remains unverified/untested until run under a real Deno toolchain or CI
// (see docs/BACKLOG.md's BL-042: no CI job runs Supabase Edge Function
// tests yet).
//
// index.ts exposes a `handleRequest(req, deps)` seam specifically so these
// tests can substitute fake supabase-js/S3 clients -- Deno's module system
// has no jest.mock()-style interception of `npm:`/`esm.sh` imports.
//
// Test-plan items 8/9 (originally: assert an S3 presigned-POST policy's
// `fields` pin Content-Type/content-length-range, and that a mock policy
// validator rejects a mismatched POST) are N/A as originally written --
// live-verified against the real R2 bucket this session, R2 rejects
// presigned POST entirely (501 NotImplemented), so this Edge Function
// returns a presigned PUT, not a POST policy (see index.ts's file-level
// comment for the full live-verification note). The closest equivalent
// check for the PUT-based fallback is below: confirming `signableHeaders`
// (the mechanism that makes Content-Type actually enforceable against a real
// PUT, also live-verified) is actually wired into the getSignedUrl call, not
// just present in code as dead config. There is no PUT-based equivalent for
// the size-range condition -- that gap stays open (flagged, not tested,
// because there is nothing to test).

import { assertEquals, assertExists } from "jsr:@std/assert";
import {
  CONTENT_TYPE,
  FREE_TIER_WARDROBE_CAP,
  type HandleRequestDeps,
  handleRequest,
  PRESIGNED_URL_EXPIRY_SECONDS,
  WARDROBE_LIMIT_MESSAGE,
} from "./index.ts";

type PlanTier = "free" | "premium" | "premium_annual";

function buildFakeSupabaseClient(options: {
  user: { id: string } | null;
  userError?: unknown;
  planTier?: PlanTier;
  wardrobeCount?: number;
}) {
  return {
    auth: {
      getUser: () =>
        Promise.resolve({
          data: { user: options.user },
          error: options.userError ?? null,
        }),
    },
    from(table: string) {
      if (table === "users") {
        return {
          select: () => ({
            eq: () => ({
              maybeSingle: () =>
                Promise.resolve({
                  data: options.planTier
                    ? { plan_tier: options.planTier }
                    : null,
                  error: null,
                }),
            }),
          }),
        };
      }
      if (table === "wardrobe_items") {
        return {
          select: () =>
            Promise.resolve({
              count: options.wardrobeCount ?? 0,
              error: null,
            }),
        };
      }
      throw new Error(`Unexpected table: ${table}`);
    },
    // deno-lint-ignore no-explicit-any
  } as any;
}

function fakeDeps(
  overrides: {
    user?: { id: string } | null;
    userError?: unknown;
    planTier?: PlanTier;
    wardrobeCount?: number;
    signedUrl?: string;
  } = {},
): HandleRequestDeps {
  const client = buildFakeSupabaseClient({
    user: overrides.user === undefined ? { id: "user-1" } : overrides.user,
    userError: overrides.userError,
    planTier: overrides.planTier,
    wardrobeCount: overrides.wardrobeCount,
  });

  return {
    createSupabaseClient: (_authHeader: string) => client,
    // deno-lint-ignore no-explicit-any
    createR2Client: () => ({} as any),
    getSignedUrl: (() =>
      Promise.resolve(
        overrides.signedUrl ??
          "https://example.r2.cloudflarestorage.com/signed",
      )) as HandleRequestDeps["getSignedUrl"],
  };
}

function requestWithAuth(body?: Record<string, unknown>): Request {
  return new Request("https://edge.local/get-upload-url", {
    method: "POST",
    headers: { Authorization: "Bearer test-token" },
    body: body ? JSON.stringify(body) : undefined,
  });
}

Deno.test(
  "OPTIONS preflight returns 204 with CORS headers, without touching auth/deps",
  async () => {
    const req = new Request("https://edge.local/get-upload-url", {
      method: "OPTIONS",
    });
    // No Authorization header and deliberately-throwing deps -- if the
    // preflight branch didn't short-circuit before the auth check, this
    // would blow up instead of returning 204.
    const throwingDeps: HandleRequestDeps = {
      createSupabaseClient: () => {
        throw new Error("should not be called for OPTIONS");
      },
      createR2Client: () => {
        throw new Error("should not be called for OPTIONS");
      },
      getSignedUrl: () => {
        throw new Error("should not be called for OPTIONS");
      },
    };
    const res = await handleRequest(req, throwingDeps);
    assertEquals(res.status, 204);
    assertEquals(res.headers.get("Access-Control-Allow-Origin"), "*");
    assertExists(res.headers.get("Access-Control-Allow-Methods"));
    // Must cover every header the installed supabase-js SDK actually
    // attaches via functions.invoke() -- verified against
    // @supabase/supabase-js/src/cors.ts's own SUPABASE_HEADERS list, not
    // just the two most obvious ones (a first pass missed x-client-info).
    const allowHeaders = res.headers.get("Access-Control-Allow-Headers") ?? "";
    for (
      const required of [
        "authorization",
        "x-client-info",
        "apikey",
        "content-type",
        "x-retry-count",
      ]
    ) {
      assertEquals(
        allowHeaders.toLowerCase().includes(required),
        true,
        `Access-Control-Allow-Headers missing "${required}"`,
      );
    }
  },
);

Deno.test("real POST responses (success and error) also carry CORS headers", async () => {
  const req = requestWithAuth();
  const res = await handleRequest(
    req,
    fakeDeps({ planTier: "free", wardrobeCount: 0 }),
  );
  assertEquals(res.status, 200);
  assertEquals(res.headers.get("Access-Control-Allow-Origin"), "*");

  const unauthedReq = new Request("https://edge.local/get-upload-url", {
    method: "POST",
  });
  const unauthedRes = await handleRequest(unauthedReq, fakeDeps());
  assertEquals(unauthedRes.status, 401);
  assertEquals(unauthedRes.headers.get("Access-Control-Allow-Origin"), "*");
});

Deno.test("returns 401 when no Authorization header is present", async () => {
  const req = new Request("https://edge.local/get-upload-url", {
    method: "POST",
  });
  const res = await handleRequest(req, fakeDeps());
  assertEquals(res.status, 401);
});

Deno.test("returns 401 when auth.getUser() resolves an error", async () => {
  const req = requestWithAuth();
  const res = await handleRequest(
    req,
    fakeDeps({ user: null, userError: new Error("invalid token") }),
  );
  assertEquals(res.status, 401);
});

Deno.test(
  "returns 200 with uploadUrl/itemId/key for a free user with 0 existing items",
  async () => {
    const req = requestWithAuth();
    const res = await handleRequest(
      req,
      fakeDeps({ planTier: "free", wardrobeCount: 0 }),
    );
    assertEquals(res.status, 200);
    const body = await res.json();
    assertExists(body.uploadUrl);
    assertEquals(body.key, `wardrobe/user-1/${body.itemId}/original.jpg`);
    assertEquals(body.contentType, CONTENT_TYPE);
    assertEquals(body.existingItemCount, 0);
  },
);

Deno.test(
  'returns 403 with an "Upgrade to premium" message at 50 existing items',
  async () => {
    const req = requestWithAuth();
    const res = await handleRequest(
      req,
      fakeDeps({ planTier: "free", wardrobeCount: FREE_TIER_WARDROBE_CAP }),
    );
    assertEquals(res.status, 403);
    const body = await res.json();
    assertEquals(body.code, "wardrobe_limit_reached");
    assertEquals(body.message, WARDROBE_LIMIT_MESSAGE);
  },
);

Deno.test(
  "allows the request at exactly 49 existing items (boundary)",
  async () => {
    const req = requestWithAuth();
    const res = await handleRequest(
      req,
      fakeDeps({ planTier: "free", wardrobeCount: 49 }),
    );
    assertEquals(res.status, 200);
  },
);

Deno.test(
  "skips the item-count block entirely for a premium user at 50+ items",
  async () => {
    const req = requestWithAuth();
    const res = await handleRequest(
      req,
      fakeDeps({ planTier: "premium", wardrobeCount: 60 }),
    );
    assertEquals(res.status, 200);
  },
);

Deno.test(
  "reuses the caller-supplied itemId (same key, freshly re-signed url)",
  async () => {
    const existingItemId = "11111111-2222-4333-8444-555555555555";
    const req = requestWithAuth({ itemId: existingItemId });
    const res = await handleRequest(
      req,
      fakeDeps({ planTier: "free", wardrobeCount: 1 }),
    );
    const body = await res.json();
    assertEquals(body.itemId, existingItemId);
    assertEquals(body.key, `wardrobe/user-1/${existingItemId}/original.jpg`);
  },
);

Deno.test("expiresAt is ~300 seconds from the call time", async () => {
  const req = requestWithAuth();
  const before = Date.now();
  const res = await handleRequest(
    req,
    fakeDeps({ planTier: "free", wardrobeCount: 0 }),
  );
  const body = await res.json();
  const expiresAtMs = new Date(body.expiresAt).getTime();
  const deltaSeconds = (expiresAtMs - before) / 1000;
  assertEquals(
    Math.abs(deltaSeconds - PRESIGNED_URL_EXPIRY_SECONDS) < 5,
    true,
  );
});

// Replaces the original Test Plan's "policy fields pin Content-Type/size"
// assertion -- see this file's header comment for why. This confirms the
// PUT-based Content-Type enforcement mechanism (live-verified against real
// R2 this session) is actually wired into the getSignedUrl call.
Deno.test(
  "forces content-type into the signed headers passed to getSignedUrl",
  async () => {
    const req = requestWithAuth();
    let capturedOptions: { signableHeaders?: Set<string> } | undefined;
    const deps = fakeDeps({ planTier: "free", wardrobeCount: 0 });
    deps.getSignedUrl = ((_client, _command, options) => {
      capturedOptions = options as { signableHeaders?: Set<string> };
      return Promise.resolve(
        "https://example.r2.cloudflarestorage.com/signed",
      );
    }) as HandleRequestDeps["getSignedUrl"];

    const res = await handleRequest(req, deps);
    assertEquals(res.status, 200);
    assertExists(capturedOptions?.signableHeaders);
    assertEquals(capturedOptions?.signableHeaders?.has("content-type"), true);
  },
);
