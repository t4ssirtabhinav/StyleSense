# SS-048 — Rail Presets & Precompute Job — Design

## Tier note

The orchestrator handed this Architect pass `Tier: standard`, but the ticket header's own `Est: 16h` is above CLAUDE.md's `>12h → heavy` boundary. Treating this as **heavy** instead (full doc + numbered Implementation units) — the mismatch is flagged in the final report to the orchestrator rather than silently resolved either way.

## Scope restatement

This ticket adds a `suggestion_rails` table plus the plumbing to keep it populated, turning the four home-screen rail presets (`todays_picks`, `never_tried_pairs`, `not_yet_worn`, `newest_pieces`) from an on-request computation into a precomputed cache that a client reads with a single indexed query. `todays_picks` and `newest_pieces` are thin parameterisations of the already-existing `EngineV2.generate_portfolio` (one engine call serves both, sliced two ways); `never_tried_pairs` and `not_yet_worn` are pure query-layer logic with zero engine involvement, proven by a test that asserts no `engine_v2*` module is ever called from that code path. Recompute is triggered by wardrobe writes (debounced via an `app_config`-driven window, not a real background job — there is no deployed backend/scheduler to run one against, per `BL-037`) and by an explicit on-demand refresh action; a `GET` read is a pure cache read with no side effects. `SS-040`'s `do_not_style`/`is_archived` exclusion is inherited for free everywhere this ticket reads wardrobe items through the existing eligibility-aware paths or the same lifecycle columns directly.

## Files to create/modify

**Migration**

- `supabase/migrations/024_suggestion_rails.sql` — new `suggestion_rails` table. Confirmed free: this worktree's `supabase/migrations/` tops out at `023_item_lifecycle_columns.sql`; `025` is pre-claimed by `SS-057` (parallel worktree), left untouched.

**Backend — ports/adapters (hexagonal, per CLAUDE.md)**

- `backend/adapters/interfaces.py` — MODIFY (additive only, per its own "never modify this signature to fit a new caller" rule):
  - new `ISuggestionRailsRepository` ABC (`upsert_rails`, `get_rails`, `get_most_recent_computed_at`)
  - new abstract method `IWardrobeRepository.get_items_for_rails` (id, category, created_at, wear_count, do_not_style, is_archived, color_primary — the columns `get_items_for_styling` doesn't select, chiefly `created_at`)
  - new abstract method `IOutfitRepository.get_item_ids_for_user` (reads `outfits.item_ids` for the never-tried-pairs co-occurrence check)
- `backend/adapters/suggestion_rails_repository.py` — new `SupabaseSuggestionRailsRepository`, RLS-scoped client per call (same `_client_for(jwt)` pattern as every other adapter in this file's family), `upsert` on `(user_id, rail_key)`.
- `backend/adapters/wardrobe_repository.py` — MODIFY: implement `get_items_for_rails` (new method, existing `get_items_for_styling` untouched).
- `backend/adapters/outfit_repository.py` — MODIFY: implement `get_item_ids_for_user` (new method, existing methods untouched).

**Backend — shared extraction (DRY, so the rail job is provably not a second scoring/orchestration implementation)**

- `backend/services/occasion_resolution.py` — new. `resolve_occasion_input(raw_occasion, *, jwt, occasion_normalizer) -> OccasionStylingInput`, extracted **verbatim** from `OutfitPortfolioService._resolve_occasion`.
- `backend/services/wardrobe_fetch.py` — new. `fetch_wardrobe_for_styling(*, jwt, user_id, wardrobe_repo) -> dict[str, WardrobeItemInput]`, extracted **verbatim** from `OutfitPortfolioService._fetch_wardrobe`.
- `backend/services/outfit_portfolio_service.py` — MODIFY: `_resolve_occasion`/`_fetch_wardrobe` become one-line delegations to the two functions above. Pure extract-method refactor — behavior must be byte-identical; the existing SS-020/22/23 test suite for this file is the regression guard and must still pass unmodified.

**Backend — the rail logic itself**

- `backend/services/suggestion_rails_query.py` — new, pure Python, **zero imports from `services.engine_v2*`**: `build_never_tried_pairs(...)`, `build_not_yet_worn(...)`.
- `backend/services/rail_precompute_service.py` — new `RailPrecomputeService.recompute_all_rails(*, jwt, user_id) -> None`: one `EngineV2.generate_portfolio` call sliced into `todays_picks`/`newest_pieces`, plus the two query-layer rails, then one `upsert_rails` call.
- `backend/services/rail_staleness.py` — new: `maybe_trigger_rail_recompute(...)` — the debounce check + `BackgroundTasks.add_task(...)` call, used by every wardrobe-write call site.
- `backend/services/app_config_specs.py` — MODIFY (additive): new `RailPrecomputeDebounceConfig`/`RAIL_PRECOMPUTE_DEBOUNCE_SPEC`, same shape as `SuggestionNarrationCacheTtlConfig`/`SUGGESTION_NARRATION_CACHE_TTL_SPEC` (coded default, no seed migration needed).

**Backend — router**

- `backend/routers/suggestion_rails.py` — new: `GET /suggestion-rails` (pure read), `POST /suggestion-rails/refresh` (synchronous recompute, mirrors `OutfitPortfolioService`'s own "awaited synchronously, explicit user action" precedent).
- `backend/main.py` — MODIFY: `app.include_router(suggestion_rails.router)`.
- `backend/routers/wardrobe.py` — MODIFY: call `maybe_trigger_rail_recompute` from the existing `BackgroundTasks` callbacks on `/tag` completion and `DELETE /items/{id}` (`/remove-bg` deliberately not wired — see "Debounce trigger wiring" below).
- `backend/routers/outfit_suggestions.py` — MODIFY: call `maybe_trigger_rail_recompute` from `/outcome` for `saved`/`worn` outcome types (these are exactly the writes `never_tried_pairs`/`not_yet_worn` depend on).

**Tests**

- `backend/tests/test_suggestion_rails_query.py`
- `backend/tests/test_rail_precompute_service.py`
- `backend/tests/test_rail_staleness.py`
- `backend/tests/test_suggestion_rails_router.py`
- `backend/tests/test_wardrobe_repository.py` / `backend/tests/test_outfit_repository.py` — MODIFY, extend with the two new methods.

## Concrete values to use, not invent

**`024_suggestion_rails.sql` shape** (transcribed from the ticket's own AC, following `013`/`023`'s established conventions — forward-only, `001_initial.sql` never edited, per `BL-060`):

```sql
CREATE TABLE suggestion_rails (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  rail_key       TEXT NOT NULL CHECK (rail_key IN
                   ('todays_picks','never_tried_pairs','not_yet_worn','newest_pieces')),
  computed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  engine_version TEXT,             -- NULL for the two query-layer rails; ENGINE_VERSION ("engine-v2") for the two engine-backed rails
  payload        JSONB NOT NULL DEFAULT '{"items": []}'::jsonb,
  CONSTRAINT uq_suggestion_rails_user_rail UNIQUE (user_id, rail_key)
);
CREATE INDEX idx_suggestion_rails_user ON suggestion_rails (user_id);

ALTER TABLE suggestion_rails ENABLE ROW LEVEL SECURITY;
CREATE POLICY "user_owns_rails" ON suggestion_rails
  FOR ALL USING (auth.uid() = user_id);
```
This is the AC's literal `(id, user_id, rail_key, computed_at, payload JSONB)` shape plus `engine_version` (needed for the edge-case-#4 staleness decision below) — one row per `(user_id, rail_key)` via the unique constraint, upserted with `on_conflict="user_id,rail_key"`. RLS mirrors `wardrobe_items`' `user_owns_wardrobe` `FOR ALL` pattern exactly, as the AC specifies.

**Fingerprint function — resolving `BL-134` for this ticket's payloads.** Two non-interchangeable `outfit_fingerprint` implementations coexist (`suggestion_log_service.py`, colon-joined; `engine_v2_portfolio.compute_outfit_fingerprint`, comma-joined). `todays_picks`/`newest_pieces` payload items **use `engine_v2_portfolio.compute_outfit_fingerprint` exclusively** — it's what `EngineV2._log_session` and `OutfitPortfolioService` already compute for the same `ScoredCandidate.item_ids`, so a rail's stored fingerprint is directly comparable to `suggestion_impressions.outfit_fingerprint` for the same candidate. This does not resolve `BL-134` itself (both implementations still exist) but avoids adding a third divergent caller — noted back on that row.

**Debounce window:** `RailPrecomputeDebounceConfig.seconds = 600` (10 minutes) — transcribed from `docs/competitive/08-CHEAP-SUGGESTION-ENGINE.md` §5.2's own precompute-schedule table ("On wardrobe write (debounced ~10 min)"), not invented. `app_config`-driven per the Technical Notes, coded default, no seed migration (mirrors `SuggestionNarrationCacheTtlConfig`'s posture exactly).

**Engine call parameters for the precompute job** (`backend/services/rail_precompute_service.py`):
- `occasion = "everyday"` — the exact same fallback string `OutfitPortfolioService._resolve_occasion` degrades to for an unresolvable occasion (`_FALLBACK_OCCASION_KIND`). Not a weekday-frequency inference (that's `08-CHEAP-SUGGESTION-ENGINE.md` §5.1's aspirational framing, not this ticket's AC) — "sensible default", per the Technical Notes' own words.
- `as_of = ist_today()` (same helper `outfit_portfolio_service.py` already imports).
- `portfolio_size_range = (15, 20)` — an existing, already-supported `generate_portfolio` kwarg (used today by SS-039's effort tiers), widened from the engine's own default `(5, 8)` so **one** call yields enough candidates to slice into both `todays_picks` and `newest_pieces` without a second engine invocation. Every other kwarg (`search_pool_size`, `mmr_lambda`, `max_exploration`) is left at the engine's own default — no new tuning surface invented.
- `exclude_fingerprints = None`, `style_preferences = None` (read from `wardrobe_repo.get_style_preferences` the same way the live endpoint does — reuse, not a new default), `weather = None` (the precompute job deliberately skips the weather round-trip; rails are refreshed on writes/explicit refresh far more often than weather materially changes, and skipping it keeps the job dependency-light — noted in Open Questions as a deliberate simplification, not an oversight).

**Rail slice sizes** (product-shaped values, not load-bearing — flagged as adjustable, not re-derived from anywhere): `todays_picks` = top 5 of the engine portfolio, in ranked order. `newest_pieces` anchor set = top 5 wardrobe items by `created_at DESC` (no 14-day cutoff — the ticket's own Description says "most recently added items, ordered by created_at", not a time window; the 14-day figure is `08-CHEAP-SUGGESTION-ENGINE.md`'s own framing for a different, uncommitted rail); `newest_pieces` payload = engine-portfolio candidates whose `item_ids` intersect that anchor set, ranked by `total_score`, capped at 5 — legitimately empty if no anchor item survives eligibility/candidate search into any portfolio slot (an accepted empty-state, not a bug). `not_yet_worn` = up to 10 items with `wear_count = 0`, excluding `do_not_style`/`is_archived`. `never_tried_pairs` = up to 10 pairs.

**Display snapshot fields**, mirroring `outfits.items_snapshot`'s denormalisation rationale (`020_outfits_first_writer.sql`) for the same "a since-deleted item must not corrupt or crash the read" reason: each payload item carries `{item_id, category, color_primary, thumbnail_url}` captured **at compute time**, via the already-existing `IWardrobeRepository.get_items_image_info_bulk` for the image fields. Serving never re-joins `wardrobe_items`.

**`never_tried_pairs`/`not_yet_worn` algorithm — deliberately not raw SQL, despite `08-CHEAP-SUGGESTION-ENGINE.md`'s `NOT EXISTS` framing.** This codebase's own convention for "deterministic, engine-adjacent logic" is a pure Python stage function operating on already-fetched data (`engine_v2_eligibility.filter_eligible`, `engine_v2_novelty.fetch_novelty_inputs`, etc.), unit-testable without a live Postgres connection — `suggestion_rails_query.py` follows that convention instead of hand-written `NOT EXISTS` SQL, which also sidesteps a real gap: `wardrobe_category`'s 21-value enum has no dedicated "ethnic bottom" category (churidar/palazzo aren't first-class), so a category-name-based SQL `top × bottom` join can't be written correctly today anyway. Concretely:
1. Fetch wardrobe rows via the new `get_items_for_rails` (id, category, wear_count, created_at, do_not_style, is_archived), excluding lifecycle-flagged items.
2. Resolve each item's `assembly_slot` via `garment_registry_adapter.get_garment_attributes(category)` (a registry lookup, not an `engine_v2*` stage — `await garment_registry_adapter.refresh()` first, same as `EngineV2.generate_portfolio`'s own first statement) — bucket into `top`/`bottom`/`one_piece`/etc.
3. Fetch `outfits.item_ids` for the user via the new `get_item_ids_for_user` — this is `outfits`, not a separate "accepted suggestion" table: every `saved`/`worn`/`shared` outcome on `POST /outfit-suggestions/outcome` already writes an `outfits` row (confirmed via `backend/adapters/outfit_repository.py::insert_outfit`), so `outfits.item_ids` is already the complete union of "saved outfit or accepted suggestion" the AC asks to exclude — no second table join needed.
4. `build_never_tried_pairs`: cartesian `top × bottom` items, minus any pair where both ids appear together in any `outfits.item_ids` row (pure Python set membership), capped at the limit.
5. `build_not_yet_worn`: filter to `wear_count == 0`, capped at the limit.

Both functions import nothing from `services.engine_v2*` — the test in the Test plan below asserts this directly (patch `EngineV2.generate_portfolio` to raise if called, run both functions, assert no exception).

**Router contract** (`backend/routers/suggestion_rails.py`, same auth pattern as `outfit_suggestions.py`'s `/portfolio`: `Depends(get_current_user_id)` + `_extract_bearer_token(authorization)`):
- `GET /suggestion-rails` — **pure read**, no side effects, no `BackgroundTasks` triggered here (the AC's "on wardrobe write" / "on demand" trigger list deliberately does not include a plain read — see Edge cases). Returns `{"rails": [...]}`, one entry per rail that currently has ≥1 item in its payload — a rail with an empty/missing payload is **omitted from the array entirely**, so `SS-049`'s mobile consumer can render exactly what it receives with no empty-state branching of its own. Each entry: `{rail_key, computed_at, engine_version, items: [...]}`.
- `POST /suggestion-rails/refresh` — synchronous, awaited (mirrors `OutfitPortfolioService`'s own "awaited synchronously... explicit user action" precedent from `SS-020`'s signed-off Open Question #1) — calls `RailPrecomputeService.recompute_all_rails` directly, then returns the same shape as the `GET`.

**Debounce trigger wiring** (`maybe_trigger_rail_recompute`, called from existing `BackgroundTasks`-bearing router handlers — `routers/wardrobe.py`'s `/tag` completion callback and `DELETE /items/{id}`'s cleanup callback, and `routers/outfit_suggestions.py`'s `/outcome` for `saved`/`worn`): reads `RAIL_PRECOMPUTE_DEBOUNCE_SPEC` from the config snapshot, reads `ISuggestionRailsRepository.get_most_recent_computed_at(jwt, user_id)` (`MAX(computed_at)` across the user's 4 rows, or `None`), and calls `background_tasks.add_task(rail_precompute_service.recompute_all_rails, jwt=jwt, user_id=user_id)` only if that value is `None` or older than the debounce window. Wrapped in its own `try/except` (logs and swallows) — a failed staleness check must never fail the wardrobe write it's attached to, same defensive posture as `EngineV2._log_session`/`_resolve_weather`. `/remove-bg` itself is **not** wired (it writes `category=None`, before an item is stylable at all — wiring `/tag`'s completion callback, which is where a row actually becomes eligible for the engine, is sufficient and avoids double-triggering on the same upload).

## Edge cases

Carried forward from the raw ticket, plus new ones from this pass:

- **New user, < 5 wardrobe items** (ticket) — `generate_portfolio`'s own graceful-degradation for a small wardrobe (limited/empty portfolio, `limited_options` flag) is inherited unmodified; the precompute job must not raise just because `engine_result.portfolio` is short or empty — `todays_picks`/`newest_pieces` payload construction degrades to a shorter or empty `items` list, never an exception.
- **Item deleted after a rail was cached** (ticket) — solved by the compute-time display snapshot (see Concrete values); serving never re-reads `wardrobe_items`, so a stale id in a cached payload renders its last-known snapshot rather than crashing. `DELETE /items/{id}` also triggers a debounced recompute (see wiring above), so the rail self-heals on the next write within the debounce window regardless.
- **Two rapid wardrobe writes race the debounced recompute** (ticket) — accepted as-is, per the ticket's own "last-write-wins... no lock needed" directive: `upsert_rails` is a plain `UPDATE`/`ON CONFLICT` per `(user_id, rail_key)`, so two overlapping `BackgroundTasks` recomputes just leave whichever finishes last; no lock, no queue.
- **Rail computed under an old `engine_version` and never refreshed** (ticket) — resolved by storing `engine_version` on the row (see Concrete values): the staleness check treats a non-NULL `engine_version` that doesn't match the current `ENGINE_VERSION` constant as stale unconditionally, regardless of `computed_at` recency. The two query-layer rails have no analogous version primitive (their logic isn't versioned anywhere in this codebase) — `computed_at` alone governs their staleness, an accepted gap noted in Open questions.
- **`GET /suggestion-rails` is a pure read with no trigger (new, this pass)** — the AC's trigger list is exactly "on wardrobe write" and "on demand (explicit refresh)"; a plain read is neither, so a user who never writes to their wardrobe after this ticket ships and never taps refresh sees empty rails indefinitely. This is a real bootstrap gap for **existing** users (wardrobe already populated before this ticket merges) — flagged in Open questions for `SS-049` (the mobile consumer) to close, e.g. by calling `POST /suggestion-rails/refresh` once when `GET` returns a fully empty array on first load.
- **`newest_pieces` anchor exists but is ineligible for any portfolio slot** (new, this pass) — e.g. the newest item is an accessory with no viable pairing under the current occasion's styling rules. The rail is legitimately empty this cycle, not an error — same empty-state contract as `not_yet_worn` on a fully-worn wardrobe.
- **`never_tried_pairs` on a wardrobe with no bottom-slot items at all** (new, this pass) — e.g. an all-ethnic-one-piece or all-accessory wardrobe. `top × bottom` cartesian is empty by construction; the rail is empty, not an error.
- **Debounce staleness check itself fails** (new, this pass) — wrapped in `try/except` (see wiring above) so a failed DB read for the staleness check can never fail the wardrobe write it's attached to; worst case, a recompute is skipped this cycle and the next write's check catches it.

## Test plan

`backend/tests/test_suggestion_rails_query.py`
- `build_never_tried_pairs` excludes any pair present together in any `outfits.item_ids` row.
- `build_never_tried_pairs` excludes `do_not_style`/`is_archived` items even when otherwise a valid pair.
- `build_never_tried_pairs` on a wardrobe with no `bottom`-slot items returns `[]`, not an error.
- `build_not_yet_worn` returns only `wear_count == 0` items, excluding `do_not_style`/`is_archived`, capped at the limit.
- **Proof test (AC's central claim):** patch `services.engine_v2.EngineV2.generate_portfolio` (and, belt-and-suspenders, assert `"engine_v2" not in` this module's own `import` list via `ast`/`inspect` source scan) to raise if called; run both `build_never_tried_pairs` and `build_not_yet_worn`; assert no exception and the mock was never invoked.

`backend/tests/test_rail_precompute_service.py`
- `recompute_all_rails` calls `EngineV2.generate_portfolio` **exactly once** per invocation (proves `todays_picks`+`newest_pieces` share a single engine call, not two).
- `todays_picks` payload is the top 5 of the returned portfolio, in the engine's own ranked order.
- `newest_pieces` payload contains only candidates whose `item_ids` intersect the top-5-by-`created_at` anchor set; empty when no such candidate exists.
- Every row this service writes for `todays_picks`/`newest_pieces` carries `engine_version = ENGINE_VERSION`; every row for `never_tried_pairs`/`not_yet_worn` carries `engine_version = NULL`.
- A wardrobe with 0 wardrobe items (or 0 items surviving eligibility) produces empty payloads for all 4 rails without raising.
- `upsert_rails` overwrites the existing `(user_id, rail_key)` row on a second `recompute_all_rails` call — no duplicate rows (idempotent upsert semantics, per AC).
- Stored `outfit_fingerprint` values (inside `todays_picks`/`newest_pieces` payload items) match `engine_v2_portfolio.compute_outfit_fingerprint(item_ids)` exactly (the `BL-134` consistency choice).

`backend/tests/test_rail_staleness.py`
- `maybe_trigger_rail_recompute` adds a background task when no `suggestion_rails` row exists yet for the user.
- Adds a background task when the most recent `computed_at` is older than the configured debounce window.
- Does **not** add a background task when the most recent `computed_at` is within the debounce window.
- A failed `get_most_recent_computed_at` call is swallowed (logged, no exception propagates to the caller).

`backend/tests/test_suggestion_rails_router.py`
- `GET /suggestion-rails` returns cached rows with **no** call to `EngineV2.generate_portfolio` and **no** `BackgroundTasks.add_task` call (proves the "one indexed read, no side effects" AC).
- `GET /suggestion-rails` omits any rail whose payload has 0 items from the response array.
- `GET /suggestion-rails` on a brand-new user (no rows at all) returns `{"rails": []}`, not a 404/500.
- `POST /suggestion-rails/refresh` calls `RailPrecomputeService.recompute_all_rails` and returns the freshly-written rows.
- Both routes 401 without a valid bearer token (mirrors `outfit_suggestions.py`'s existing auth test pattern).

`backend/tests/test_wardrobe_repository.py` / `test_outfit_repository.py`
- `get_items_for_rails` selects `created_at` (the field `get_items_for_styling` omits) alongside the lifecycle columns.
- `get_item_ids_for_user` returns every `outfits.item_ids` row for the caller's own `user_id`, RLS-scoped (no cross-user leakage — same assertion shape as this file's existing tests).

**Regression guard, not a new test:** the existing `outfit_portfolio_service` test suite (SS-020/22/23) must still pass unmodified after `_resolve_occasion`/`_fetch_wardrobe` become delegations to the new shared functions — this is the proof the refactor is behavior-preserving.

**Not automated, matches repo convention** (per `013`/`020`/`023`'s own posture): `024_suggestion_rails.sql` is verified via `supabase db push` (linked project) then `supabase db diff --linked` reporting empty, not a pytest — see Open questions for the parallel-worktree `db push` serialization this requires (`BL-060`/`BL-110`).

## Implementation units

Numbered, independently-committable, in dependency order — the Developer's checkpoint checklist maps 1:1 onto these (one `wip(SS-048)` commit per unit).

1. **Migration `024_suggestion_rails.sql`** — table, RLS, indexes, rollback block. Apply via `supabase db push` (serialize against `SS-056`/`SS-057`'s parallel worktrees per the worklog's standing directive) and confirm `supabase db diff --linked` is empty.
2. **Port widening** — `ISuggestionRailsRepository` + new `IWardrobeRepository.get_items_for_rails` / `IOutfitRepository.get_item_ids_for_user` abstract methods (interfaces only, no implementation yet).
3. **Adapter implementations** — `SupabaseSuggestionRailsRepository`, `wardrobe_repository.get_items_for_rails`, `outfit_repository.get_item_ids_for_user`, plus their tests.
4. **Shared extraction refactor** — `occasion_resolution.py` + `wardrobe_fetch.py`, `outfit_portfolio_service.py`'s two methods reduced to delegations. Run the *existing* `outfit_portfolio_service` test suite here and confirm it still passes byte-for-byte before moving on — this unit is the riskiest one to get wrong silently.
5. **`suggestion_rails_query.py`** (`build_never_tried_pairs`, `build_not_yet_worn`) + its tests, including the "zero `engine_v2*` calls" proof test.
6. **`app_config_specs.py` addition** (`RAIL_PRECOMPUTE_DEBOUNCE_SPEC`) + `rail_staleness.py` (`maybe_trigger_rail_recompute`) + its tests.
7. **`rail_precompute_service.py`** (`RailPrecomputeService.recompute_all_rails`, the one-engine-call-sliced-two-ways logic) + its tests.
8. **Router** — `suggestion_rails.py` (`GET`/`POST /refresh`), wired into `main.py`, + its tests.
9. **Write-path wiring** — `maybe_trigger_rail_recompute` calls added to `wardrobe.py`'s `/tag` and `DELETE /items/{id}`, and `outfit_suggestions.py`'s `/outcome` (`saved`/`worn`). Confirm no existing test in either router file regresses.

## Open questions / blockers

- **Tier mismatch flagged, not silently resolved** — orchestrator handed `Tier: standard` but `Est: 16h` is above the `>12h → heavy` boundary; this doc is written at `heavy` tier. Orchestrator should confirm/correct for downstream phases (Developer's checkpoint cadence assumes the Implementation units above).
- **No nightly cron, confirmed out of scope** — the raw ticket already states this plainly (`BL-037`: no deployed backend exists anywhere). Restated here so it isn't silently re-attempted: the debounce/on-demand mechanism this design ships is the entire precompute story for this environment. A real scheduled job is future work once a backend is deployed.
- **Existing-user bootstrap gap** — a user with wardrobe items already in place *before* this ticket ships has zero `suggestion_rails` rows and no pending write to trigger one. `GET /suggestion-rails` is a pure read (see Edge cases), so nothing self-heals this automatically. Recommend `SS-049` (the mobile consumer, not yet designed) call `POST /suggestion-rails/refresh` once on first load if `GET` returns an empty array — noted here for that ticket's Architect pass to pick up, not solved in this backend-only ticket.
- **Weather deliberately excluded from the precompute call** — the live `/portfolio` endpoint resolves weather (`SS-022`); this precompute job does not, to keep the job's dependency surface light and because rails refresh far more often (on writes) than weather materially changes. If a future ticket wants weather-aware rails, this is the point to revisit — logging as `BL-197` below rather than deciding it here.
- **Query-layer rails have no staleness primitive analogous to `engine_version`** — `never_tried_pairs`/`not_yet_worn`'s logic isn't versioned anywhere in this codebase (no `NOVELTY_QUERY_VERSION` constant exists), so a future change to either function's behavior won't force existing cached rows to invalidate on `engine_version` grounds the way the two engine-backed rails do. `computed_at`-driven debounce staleness is the only mechanism for them. Low stakes today (nothing has shipped that would need to invalidate on logic-version grounds yet) — noted, not built.
- **`SS-056`/`SS-057` parallel-worktree `db push` serialization** — this ticket's `024` migration must be pushed with the same "serialize `supabase db push` across the three parallel worktrees" discipline the worklog header already states (`BL-060`/`BL-110` precedent). Flagged for whoever runs DevOps on this ticket, not a design decision.

## Backlog

- **`BL-134`** (two non-interchangeable `outfit_fingerprint` implementations) — re-scanned, not resolved, but this ticket's engine-backed rail payloads deliberately use `engine_v2_portfolio.compute_outfit_fingerprint` (not `suggestion_log_service`'s), keeping the codebase at two divergent implementations rather than three. Noted on the existing Active row, not moved.
- **New: `BL-197`** (Tag: `ai`) — Source: SS-048 / Architect. The rail precompute job (`todays_picks`/`newest_pieces`) deliberately skips `WeatherService.resolve_for_user` (unlike the live `/portfolio` endpoint, `SS-022`) to keep the precompute job's dependency surface light, since rails refresh far more often on wardrobe writes than weather materially changes. A future ticket wanting genuinely weather-aware precomputed rails (e.g. "beat the heat" from `08-CHEAP-SUGGESTION-ENGINE.md` §5.1) needs to revisit this. Active — plausible for a near-future rail-preset ticket.
- **New: `BL-198`** (Tag: `infra`) — Source: SS-048 / Architect. Existing users (wardrobe already populated before this ticket ships) get zero `suggestion_rails` rows and no automatic bootstrap — `GET /suggestion-rails` is a pure read with no trigger, and no nightly job exists to backfill (`BL-037`). `SS-049` (mobile consumer, not yet designed) should call `POST /suggestion-rails/refresh` once when `GET` returns empty on first load, or a future ticket adds a one-time backfill script. Active — directly blocks `SS-049` having anything to show a pre-existing user on first launch.

## Risk classification

`Risk: med` — confirmed, matches the ticket header. This ticket adds one new table (`suggestion_rails`) via an additive-only, forward-only migration with a standard RLS `FOR ALL USING (auth.uid() = user_id)` policy identical in shape to `wardrobe_items`' own — not a change to an existing schema, not auth, not payments, not secrets, and not externally reachable by anyone but the row's own owner. The heaviest surface is the `outfit_portfolio_service.py` refactor (Implementation unit 4), which is why that unit is called out explicitly as needing the existing test suite to pass unmodified before proceeding — but an extract-method refactor with a regression-test guard is not itself a one-way door. Nothing here touches money, and nothing is irreversible (the table can be dropped with zero data-loss consequence to any other table, per the migration's own rollback block). Stays `med`, not `high`.
