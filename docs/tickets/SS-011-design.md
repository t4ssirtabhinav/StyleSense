# SS-011 — Background Removal Pipeline (Replicate BRIA-RMBG) — Design

## Scope restatement

This ticket builds the first real (costed, external-facing) FastAPI endpoint in the backend: `POST /wardrobe/remove-bg`, which takes an uploaded wardrobe photo (already sitting in R2 per SS-010) through background removal via Replicate's BRIA-RMBG model, generates a 300px thumbnail, writes both back to R2, and updates the item's `wardrobe_items` row — all behind a real per-user daily rate limit (20/day free, unlimited premium) and a circuit breaker that protects against a Replicate outage. Because SS-010 deliberately created no `wardrobe_items` row (upload is R2-only), and because `category` is `NOT NULL` with no default, **this ticket is also the one that first creates the row** and therefore owns the schema fix (`BL-040`) that makes that possible. It is also the first ticket to attach real money (Replicate's $0.0023/run) and a real per-user quota to a FastAPI endpoint, which — combined with the fact that no real JWT verification exists anywhere in this backend yet (`BL-033`) — means this ticket also builds the first real JWT-verification dependency, rather than reusing SS-006's explicitly-non-production stub. Mobile UI (upload triggering this call, "processing" shimmer, low-confidence warning) is explicitly out of scope — that's SS-013.

## Files to create/modify

**Supabase migration:**
- `supabase/migrations/005_wardrobe_processing_status.sql` — new. Drops `wardrobe_items.category`'s `NOT NULL`, adds `processing_status` (new enum), enables Realtime on `wardrobe_items`. Resolves `BL-040`. See Concrete values for exact SQL.
- `mobile/types/supabase.ts` — regenerate (not hand-write) via `supabase gen types typescript --project-id mefpfykuinasgkpfhmzk --schema public > mobile/types/supabase.ts` (exact command per `docs/tickets/SS-002-design.md`'s precedent), after the migration is applied.

**Backend — ports & adapters (hexagonal, per CLAUDE.md):**
- `backend/ai/ports/interfaces.py` — modify. Add `BackgroundRemovalResult` (dataclass — binary payload, not a natural fit for a JSON-shaped Pydantic model like the file's existing `StylePreferencesInput` etc.) and `IBackgroundRemovalProvider(ABC)`. New port, distinct from the not-yet-created `IVisionProvider` (that's SS-012's — Gemini tagging, image→structured-tags; this is image→image, a different capability). Never modify `IStylingProvider`.
- `backend/ai/adapters/replicate_bg_removal_adapter.py` — new. `ReplicateBgRemovalAdapter(IBackgroundRemovalProvider)`, wraps the `replicate` Python SDK (already in `requirements.txt` — `replicate==1.0.7`, no new install needed).

**Backend — DB & storage adapters:**
- `backend/adapters/interfaces.py` — new. `IWardrobeRepository(ABC)`. Placement note: CLAUDE.md's one-line description of `adapters/` names DB access specifically ("WardrobeRepository / IWardrobeRepository"); R2 object storage access doesn't fit either `ai/` or a DB-repository description literally, but is the same *kind* of thing (an adapter to an external system, just cloud storage instead of Postgres) — flagging this placement call explicitly rather than silently inventing a new top-level folder.
- `backend/adapters/wardrobe_repository.py` — new. `SupabaseWardrobeRepository(IWardrobeRepository)` — every method takes the caller's raw bearer token and constructs an RLS-scoped Supabase client per call (never `service_role`), so Postgres's own `user_owns_wardrobe` RLS policy (`auth.uid() = user_id`) is a real defense-in-depth backstop against an application-layer bug passing the wrong `user_id`.
- `backend/adapters/r2_storage.py` — new. Thin `boto3` S3-compatible client wrapper: `get_object_bytes(key) -> bytes`, `put_object_bytes(key, data, content_type) -> None`. This is a **direct, non-presigned** server-side write using the real `CLOUDFLARE_R2_ACCESS_KEY`/`SECRET_KEY` (the backend holds real credentials, unlike the mobile client) — entirely separate from SS-010's presigned-URL mechanism, so `BL-051`'s R2-presigned-POST-not-supported finding does **not** apply here.

**Backend — services (single-responsibility, per CLAUDE.md):**
- `backend/services/image_processing.py` — new/**amended post-QA (2026-07-25)**. Pure Pillow helpers: `generate_thumbnail(image_bytes, width=300) -> bytes` (JPEG), `looks_already_transparent_or_white(original_bytes) -> bool` (corner-pixel heuristic, pre-Replicate cost-saving check), `foreground_ratio(clean_png_bytes) -> float` (post-Replicate low-confidence heuristic, see Edge cases). **New, added post-QA**: `resize_for_bg_removal(original_bytes, max_width=800) -> bytes` and `apply_alpha_mask_to_original(original_bytes, low_res_rgba_bytes) -> bytes` — see "Image sizing strategy for the Replicate call" below.
- `backend/services/circuit_breaker.py` — new. `CircuitBreaker` — Redis-backed (Upstash REST via `httpx`, same mechanism as the existing `RateLimiter`), global (not per-user) `consecutive_failures` counter + `open_until` timestamp.
- `backend/services/rate_limiter.py` — modify. Add `DailyRateLimiter` alongside the existing `RateLimiter` (kept separate — different reset semantics, see Concrete values; existing class untouched).
- `backend/services/wardrobe_bg_removal_service.py` — new. `WardrobeBgRemovalService` — constructor-injected `IBackgroundRemovalProvider`, `IWardrobeRepository`, R2 storage client, `CircuitBreaker`; owns the full pipeline orchestration (see Concrete values) plus an in-process `asyncio.Semaphore` capping concurrent Replicate calls.

**Backend — shared auth (new folder, per SS-006's own forward note):**
- `backend/dependencies/__init__.py` — new.
- `backend/dependencies/auth.py` — new. `get_current_user_id` — **real** JWT verification via `supabase-py`'s `auth.get_user(token)` (calls Supabase's hosted Auth API to validate the token's signature server-side), replacing the pattern of SS-006's explicitly-non-production `get_current_user_id_stub`. Resolves `BL-033`. `backend/routers/outfit_suggestions.py`'s stub is **not** touched by this ticket (see Open questions).

**Backend — router:**
- `backend/routers/wardrobe.py` — new. `POST /wardrobe/remove-bg`.
- `backend/main.py` — modify. `app.include_router(wardrobe.router)`.

**Backend — no new dependencies.** `requirements.txt` already has everything needed: `replicate==1.0.7`, `boto3==1.43.40`, `pillow==12.3.0`, `redis==8.0.1` (unused directly — Upstash access stays REST/`httpx`, per the existing `RateLimiter`'s established pattern), `supabase==2.31.0`, `httpx==0.28.1`. Confirmed by reading the file directly — no `pip install` / `requirements.txt` edit needed.

**Tests:**
- `backend/tests/test_ai_ports.py` — modify. Add `IBackgroundRemovalProvider` ABC-enforcement test.
- `backend/tests/test_replicate_bg_removal_adapter.py` — new.
- `backend/tests/test_image_processing.py` — new.
- `backend/tests/test_circuit_breaker.py` — new.
- `backend/tests/test_rate_limiter.py` — modify. Add `DailyRateLimiter` tests.
- `backend/tests/test_wardrobe_repository.py` — new.
- `backend/tests/test_r2_storage.py` — new.
- `backend/tests/test_auth_dependency.py` — new.
- `backend/tests/test_wardrobe_bg_removal_service.py` — new.
- `backend/tests/test_wardrobe_router.py` — new.

## Concrete values to use, not invent

Transcribed verbatim from `docs/tickets/raw/SS-011.md`:
- Replicate model reference: `bria-rmbg` (exact current Replicate model slug/version **not verified this session** — no WebFetch tool available; label per `docs/OPERATOR_RULEBOOK.md` §E. Developer must confirm the exact `owner/model[:version]` string against Replicate's current model page before the first real call — the ticket's own text only gives the informal name).
- Cost: `$0.0023` per run — logged verbatim on every real (non-skipped) Replicate call.
- Free tier: 20 BG removals/day; unlimited for `premium`/`premium_annual` (same `users.plan_tier` enum SS-010 reads).
- Rate-limit key: **exactly** `bg_remove:{user_id}:{date}` (ticket's own literal format — do not add the existing `RateLimiter`'s `stylesense:outfit_suggestions:rate_limit` -style prefix; this is a different, ticket-pinned key). `{date}` = IST calendar date, `YYYY-MM-DD`.
- Circuit breaker: opens after 3 consecutive Replicate failures; auto-closes after 60 seconds.
- Thumbnail: 300px width, stored at a `/thumbnail.jpg`-suffixed key (JPEG).
- Clean image: `clean.png` (PNG — must preserve the alpha channel BRIA-RMBG produces).
- Target latency: **renegotiated post-QA (2026-07-25) against real measured data, not the raw ticket's original figures.** The raw ticket's "<10s worst case, <4s average" was written without access to real Replicate timing. Live testing against two real clothing photos (not synthetic test data) found: raw uncompressed originals (2340px) took 28-56s; SS-010's 1200px-compressed originals took 10.1-10.8s on two runs and 4.1s on a third (same width, same image) — a >2.5x spread with no code/input change, indicating Replicate-side cold-start/queue variance dominates over pure pixel count within the "already reasonably sized" range. **Revised target: typical case 4-8s, acceptable worst case up to ~15s to accommodate a genuine Replicate cold start** (matches the ticket's own "cold start after 30+s idle" edge case) — a hard "<10s always" ceiling is not realistic given observed Replicate-side variance outside this pipeline's control. See "Image sizing strategy for the Replicate call" below for the mitigation actually applied (smaller proxy image), and the real before/after data table.
- Log fields per real Replicate call: `user_id`, `cost` (`$0.0023`), `latency_ms` — `logger.info("ai_call", extra={"user_id": ..., "cost_usd": 0.0023, "latency_ms": ...})`, mirroring CLAUDE.md's "Log all AI calls" convention (this ticket logs `cost_usd` in place of `tokens_used`, since Replicate is billed per-run, not per-token).

Reconciled with the existing schema / SS-010's hand-off contract:
- **`id` continuity (SS-010's hand-off contract, honored here):** this ticket is the first to actually insert a `wardrobe_items` row. The row's `id` is set to the client-supplied `item_id` (the same UUID SS-010's `get-upload-url` Edge Function returned), **overriding** the column's `DEFAULT gen_random_uuid()` — exactly as SS-010's design doc specified. Enforced via `INSERT ... (id, user_id, image_url, category, processing_status) VALUES (...) ON CONFLICT (id) DO NOTHING` (idempotent — a client retry of the same `remove-bg` call is safe).
- **Row-creation timing (resolves the open half of `BL-040`):** the row is created **synchronously inside the route handler**, immediately after auth + rate-limit checks pass and *before* the `202` response is returned — not inside the background task. Rationale: a client that immediately subscribes to Supabase Realtime on `id=eq.{item_id}` right after getting `202` should find the row already exists; deferring creation into the (unawaited) background task risks a client racing ahead of row-creation. The *heavy* work (Replicate call, R2 writes, subsequent `UPDATE`s) still happens in `background_tasks.add_task(...)`, per CLAUDE.md's "never call AI APIs synchronously."
- **`processing_status` enum (new, resolves `BL-040`):**
  ```sql
  CREATE TYPE wardrobe_processing_status AS ENUM (
    'uploaded',       -- row created, BG removal not yet started
    'bg_processing',  -- BG-removal pipeline actively running
    'bg_removed',     -- success — image_clean_url/thumbnail_url set
    'bg_pending'      -- failed or circuit-open fallback; original image_url
                       -- remains the usable fallback; eligible for retry via
                       -- the same POST /wardrobe/remove-bg call (idempotent
                       -- upsert above makes re-invocation safe)
  );
  ```
  `bg_pending` is spelled exactly as the ticket's own AC wording ("flagged `bg_pending` for retry") — it means **failed-needs-retry**, not "not yet attempted" (that's `uploaded`). **Note for SS-012's Architect phase:** extend this enum additively (`ALTER TYPE wardrobe_processing_status ADD VALUE '...'`) for tagging-stage states (e.g. `tag_processing`/`complete`) rather than repurposing an existing value or creating a second status column.
- **`category` becomes nullable** (`ALTER TABLE wardrobe_items ALTER COLUMN category DROP NOT NULL`) — required because this ticket's row-creation happens before AI tagging (SS-012) assigns a category.
- **Full migration** (`supabase/migrations/005_wardrobe_processing_status.sql`):
  ```sql
  CREATE TYPE wardrobe_processing_status AS ENUM (
    'uploaded', 'bg_processing', 'bg_removed', 'bg_pending'
  );

  ALTER TABLE wardrobe_items ALTER COLUMN category DROP NOT NULL;

  ALTER TABLE wardrobe_items
    ADD COLUMN processing_status wardrobe_processing_status NOT NULL DEFAULT 'uploaded';

  -- Required for this ticket's own "notify via Supabase Realtime when done"
  -- Technical Note: a client subscribed to postgres_changes on this table
  -- only receives events if the table is in the realtime publication.
  -- [trained-knowledge, not verified this session]: assumes a
  -- `supabase_realtime` publication already exists on this project (Supabase
  -- creates one by default the first time Realtime is enabled via
  -- dashboard/CLI). If this statement errors with "publication does not
  -- exist," first run `CREATE PUBLICATION supabase_realtime;` (or check
  -- Supabase Studio -> Database -> Replication) before re-running.
  ALTER PUBLICATION supabase_realtime ADD TABLE wardrobe_items;
  ```
- **R2 key convention (extends SS-010's `wardrobe/{user_id}/{item_id}/original.jpg` pattern):**
  - Clean image: `wardrobe/{user_id}/{item_id}/clean.png`
  - Thumbnail: `wardrobe/{user_id}/{item_id}/thumbnail.jpg`
- **Read-path "shape" decision (partial resolution of `BL-046` — the *value shape*, not the full read-path architecture, per this ticket's own instructions):** `image_url` (this ticket is also the first to ever populate this column), `image_clean_url`, and `thumbnail_url` are all written as **bare R2 object keys** (e.g. `wardrobe/{user_id}/{item_id}/clean.png`), **not** full URLs and **not** presigned GET URLs (which would expire and go stale sitting in the DB). This is a deliberate mismatch against the column's own SQL comment ("-- Original R2 URL" / "-- BG-removed R2 URL") — flagged loudly here rather than silently: whichever ticket builds the real read path (still `BL-046`, likely SS-014) must generate a signed GET URL from this key at render time, not read the column directly as a renderable URL.
- **`ai_tags` JSONB namespacing (new coordination contract for SS-012):** this ticket writes only under a nested `ai_tags.bg_removal` key — `{"bg_removal": {"source": "replicate" | "skipped_already_transparent", "low_confidence": bool, "latency_ms": int}}` — never overwriting the whole `ai_tags` blob. SS-012's Architect phase must do the same (write under its own key, e.g. `ai_tags.tagging`, not blind-overwrite) — logged as `BL-053` (see Backlog deltas) so this isn't silently assumed.
- **Plan-tier check** — reuses SS-010's exact pattern: `select plan_tier from users` via the RLS-scoped client (implicitly filtered to the caller's own row by `user_owns_profile` RLS), read inside `SupabaseWardrobeRepository.get_plan_tier(user_id, jwt)`.

**Real JWT verification (`backend/dependencies/auth.py`, resolves `BL-033`):**
```python
async def get_current_user_id(authorization: str | None = Header(default=None)) -> str:
    # ... 401 on missing/malformed header, same shape as SS-006's stub ...
    token = ...
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])
    try:
        response = client.auth.get_user(token)  # validates against Supabase's Auth API
    except Exception as exc:
        raise HTTPException(401, "Invalid or expired token") from exc
    user = getattr(response, "user", None)
    if user is None or not getattr(user, "id", None):
        raise HTTPException(401, "Token did not resolve to a valid user")
    return str(user.id)
```
**[trained-knowledge, not verified this session]** — `supabase-py==2.31.0`'s exact `auth.get_user(jwt)` call shape (sync vs. async, exact exception type on an invalid token) is asserted from general familiarity with the Supabase Python client's documented pattern for server-side token verification, not confirmed against this session's installed version (no WebFetch tool available). **Developer must confirm this against the installed `supabase-py` version's actual API before relying on it** — this is the load-bearing security boundary for a real-money endpoint, so "should work" is not sufficient; if the call shape differs, adjust accordingly and note what was actually observed (per `docs/OPERATOR_RULEBOOK.md`'s "verify, don't recite"). `SupabaseWardrobeRepository`'s DB calls use the same pattern (RLS-scoped client per caller token), not `service_role`.

**Daily rate limiter (`DailyRateLimiter`, new class in `services/rate_limiter.py`):**
- `check_and_increment(user_id: str, *, skip: bool) -> bool` — `skip=True` (premium/premium_annual) returns `True` immediately, no Redis call at all (mirrors SS-010's "skip the check entirely for premium" convention).
- Key: `bg_remove:{user_id}:{ist_date}` (exact ticket format, see above).
- TTL: computed as **exact seconds remaining until next IST midnight** (`datetime.now(ZoneInfo("Asia/Kolkata"))` → next `00:00` IST), set via `EXPIRE ... NX` (same idempotent-NX pattern as the existing `RateLimiter`, SS-018's fix) — this, combined with the IST-date-in-key, is what makes "resets at IST midnight, not UTC" literally true rather than an approximate rolling window.
- **Fails closed by default** (`fail_open=False`) on Redis-unavailable, matching the existing `RateLimiter`'s SS-018-established convention for a real, costed gate — this directly protects real money exposure, unlike the circuit breaker below.

**Circuit breaker (`CircuitBreaker`, new, Redis-backed via the same Upstash REST/`httpx` mechanism):**
- Global (not per-user) keys: `stylesense:bg_removal_circuit:consecutive_failures`, `stylesense:bg_removal_circuit:open_until` (Architect's own reasonable choice — the ticket doesn't specify key names or per-user vs. global scope; global is the natural read of "3 consecutive Replicate calls fail," since this is meant to detect a systemic Replicate outage, not one user's problem).
- `is_open() -> bool`: `now < open_until`. If open, the service skips calling Replicate entirely and goes straight to the `bg_pending` fallback path (no wasted call, no cost).
- On a real Replicate call: success resets `consecutive_failures` to 0; failure increments it, and reaching 3 sets `open_until = now + 60s`.
- **Fails "closed-circuit" (i.e., proceeds with the Replicate call) on Redis-unavailable** — the opposite default from the daily rate limiter, deliberately: this is a resilience/UX optimization, not a security or money-gating boundary (a missed circuit-open decision costs at most a few wasted $0.0023 calls; blocking *all* BG removal because Upstash briefly hiccuped would be a worse trade). Flagged explicitly since it's the opposite fail-mode from the rate limiter in the same file, for the same reason CLAUDE.md's "risk-weight effort" applies differently to a cost-gate vs. a resilience heuristic.

**Concurrency control (server-side, addresses the ticket's own "batch of 10, queue sequentially" edge case):**
- `WardrobeBgRemovalService` wraps each Replicate call in an `asyncio.Semaphore(3)` (Architect's own reasonable default — ticket doesn't pin a number), so the backend itself never fires more than 3 concurrent Replicate calls regardless of how many `remove-bg` requests a client batch fires in parallel. **Known limitation, flagged, not fixed here:** this is in-process state — correct for today's single-`uvicorn`-process reality, but would not coordinate across multiple worker processes/instances if this backend is ever deployed with >1 worker (compounds with `BL-037`, no deployment exists yet at all).

**Pre/post-processing heuristics (`services/image_processing.py`, Architect's own reasonable choices — not ticket-pinned numbers):**
- `looks_already_transparent_or_white`: samples the 4 corner pixels; if each is either near-white (`R,G,B > 245`) or near-transparent (alpha `< 10`, if the source has an alpha channel), skips the Replicate call entirely (cost saving, per the ticket's own edge case) and treats the original image bytes as the "clean" result directly. Approximate by design (a patterned background near the corners could false-negative into calling Replicate anyway) — acceptable, since getting this wrong just means one extra $0.0023 call, not a correctness or security issue.
- `foreground_ratio`: after a real Replicate call, computes the fraction of pixels with alpha `> 10` in the resulting PNG; if `< 0.03` (i.e., BRIA-RMBG kept almost nothing as foreground), sets `ai_tags.bg_removal.low_confidence = true`. This is this ticket's answer to the raw ticket's "non-clothing image... add a confidence check" edge case — BRIA-RMBG itself returns no classification/confidence score, so this is a proxy, not a real content classifier (SS-012's Gemini-based `confidence` field is the real one, a different signal for a different pipeline stage). **Actually surfacing a user-facing warning from this flag is out of this backend-only ticket's scope — that's SS-013's job**, flagged in Open questions.

## Image sizing strategy for the Replicate call (added post-QA, 2026-07-25)

**Why this exists:** QA's original live-verification measured 4-5s latency, but against a synthetic 100×100 solid-color test image — not representative. User-directed re-testing against two real clothing photos (compressed to SS-010's actual 1200px-width upload spec) measured 10.1-10.8s, over the ticket's original 10s ceiling. Further empirical testing (see table below) showed smaller input is *somewhat* faster but the relationship is noisy — cold-start/queue variance on Replicate's side is a bigger factor than pure pixel count within the already-reasonably-sized range. User decision: keep SS-010's 1200px original untouched in R2 (other tickets — SS-012 tagging, SS-014 display — may want that resolution), but generate a **separate, smaller in-memory proxy specifically for the Replicate call**, then composite the returned (lower-resolution) alpha mask back onto the full-resolution original so the final stored `clean.png` doesn't lose quality.

**Real latency data gathered (same `test2` photo throughout, spaced calls to avoid the account's rate limit — see Open questions):**

| Input | File size | Latency |
|---|---|---|
| Raw original (2340px) | ~775KB | 28-56s (one transient failure + retry) |
| 1200px (SS-010 upload spec) | ~290KB | 10.8s, 10.1s, 4.1s (three separate runs, same input) |
| 1000px | ~215KB | 6.1s |
| 800px | ~142KB | 6.5s |
| 500px | ~64KB | 4.4s |

**Design:**
1. `resize_for_bg_removal(original_bytes, max_width=800) -> bytes` — resizes the (already 1200px) original down to 800px width, JPEG-encodes, **in memory only** — never written to R2. 800px chosen as a middle point in the observed data (500px is fastest but starts trading away detail BRIA-RMBG needs for clean edges on fine garment patterns like embroidery; 800px keeps a visible latency improvement over 1200px without going as aggressive as 500px). Flagged as an Architect's reasoned choice from a small sample, not a guaranteed-optimal number — worth revisiting once real production traffic gives a bigger sample.
2. `WardrobeBgRemovalService.process()` calls `self._provider.remove_background(proxy_bytes)` (the 800px proxy), **not** `original_bytes` directly.
3. On success, `apply_alpha_mask_to_original(original_bytes, result.image_bytes) -> bytes`: extracts the alpha channel from Replicate's (800px-resolution) RGBA output, upscales that alpha channel back to the original's full resolution (1200px width) using `Image.Resampling.LANCZOS`, and composites it onto the full-resolution original's RGB — producing a full-quality `clean.png` at the original's resolution despite the Replicate call itself having processed a smaller image. **Tradeoff, stated plainly:** the upscaled alpha mask's edges are marginally softer than a native full-resolution mask would produce (no free lunch — this trades a small amount of edge precision for a real, measured latency improvement). Acceptable for a v1; revisit if edge quality complaints surface.
4. `looks_already_transparent_or_white` (the pre-check) continues to run against the full-resolution `original_bytes`, unchanged — it's cheap (4 corner pixels) regardless of resolution.
5. `foreground_ratio`/`is_low_confidence` runs against Replicate's raw (800px) output, before compositing — the ratio is scale-invariant, so this is equivalent to running it post-composite but cheaper.

**What this does NOT fully solve:** per the data table above, resolution is not the dominant source of variance — a 1200px input ranged from 4.1s to 10.8s with no change at all. The 800px proxy should shift the *typical* case faster (roughly in the 4-7s band based on the 800px/1000px/500px data points), but a genuine Replicate cold-start can still push any single call well past 10s regardless of input size. This is why the AC itself was renegotiated above rather than treating this proxy change as a complete fix.

## Edge cases

Carried forward from the ticket, plus new ones surfaced while designing:

- Non-clothing image: handled via the `foreground_ratio` proxy above, not a real classifier — flagged as approximate.
- Replicate cold start (30+s idle): the background task has no hard timeout in this design (matching the ticket's "process async" framing) — a slow first call just takes longer before the Realtime update lands; no user-facing "patience message" exists yet since that's mobile-side (SS-013) scope.
- Already-transparent/white background: skipped via the corner-pixel heuristic, cost saved, `ai_tags.bg_removal.source = "skipped_already_transparent"`.
- Batch of 10: bounded server-side via the `asyncio.Semaphore(3)` regardless of client behavior.
- Replicate call fails (not yet 3-in-a-row): retried? **No** — this design does not retry a single failed call automatically within one request; it counts toward the circuit breaker and the item is marked `bg_pending` immediately. A "retry" is the client re-invoking `POST /wardrobe/remove-bg` for the same `item_id` later (idempotent upsert makes this safe). Ticket's own AC ("flagged `bg_pending` for retry") supports this — it describes a flag for a *future* retry, not an automatic in-request retry loop.
- Circuit open when a request arrives: skipped straight to `bg_pending`, `ai_tags.bg_removal.source = "circuit_open"`, no Replicate call attempted (no cost).
- Daily limit reached (free tier): `429` returned synchronously before any row creation or background task is queued — no partial state left behind.
- New edge case: **concurrent `remove-bg` calls for the same `item_id`** (e.g., a client double-tap or retry racing the original request) — the `INSERT ... ON CONFLICT (id) DO NOTHING` makes row creation idempotent; the two background tasks could still both call Replicate concurrently for the same item, wasting one call. Not fixed here (would need a per-item advisory lock) — acceptable low-probability, low-cost race, noted rather than silently ignored.
- New edge case: **Upstash unreachable.** Daily limiter fails closed (denies) — a user simply can't do a BG removal while Upstash is down, consistent with SS-018's established convention for a real cost gate. Circuit breaker fails "closed-circuit" (proceeds) — see Concrete values for why these two deliberately differ.
- New edge case: **R2 write fails after a successful Replicate call** (e.g., R2 transient error uploading `clean.png`/`thumbnail.jpg`). Treated as a pipeline failure — item marked `bg_pending` even though the Replicate call itself succeeded (the $0.0023 cost is still logged, since it was actually incurred) — not left in an inconsistent "processing forever" state.
- New edge case (mobile-facing gap, not fixed here): `foreground_ratio`'s `low_confidence` flag is written to `ai_tags` but nothing renders it to the user yet — flagged in Open questions for SS-013.
- New edge case (added post-QA, 2026-07-25): **the Replicate account is rate-limited to 6 requests/minute (burst of 1) while its balance is under $5.** Confirmed live via a real `429` response: `"Your rate limit for creating predictions is reduced to 6 requests per minute with a burst of 1 requests while you have less than $5.0 in credit."` This is a real operational constraint, not a code bug — at low balance, even the existing `asyncio.Semaphore(3)` concurrency cap could still exceed Replicate's own 6/min ceiling under bursty traffic (3 concurrent long-running calls could still submit new requests faster than 6/min if items complete quickly). Not fixed in this design (would need either maintaining a higher account balance or adding client-side request pacing beyond the existing semaphore) — flagged as `BL-059`, revisit once real traffic patterns are known or before assuming the concurrency cap alone is sufficient.

## Test plan

**`backend/tests/test_ai_ports.py`** (modify):
1. `IBackgroundRemovalProvider` cannot be instantiated directly (`TypeError`, enforces the ABC).

**`backend/tests/test_replicate_bg_removal_adapter.py`**:
1. Calls the `replicate` SDK with the configured model reference and the input image bytes.
2. On a successful call, returns a `BackgroundRemovalResult(success=True, image_bytes=..., latency_ms=...)`.
3. On the SDK raising, returns `success=False` rather than propagating the exception (caller — the service — decides retry/circuit-breaker policy, per the port's documented contract).

**`backend/tests/test_image_processing.py`**:
1. `generate_thumbnail` produces a JPEG with width 300 for a range of input aspect ratios.
2. `looks_already_transparent_or_white` returns `True` for a synthetic all-white image and `False` for a synthetic non-white image.
3. `looks_already_transparent_or_white` returns `True` for a synthetic image with fully-transparent corners (alpha channel present).
4. `foreground_ratio` returns a value `< 0.03` for a synthetic near-fully-transparent PNG and a value `> 0.03` for one with a large opaque region.
5. **New (post-QA):** `resize_for_bg_removal` produces an image with width exactly `max_width` (default 800) for an input wider than that, and leaves an already-narrower input unchanged (never upscales).
6. **New (post-QA):** `apply_alpha_mask_to_original` returns an RGBA image matching the *original's* dimensions (not the low-res input's), with alpha values sampled from the (upscaled) low-res mask — e.g. a low-res mask that's fully opaque in its center produces a corresponding fully-opaque region in the full-resolution output, scaled proportionally.

**`backend/tests/test_circuit_breaker.py`**:
1. `is_open()` is `False` initially (no failures recorded).
2. After 3 consecutive `record_failure()` calls, `is_open()` becomes `True`.
3. A `record_success()` call resets `consecutive_failures` to 0.
4. `is_open()` returns `False` (fails "closed-circuit," i.e., proceeds) when Upstash env vars are unset or the REST call errors.

**`backend/tests/test_rate_limiter.py`** (modify — add `DailyRateLimiter` cases):
1. `skip=True` (premium) returns `True` with zero HTTP calls made (no Redis round-trip at all).
2. Uses the exact key format `bg_remove:{user_id}:{ist_date}` (assert the constructed URL).
3. `EXPIRE` is called with the seconds remaining until next IST midnight, not a fixed 86400 (assert within a small tolerance around a mocked "now").
4. At `count == 20`, allowed; at `count == 21`, denied (boundary, matching the ticket's 20/day free cap).
5. Fails closed (denies) by default when Upstash env vars are unset.

**`backend/tests/test_wardrobe_repository.py`** (mocked `supabase-py` client):
1. `upsert_uploaded_row` issues an `INSERT` with `id` set to the caller-supplied `item_id` (not the column default), `category=None`, `processing_status='uploaded'`, and constructs the client scoped to the caller's JWT (not `service_role`).
2. A second `upsert_uploaded_row` call with the same `item_id` does not raise / does not duplicate (`ON CONFLICT DO NOTHING` semantics asserted via the mocked call args).
3. `update_bg_removal_result` merges `ai_tags` under the `bg_removal` key without clobbering pre-existing top-level keys (simulated pre-existing `ai_tags` value).
4. `get_plan_tier` issues a `select plan_tier from users` scoped to the caller's own JWT.

**`backend/tests/test_r2_storage.py`** (mocked `boto3` client):
1. `get_object_bytes` calls `get_object` with the exact bucket/key and returns the body bytes.
2. `put_object_bytes` calls `put_object` with the exact bucket/key/`ContentType`.

**`backend/tests/test_auth_dependency.py`**:
1. Missing `Authorization` header → `401`.
2. Malformed (non-`Bearer`) header → `401`.
3. A token that `auth.get_user` rejects (mocked to raise/return no user) → `401`.
4. A token `auth.get_user` resolves successfully → returns the resolved user's `id` as a string.

**`backend/tests/test_wardrobe_bg_removal_service.py`**:
1. Happy path: calls the provider once **with the downscaled proxy, not the full-resolution original** (post-QA amendment — assert the bytes passed to `provider.remove_background` are the `resize_for_bg_removal` output, not `original_bytes` verbatim), uploads a full-resolution `clean.png` (composited via `apply_alpha_mask_to_original`) + thumbnail to R2, updates the repository with `processing_status='bg_removed'` and both URLs (keys).
2. Already-transparent input: skips the provider call entirely (`source='skipped_already_transparent'`), still uploads a "clean" result and marks `bg_removed`.
3. Circuit open: skips the provider call, marks `processing_status='bg_pending'`, `source='circuit_open'`, no cost logged.
4. Provider failure (not yet 3rd consecutive): marks `bg_pending`, `record_failure()` called on the circuit breaker exactly once.
5. 3rd consecutive provider failure: circuit breaker's `open_until` gets set (verifies the service actually calls `record_failure()` enough times to open it, integration-style with a real `CircuitBreaker` instance backed by a fake Redis).
6. R2 upload failure after a successful provider call: marks `bg_pending`, but the `$0.0023` cost is still logged (the call did happen).
7. `asyncio.Semaphore(3)` caps concurrency: launching 10 concurrent `process()` calls against a slow fake provider never has more than 3 in flight simultaneously.
8. Successful real (non-skipped) call logs `user_id`, `cost_usd=0.0023`, `latency_ms` via `caplog`.

**`backend/tests/test_wardrobe_router.py`** (FastAPI `TestClient`):
1. Missing/invalid auth → `401` (via the real dependency, mocked `auth.get_user`).
2. Free user under the daily cap → `202 {"status": "processing", "item_id": ...}`, and the `wardrobe_items` row exists (mocked repository) before the response returns.
3. Free user at the daily cap → `429`, no row created, no background task queued (asserted via a spy on `background_tasks.add_task`).
4. Premium user beyond 20 calls that day → still `202` (rate limiter skipped).
5. `app.dependency_overrides[IBackgroundRemovalProvider]` swap works, mirroring SS-006's router-swappability test pattern.
6. Malformed `item_id` (not a valid UUID) → `422` (Pydantic validation, not a `500`).

**Not automatable this pass (manual/live verification):**
- A real end-to-end Replicate call against `bria-rmbg` returning an actual BG-removed PNG — **may now actually be achievable** (see Open questions — a real `REPLICATE_API_TOKEN` was just added).
- A real end-to-end `boto3` write of `clean.png`/`thumbnail.jpg` to the live `stylesense-media` R2 bucket — **also may now be achievable**, since SS-010's Developer phase already live-verified real `CLOUDFLARE_R2_*` credentials work against this bucket (`BL-051`).
- A real Supabase Realtime subscription actually receiving the `UPDATE` event after the migration's `ALTER PUBLICATION` — needs a live project + a subscribed client; not exercisable by an automated backend test.

## Open questions / blockers

1. **`REPLICATE_API_TOKEN` now has a real value (per this run's task briefing) — attempt a real live call, don't assume blocked.** The raw ticket's own Status note assumed this was still an empty placeholder and that "real end-to-end verification is blocked on account provisioning, not code" — that assumption is now stale. The Developer phase should actually try a real `replicate.run(...)` call against the real token (confirming the exact model slug/version first, per Concrete values) rather than defaulting to mocked-only testing.
2. **Real `CLOUDFLARE_R2_*` credentials also already exist and were live-verified** (`BL-051`, SS-010's Developer phase, 2026-07-24) — so this ticket's direct `boto3` R2 writes are *also* not credential-blocked, unlike SS-010's original framing. Attempt a real write to `stylesense-media` during Developer phase.
3. **`supabase-py`'s `auth.get_user()` call shape is unverified this session** (see Concrete values) — this is the load-bearing security check for a real-money endpoint. Developer must confirm the exact API against the installed `supabase==2.31.0` and note what was actually observed, not assume the sketch above is correct as written.
4. **`ALTER PUBLICATION supabase_realtime ADD TABLE wardrobe_items` assumes the `supabase_realtime` publication already exists** on this project — unverified this session (no WebFetch tool). If it errors, the migration needs a preceding `CREATE PUBLICATION supabase_realtime;` — flagged, not silently assumed.
5. **`outfit_suggestions.py`'s non-production JWT stub is untouched by this ticket.** Migrating it to the new real `backend/dependencies/auth.py::get_current_user_id` would retire the last unsafe stub in the codebase but is out of this ticket's scope (would require re-testing that router). Logged as `BL-052`.
6. **`low_confidence` flag has no UI consumer yet.** `ai_tags.bg_removal.low_confidence` is written but nothing surfaces a warning to the user — that's SS-013's job when it builds the upload/review screen.
7. **In-process semaphore/circuit-breaker-`open_until` check is single-instance-safe only** — compounds with `BL-037` (no deployment exists yet); revisit if/when this backend is ever run with >1 worker process.
8. **`BL-040` is resolved by this ticket's migration** (nullable `category` + `processing_status`). **`BL-041` is resolved by this ticket's explicit decision**: there is no combined `POST /wardrobe/items/process` orchestration endpoint — the mobile client (SS-013) is expected to call `POST /wardrobe/remove-bg` first (this is what creates the row) and SS-012's own tagging endpoint second, sequentially, against the same `item_id`. **SS-012's Architect phase must design its tagging endpoint to `UPDATE` an existing row (created here), never `INSERT`** — flagged here as a directive for that ticket, not built by this one.
9. **`BL-046` is partially addressed** (the *value shape* written to `image_url`/`image_clean_url`/`thumbnail_url` is now decided: bare R2 keys, not URLs) but the actual read-path mechanism (signed GET, CDN, TTL) is still undecided — remains Active for whichever ticket (likely SS-014) builds the read path.
10. **New `BL-053`**: `ai_tags` JSONB namespacing contract (`bg_removal` key, reserved for this ticket) — SS-012's Architect phase must honor this and use its own non-colliding key.
11. **New, post-QA (2026-07-25): `BL-056`** — no explicit timeout on the Replicate call, no durable/resumable tracking for in-flight `BackgroundTasks`. A server crash/restart mid-task silently strands the item at `processing_status='uploaded'` (never even reaches `bg_processing`), possibly after Replicate has already billed the run, with no automatic retry. Not fixed in this design pass — needs a dedicated follow-up (explicit timeout + a `bg_processing` status write before the call + either a durable queue or a periodic stuck-row sweep).
12. **New, post-QA: `BL-057`** — a photo with multiple garments (e.g. full-body shot, top + bottom) becomes exactly one tagged item; the non-dominant garment is never captured. User decision: accept for MVP, SS-013 should add UI copy encouraging one-item-per-photo.
13. **New, post-QA: `BL-058`** — real-photo latency (10-11s on SS-010's 1200px spec) exceeded the ticket's original AC; addressed by this amendment's proxy-image strategy + AC renegotiation (see "Image sizing strategy" above). Not fully closed — cold-start variance outside this pipeline's control remains, hence the renegotiated (not simply re-asserted) target.
14. **New, post-QA: `BL-059`** — the Replicate account is rate-limited to 6 req/min (burst 1) while balance is under $5 (confirmed live via a real `429`). The existing `asyncio.Semaphore(3)` concurrency cap doesn't guarantee staying under this — not addressed in this design pass.

## Backlog deltas

Moved to **Resolved** in `docs/BACKLOG.md`:
- `BL-040` (schema) — resolved by this ticket's migration (nullable `category` + `processing_status` enum column).
- `BL-041` (infra) — resolved by this ticket's explicit ownership decision (no combined endpoint; sequential client calls, `remove-bg` creates the row, SS-012 updates it).
- `BL-033` (auth) — resolved by this ticket's new real `backend/dependencies/auth.py::get_current_user_id` (via `supabase-py`'s `auth.get_user()`), replacing the need for any future router to reuse SS-006's non-production stub. Residual note: the exact `supabase-py` call shape is unverified this session (see Open questions #3) — Developer must confirm.

Added to **Active**:
- `BL-052` (auth) — `backend/routers/outfit_suggestions.py`'s non-production JWT stub should migrate to the new real `get_current_user_id` dependency this ticket introduces, retiring the last unsafe stub in the codebase. Not urgent (no real caller reaches that router yet).
- `BL-053` (ai/schema) — `wardrobe_items.ai_tags` JSONB namespacing contract: this ticket writes only under `ai_tags.bg_removal`; SS-012's Architect phase must use its own non-colliding key rather than overwriting the whole blob.

Clarifying notes appended (not resolved, not moved) to existing Active rows scanned this pass (tags `schema`/`infra`/`ai`):
- `BL-037` (infra, Railway/no deployment) — reaffirmed not a blocker for this ticket (same reasoning as SS-010's re-scan); additionally noted that this ticket's in-process semaphore/circuit-breaker state would need a distributed (Redis-based) rework if this backend is ever deployed with >1 worker process — compounds with this row, not a new one.
- `BL-046` (infra, read path) — updated with the "shape decided, mechanism still open" note (see Open questions #9).
- `BL-044` (ai, content moderation) — reconfirmed out of this ticket's scope, stays assigned to SS-012 as already decided.
- `BL-043`/`BL-045` (schema/infra) — scanned, not applicable to this ticket (cross-wardrobe image-hash dedupe and `get-upload-url` rate limiting are both unrelated to the BG-removal pipeline).

Added post-QA (2026-07-25), see Open questions #11-14 for full detail: `BL-056` (infra — no timeout/durable job tracking), `BL-057` (ai — multi-garment photos, accepted for MVP), `BL-058` (ai — real-photo latency exceeded AC, addressed by this amendment's proxy strategy + AC renegotiation, not fully closed), `BL-059` (infra — Replicate's own 6/min rate limit under $5 balance, not addressed by the existing semaphore).

## Risk: high

This ticket touches a DB schema migration (new enum type, `DROP NOT NULL`, new column, publication change — squarely CLAUDE.md's/`OPERATOR_RULEBOOK.md` §C2's schema/migration one-way-door bucket on its own), introduces the backend's first real JWT-verification dependency (auth), calls a real paid third-party API with per-call cost (money, external-facing), and writes real external cloud credentials into a direct server-side R2 write path (secrets, external-facing). Any one of these would already justify `high`; all four co-occurring makes this an easy, non-borderline call — full lane, every gate preserved.
