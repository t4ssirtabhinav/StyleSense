# SS-010 — Cloudflare R2 Presigned Upload Infrastructure — Design

## Scope restatement

This ticket builds the plumbing that lets the mobile client upload a wardrobe photo straight to Cloudflare R2 without the file ever touching our backend: a Supabase Edge Function (`get-upload-url`) that authenticates the caller, enforces the free-tier 50-item wardrobe cap, and mints a 5-minute presigned R2 `PUT` URL under the `wardrobe/{user_id}/{item_id}/original.jpg` key convention; and a client-side upload pipeline (compress → request URL → upload with progress → retry-on-failure/expiry) in a new `features/wardrobe/` domain. It is the first ticket of Epic 2 (Wardrobe Core) and a hard dependency of SS-011 (BG removal), SS-012 (AI tagging) and SS-013 (upload UI) — none of which exist yet. It does **not** build the camera/gallery UI, the BG-removal/AI-tagging pipeline, or any `wardrobe_items` row-creation logic — those are explicitly the next three tickets' jobs, and this design says so wherever the raw ticket text brushes up against that boundary (notably its Description's mention of `POST /wardrobe/items/process`, which no AC in this ticket actually requires — see Open Questions).

## Files to create/modify

**Supabase (Edge Function + config):**
- `supabase/functions/get-upload-url/index.ts` — new. The presigned-URL endpoint.
- `supabase/functions/get-upload-url/index.test.ts` — new. Deno tests (see Test Plan).
- `supabase/config.toml` — modify. Add:
  ```toml
  [functions.get-upload-url]
  verify_jwt = true
  ```
  Explicit rather than relying on the platform default (see Open Questions — the default is trained-knowledge, not verified this session) so the security boundary is self-documenting regardless of what the default actually turns out to be.

**Mobile — new `features/wardrobe/` domain:**
- `mobile/features/wardrobe/wardrobe.types.ts` — new. `UploadUrlRequest`, `UploadUrlResponse`, `WardrobeUploadTask`, `WardrobeUploadStatus`, `WardrobeUploadError`. `WardrobeUploadTask`/the mutation input also carry a `source: 'camera' | 'gallery'` field (see "Monitoring & analytics wiring") — SS-010 doesn't know how the photo was picked, so this is a required param the caller (SS-013) must supply, not something this ticket infers.
- `mobile/features/wardrobe/wardrobe.constants.ts` — new. Compression/limit/retry constants (see Concrete values).
- `mobile/features/wardrobe/wardrobe.service.ts` — new. `compressImageForUpload`, `requestUploadUrl`, `uploadToR2WithProgress`, `computeBatchDedupeHash`. The only place `supabase.functions.invoke` is called from for this domain (mirrors `auth.service.ts`/`home.service.ts`'s existing "only place `supabase.*` is called from" pattern).
- `mobile/features/wardrobe/wardrobe.queries.ts` — new. `useUploadWardrobeItem()` — the React Query mutation hook that orchestrates the full compress→request→upload→retry flow and is the only thing screens should import. Also the wiring point for SS-009's monitoring primitives (see "Monitoring & analytics wiring" below) — the only file in this domain that imports `useAnalytics`/`captureException`.
- `mobile/features/wardrobe/wardrobe.store.ts` — new. Zustand store (`useWardrobeUploadStore`) holding per-task progress/status/retry state, keyed by a client-generated task id (not the same as R2's `itemId` until the upload actually starts — see `wardrobe.types.ts`).

**Design system:**
- `mobile/components/ui/ProgressBar.tsx` — new. Minimal linear progress bar primitive (track + animated fill), needed because this ticket's own AC requires upload progress to be "visible" and no such primitive exists yet. Follows `Skeleton.tsx`'s conventions (tokens-driven colours, Reanimated for the fill's `withTiming` transition, NativeWind for anything static).
- `mobile/components/ui/index.ts` — modify. Export `ProgressBar`/`ProgressBarProps`.

**Tests:**
- `mobile/__tests__/features/wardrobe/wardrobe.service.test.ts` — new.
- `mobile/__tests__/features/wardrobe/wardrobe.queries.test.tsx` — new.
- `mobile/__tests__/features/wardrobe/wardrobe.store.test.ts` — new.
- `mobile/__tests__/components/ui/ProgressBar.test.tsx` — new.

**Package changes:**
- `mobile/package.json` — add `expo-crypto` (install via `npx expo install expo-crypto`) for the in-batch dedupe hash (`Crypto.digestStringAsync(CryptoDigestAlgorithm.SHA256, base64)`; works on both web via SubtleCrypto and native). No other new dependency needed — `expo-image-manipulator` is already installed (`^56.0.19`), and the R2 upload itself is done with a plain `XMLHttpRequest` (see below), not `expo-file-system`, so that native module is deliberately **not** added.

**Explicitly not touched:** no `backend/` files (no new FastAPI route), no `supabase/migrations/*.sql` (no schema change — `wardrobe_items` already exists from SS-002), no `.env.example` change (R2 vars already present as empty placeholders).

## Concrete values to use, not invent

Transcribed verbatim from `docs/tickets/raw/SS-010.md`:
- R2 key pattern: `wardrobe/{user_id}/{item_id}/original.jpg`
- Presigned URL expiry: 5 minutes → `expiresIn: 300` (seconds) in `getSignedUrl()`
- Free-tier wardrobe cap: 50 items; unlimited for `premium`/`premium_annual` (`users.plan_tier` enum from `001_initial.sql`: `'free' | 'premium' | 'premium_annual'`)
- Client-side compression: max width 1200px; compress large originals (20MB+) to under 2MB
- Bucket name: `CLOUDFLARE_R2_BUCKET=stylesense-media` (already set in `.env.example`, don't invent a different name)

Reconciled with the existing schema (`supabase/migrations/001_initial.sql`):
- Free-tier check query (via a client scoped to the caller's own JWT, so RLS's `user_owns_wardrobe` policy — `auth.uid() = user_id` — already restricts the count to the caller): `select count(*) from wardrobe_items` with no explicit `user_id` filter needed (RLS does it); `plan_tier` read via `select plan_tier from users` (RLS `user_owns_profile` policy scopes this to one row, the caller's own). Block when `!isPremium && count >= 50` — this satisfies the ticket's own boundary edge case verbatim ("Free user at 49 items uploads 1 — should succeed. 51st blocked."): at `count === 49` the check passes (uploading the 50th); at `count === 50` it blocks (the 51st attempt).
- `item_id`: generated by the Edge Function itself (`crypto.randomUUID()`, Deno's global Web Crypto), **not** supplied by the client on first request — this ticket does not create a `wardrobe_items` row, so there is no existing UUID to reuse. The client may pass an existing `itemId` back on a *retry* request (see Edge Cases) to get a fresh signature for the same R2 key rather than a brand-new key.
- **Hand-off contract for SS-011/012/013 (write this down now so it isn't re-litigated per-ticket):** whichever future ticket first inserts the `wardrobe_items` row for an uploaded photo must explicitly set `id` to the same UUID this function returned as `itemId` (overriding the column's `DEFAULT gen_random_uuid()`), so the DB row's primary key and the R2 key's `{item_id}` segment stay the same value. Flagged in Open Questions since it isn't enforceable by this ticket's own code — there's nothing in `wardrobe_items` yet for this ticket to write to.

Architect's own reasonable choices (ticket doesn't pin these down — flagged as such, not verbatim spec):
- Retry/backoff: exponential, base 1s, ×2 factor, cap 8s, max 3 attempts for a plain network failure (`xhr.onerror`/timeout). A `403` mid-upload is handled differently (see Edge Cases) — not just backoff-retried against the same (now-invalid) URL.
- Compression quality ladder: start `compress: 0.8` (JPEG), and only if the resulting blob is still over 2MB, step down in `0.1` decrements to a floor of `0.5`, re-running `manipulateAsync` each step (checked via the same `Blob` already fetched for upload, see below — no extra file-size API needed).
- Upload transport: `fetch(localUri).then(r => r.blob())` to read the (already-compressed) local file into an in-memory `Blob`, then an `XMLHttpRequest` **POST** (see below — not a plain PUT) with `xhr.upload.onprogress` driving the store's progress percentage. This one code path works identically on web (Expo Router's `web.output: "static"` target) and native — deliberately avoiding `expo-file-system`'s `createUploadTask`, which is native-only and would need a separate web code path. This is a real architectural decision worth flagging: CLAUDE.md's stack line ("Expo React Native web-first") makes a single cross-platform path the right default, not a native-first one with a web shim bolted on later.
- **Server-side Content-Type/size enforcement (added post-review, before Developer starts — see Open Questions §1 in the original pass).** A plain presigned `PutObjectCommand` URL cannot enforce a size range, only an exact `ContentLength` (impractical here since final compressed size isn't known until after compression). Switched the Edge Function to return an **S3-compatible presigned POST policy** instead (`createPresignedPost` from `@aws-sdk/s3-presigned-post`), with conditions:
  - `['eq', '$Content-Type', 'image/jpeg']` — rejects any non-JPEG body at the R2 layer itself, not just client-enforced.
  - `['content-length-range', 1024, 3145728]` — 1KB–3MB (headroom above the 2MB client-compression target, since the compression ladder's floor at `compress: 0.5` isn't a hard guarantee for every image). Anything outside this range is rejected by R2 before the object is ever written, not caught after the fact.
  - `{ key: <the wardrobe/{user_id}/{item_id}/original.jpg key> }` — exact key match, unchanged from the PUT-based design.
  - `Response.uploadUrl`/`fields` replace the old single `uploadUrl` string: client does `POST` with a `multipart/form-data` body (policy `fields` + the file), not a raw-body `PUT`. `xhr.upload.onprogress` still fires normally on a `FormData` POST, so the progress-bar wiring is unaffected.
  - **`[trained-knowledge, not verified this session]`**: R2's S3-compatibility includes presigned POST/policy support the same way it supports presigned PUT — this is the standard S3 mechanism for browser-enforced upload size limits and R2 documents itself as S3-API-compatible, but POST policies are used far less commonly than presigned PUT in existing integrations. Developer must confirm this against current Cloudflare R2 docs (or a live test once real credentials exist) before relying on it; if R2 rejects POST-policy uploads for any reason, the fallback is reverting to presigned PUT with `ContentType` pinned (closes the type gap, but reopens the size gap — flag back to Architect if that fallback is needed).
- `ProgressBar` visual: track colour `colors.bg.secondary` (`#F4F2ED`), fill colour `colors.accent.marigold` (`#E8A420`, the primary-CTA colour per SS-008's tokens — matches "processing/progress" rather than `emerald` which SS-008's tokens reserve for success states), radius `radii.pill`.
- **Monitoring & analytics wiring (added post-review, 2026-07-24 — SS-009 merged same day, PR #20).** At the time of this ticket's original Architect pass, SS-009 (Sentry/PostHog instrumentation) was parked and unbuilt, so no monitoring hook existed for this domain to call. It has since shipped real, working primitives — `useUploadWardrobeItem()` in `wardrobe.queries.ts` must wire into them rather than leave upload failures/successes invisible:
  - **Errors:** on a terminal (non-retried-away) upload failure — retry attempts exhausted on a generic network/expired-URL error, or the new non-retryable policy-violation `400` (Edge Cases, above) — call `Sentry.captureException` (`mobile/lib/sentry.ts`) with `Sentry.setTag('feature', 'wardrobe_upload')` (or an equivalent scoped tag) before capture, so these are filterable in the dashboard from other error sources. Do **not** capture the routine "got a 403, retried, second attempt succeeded" path — that's expected behavior, not an error.
  - **Success:** on a successful upload, call `useAnalytics().track(ANALYTICS_EVENTS.ITEM_UPLOADED, { source })` (`item_uploaded`, from `constants/analyticsEvents.ts`) — `category` is left `undefined` (the type marks it optional) since SS-010 never learns the item's category; that's SS-012's job, later. `source` (`'camera' | 'gallery'`) is threaded through from the mutation's input (see `wardrobe.types.ts` above), supplied by SS-013's UI when it calls this hook.
  - **First-item funnel step:** the free-tier cap check (Concrete values, above) already queries the caller's pre-upload `wardrobe_items` count as part of every request. When that count is `0` (i.e., this upload is the user's first-ever wardrobe item), additionally fire `ANALYTICS_EVENTS.FIRST_ITEM_ADDED` (`first_item_added`) alongside `item_uploaded`. This is the second step of the `register → first_item_added → first_suggestion_viewed → premium_paywall_viewed` PostHog funnel SS-009 defined but couldn't populate (its own AC only wired `register`) — SS-010 is the first ticket able to give that funnel real data for its second step.
  - Both calls belong in `wardrobe.queries.ts` (the orchestration hook), not `wardrobe.service.ts` (kept a pure API-call layer, no monitoring side effects) — mirrors the existing separation already established by `auth.service.ts`/`hooks/useAuth.ts` in SS-009's own Developer phase.

Labeled per `docs/OPERATOR_RULEBOOK.md` §E — trained-knowledge, **not verified this session** (no WebFetch tool available in this environment):
- R2's S3-compatible endpoint format, `https://{ACCOUNT_ID}.r2.cloudflarestorage.com`, region `auto`, used to construct the `S3Client` in the Edge Function.
- That Deno's `npm:@aws-sdk/client-s3` / `npm:@aws-sdk/s3-request-presigner` specifiers resolve correctly inside Supabase's Edge Runtime (the two existing functions in this repo only import via `esm.sh`, never `npm:` — no precedent in this codebase either way). Developer should try `npm:` first (Deno's native, most current mechanism for this SDK) and fall back to `esm.sh/@aws-sdk/client-s3` if it doesn't resolve, noting whichever actually works.
- Whether `[functions.<slug>].verify_jwt` in `config.toml` truly defaults to `true` platform-side, and the exact mechanics of when the gateway rejects vs. when it's left to the function to call `supabase.auth.getUser()`. This is exactly why the design sets `verify_jwt = true` explicitly rather than leaning on an assumed default (see above) — and why the function *also* calls `auth.getUser()` itself (defense in depth, and it's needed anyway to get the caller's `user_id` for the R2 key and the RLS-scoped queries).

Both of the above should be spot-checked against current Cloudflare/Supabase docs during the Developer phase (or via a live WebFetch, same remediation pattern as BL-035/BL-039), and are bundled with this ticket's bigger blocker below: none of it can be end-to-end verified against a real bucket regardless.

## Edge cases

Carried forward from the ticket, plus new ones surfaced while designing:

- Slow 3G (Tier-2/3 India): plain network failure → exponential backoff retry (see Concrete values), same presigned URL reused (still within its 5-minute window in the common case).
- Very large image (20MB+ DSLR): compress iteratively to under 2MB (quality ladder above) before ever calling `requestUploadUrl` — never uploads the uncompressed original.
- Presigned URL expires mid-upload: `uploadToR2WithProgress` must distinguish an R2 `403` (expired/invalid signature) from a generic network error (`xhr.onerror`) by inspecting `xhr.status` in the `onload` handler, not just `onerror`. On `403`: call `requestUploadUrl({ itemId })` again (passing the *same* `itemId` so the R2 key doesn't change), get a fresh URL, retry the `PUT` — up to 2 additional attempts before surfacing a "please try again" error.
- Hash-based dedup ("check against existing items before processing"): **scoped down from the ticket's literal wording.** This ticket creates no `wardrobe_items` rows and the schema has no `image_hash` column, so a true check against a user's *entire existing wardrobe* isn't implementable at this layer without a schema change (logged as BL-043, not resolved here). What this ticket does implement: an **in-batch** dedupe — `computeBatchDedupeHash` (SHA-256 of the compressed image's base64 via `expo-crypto`) compared against other hashes already seen in the *same* upload session (relevant once SS-013's bulk-select UI exists), so selecting the same photo twice in one gallery multi-select doesn't burn two uploads. Flagged in Open Questions, not silently narrowed without saying so.
- Free user at 49 items uploads 1 → succeeds (becomes the 50th); the 51st attempt is blocked with the "Upgrade to premium" message. Boundary-tested explicitly (see Test Plan).
- New edge case (not in the raw ticket): **concurrent uploads from two devices/tabs for the same user, both at 49 items.** The count-then-allow check is not atomic against a race — both could read `count = 49` and both proceed, landing the user at 51 (soft cap, over by one). Given wardrobe count isn't a payment-integrity boundary (unlike, say, a Razorpay-gated entitlement), this is an acceptable soft-limit race for now — noted rather than fixed with a heavier atomic-increment scheme, since nothing this ticket touches (no counter table, no advisory lock) makes that cheap. Flagged in Open Questions in case a future ticket wants to harden it.
- New edge case: user backgrounds/closes the app mid-upload (native). The in-memory `Blob` read via `fetch(localUri)` and the `XMLHttpRequest` both live in JS memory tied to the running app process — there is no background-upload continuation (that would require `expo-file-system`'s native background upload task, deliberately not used here, see Concrete values). On resume, the task's store state should be inspected and, if still `'uploading'` with no recent progress update, treated as failed and offered a retry rather than left silently stuck. `wardrobe.store.ts` should expose this as a derived "stale" check (e.g. last-progress timestamp older than some threshold) for whichever screen (SS-013) renders it — this ticket only needs to make the state observable, not resolve the UX for it.
- New edge case: R2 returns a non-403 error (e.g. `500`, or the bucket is temporarily unreachable) — treated the same as a generic network failure (backoff-retry), not the expired-URL path, since retrying with a fresh URL wouldn't help a server-side R2 outage.
- New edge case (added post-review): **policy rejection — `400` with an R2 `EntityTooLarge`/`InvalidArgument` (Content-Type mismatch) response.** This is neither a network failure nor an expired-signature case — it means the file itself violates the signed policy (shouldn't happen via the app's own compression pipeline, but could happen if a non-standard client hits the endpoint, or a compression-ladder edge case still produces a file outside the 1KB–3MB range). `uploadToR2WithProgress` must distinguish this from `403` and from generic network errors, surface it as a **non-retryable** "file couldn't be uploaded" error (retrying the same oversized/wrong-type file against a fresh policy would fail identically). `wardrobe.queries.ts` must `Sentry.captureException` this case (see "Monitoring & analytics wiring" above) — this is exactly the abuse case the policy conditions exist to catch, so a spike in this error is now actually visible in the Sentry dashboard (SS-009 shipped 2026-07-24), not just a hypothetical "worth watching" note.

## Test plan

**`supabase/functions/get-upload-url/index.test.ts`** (Deno test, mocking the Supabase client and `S3Client`):
1. Returns `401` when no `Authorization` header is present (or `auth.getUser()` resolves an error).
2. Returns a `200` with `uploadUrl`/`itemId`/`key` matching `wardrobe/{user_id}/{item_id}/original.jpg` for a free user with 0 existing wardrobe items.
3. Returns `403` with an "Upgrade to premium" message for a free user who already has 50 wardrobe items.
4. Allows the request (boundary) for a free user at exactly 49 existing items.
5. Skips the item-count check entirely for a `premium`/`premium_annual` user, even at 50+ items.
6. Reuses the caller-supplied `itemId` (same `key`, freshly re-signed `uploadUrl`) when the request body includes a valid `itemId`.
7. `expiresAt` in the response is ~300 seconds from the call time (within a small tolerance).
8. The returned policy's `fields` include a `Content-Type` condition pinned to `image/jpeg` and a `content-length-range` condition of `[1024, 3145728]`.
9. (Integration-style, mocked R2) A POST matching the policy with a non-`image/jpeg` `Content-Type` field is rejected by the mock policy validator; same for a body outside the size range — confirms the conditions are actually wired into the returned policy object, not just present in code as dead config.

**`mobile/__tests__/features/wardrobe/wardrobe.service.test.ts`**:
1. `compressImageForUpload` calls `manipulateAsync` with a `resize.width` of 1200 and JPEG `SaveFormat`.
2. `compressImageForUpload` re-invokes with a lower `compress` value when the first pass's output blob exceeds 2MB, stopping at the 0.5 floor.
3. `requestUploadUrl` calls `supabase.functions.invoke('get-upload-url', ...)` and returns the typed `UploadUrlResponse`.
4. `requestUploadUrl` maps a `403 wardrobe_limit_reached` function response into a typed `WardrobeUploadError` carrying the exact upgrade-to-premium copy (not a generic error).
5. `uploadToR2WithProgress` constructs a `FormData` POST (policy `fields` + file field), not a raw-body PUT, and resolves on XHR status `200`/`204`, invoking `onProgress` with monotonically increasing percentages.
6. `uploadToR2WithProgress` rejects with a retryable error on `xhr.onerror`.
7. `uploadToR2WithProgress` detects HTTP `403` specifically in `onload` and rejects with a distinct "expired-url" error (not the generic network-failure error).
8. `uploadToR2WithProgress` detects a policy-violation `400` (Content-Type/size mismatch) in `onload` and rejects with a distinct, **non-retryable** "invalid file" error — never enters the backoff-retry path.
8. `computeBatchDedupeHash` returns identical hashes for identical compressed-image bytes, enabling a caller to flag the second occurrence within one batch as a duplicate.

**`mobile/__tests__/features/wardrobe/wardrobe.queries.test.tsx`**:
1. `useUploadWardrobeItem` orchestrates compress → requestUploadUrl → upload and resolves with `{ itemId, key }` on success.
2. On a `403` mid-upload, the hook requests a fresh presigned URL (same `itemId`) and retries before surfacing an error to the caller.
3. On a generic network failure, the hook retries with the configured exponential backoff up to the max attempt count before failing.
4. A `wardrobe_limit_reached` error is surfaced to the caller unchanged and immediately (no retry loop — retrying a hard cap is pointless).
5. On success, calls `track(ANALYTICS_EVENTS.ITEM_UPLOADED, { source })` exactly once with the caller-supplied `source`.
6. On success **when the pre-upload item count was 0**, additionally calls `track(ANALYTICS_EVENTS.FIRST_ITEM_ADDED)`; when the pre-upload count was ≥1, `FIRST_ITEM_ADDED` is not called.
7. On a terminal failure (retries exhausted, or the non-retryable policy-violation error), calls `Sentry.captureException` exactly once with the tagged scope; does **not** call it when a `403` retry ultimately succeeds.

**`mobile/__tests__/features/wardrobe/wardrobe.store.test.ts`**:
1. `startUpload` adds a new task in `'idle'`/`'compressing'` status.
2. `updateProgress` updates only the targeted task's percent, leaving sibling tasks (a batch) untouched.
3. Setting `'error'` status preserves the last-known progress percent (so a retry-button UI can show where it stalled).
4. `retryUpload` resets a failed task back to an in-progress status without losing its `localUri`.

**`mobile/__tests__/components/ui/ProgressBar.test.tsx`**:
1. Renders the fill at the correct width percentage for `progress` values `0`/`50`/`100`.
2. Clamps out-of-range `progress` values (negative, >100) instead of rendering an invalid width.

**Not automatable this pass (manual/device verification, blocked on R2 provisioning — see Open Questions):**
- A real end-to-end presigned `PUT` actually landing an object in a real `stylesense-media` R2 bucket.
- "R2 upload completes under 3s on 4G" and the slow-3G retry-in-the-wild behavior — needs a real device on a real network; compounds with the pre-existing `BL-013` (Expo Go/LAN) gap for on-device testing.

No backend (`backend/tests/`) changes — this ticket touches no FastAPI code.

## Open questions / blockers

1. **R2 credentials/bucket not provisioned (this ticket's own Status note, same class as `BL-001`).** `CLOUDFLARE_R2_ACCOUNT_ID`/`ACCESS_KEY`/`SECRET_KEY` are empty in `.env.example`; no real R2 bucket exists. This design and the Developer phase can build and unit-test the full contract above (mocked `S3Client`, mocked Supabase client), but real end-to-end upload verification — including confirming the bucket is actually configured **private** (AC: "Private bucket — URL requires signed access" is an R2-dashboard/bucket-creation setting, not code this ticket writes) — is blocked until a business/account-setup step provisions real credentials. Flag explicitly at sign-off rather than mocking this away silently.
2. **`BL-031` (Home nudge/Wardrobe CTA destination) — confirmed still open, not resolved by this ticket.** SS-010 is backend/infra only; it ships no screen and no navigable destination. Per SS-013's own Status note, resolution is split further than the original BL-031 framing suggested: SS-013 closes the Wardrobe tab's empty-state CTA half, SS-014 closes the Home nudge's "hide once the user has ≥1 real item" half. This design doesn't move BL-031 — it stays Active until SS-013 lands (SS-014 for the other half).
3. **`BL-033` (no FastAPI JWT-verification dependency) — independent of this ticket, not resolved, not worsened.** This ticket's JWT check lives entirely inside a Supabase Edge Function, a different runtime/trust boundary than the FastAPI backend BL-033 is scoped to (the Edge Function relies on `config.toml`'s `verify_jwt` gateway-level check plus its own `auth.getUser()` call — see Concrete values' §E-flagged note; the FastAPI stub in `routers/outfit_suggestions.py` is untouched by this design). Since SS-010 adds no new FastAPI route, it neither closes BL-033 nor extends the unsafe stub pattern to new surface.
4. **`BL-037` (no backend deployment) does not block this ticket.** The ticket Description's mention of `POST /wardrobe/items/process` implied a FastAPI call, but that endpoint is in none of this ticket's ACs, and this design deliberately keeps SS-010 to Supabase Edge Functions only (no FastAPI route added) — so Railway/BL-037 is simply not in this ticket's dependency path at all.
5. **Ownership gap: nobody's ticket actually defines `POST /wardrobe/items/process`.** SS-011 defines `POST /wardrobe/remove-bg`; SS-012 defines no endpoint of its own; the raw SS-010 ticket's Description names a combined `/wardrobe/items/process` orchestration call that appears in no ticket's AC list. Logged as `BL-041` (see Backlog deltas) rather than resolved here or folded silently into SS-011/012's scope.
6. **Row-creation timing vs. `wardrobe_items.category NOT NULL`.** No column exists to represent "uploaded but not yet AI-tagged" (SS-011's AC references a `bg_pending` flag with no backing column), and `category` has no default — a row can't exist until a category is known, which happens only after Gemini tagging (SS-012). This affects when/how SS-011's pipeline can create the row it needs to update. Logged as `BL-040`, not resolved here (out of this ticket's scope — SS-010 creates no rows at all).
7. **In-batch-only dedupe, not cross-wardrobe dedupe** (see Edge Cases). A real fix needs an `image_hash` column. Logged as `BL-043`.
8. **No CI job runs Supabase Edge Function (Deno) tests.** `.github/workflows/ci.yml` has frontend and backend quality jobs but nothing for `supabase/functions/`; this is the first Edge Function in this pipeline with real auth/money-adjacent logic (free-tier gating) worth testing in CI, not just locally. Logged as `BL-042`.
9. **`ProgressBar`'s actual integration point in the upload UX is undecided.** SS-013's own 3-step description (Capture → Processing shimmer → Review) never explicitly mentions a raw upload-percentage bar — its "Processing" shimmer represents the *post-upload* BG-removal/AI-tagging wait (SS-011/012), a different moment than the R2 `PUT` this ticket instruments. SS-013's Architect phase should decide exactly where (if at all, vs. e.g. just a spinner) this primitive gets used; this ticket ships it as a generic, tested, reusable component rather than guessing its placement.
10. If the ticket's ACs and the "SS-010 is infra-only" framing feel in tension (progress bar / retry button are UI-facing ACs on a ticket titled "Infrastructure"), that tension is real and called out rather than silently resolved: this design ships the *mechanism* (store + hook + a generic `ProgressBar` primitive) fully tested, but a user actually *seeing* it requires a screen, which is SS-013's job.

## Backlog deltas

Added to `docs/BACKLOG.md`'s **Active** table:
- `BL-040` (schema) — `wardrobe_items.category` is `NOT NULL` with no default and no processing-status column exists, so no row can represent an uploaded-but-not-yet-tagged item; blocks a clean answer to when/how SS-011/012's pipeline creates its row.
- `BL-041` (infra) — no ticket's AC list actually defines the combined `POST /wardrobe/items/process` orchestration endpoint the raw SS-010 ticket's Description names; SS-011 owns `/wardrobe/remove-bg` only, SS-012 owns no endpoint.
- `BL-042` (ci) — no CI job runs Supabase Edge Function (Deno) tests; this ticket adds the first Edge Function with real auth/tier-gating logic worth testing automatically.
- `BL-043` (schema) — no `image_hash` column exists for true cross-wardrobe duplicate-image detection; this ticket implements only in-batch (same upload session) dedupe.

`BL-031`/`BL-033`/`BL-037` scanned per the Architect resurfacing pass (tags `infra`/`auth`/`infra`): none resolved by this ticket (see Open Questions 2–4 above for why) — left Active, unchanged, with the specific clarifying note each needed.

## Post-review amendments (2026-07-24, before Developer start)

User review of this design surfaced three additional abuse/risk questions not caught by the original Architect pass. Decisions, made before Developer begins (full-lane gate):

1. **Server-side Content-Type/size enforcement — fixed in this design, not backlogged.** Switched the Edge Function from a plain presigned PUT to an S3-compatible presigned POST policy (`Content-Type` pinned to `image/jpeg`, `content-length-range` 1KB–3MB). See "Concrete values" and the updated Edge Cases/Test Plan above. This closes the gap where only client-side compression enforced type/size, meaning a caller bypassing the app (but still holding a valid JWT) could previously PUT an arbitrary file/size to a signed key.
2. **Content moderation (NSFW/illegal content) — deferred, scoped into SS-012, not this ticket.** SS-012 (Gemini Vision AI auto-tagging) already runs every uploaded image through a vision model for tagging; logged as `BL-044` (tag `ai`) instructing SS-012's own Architect pass to evaluate adding a moderation/SafeSearch-style check to that same pass rather than standing up a separate service. Not resolved here — SS-010 ships no moderation of any kind; this is a real gap between upload and any content check.
3. **Rate limiting on `get-upload-url` invocations — deferred, not resolved.** No limit on how often an authenticated caller can invoke this Edge Function. Logged as `BL-045` (tag `infra`) for a follow-up once real usage data exists to size a sensible limit; not urgent pre-launch (no public traffic yet), but flagged so it isn't forgotten once this ships.

Also surfaced during review, **not yet resolved anywhere and not this ticket's scope**: no ticket currently defines the **read path** for these images (viewing wardrobe photos back in the app — thumbnails in the wardrobe grid, etc.) once uploaded. SS-010 only builds the write side (`PUT`/`POST` to R2). Logged as `BL-046` (tag `infra`) for whichever ticket first needs to render an uploaded image back to the user (likely SS-014, Wardrobe Grid) to decide: signed GET URLs generated per-view, a short-lived CDN-fronted signed URL, or something else — private-bucket + no-read-path-yet means this is currently an unanswered question, not an oversight to silently patch here.

## Post-review amendment #2 (2026-07-24 — SS-009 shipped same day)

SS-009 (Error Monitoring & Analytics Instrumentation) was parked at the time of this ticket's original Architect pass; it has since run its full pipeline and merged (PR #20). Its real primitives — `mobile/lib/sentry.ts` (`captureException`, `setSentryUserContext`), `mobile/lib/analytics.ts`/`hooks/useAnalytics.ts` (`useAnalytics().track()`), and `constants/analyticsEvents.ts` (13 typed events, including `item_uploaded` and `first_item_added`) — now exist and are wired into `app/_layout.tsx`/`hooks/useAuth.ts` already. This ticket's design is updated (see "Monitoring & analytics wiring" under Concrete values, plus the corresponding Edge Cases/Test Plan updates above) to actually call into them rather than ship blind:

- `useUploadWardrobeItem()` now `Sentry.captureException`s terminal upload failures (tagged `feature: 'wardrobe_upload'`).
- It fires `item_uploaded` on every successful upload, and additionally `first_item_added` when the pre-upload wardrobe count was 0 — populating the second step of SS-009's own PostHog funnel (`register → first_item_added → ...`), which SS-009 shipped able to define but not populate.
- No new files added by this amendment — `wardrobe.queries.ts`'s scope (already listed under Files to create/modify) absorbs this wiring; no change to `wardrobe.service.ts`'s pure-API-layer boundary.
- This doesn't touch or resolve `BL-049` (10 of 13 analytics events still have no call site) directly as a backlog *closure* — that row should be updated to reflect `item_uploaded`/`first_item_added` now having real call sites once this ticket's Developer phase actually lands the code, not at design time.

## Risk: high

Justification: even though this ticket touches no DB schema/migration and no payments, it directly implements (a) a JWT-authenticated endpoint gating a real (if soft) business limit, (b) a presigned-URL generation flow that hands a signed, time-boxed write capability to an external cloud storage service, and (c) wiring for real external cloud credentials (R2 access/secret keys) — squarely inside CLAUDE.md's/`OPERATOR_RULEBOOK.md` §C2's "auth, secrets, external-facing" high-risk bucket, and the per-ticket prompt for this run explicitly called out the same reasoning. Per the rubric, when auth+secrets+external-facing surface all co-occur, classify up rather than down even though nothing here is literally a schema/payments change — full lane, every gate preserved.
