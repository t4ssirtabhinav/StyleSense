# SS-012 — AI Auto-Tagging with Gemini Vision (India Taxonomy) — Design

> **Amendment 1 — 2026-07-25 (post-live-research, orchestrator + user-approved).** Live web research (orchestrator) invalidated two core assumptions from the first pass and added three requirements. All four changes below are user-confirmed ("yes, let's go ahead"). Amended sections are tagged **(amended A1)** inline; unrelated sections are unchanged.
> 1. **Model + SDK are dead, not just unverified:** `gemini-1.5-flash` was shut down 2025-09-29, and the pinned `google-generativeai==0.8.6` SDK's support ended 2025-11-30 (Google's own repo says "deprecated, use the new unified Google GenAI SDK"). → Use model **`gemini-3.5-flash-lite`** via the **`google-genai`** SDK. `requirements.txt` now changes (still no DB migration).
> 2. **Explicit enforced timeout + bounded retry/backoff** added to the adapter (the SDK's own `HttpOptions.timeout` is confirmed unreliable — can hang past 60s; a partial call bills input tokens).
> 3. **Gemini paid-tier is a precondition** for processing real user photos (free tier trains on / human-reviews submitted images; wardrobe photos routinely contain faces → DPDP concern). Plus a new `contains_person` moderation signal, distinct from `content_flag`.
> 4. **Concurrent `ai_tags` read-merge-write race** is now an explicit documented Edge case (accept-and-reduce, same posture as `BL-036`).

## Scope restatement

This ticket adds the backend's first **vision** capability: a `POST /wardrobe/tag` endpoint that runs an already-uploaded wardrobe photo through **Gemini `gemini-3.5-flash-lite`** (amended A1) with an India-first fashion-taxonomy prompt, gets back structured tags (category, subcategory, primary/secondary colour, pattern, fabric, occasion tags, season tags, confidence), Pydantic-validates every enum-backed field against the real DB enums, and writes the result onto the existing `wardrobe_items` row — the same row SS-011's `POST /wardrobe/remove-bg` already creates. It follows the exact hexagonal shape SS-006/SS-011 established: a new `IVisionProvider` port (image → structured tags — distinct from `IStylingProvider` and `IBackgroundRemovalProvider`), a `GeminiVisionAdapter` behind it, a `WardrobeTaggingService` orchestrator, and a router that depends on the port via `Depends()`. It reuses SS-011's real `get_current_user_id` JWT dependency (`BL-052` directive) and RLS-scoped `SupabaseWardrobeRepository` pattern. It caches raw responses in Upstash Redis (`tag:{md5}`, 30-day TTL) and in `wardrobe_items.ai_tags` under its **own** `tagging` key (never clobbering SS-011's `ai_tags.bg_removal`, per `BL-053`). It is also where **content moderation** (`BL-044`, deferred from SS-010) gets its home — as prompt-based safety fields (`content_flag` + `contains_person`, amended A1) on the same Gemini pass, not a separate service. **Crucially, this ticket adds NO DB migration**: every output field maps to a column that already exists in `001_initial.sql`, and tagging state lives in the `ai_tags.tagging` JSON sub-key rather than extending the `processing_status` enum (reasoning below). Mobile UI (upload screen, "tagging…" shimmer, low-confidence review, top-2 disambiguation picker) is out of scope — that's SS-013.

## Files to create/modify

**Backend — ports & adapters (hexagonal, per CLAUDE.md):**
- `backend/ai/ports/interfaces.py` — **modify**. Add the tagging taxonomy `Literal`s (`WardrobeCategory`, `OccasionType`, `SeasonTag`, `ContentFlag`), the `GarmentTags` + `VisionTaggingResult` Pydantic models, and `IVisionProvider(ABC)`. This is the file's first **vision** port. **Never modify `IStylingProvider`, `IBackgroundRemovalProvider`, or their models.** See Concrete values for the exact model shape and enum values. `GarmentTags` includes both `content_flag` and the new `contains_person: bool` (amended A1).
- `backend/ai/adapters/gemini_vision_adapter.py` — **new**. `GeminiVisionAdapter(IVisionProvider)`, wraps the **`google-genai`** SDK (amended A1 — `from google import genai`, `genai.Client(api_key=...)`, `client.models.generate_content(model="gemini-3.5-flash-lite", contents=[...], config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=...))`). Forces JSON via `response_mime_type` (and ideally `response_schema` derived from `GarmentTags`), sends the India taxonomy prompt + image bytes, parses into `VisionTaggingResult`. **Owns an explicit enforced timeout + bounded retry (amended A1 — see "Timeout, retry & cost-safety" below).** **Never raises** — any SDK/network/safety-block/parse/timeout failure is caught and returned as `VisionTaggingResult(success=False, ...)` so the service owns fallback policy uniformly (mirrors `IBackgroundRemovalProvider`'s contract).

**Backend — services (single-responsibility, per CLAUDE.md):**
- `backend/services/wardrobe_tagging_service.py` — **new**. `WardrobeTaggingService` — constructor-injected `IVisionProvider`, `IWardrobeRepository`, `R2StorageClient`, `TagCache`, and a `GeminiRateLimiter`. Owns the full pipeline (fetch original from R2 → MD5 hash → cache lookup → **in-flight marker** (amended A1) → provider call under the rate gate → validate → cache store → repo `UPDATE`), all inside a `BackgroundTasks`-dispatched call. Logs the AI call (`user_id`, `latency_ms`, `model`) per CLAUDE.md's "Log all AI calls".
- `backend/services/gemini_rate_limiter.py` — **new**. In-process async token-bucket gate honouring Gemini's 15 RPM free-tier limit: `await acquire()` **blocks (queues)** until a token frees rather than rejecting — satisfies the AC's "excess queued, not dropped". Global (per-process, not per-user), since 15 RPM is a per-API-key limit. **Known limitation (flagged, same as SS-011's semaphore):** in-process state only — correct for today's single-`uvicorn`-process reality, needs a distributed (Redis) rework if ever deployed >1 worker (compounds `BL-037`). (Note: the user's own Gemini dashboard confirms the account's real limits are **15 RPM / 500K TPM / 500 RPD** — matching `gemini-3.5-flash-lite` on the free tier; trust that reading. 500 RPD is a second bound worth being aware of, though the per-user-cap gap `BL-062` already covers spend control.)
- `backend/services/tag_cache.py` — **new**. Thin Upstash REST wrapper (`httpx`, same mechanism as `RateLimiter`): `get(image_hash) -> dict | None`, `set(image_hash, payload)` with a 30-day TTL, and **(amended A1)** `mark_inflight(image_hash) -> bool` / `clear_inflight(image_hash)` — a short-TTL (~60s) `SET tag_inflight:{hash} NX` marker written *before* the Gemini call so a duplicate `/wardrobe/tag` for the same image within the window short-circuits instead of firing a second (cost-incurring) Gemini call. Key: result `tag:{md5_hex}`, in-flight `tag_inflight:{md5_hex}`. **Fails open** (returns `None` / no-op on any error or unset env) — a cache is an optimisation, not a gate, so a cache/marker miss must never block tagging (opposite posture from `DailyRateLimiter`, deliberately; the in-flight marker is a best-effort dedupe, not a hard lock).

**Backend — DB adapter (extend the existing port, per its own "add a new method" contract):**
- `backend/adapters/interfaces.py` — **modify**. Add one new abstract method `update_tagging_result(...)` to `IWardrobeRepository`. The port's own docstring sanctions "add a new method or a new adapter" — this is the sanctioned path, not a signature change to an existing method. **CI-breaking gotcha, must be handled:** adding an `@abstractmethod` to the ABC means every existing concrete subclass must implement it or fail to instantiate. See the two test fakes below.
- `backend/adapters/wardrobe_repository.py` — **modify**. Implement `update_tagging_result` on `SupabaseWardrobeRepository`: write the first-class columns (`category`, `subcategory`, `color_primary`, `color_secondary`, `pattern`, `fabric`, `occasion_tags`, `season_tags`) and **read-merge-write** `ai_tags` so `ai_tags.tagging` is set without clobbering `ai_tags.bg_removal` — the exact same read-then-`{**existing, "tagging": ...}` pattern the existing `update_bg_removal_result` uses for its own key. RLS-scoped client per caller JWT (never `service_role`), same as all other methods. **(amended A1) Known race:** this app-level read-merge-write shares `BL-036`'s concurrent-write class — see Edge cases / `BL-066`.

**Backend — router:**
- `backend/routers/wardrobe.py` — **modify** (add to SS-011's existing `/wardrobe` router, don't create a new file). Add `POST /wardrobe/tag`, plus the DI providers `get_vision_provider()` (port→`GeminiVisionAdapter` binding, overridable for tests), `get_tag_cache()`, `get_gemini_rate_limiter()`, and `get_tagging_service()`. **No `main.py` change** — `app.include_router(wardrobe.router)` already registered (SS-011).

**Backend — dependency change (amended A1 — the first pass said "no new dependencies"; that is now false, but there is still NO DB migration):**
- `backend/requirements.txt` — **modify**. **Add `google-genai`** (the current unified SDK). **Remove `google-generativeai==0.8.6` (line 24) and `google-ai-generativelanguage==0.6.15` (line 19)** — both belong to the deprecated old SDK. **Confirmed safe to remove:** a repo-wide grep (`generativeai|generativelanguage`) finds these two strings *only* in `requirements.txt` — no Python module in the backend imports the old SDK (the adapter doesn't exist yet). Developer must still re-confirm the grep after adding `google-genai` (pin whatever version `pip install` resolves) and **re-verify the exact installed `google-genai` call shape against the package source** before relying on the sketch above (same "verify, don't recite" discipline SS-011 applied to the Replicate slug — the orchestrator's summary is a starting point, not gospel). `httpx`, `supabase`, `pillow` remain already-present.

**Tests** (see Test plan for cases):
- `backend/tests/test_ai_ports.py` — **modify**. Add `IVisionProvider` ABC-enforcement + `VisionTaggingResult`/`GarmentTags` validation cases (incl. `contains_person`).
- `backend/tests/test_gemini_vision_adapter.py` — **new**. Includes timeout + retry-class cases (amended A1).
- `backend/tests/test_wardrobe_tagging_service.py` — **new**. Includes in-flight-marker dedupe + `contains_person` cases (amended A1).
- `backend/tests/test_gemini_rate_limiter.py` — **new**.
- `backend/tests/test_tag_cache.py` — **new**. Includes `mark_inflight`/`clear_inflight` cases (amended A1).
- `backend/tests/test_wardrobe_repository.py` — **modify**. Add `update_tagging_result` non-clobber case.
- `backend/tests/test_wardrobe_router.py` — **modify**. Add `POST /wardrobe/tag` cases.
- `backend/tests/test_wardrobe_bg_removal_service.py` — **modify (mechanical only)**. Its `_FakeRepository(IWardrobeRepository)` (line 69) must gain a stub `async def update_tagging_result(self, **kwargs) -> None: ...` or it will fail to instantiate against the extended ABC. Same for `_FakeRepository` in `test_wardrobe_router.py` (line 45). This is a required, no-behaviour-change edit — flag it loudly so it isn't missed (it's a green-locally/red-in-CI trap otherwise).

## Why no migration (and how this honours SS-011's directive)

SS-011's design doc left a conditional directive: *if* tagging tracks state in `processing_status`, extend that enum additively (`ALTER TYPE ... ADD VALUE`) rather than repurposing a value. This design chooses **not to track tagging in `processing_status` at all**, so no `ALTER TYPE` (and no migration) is needed. Reasoning:
1. **Every tagging output field already has a column** in `001_initial.sql`'s `wardrobe_items`: `category`, `subcategory`, `color_primary`, `color_secondary`, `pattern`, `fabric`, `occasion_tags occasion_type[]`, `season_tags TEXT[]`, `ai_tags JSONB DEFAULT '{}'`. Nothing to add.
2. **Bg-removal and tagging are two independent pipelines.** A single linear enum (`uploaded → bg_processing → bg_removed`) cannot cleanly represent the cross-product of "bg done / bg pending" × "tagging done / tagging pending" without a combinatorial blow-up. Two independent status signals is the correct model. `processing_status` stays owned by SS-011's bg-removal pipeline; tagging carries its own lightweight status in `ai_tags.tagging.status` (`"tagging" | "tagged" | "flagged" | "failed"`), a JSON sub-key — no schema change.
3. SS-011's directive is thereby satisfied to the letter: we neither repurpose an existing `processing_status` value **nor add a second status *column*** — we use a JSON sub-key, the lightest possible option.
4. **Client contract for SS-013 (document this):** an item is fully ready when `processing_status = 'bg_removed'` **and** `ai_tags.tagging.status = 'tagged'`. The client subscribes to `wardrobe_items` UPDATE on `id=eq.{item_id}` (SS-011's migration already added this table to the `supabase_realtime` publication — so tagging's `UPDATE` fires a Realtime event too, no migration needed) and combines the two signals.

Note (amended A1): the ticket still adds no DB migration, but it *does* now change `requirements.txt` (SDK swap) — the "no migration" property is what's load-bearing for the risk/schema reasoning, not "no dependency change."

## Endpoint contract (`POST /wardrobe/tag`)

- **Request:** `{ "item_id": "<uuid>" }` — a `TagRequest` Pydantic model reusing SS-011's `RemoveBgRequest` UUID `field_validator` pattern (malformed UUID → `422`, not `500`).
- **Auth:** `Depends(get_current_user_id)` (SS-011's real dependency — `BL-052`). Missing/invalid bearer → `401`.
- **Row must already exist.** The endpoint does a **synchronous existence check** (`SELECT id` on the RLS-scoped client) before dispatching: if no row for `item_id` exists, return **`404`** ("call `/wardrobe/remove-bg` first"). This honours `BL-041`'s directive literally (SS-012 only ever **UPDATE**s; it never `INSERT`s) and guards against the silent-0-row-`UPDATE` class of bug that bit this repo in `BL-029`. Per `BL-041`'s recorded client flow, `remove-bg` (which creates the row) is always called first, so this check passes in the normal path; it fails loudly only if a client skips the contract. (A future relaxation to decouple ordering via an idempotent upsert is noted in Open questions, not built.)
- **Dispatch:** heavy work (R2 read, Gemini call, DB write) goes to `background_tasks.add_task(service.tag, jwt=..., user_id=..., item_id=...)` — CLAUDE.md's "never call AI APIs synchronously." Return **`202 {"status": "processing", "item_id": ...}`** immediately, matching SS-011's `remove-bg` shape.
- **Which image is tagged:** `wardrobe/{user_id}/{item_id}/original.jpg` (SS-010's 1200px-compressed upload — always present, independent of whether bg-removal succeeded). Deliberately **not** `clean.png`, to decouple tagging from bg-removal success/timing. Trade-off (tagging the isolated garment might be marginally more accurate) noted in Open questions / `BL-063`.
- **No per-user rate limit / cost gate** (unlike `remove-bg`): the AC defines only the global 15 RPM Gemini constraint, not a per-user daily cap. Runaway cost is bounded by the global `GeminiRateLimiter` (and Gemini's own 500 RPD). Absence of a per-user cap is flagged as `BL-062` (money-adjacent), not silently assumed to be intended.

**Data flow (background task):**
1. Read `original.jpg` bytes from R2 (`asyncio.to_thread(storage.get_object_bytes, ...)` — `boto3` is sync, same offload pattern SS-011 uses). R2 read fails → mark `ai_tags.tagging.status='failed'`, return (no raise).
2. `image_hash = md5(original_bytes).hexdigest()`. Cache lookup `TagCache.get(image_hash)`. **Hit → skip Gemini entirely**, write the cached tags to the row (AC: "re-upload of the same image returns the cached result"), done.
3. Miss → `TagCache.mark_inflight(image_hash)` (amended A1). If a marker already exists (a concurrent/retry call is mid-flight for the same image), short-circuit without calling Gemini (avoids double-charging for the same image — see Edge cases). Else set the marker, then `await gemini_rate_limiter.acquire()` (queues if 15 RPM saturated), then `provider.tag_garment(original_bytes)`.
4. `result.success is False` (SDK error, safety block, timeout, or parse/validation failure) → `ai_tags.tagging.status='failed'`, no columns written, `clear_inflight`, log, return.
5. Success → `TagCache.set(image_hash, payload)` (30-day TTL) + `clear_inflight`; compute `flagged_for_review = confidence < 0.7` and `status = 'flagged' if (flagged_for_review or content_flag != 'ok' or contains_person) else 'tagged'`; `repository.update_tagging_result(...)` writes the columns + merges `ai_tags.tagging`. Log `ai_call` (`user_id`, `latency_ms`, `model`).
   - **(amended A1)** `clear_inflight` should also run in a `finally` so a crash between mark and clear just lets the ~60s TTL expire the marker — never a permanently-stuck marker.

## Timeout, retry & cost-safety (amended A1 — new section)

Live-verified constraints driving this: (a) `google-genai`'s `HttpOptions.timeout` defaults to `None` and has open SDK issues (`googleapis/python-genai` #911, #1330) where setting it doesn't reliably enforce a cutoff — a call can hang past 60s before the server drops it; (b) a request that partially processes before failing still **bills for input tokens** even if no output is returned (the "credit spent, no data received" case the user flagged from SS-011's `BL-056`); (c) a `503` is documented as *not* billed (server rejects before processing), so retrying a `503` specifically is cost-safe.

Adapter/service design:
- **Explicit enforced timeout at the call-site:** wrap the Gemini call in `asyncio.wait_for(..., timeout=<~30s>)` rather than relying on `HttpOptions.timeout` alone (the unreliable part). On timeout → `VisionTaggingResult(success=False, error="timeout")`, no raise; the service marks `status='failed'`.
- **Bounded retry with exponential backoff + jitter (small count, 2–3):** retry **only retryable classes** — `503`/transient network/connection errors — **not** `400`-class (bad request / malformed) or safety-block responses, where a retry just burns another attempt against the 15 RPM / 500 RPD budget for the same guaranteed failure. Each retry still passes through the shared `GeminiRateLimiter` so retries can't exceed the rate cap.
- **Residual, documented not fully closed:** a call that times out mid-processing has already incurred input-token cost, and `TagCache.set` only writes on success — so nothing caches a timed-out result. The **in-flight marker** (data-flow step 3) mitigates the *duplicate-call* cost (a user re-tapping `/wardrobe/tag` for the same item within ~60s no-ops instead of re-calling Gemini), but a retry *after* the marker's TTL still re-calls Gemini for that image. This is an accepted residual for MVP (bounded cost, `gemini-3.5-flash-lite` is a cheap model), not a new deferred row — it's inherent to "no output = nothing to cache," and the in-flight marker already covers the common double-tap case.

## Concrete values to use, not invent

**`wardrobe_category` — transcribed verbatim from `supabase/migrations/001_initial.sql` (lines 7–14), the source of truth. Note: the raw ticket says "20-value" — the actual enum has 21 values. Use all 21 exactly (the DB write will reject any non-member):**
```
western_top, western_bottom, western_dress, western_outerwear,
ethnic_kurta, ethnic_saree, ethnic_lehenga, ethnic_anarkali,
ethnic_salwar_kameez, ethnic_dupatta, ethnic_sherwani, indo_western,
footwear_formal, footwear_casual, footwear_ethnic, footwear_sports,
accessory_bag, accessory_jewellery, accessory_watch,
accessory_belt, accessory_scarf
```
The Pydantic `WardrobeCategory` is a `Literal[...]` of exactly these 21 strings, and `GarmentTags.category` is `WardrobeCategory | None` (nullable for the non-clothing edge case → `null` + `confidence: 0.0`).

**`occasion_type` — verbatim from `001_initial.sql` (lines 18–21). `occasion_tags` is a `list[OccasionType]`, and this IS a DB enum (`occasion_type[]` column), so validate strictly:**
```
office, casual, date_night, wedding_guest, festival, puja,
party, travel, workout, beach, formal_event, college
```

**`SeasonTag`** = `Literal["summer", "winter", "monsoon", "all"]` (`season_tags` column is `TEXT[]`, not a DB enum — validate against this closed set, drop unknowns rather than failing the whole result). India-first: `monsoon` is a first-class season.

**Colours:** `color_primary` / `color_secondary` as hex strings (e.g. `#RRGGBB`); prompt must instruct hex output. Stored in the `TEXT` columns as-is.

**`pattern` / `fabric` / `subcategory`:** stored as free `TEXT` in the DB, so validated only as `str` (not a hard `Literal`). The prompt supplies a guiding India-aware vocabulary (patterns: `solid, stripes, checks, floral, block_print, bandhani, ikat, paisley, polka_dots, embroidered, printed`; fabrics: `cotton, silk, linen, denim, wool, rayon, polyester, georgette, chiffon, khadi, chikankari`) but an out-of-vocab value must **not** nuke the whole result (risk-weighted: strict where the DB enforces an enum, lenient where it's free text). A canonical controlled vocabulary is a product/taxonomy decision → `BL-064`.

**Confidence threshold:** `confidence < 0.7` → `flagged_for_review = True` (AC). `confidence` is a `float` in `[0.0, 1.0]`.

**Moderation fields (resolves `BL-044`; amended A1 adds the second field):**
- `GarmentTags.content_flag: Literal["ok", "nsfw", "not_clothing", "other"]` — explicit-content / not-clothing classification.
- `GarmentTags.contains_person: bool` (amended A1) — **distinct** from `content_flag`: "is any identifiable person visible" (a mirror selfie is a normal, non-NSFW way to shoot an outfit). Kept separate so the app can nudge users toward flat-lay/mannequin shots independently of the NSFW check, and so this privacy-relevant signal isn't conflated with `content_flag`. Written into `ai_tags.tagging.moderation` alongside `content_flag`.

**Gemini specifics (amended A1 — model + SDK corrected):**
- Model: **`gemini-3.5-flash-lite`** (current GA; image input, structured JSON via `response_schema`/`response_mime_type`, 1M-token context, 64K max output — correctly sized). Replaces the shut-down `gemini-1.5-flash`. `VisionTaggingResult.model` default updated accordingly.
- SDK: **`google-genai`** (`from google import genai`; `client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])`; `client.models.generate_content(model=..., contents=[prompt, image_part], config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=<GarmentTags schema>))`). Replaces the deprecated `google-generativeai`. `[verify-against-installed-SDK]` — confirm the exact `contents=` image-part shape (bytes / `types.Part.from_bytes(mime_type=..., data=...)`), the `config` field names, and the response-text access path against the actually-installed `google-genai` source before relying on it. Image bytes are the `original.jpg` read from R2.
- Safety: rely on the model's own default safety filters as a free extra layer; the adapter must handle a blocked/empty-candidates response gracefully (→ `success=False`, never a raised exception).
- Cache: Upstash REST `SET ... EX 2592000` (30-day) for results + `SET ... EX ~60 NX` for the in-flight marker. `[verify-against-Upstash-docs]` — confirm the exact REST shape for `SET`/`GET`/`SETEX`/`SET NX` of a JSON body (same `BL-039`/`BL-035` precedent that bit the `RateLimiter`; don't assert from memory).

**`IVisionProvider` port shape (mirrors the file's existing ports):**
```python
class IVisionProvider(ABC):
    @abstractmethod
    async def tag_garment(self, image_bytes: bytes) -> VisionTaggingResult:
        """Must never raise -- any SDK/network/safety/parse/timeout failure is
        caught and returned as VisionTaggingResult(success=False, error=...) so
        the caller (WardrobeTaggingService) applies fallback policy uniformly."""
```
`VisionTaggingResult` is a Pydantic `BaseModel` (JSON-shaped, like `OutfitSuggestionResult` — unlike the binary `BackgroundRemovalResult` dataclass): `success: bool`, `tags: GarmentTags | None`, `latency_ms: int | None`, `model: str = "gemini-3.5-flash-lite"`, `source: Literal["gemini", "cache", "mock"] = "gemini"`, `error: str | None`. `GarmentTags` carries the AC's fields plus `content_flag`, `contains_person` (amended A1), and an optional `alternatives: list[WardrobeCategory]` (top-2 for the Indo-Western fusion edge case).

## Content moderation decision (`BL-044`)

**Decision: fold prompt-based moderation classification into the same Gemini pass** (`content_flag` + `contains_person` fields on the structured JSON), rather than standing up a separate moderation service or a second API call. Rationale:
- The vision model already sees every uploaded image — two extra JSON keys cost zero extra latency and zero extra API calls. This is the cheapest place in the whole pipeline to get a first-pass safety signal (exactly why `BL-044` was routed here from SS-010).
- **What action a flag triggers (MVP):** on `content_flag` ∈ {`nsfw`,`other`}, the service sets `category = None`, `status = 'flagged'`, and stores the flag in `ai_tags.tagging.moderation`; it does **not** hard-delete anything. `not_clothing` reuses the existing non-clothing path (null category, `confidence 0.0`). `contains_person = true` sets `status='flagged'` too (surfaced to SS-013 as a "try a flat-lay" nudge) but does **not** null a valid category — a garment in a selfie is still a real garment.
- **Scope boundary (flagged, not silently dropped):** this is a first-pass *signal*, not a compliance-grade moderation system, and it deploys **no enforcement/takedown pipeline**. Acceptable for MVP (no social exposure yet). Enforcement/action policy → new `BL-061` (Parked, Social epic). So `BL-044` is **Resolved** (a moderation signal now exists in-pipeline) with that residual explicitly carried forward.

## Edge cases

Carried forward from the ticket, plus new ones from the current codebase (amended A1 adds the last three):
- **Not clothing (food, pet):** `category = null`, `confidence = 0.0` (prompt-instructed); service writes null category, `status='flagged'`, no crash. Client (SS-013) shows "Doesn't look like clothing".
- **Ambiguous Indo-Western fusion:** `GarmentTags.alternatives` carries the top-2 category candidates; the primary `category` is the model's best pick. SS-013 renders a picker.
- **Accessories alongside clothing / multiple items in one photo:** prompt instructs "tag the single dominant/largest garment only" — consistent with `BL-057` (multi-garment accepted for MVP; SS-013 adds one-item-per-photo UI copy).
- **Saree vs. dupatta disambiguation:** prompt includes size/drape/context cues (a dupatta is a narrower accompanying drape; a saree is the primary 5–6 yard garment) — both distinct enum values.
- **Never suggest white for `wedding_guest`** (CLAUDE.md India rule): tagging *classifies*, it does not *suggest* outfits — this rule belongs to the styling path (`IStylingProvider`), not here. Noted so a reviewer doesn't expect it in this output.
- **Gemini returns an invalid enum value** (category not in the 21): Pydantic `ValidationError` in the adapter → adapter returns `success=False` (never raises); service marks `status='failed'` (retryable). A patterns/fabric out-of-vocab value does **not** fail (free `str`).
- **Gemini safety-blocks / empty candidates:** adapter catches, returns `success=False`; no unhandled background-task exception. Not retried (safety block is deterministic — see Timeout/retry section).
- **Cache hit (same image re-uploaded/re-tagged):** Gemini not called at all; cached tags written; `source='cache'`. Covers the AC directly.
- **15 RPM saturated (batch of many uploads):** `GeminiRateLimiter.acquire()` **awaits** (queues) rather than dropping — AC "excess queued, not dropped". Single-instance-safe only (`BL-037`).
- **Upstash unreachable:** `TagCache` (result cache + in-flight marker) fails **open** (treats as miss / no-op) — tagging still proceeds via a live Gemini call. Deliberately the opposite posture from `DailyRateLimiter`; the in-flight dedupe degrades to "no dedupe," not "blocked."
- **Row doesn't exist (tag called before remove-bg):** synchronous `404` before any background task is queued — no partial state, no silent 0-row update (`BL-029` precedent).
- **`GEMINI_API_KEY` unset:** adapter's live call fails → `success=False` → `status='failed'`; tests run fully against a fake provider (dependency-override), so the suite is green regardless. Live E2E blocked until a real key exists on the **paid tier** (see Open questions).
- **Server crash mid-background-task:** same durability gap as SS-011's `BL-056` — reaffirmed, not a new row.
- **(amended A1) Gemini call times out mid-processing:** adapter's `asyncio.wait_for` cutoff → `success=False`; input tokens may have been billed with no output cached (documented residual in Timeout/retry section). Duplicate user-retry within ~60s is deduped by the in-flight marker.
- **(amended A1) `contains_person = true`:** a real garment in a mirror-selfie is still tagged (valid category kept) but `status='flagged'` so SS-013 can nudge toward flat-lay/mannequin shots — a privacy/quality nudge, not a rejection.
- **(amended A1) Concurrent `/wardrobe/tag` (or tag racing bg-removal) read-merge-writing `ai_tags`:** two app-level read-merge-writes on the same `ai_tags` column can interleave and lose a key — the identical class as this repo's `BL-036` (onboarding prefs), which was documented-not-fixed. **Posture: accept-and-reduce, not block.** The **in-flight marker** collapses the common tag-vs-tag double-tap/retry case before it reaches the write; the residual concern is a tag write racing SS-011's `bg_removal` write (different keys, different pipelines) and clobbering the other's key — low-probability because the client flow is sequential (`remove-bg` then `tag`, per `BL-041`), so genuine concurrency is only a double-tap/retry edge. A durable fix (an atomic `jsonb_set` inside the `UPDATE`, which the PostgREST query builder can't express without an RPC/migration — deliberately avoided to preserve "no migration" — or optimistic-concurrency) is **deferred as new `BL-066`**, same accept-and-document reasoning `BL-036` used. Stated explicitly here rather than left as an unstated gap.

## Test plan

**`backend/tests/test_ai_ports.py`** (modify):
1. `IVisionProvider` cannot be instantiated directly (`TypeError`, ABC enforced).
2. `GarmentTags` rejects a `category` not in the 21-value enum (`ValidationError`).
3. `GarmentTags` accepts `category=None` with `confidence=0.0` (non-clothing path valid).
4. `GarmentTags` rejects an `occasion_tags` member outside the 12-value `occasion_type` set.
5. A fully-valid ethnic payload (`ethnic_kurta`, occasions `festival`/`puja`, `season_tags=["summer","all"]`, hex colours, `confidence=0.9`, `content_flag="ok"`, `contains_person=false`) parses cleanly.
6. (amended A1) `contains_person` is a required `bool` — a payload omitting it (or with a non-bool) fails validation.

**`backend/tests/test_gemini_vision_adapter.py`** (new, mocked `google-genai` client):
1. Calls the client with `model="gemini-3.5-flash-lite"` and `response_mime_type="application/json"`, passing both the taxonomy prompt and the image bytes.
2. A valid JSON response → populated `VisionTaggingResult(success=True, ...)` with category/occasions/confidence/`content_flag`/`contains_person` mapped through.
3. Malformed / non-JSON model output → `VisionTaggingResult(success=False)`, does not raise.
4. Out-of-enum category → `success=False` (Pydantic path), does not raise.
5. Safety-blocked / empty-candidates response → `success=False`, does not raise, **not retried**.
6. (amended A1) **Timeout:** a call exceeding the `asyncio.wait_for` cutoff → `success=False, error~="timeout"`, does not raise.
7. (amended A1) **Retry class:** a `503`/transient error is retried up to the bounded count (assert N attempts) then returns `success=False`; a `400`/bad-request is **not** retried (assert exactly 1 attempt).

**`backend/tests/test_wardrobe_tagging_service.py`** (new, fake provider/repo/cache/limiter):
1. Cache **hit**: returns cached tags, provider `tag_garment` **never called**, repo updated (`source='cache'`).
2. Cache **miss**: provider called once, in-flight marker set then cleared, `TagCache.set` invoked with a 30-day TTL, repo `update_tagging_result` called with the returned columns.
3. `confidence < 0.7`: `flagged_for_review=True`, `status='flagged'`.
4. Non-clothing (`category=None`, `confidence=0.0`): null category written, `status='flagged'`, no crash.
5. Moderation `content_flag='nsfw'`: `category` forced `None`, `status='flagged'`, flag stored in `ai_tags.tagging.moderation`.
6. (amended A1) `contains_person=true` on an otherwise-valid garment: valid category **kept**, `status='flagged'`, `contains_person` stored in `ai_tags.tagging.moderation`.
7. Provider `success=False` (SDK/validation/timeout): `status='failed'`, no columns written, in-flight marker cleared, no raise.
8. **`ai_tags` non-clobber (`BL-053`):** given pre-existing `ai_tags = {"bg_removal": {...}}`, after tagging the row still contains the original `bg_removal` key intact **and** a new `tagging` key.
9. (amended A1) **In-flight dedupe:** with a marker already present for the image hash, a second concurrent `tag()` short-circuits without calling the provider.
10. R2 read failure: `status='failed'`, no raise.
11. Successful call logs `ai_call` with `user_id`, `latency_ms`, `model` (via `caplog`).

**`backend/tests/test_gemini_rate_limiter.py`** (new):
1. Up to 15 `acquire()` in a window return without blocking.
2. The 16th `acquire()` **awaits** (queues) until a token frees — assert it completes (not rejects).
3. Tokens refill over elapsed time (mocked/injected clock).

**`backend/tests/test_tag_cache.py`** (new, mocked Upstash REST):
1. `get` returns the parsed payload on a hit, `None` on a miss.
2. `set` issues key `tag:{hash}` with a 30-day (`2592000`s) TTL.
3. (amended A1) `mark_inflight` issues `tag_inflight:{hash}` with `NX` + a ~60s TTL and returns `True` on first set / `False` when already present; `clear_inflight` deletes it.
4. Fails open: `get`→`None`, `set`/`mark_inflight`/`clear_inflight`→no-op (no raise) when Upstash env vars are unset or the REST call errors.

**`backend/tests/test_wardrobe_repository.py`** (modify, mocked async client):
1. `update_tagging_result` writes the 8 first-class columns and merges `ai_tags` under `tagging` **without clobbering** a simulated pre-existing `ai_tags.bg_removal`, scoped to the caller's JWT (not `service_role`).

**`backend/tests/test_wardrobe_router.py`** (modify, FastAPI `TestClient`):
1. `POST /wardrobe/tag` missing/invalid auth → `401`.
2. Existing row → `202 {"status":"processing","item_id":...}` and a background task queued (spy on `add_task`).
3. Nonexistent row → `404`, no background task queued.
4. Malformed `item_id` → `422` (Pydantic, not `500`).
5. `app.dependency_overrides[get_vision_provider]` swap works (override the DI provider callable, not the ABC — per SS-011's Developer note).

**`test_wardrobe_bg_removal_service.py` / `test_wardrobe_router.py`** (modify, mechanical): the two `_FakeRepository(IWardrobeRepository)` fakes gain a no-op `update_tagging_result` stub so they still instantiate against the extended ABC.

**Not automatable this pass (manual/live):**
- A real `gemini-3.5-flash-lite` call via `google-genai` against the real `GEMINI_API_KEY` returning valid India-taxonomy JSON — **blocked until (a) a real key exists and (b) the account is on the paid tier** (see Open questions).
- Real-photo accuracy ACs ("kurta → `ethnic_kurta`", "formal shoe → `footwear_formal` + `office`/`formal_event`", ">85% kurta-vs-western-top") and the "<3s" latency AC — checked against **real photos, not a synthetic image** (`BL-058` lesson), during Developer/QA once a paid-tier key exists.

## Open questions / blockers

1. **Gemini paid-tier is a precondition for real user photos (amended A1 — new, privacy/DPDP).** Live-verified: on the **free tier**, Google may use submitted prompts/images to improve products (incl. ML training) and may have humans review them — the terms explicitly warn against sensitive/personal data there. On the **paid tier**, Google contractually does not, under the Cloud Data Processing Addendum. StyleSense wardrobe photos routinely contain identifiable faces (mirror selfies), and the account's `15 RPM / 500 RPD` signal indicates it is currently on the **free tier**. **This endpoint must not process real user photos until the Gemini account is on the paid tier.** This is a billing-account decision, not code — logged as new Active `BL-065`, a "gate before real traffic" of the same class as `BL-045`/`BL-051`. Mock/synthetic testing on the free tier is fine.
2. **`GEMINI_API_KEY` is an empty placeholder** in `.env.example` (line 17) — no real key provisioned this session. Developer checks `.env`; if a real (paid-tier) key exists, attempt a real call (confirming SDK call shape + model first); else ship mock-verified, note live E2E blocked (not a code defect).
3. **`google-genai` call shape + `gemini-3.5-flash-lite` availability unverified against the installed package** `[verify-against-installed-SDK]` — after `pip install google-genai`, confirm the exact client construction, `contents=` image-part shape, `config` fields, and response-text access against the package source before treating as load-bearing (the orchestrator's summary is a starting point; SS-011's Replicate-slug precedent).
4. **Upstash REST `SET`/`GET`/`SETEX`/`SET NX` shape unverified** `[verify-against-Upstash-docs]` — confirm before relying (the `BL-035`/`BL-039` precedent).
5. **"<3s" latency AC must be verified with real photos, not synthetic** (`BL-058` lesson). Tagging is async (`202` + Realtime), so it's a backend *processing* target, not a user-blocking wait — a 4–5s tag has minimal UX impact. QA measures against real images and renegotiates if needed. (Directive for QA; not a separate row.)
6. **No per-user cost cap on tagging** — only the global 15 RPM / 500 RPD bounds spend → `BL-062` (money-adjacent; compounds `BL-037`/`BL-045`).
7. **Tags `original.jpg`, not `clean.png`** — decouples tagging from bg-removal, at a possible small accuracy cost → `BL-063`.
8. **Content-moderation enforcement/action** not built — only first-pass flags stored → `BL-061`.
9. **`pattern`/`fabric` are free `TEXT`** with only prompt guidance → `BL-064` (canonical vocabulary decision).
10. **In-process `GeminiRateLimiter` is single-instance-safe only** — compounds `BL-037` (distributed limiter needed at >1 worker).
11. **Extending `IWardrobeRepository` requires updating SS-011's two test fakes** (mechanical) — green-locally/red-in-CI trap if missed.
12. **(amended A1) Concurrent `ai_tags` read-merge-write race** documented-not-fixed → `BL-066` (durable `jsonb_set`-in-`UPDATE`/RPC or optimistic-concurrency fix, deferred to preserve "no migration"; in-flight marker reduces the common case). Same class as `BL-036`.

## Backlog deltas

**Resolved** (moved to Resolved in `docs/BACKLOG.md`):
- `BL-044` (ai) — content moderation: resolved via prompt-based `content_flag` + `contains_person` (amended A1) on the same Gemini pass, with stored flags + review status. Residual (enforcement/takedown) → new `BL-061`.
- `BL-053` (ai) — `ai_tags` namespacing: resolved by writing under `ai_tags.tagging` via a read-merge-write preserving `ai_tags.bg_removal`, with a dedicated non-clobber test.

**Added to Active:**
- `BL-062` (infra) — no per-user cost cap on Gemini tagging; bounded only by the in-process 15 RPM / 500 RPD global limits (single-instance). Revisit before beta.
- `BL-065` (infra) — **(amended A1)** Gemini account must move to the **paid tier** before processing real user photos (free tier may train on / human-review submitted images; wardrobe photos contain faces → DPDP). Billing-account gate before real traffic, same class as `BL-045`/`BL-051`.
- `BL-066` (schema) — **(amended A1)** concurrent read-merge-write on `ai_tags` (tag-vs-tag, or tag-vs-`bg_removal`) can clobber a key — same class as `BL-036`; accepted-and-reduced (in-flight marker) for MVP, durable fix (`jsonb_set`-in-`UPDATE` via RPC, or optimistic concurrency) deferred to avoid a migration.

**Added to Parked:**
- `BL-061` (ai) — content-moderation *enforcement/action policy* not built; SS-012 stores only first-pass flags. Matters at Epic 4 (Social) / try-on. Residual of `BL-044`.
- `BL-063` (ai) — tagging runs on `original.jpg`, not `clean.png`; tagging the isolated garment may improve accuracy. Deferred.
- `BL-064` (ai) — `pattern`/`fabric` free `TEXT` with only prompt guidance; canonical controlled vocabulary is an open taxonomy decision.

**Scanned, reaffirmed (not resolved):** `BL-041` (honoured — only UPDATEs), `BL-052` (honoured — reuses real dependency, its own subject untouched), `BL-057` (consistent — dominant item only), `BL-058` (real-photo-not-synthetic lesson applied to "<3s"), `BL-056` (shared crash-durability gap), `BL-037` (in-process limiter caveat), `BL-036` (the sibling of new `BL-066`).

## Risk: high (reaffirmed and strengthened, amended A1)

**Still a "classify up" call — and the live research strengthens it, doesn't weaken it.** The strict §C2 profile is unchanged from the first pass: **no DB migration** (every output column already exists; tagging state lives in an `ai_tags` JSON sub-key), no new auth, no RLS change, no payments, reversible writes. It is classified **high** because load-bearing surfaces co-occur, each wanting a human gate before build: (1) it owns the content-moderation decision (`BL-044`) — trust-and-safety on user imagery, now with an explicit **privacy/DPDP dimension** (amended A1: free-tier data-training risk on photos that contain faces, gated by new `BL-065`); (2) first live use of a new external paid AI provider (`GEMINI_API_KEY`) in a server-side call path, now on a **corrected model/SDK** (the originals were dead, not just unverified — an amendment that would itself have been a first-call failure), with **timeout/retry/cost-safety** logic that touches real money; and (3) a cross-ticket data-integrity write contract — the `ai_tags` read-merge-write must not clobber SS-011's `bg_removal`, now with an explicitly-documented concurrent-write race (`BL-066`). The privacy precondition and the dead-model correction are exactly the class of one-way-door issue §C2's full lane exists to catch *before* build, so high is, if anything, more clearly correct than in the first pass. (Model note: this pass ran on `model: opus` per the orchestrator's triage override.)
