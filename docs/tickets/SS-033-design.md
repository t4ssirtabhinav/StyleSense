# SS-033 — Suggestion Impression & Outcome Logging — Design

Ticket: [`docs/tickets/raw/SS-033.md`](raw/SS-033.md) · `[Infra]` `[P0]` `[Sprint 5]` `[4 pts]` · Depends on SS-025, SS-026
Source: [`docs/proposals/STYLING-ENGINE-V2.md`](../proposals/STYLING-ENGINE-V2.md) §7 (Wave 1.5)
Architect pass: 2026-07-30 (Opus — full lane; the raw ticket already carries `Risk: high`)

**This document is the Developer's spec.** Every value in it is fixed. Where a value is my own judgement (nothing upstream pins it) it says so inline. Do not re-open the proposal or the raw ticket to re-derive anything below.

---

## 1. Scope restatement

Nothing in this codebase records what the styling engine suggested or what the user did about it. `suggestion_sessions` exists (`001_initial.sql:97-106`) but **no code path anywhere writes it** — `[VERIFIED 2026-07-30, ripgrep over the working tree]` the only references are two Edge Functions that *count* it (`cost-monitor/index.ts:19`, `weekly-report/index.ts:27`), one generated TypeScript row type, and `test_db_schema.py`'s table list. SS-033 builds the write substrate for three surfaces: **request context** (extend the existing `suggestion_sessions` additively — occasion, weather, tier, effort tier, engine version, config-snapshot hash, candidate count, and a cost-incurred marker), **candidates shown** (a new `suggestion_impressions` table, one row per candidate: item-id set, total score, per-rule breakdown, rank, exploration flag), and **user reaction** (a new `suggestion_outcomes` table: `saved`/`worn`/`dismissed`/`shuffled_away`/`shared`, multiple per impression, ordered).

Three things make this more than a pair of `CREATE TABLE`s. (a) It is the **highest-volume surface in the schema by an order of magnitude** (~7.3M impression rows/month at 10k users), so the index plan and a *working* 180-day retention mechanism are part of this ticket, not a later optimisation. (b) It **silently breaks the `cost-monitor` Edge Function** the moment it starts writing sessions for cache hits and E0/degraded (₹0) requests, because that function treats one session row as one paid AI call — fixing that is an AC here (`BL-107`). (c) It **narrows a shipped RLS policy**: `001_initial.sql:172`'s `user_owns_sessions` is `FOR ALL`, i.e. a client can today insert, update and delete its own session rows, which the ticket's AC #4 explicitly forbids and which would let a user cascade-delete their own impression history or forge rows into the cost monitor's count. That narrowing is the one non-additive change in this migration and the main reason this is a full-lane ticket.

Per the ticket's Technical Notes this ships the **substrate plus tests only**. `backend/services/outfit_suggestion_service.py` is **not touched** (`BL-096`'s live landmine, per `BL-102`'s precedent); **SS-020 does the wiring**, and SS-020 must write impressions from day one because that is the unbackfillable part.

---

## 2. Files to create / modify

### 2.1 Create

| Path | Purpose |
|---|---|
| `supabase/migrations/013_suggestion_impressions.sql` | Pre-assigned number (§3). Extends `suggestion_sessions`, creates the two new tables + indexes + RLS + `user_id`-derivation triggers + the retention purge function and its schedule + the `app_config` retention seed row. |
| `backend/adapters/suggestion_log_repository.py` | `SupabaseSuggestionLogRepository(ISuggestionLogRepository)` — `service_role` writes; never raises. |
| `backend/services/suggestion_log_service.py` | `SuggestionLogService` — maps `ScoredCandidate` → impression rows, computes the outfit fingerprint and config-snapshot hash, owns `ENGINE_VERSION`, owns the log-and-continue policy. Pure orchestration, no SQL. |
| `backend/tests/test_suggestion_log_service.py` | Mapping, hashing, never-raises, zero-cost markers, boundary sweep. |
| `backend/tests/test_suggestion_log_repository.py` | Row shape, `service_role` pinning, never-raises, clamping. |
| `backend/scripts/ss033_verify_impression_logging.py` | Manual live verification (§8), same shape as `ss015_verify_wear_history.py` / `ss026_verify_config_live_reload.py`. |
| `supabase/functions/_shared/suggestionSessions.ts` | The one place the "costed session" predicate and the zero-cost-reason vocabulary are defined, imported by both Edge Functions. |
| `supabase/functions/_shared/suggestionSessions.test.ts` | Deno test of the predicate against a fixture containing a cache-hit session (AC #5's literal requirement). |
| `supabase/functions/cost-monitor/index.test.ts` | Deno test of the refactored `handleRequest` seam. |

### 2.2 Modify

| Path | Change |
|---|---|
| `backend/adapters/interfaces.py` | Add `ISuggestionLogRepository` + `SuggestionSessionLog`, `SuggestionImpressionLog`, `SuggestionOutcomeLog` dataclasses, alongside `IAppConfigRepository`/`IOccasionRepository`. Existing ports untouched. |
| `supabase/functions/cost-monitor/index.ts` | Filter to cost-incurred sessions; refactor to an exported `handleRequest(req, deps)` seam + exported constants (the `get-upload-url/index.ts` precedent, which exists precisely so a Deno test can inject a fake Supabase client). |
| `supabase/functions/weekly-report/index.ts` | Add a second, *billable* session count alongside the existing total; the total stays as the engagement metric (§7.2). |
| `backend/tests/test_db_schema.py` | Add the two new tables to `EXPECTED_TABLES`, plus assertions for the new columns, CHECK constraints, indexes, RLS posture, the deprecation comments, and the purge function. |
| `mobile/types/supabase.ts` | Regenerate — **conditionally**, see §9 Q3 (the parallel-worktree hazard makes a blind regen liable to commit sibling tickets' tables). |

### 2.3 Explicitly **not** touched

- `backend/services/outfit_suggestion_service.py` — `BL-096`'s landmine (raises `HTTPException` inside a `BackgroundTasks` callback). The ticket's Technical Notes forbid it by name; `BL-102` is the precedent for staying out. **No wiring in this ticket.**
- `backend/routers/outfit_suggestions.py` — same reason; the router is what SS-020 rebuilds.
- `mobile/**` application code — nothing user-facing here. No `features/<domain>/*.queries.ts` reads these tables yet (an authenticated read path exists via RLS, but no consumer; noted, not built).
- `001_initial.sql` — never edited (`BL-060`). Every change is forward-only in `013`.

### 2.4 Port placement rationale

`ISuggestionLogRepository` goes in **`backend/adapters/interfaces.py`**, not `backend/ai/ports/interfaces.py`, following the rationale SS-029 recorded verbatim for `ICostLedger`: `ai/ports/` is scoped by CLAUDE.md to AI *provider capabilities* (`IVisionProvider`, `IStylingProvider`, `ISearchProvider`); this is a Postgres persistence port, the same kind of thing as the `IWardrobeRepository`/`IOccasionRepository`/`IAppConfigRepository` already in that file. The ticket's Technical Notes say so explicitly ("alongside `IAppConfigRepository`/`IOccasionRepository`"). No new folder is invented.

---

## 3. Migration `013_suggestion_impressions.sql`

**Renumbered 2026-07-31** (per `docs/tickets/raw/SS-033.md`'s Technical Notes and `BL-110`'s incident note): SS-029 shipped live as migration `012`, not `011` as originally assumed — `011` was independently claimed by SS-028's `011_seed_ai_routing_config.sql`, confirmed via `supabase migration list --linked` against the shared live project. Every Wave 1.5 slot shifts up by one as a result. Wave 1.5 map: `012` SS-029, `013` this ticket, `014` SS-034, `015` SS-035, `016` SS-036.

Every statement below is forward-only and, with the single documented exception in §3.5, purely additive.

### 3.1 Extend `suggestion_sessions` (additive)

`weather_data JSONB` and `cache_key TEXT` already exist — **reuse, do not duplicate** (ticket's Technical Notes).

```sql
ALTER TABLE suggestion_sessions
  ADD COLUMN engine_version       TEXT,
  ADD COLUMN effort_tier          TEXT,
  ADD COLUMN tier                 TEXT,
  ADD COLUMN config_snapshot_hash TEXT,
  ADD COLUMN candidate_count      SMALLINT,
  ADD COLUMN request_id           UUID,
  ADD COLUMN latency_ms           INTEGER,
  ADD COLUMN cost_incurred        BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN zero_cost_reason     TEXT;
```

Constraints, added as named `ALTER TABLE … ADD CONSTRAINT` statements so a failure names itself:

```sql
ALTER TABLE suggestion_sessions
  ADD CONSTRAINT suggestion_sessions_effort_tier_check
    CHECK (effort_tier IS NULL OR effort_tier IN ('E0','E1','E2','E3','E4')),
  ADD CONSTRAINT suggestion_sessions_tier_shape_check
    CHECK (tier IS NULL OR tier ~ '^[a-z][a-z0-9_]*$'),
  ADD CONSTRAINT suggestion_sessions_candidate_count_check
    CHECK (candidate_count IS NULL OR candidate_count >= 0),
  ADD CONSTRAINT suggestion_sessions_latency_check
    CHECK (latency_ms IS NULL OR latency_ms >= 0),
  ADD CONSTRAINT suggestion_sessions_zero_cost_reason_check
    CHECK (zero_cost_reason IS NULL OR zero_cost_reason IN
      ('cache_hit','degraded_e0','rules_only','budget_denied','no_provider_call')),
  ADD CONSTRAINT suggestion_sessions_cost_marker_consistency_check
    CHECK ( (cost_incurred AND zero_cost_reason IS NULL)
         OR (NOT cost_incurred AND zero_cost_reason IS NOT NULL) );
```

Four decisions in there that are mine, with reasons, because picking silently would be wrong:

1. **`cost_incurred` defaults to `true`, not `false`.** This column is read by a cost *alert*. A default of `false` means any writer that forgets to set it silently under-reports spend — the exact silent-failure class `BL-107` exists to catch. `true` means a forgetful writer over-reports, producing a noisy alert someone investigates. Alerting fails loud, never quiet. Existing rows (zero of them today, but the default applies regardless) become `true`, i.e. counted — conservative in the same direction.
2. **`effort_tier` is `CHECK`-enumerated, `tier` is not.** The five effort tiers are a fixed dial transcribed from `STYLING-ENGINE-V2.md` §6 (`E0` degraded, `E1` economy, `E2` standard/launch default, `E3` premium, `E4` atelier); adding `E5` is a migration-worthy event that SS-035 owns, so a typo'd `"e2"` should fail loudly. `tier` is a **historical snapshot of the user's plan at request time**, and `plan_tier` is a real enum elsewhere that may gain values — a value-enumerated CHECK here would make a future plan tier fail an audit-log write, which is backwards. It gets a shape-only regex instead (same posture as `ai_cost_ledger.provider`'s `^[a-z][a-z0-9_]*$` in SS-029 §3.5). Values today are exactly `001_initial.sql`'s `plan_tier` labels: `free`, `premium`, `premium_annual`.
3. **`zero_cost_reason` is enumerated and *required* when `cost_incurred = false`.** Without it, "why was this request free" is unanswerable and cache effectiveness stays invisible — which the ticket's own edge case names as the reason cache hits must be logged at all. The paired consistency CHECK makes the two columns impossible to leave in a contradictory state, so "forgot to say why" is a hard error at write time, not a data-quality problem discovered months later.
4. **`request_id UUID` and `latency_ms`** are added now, not later: `request_id` is the join key to SS-029's `ai_cost_ledger.request_id`, which is how this table stops being a *proxy* for cost and starts being joinable to the real figure (§7.3's long-term direction). Adding it later means a backfill of a table that cannot be backfilled.

**No new trigger on `suggestion_sessions`.** Note that SS-025's `trg_suggestion_sessions_normalize_occasion` (`008_occasion_columns_to_text.sql:83-85`) already fires `BEFORE INSERT OR UPDATE` and rewrites `NEW.occasion` through `occasion_normalize_one`. Consequence the adapter must expect: **the `occasion` value read back may not be byte-identical to the one written** (an alias normalises to its canonical key; an unknown slug is written *and* logged to `occasion_unknown_tags`). The adapter must not assert round-trip equality on `occasion`. Carried into §6 as an edge case.

### 3.2 Deprecate the two superseded columns — `COMMENT`, do not drop

**Decision: keep both columns, mark them deprecated with `COMMENT ON COLUMN`, drop them in a later CONTRACT migration once no reader exists.** Recorded here because the ticket demands a decision, not drift.

```sql
COMMENT ON COLUMN suggestion_sessions.suggestions IS
  'DEPRECATED (SS-033, 2026-07-30). Superseded by the suggestion_impressions table, which '
  'stores one row per candidate with its score breakdown. Nothing has ever written this column. '
  'Do not write it; do not read it. Scheduled for removal in a later CONTRACT migration once '
  'mobile/types/supabase.ts no longer references it (see BL-112).';

COMMENT ON COLUMN suggestion_sessions.accepted_outfit_id IS
  'DEPRECATED (SS-033, 2026-07-30). A single-accepted-outfit precursor to suggestion_outcomes, '
  'which records saved/worn/dismissed/shuffled_away/shared per impression with ordering and '
  'permits multiple outcomes. Nothing has ever written this column. Use '
  'suggestion_outcomes.outcome_type = ''saved'' instead. Scheduled for removal in a later '
  'CONTRACT migration (see BL-112).';
```

Why deprecate rather than drop *or* repurpose as a denormalised blob:

- **Not a blob.** Keeping `suggestions JSONB` as a denormalised copy would create a second source of truth for the same facts, on the highest-volume path in the schema, with nothing enforcing agreement between it and `suggestion_impressions`. That is the drift the ticket is asking us to avoid, not a way of avoiding it.
- **Not a drop, in this migration.** A `DROP COLUMN` is the one genuinely irreversible statement available here, and it buys nothing measurable: both columns are `NULL` in every row, so they cost no storage and no write path. It would also invalidate the committed `mobile/types/supabase.ts` row type (which today declares `suggestions` and `accepted_outfit_id`) and any unregenerated client build. SS-025's own three-step EXPAND → MIGRATE → CONTRACT precedent (`007`/`008`/`009`) is explicit that the drop is its own migration, run once no reader remains.
- The `COMMENT` is **machine-checkable** — §7.4 adds a `test_db_schema.py` assertion that both comments exist and start with `DEPRECATED`, so the deprecation cannot silently evaporate.

### 3.3 `suggestion_impressions`

```sql
CREATE TABLE suggestion_impressions (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id         UUID NOT NULL REFERENCES suggestion_sessions(id) ON DELETE CASCADE,
  user_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  rank               SMALLINT NOT NULL CHECK (rank >= 1),
  item_ids           UUID[] NOT NULL CHECK (array_length(item_ids, 1) >= 1),
  outfit_fingerprint TEXT NOT NULL CHECK (outfit_fingerprint ~ '^[0-9a-f]{64}$'),
  total_score        NUMERIC(6,5) NOT NULL CHECK (total_score >= 0 AND total_score <= 1),
  rule_scores        JSONB NOT NULL DEFAULT '[]'::jsonb,
  gap_flags          TEXT[] NOT NULL DEFAULT '{}',
  is_exploration     BOOLEAN NOT NULL DEFAULT false,
  strategy           TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT suggestion_impressions_session_rank_unique UNIQUE (session_id, rank)
);
```

- **`item_ids UUID[]` with no foreign key — deliberate, and it is the mechanism for one of the ticket's edge cases.** An impression whose items are later deleted must survive as historical truth; a real FK (or an `ON DELETE CASCADE` from `wardrobe_items`) would erase exactly the history we are collecting. A `UUID[]` carries no referential action at all, so deletion of a wardrobe item is structurally incapable of touching this table. The cost — a stale item id can point at nothing — is the intended trade, and readers must tolerate it.
- **`outfit_fingerprint`** is `sha256(":".join(sorted(item_ids)))` as lowercase hex, computed in Python (§5.3), order-independent so the same three garments always fingerprint identically regardless of assembly order. This is what makes SS-023's "regenerate must not return the same 3 outfits" AC answerable with an index lookup instead of an array comparison across millions of rows. The regex CHECK makes a wrong-length or uppercase hash a write error, not a silently unmatched key.
- **`total_score NUMERIC(6,5)`, not `REAL`/`DOUBLE`.** `ScoredCandidate.total_score` is `float` bounded `[0.0, 1.0]` (`styling_rules_types.py:155`); `NUMERIC` avoids float drift when these are averaged over millions of rows to answer "did turning the dial up help", which is the entire point of the table. The bounds CHECK mirrors the Pydantic `Field(ge=0.0, le=1.0)` so the DB and the model cannot disagree.
- **`rule_scores JSONB`** stores `ScoredCandidate.rule_scores` verbatim — a JSON array of `{"rule": str, "score": float, "explanation": str}` objects (`styling_rules_types.py:137-145`). Stored as-is rather than exploded into a fourth table: it is written once, read as a whole, never filtered on individually, and a per-rule table would multiply an already-7.3M-rows/month surface by the rule count. `gap_flags`/`strategy` likewise come straight off `ScoredCandidate`/the engine.
- **`UNIQUE (session_id, rank)`** makes "rank" mean something. Without it a retried batch insert produces two rank-1 rows and the ordering the AC asks for is fiction.
- **`user_id` is denormalised from the session** — justified in §3.5, and *derived by trigger*, never trusted from the writer.

Indexes, each tied to one named query — no speculative indexing except the one flagged as such:

```sql
CREATE INDEX idx_suggestion_impressions_user_created
  ON suggestion_impressions (user_id, created_at DESC);            -- "what did we show this user recently" (anti-repetition); also the RLS predicate's index
CREATE INDEX idx_suggestion_impressions_user_fingerprint
  ON suggestion_impressions (user_id, outfit_fingerprint, created_at DESC);  -- "have we shown this exact outfit to this user recently" (SS-023 regenerate AC)
CREATE INDEX idx_suggestion_impressions_session
  ON suggestion_impressions (session_id);                          -- session -> impressions join AND the FK's cascade-delete path
CREATE INDEX idx_suggestion_impressions_item_ids
  ON suggestion_impressions USING GIN (item_ids);                  -- "which impressions featured item X" (per-item novelty, SS-035)
```

Two notes the Developer must not lose:

- **`idx_suggestion_impressions_session` is load-bearing for retention, not just for joins.** Postgres does *not* automatically index the referencing side of a foreign key, and the retention purge (§3.6) deletes sessions and relies on `ON DELETE CASCADE` to remove impressions. Without this index every cascaded session delete sequentially scans a 44M-row table. This index is the difference between a nightly purge that finishes and one that does not.
- **The GIN index on `item_ids` is the one forward-looking index here**, for SS-035's per-item novelty scoring rather than a query this ticket ships. It is included anyway because creating it now, on an empty table, is free, whereas creating it on 44M rows later requires `CREATE INDEX CONCURRENTLY` against a live database. If SS-035 lands without needing it, drop it then.

### 3.4 `suggestion_outcomes`

```sql
CREATE TABLE suggestion_outcomes (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  impression_id      UUID NOT NULL REFERENCES suggestion_impressions(id) ON DELETE CASCADE,
  user_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  outcome_type       TEXT NOT NULL CHECK (outcome_type IN
                       ('saved','worn','dismissed','shuffled_away','shared')),
  outfit_id          UUID REFERENCES outfits(id) ON DELETE SET NULL,
  dedupe_key         TEXT,
  client_occurred_at TIMESTAMPTZ,
  metadata           JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_suggestion_outcomes_dedupe
  ON suggestion_outcomes (impression_id, dedupe_key) WHERE dedupe_key IS NOT NULL;
CREATE INDEX idx_suggestion_outcomes_impression_order
  ON suggestion_outcomes (impression_id, created_at, id);
CREATE INDEX idx_suggestion_outcomes_user_type_created
  ON suggestion_outcomes (user_id, outcome_type, created_at DESC);
```

- **The five `outcome_type` values are the AC's list, verbatim and enumerated.** No `NOT NULL` `outfit_id`: `dismissed`/`shuffled_away` never produce an outfit row.
- **`outfit_id … ON DELETE SET NULL`, deliberately not `CASCADE`.** If a user later deletes the outfit they saved, the *fact that they saved it* is the historical truth this table exists to hold. Cascading would delete the strongest positive signal in the dataset every time someone cleans up their outfit list. Contrast the `ON DELETE CASCADE` on `user_id`, which is the right privacy default pre-launch (a user deletion erases their behavioural log) and matches every other `users`-referencing table in `001_initial.sql`.
- **Ordering (the AC's "multiple outcomes per impression are permitted and ordered").** The canonical order is `ORDER BY COALESCE(client_occurred_at, created_at), created_at, id` — a *total* order (`id` is unique, so ties resolve deterministically if arbitrarily). `client_occurred_at` leads because an offline-queued action's real time is the client's, not the server's; `created_at` is the server's `now()`, which is transaction-start time and therefore identical for two rows written in one transaction. Recorded here so two callers do not invent two different orderings. Documented in a `COMMENT ON TABLE`.
- **`dedupe_key` + the partial unique index** is the idempotency seam. Log-and-continue means retries are expected; without a dedupe key a retried "save" records two `saved` outcomes and inflates the very metric the tuning dial reads. `NULL` is allowed (and unconstrained) because genuine repeat actions are permitted — the AC's own "dismisses then later saves the same outfit → both outcomes recorded" case must not be blocked. The caller supplies a `dedupe_key` when it is retrying a specific action, and omits it when the action is genuinely new.

### 3.5 RLS — read-own, and **no write policy at all**

```sql
ALTER TABLE suggestion_impressions ENABLE ROW LEVEL SECURITY;
ALTER TABLE suggestion_outcomes    ENABLE ROW LEVEL SECURITY;

CREATE POLICY "user_reads_own_impressions" ON suggestion_impressions
  FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "user_reads_own_outcomes" ON suggestion_outcomes
  FOR SELECT USING (auth.uid() = user_id);

-- DELIBERATELY no INSERT/UPDATE/DELETE policy on either table, for any role.
-- With RLS enabled and no matching policy, every write from anon/authenticated
-- is denied; service_role bypasses RLS. ABSENCE OF A POLICY *IS* THE
-- WRITE-PROTECTION MECHANISM -- the 007_occasions_registry.sql:91-105 /
-- 010_app_config.sql shape. Do not "fix" this by adding a permissive write
-- policy.
```

**And the non-additive part — narrowing `suggestion_sessions`' shipped policy:**

```sql
-- 001_initial.sql:172 created "user_owns_sessions" as FOR ALL, i.e. clients can
-- INSERT/UPDATE/DELETE their own session rows today. AC #4 requires read-only.
DROP POLICY IF EXISTS "user_owns_sessions" ON suggestion_sessions;
CREATE POLICY "user_reads_own_sessions" ON suggestion_sessions
  FOR SELECT USING (auth.uid() = user_id);
-- ROLLBACK: DROP POLICY "user_reads_own_sessions"; CREATE POLICY "user_owns_sessions"
--           ON suggestion_sessions FOR ALL USING (auth.uid() = user_id);
```

This is the only statement in `013` that removes a capability, so it gets the scrutiny `docs/OPERATOR_RULEBOOK.md` §C2 asks for:

- **Nothing breaks.** `[VERIFIED 2026-07-30, ripgrep over the working tree]` no code in `mobile/`, `backend/`, or `supabase/functions/` reads or writes `suggestion_sessions` other than the two Edge Functions' `count` queries — and those run with `SUPABASE_SERVICE_ROLE_KEY`, which bypasses RLS entirely. There is no client write path to remove because there is no client write path.
- **Why it matters that we do remove it.** Under `FOR ALL`, an authenticated user can `DELETE` their own session rows — which now `ON DELETE CASCADE`s their impressions and outcomes, i.e. the client could erase the behavioural record the tuning dial and personalization depend on. They could also `INSERT` forged sessions with `cost_incurred = true` and drive the cost monitor's alert. Both are the "accounting data *about* a user, not authored *by* them" argument SS-029 §3.5 already made for `ai_cost_ledger`, applied to a policy that predates it.
- **Reads stay exactly as they are.** A user can still `SELECT` their own sessions; only writes are withdrawn. Fully reversible by the rollback statement above.
- `[trained-knowledge, consistent with SS-025/SS-026's precedent — not re-verified this session]` `service_role` bypasses RLS via the `bypassrls` role attribute. QA proves both directions empirically in §8, never by assumption.

**Why `user_id` is denormalised onto both new tables, and derived by trigger.** The RLS predicate has to reach a user. The alternative — `EXISTS (SELECT 1 FROM suggestion_sessions s WHERE s.id = session_id AND s.user_id = auth.uid())` — evaluates a correlated subquery per candidate row on a 44M-row table; a direct `auth.uid() = user_id` is an index seek on `idx_suggestion_impressions_user_created`. But a denormalised owner column that the *writer* supplies is a data-leak vector: one wrong `user_id` and user A can read a row describing user B's wardrobe items. So the column is not trusted, it is **derived**:

```sql
CREATE OR REPLACE FUNCTION public.suggestion_impression_set_user_id()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  SELECT s.user_id INTO NEW.user_id
    FROM suggestion_sessions s WHERE s.id = NEW.session_id;
  IF NEW.user_id IS NULL THEN
    RAISE EXCEPTION 'suggestion_impressions.user_id is not derivable: session % has no user_id', NEW.session_id;
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.suggestion_outcome_set_user_id()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  SELECT i.user_id INTO NEW.user_id
    FROM suggestion_impressions i WHERE i.id = NEW.impression_id;
  IF NEW.user_id IS NULL THEN
    RAISE EXCEPTION 'suggestion_outcomes.user_id is not derivable: impression % not found', NEW.impression_id;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_suggestion_impressions_set_user_id
  BEFORE INSERT ON suggestion_impressions
  FOR EACH ROW EXECUTE FUNCTION public.suggestion_impression_set_user_id();
CREATE TRIGGER trg_suggestion_outcomes_set_user_id
  BEFORE INSERT ON suggestion_outcomes
  FOR EACH ROW EXECUTE FUNCTION public.suggestion_outcome_set_user_id();
```

- The trigger **overwrites** whatever the writer sent, so a wrong `user_id` is structurally impossible rather than merely unlikely. The adapter still sends it (a self-describing insert, and it keeps the `NOT NULL` satisfiable if the trigger is ever dropped), and §7.1 has a test asserting a *deliberately wrong* `user_id` is corrected — that test is what pins this property against a future "optimisation" that removes the trigger.
- **Not `SECURITY DEFINER`**, unlike `008`'s normalisation functions. Those needed elevation specifically to write a *different* table (`occasion_unknown_tags`) from inside a trigger. These only read a row the writer (always `service_role`, which bypasses RLS) can already read. Least privilege — same reasoning `010_app_config.sql`'s touch-trigger recorded.
- Cost: one primary-key lookup per inserted row, i.e. 5–8 per suggestion request. Accepted, and noted as the price of making the leak impossible.
- `BEFORE INSERT` only, not `BEFORE UPDATE`: nothing updates these tables (append-only logs, no write policy for anyone), so an `UPDATE` branch would be untested dead code.

### 3.6 Retention — 180 days rolling, config-driven, cascade-purged

**Decision: scheduled batched delete, not partitioning.** This is the Architect's call per the ticket, so here is the reasoning rather than just the outcome.

Partitioning is the textbook answer at 44M rows, and I rejected it for a specific structural reason, not for effort: `suggestion_outcomes` has a foreign key to `suggestion_impressions`, and a range-partitioned parent forces the partition key into its primary key, hence into the FK — so outcomes would have to carry the impression's `created_at`. Worse, an outcome legitimately arrives weeks after its impression (a user wears a saved outfit later), so outcome and impression land in *different* monthly partitions, and dropping the impression partition then either fails on the dependent rows or orphans them — breaking the ticket's own "purge as a unit" edge case with the very mechanism chosen to satisfy it.

The delete-based purge satisfies "purge as a unit" **structurally instead of procedurally**: `suggestion_impressions.session_id` and `suggestion_outcomes.impression_id` both cascade, so deleting one session row atomically removes its impressions and their outcomes in the same transaction. Nothing can be orphaned, because nothing is deleted independently.

```sql
-- The retention window lives in SS-026's app_config so it is product-adjustable
-- without a migration (BL-108: "the number is the user's"). Coded default 180,
-- clamped to [30, 730], degrading to 180 on a missing or malformed row -- the
-- same clamp-and-degrade posture as AppConfigService._clamp_ttl.
CREATE OR REPLACE FUNCTION public.suggestion_log_retention_days()
RETURNS INTEGER LANGUAGE plpgsql STABLE AS $$
DECLARE v INTEGER;
BEGIN
  BEGIN
    SELECT (value->>'days')::int INTO v FROM app_config
      WHERE key = 'suggestion_log_retention_days';
  EXCEPTION WHEN others THEN
    v := NULL;   -- malformed JSON / non-numeric text must never break the purge
  END;
  IF v IS NULL THEN v := 180; END IF;
  RETURN LEAST(730, GREATEST(30, v));
END;
$$;

CREATE OR REPLACE FUNCTION public.purge_suggestion_logs(
  p_batch_size INTEGER DEFAULT 5000,
  p_max_batches INTEGER DEFAULT 200
) RETURNS TABLE (sessions_deleted BIGINT, retention_days INTEGER, cutoff TIMESTAMPTZ)
LANGUAGE plpgsql AS $$
DECLARE
  v_days   INTEGER := public.suggestion_log_retention_days();
  v_cutoff TIMESTAMPTZ := now() - make_interval(days => v_days);
  v_total  BIGINT := 0;
  v_n      BIGINT;
  i        INTEGER := 0;
BEGIN
  LOOP
    i := i + 1;
    DELETE FROM suggestion_sessions
     WHERE id IN (SELECT id FROM suggestion_sessions
                   WHERE created_at < v_cutoff
                   ORDER BY created_at
                   LIMIT p_batch_size);
    GET DIAGNOSTICS v_n = ROW_COUNT;
    v_total := v_total + v_n;
    EXIT WHEN v_n < p_batch_size OR i >= p_max_batches;
  END LOOP;
  RAISE LOG 'purge_suggestion_logs: deleted % sessions older than % (retention % days)',
    v_total, v_cutoff, v_days;
  RETURN QUERY SELECT v_total, v_days, v_cutoff;
END;
$$;
```

- **Batched, with a hard ceiling.** `5000 × 200 = 1M` sessions per invocation, so a nightly run cannot take an unbounded lock or blow up WAL; a backlog drains over consecutive nights instead. `ORDER BY created_at` makes it oldest-first, which needs `idx_suggestion_sessions_created` (below).
- Not `SECURITY DEFINER`: the only callers are `pg_cron`'s job owner and `service_role`, both of which already bypass RLS on `app_config` and can delete.

Scheduling — and this is where honesty matters more than confidence:

```sql
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
    PERFORM cron.schedule('purge_suggestion_logs', '0 22 * * *',
                          'SELECT public.purge_suggestion_logs();');
  ELSE
    RAISE WARNING 'pg_cron is not installed: purge_suggestion_logs() exists but is NOT SCHEDULED. Retention is unenforced until a scheduler is wired -- see SS-033-design.md 3.6 fallback.';
  END IF;
END $$;
```

`22:00 UTC = 03:30 IST`, off-peak for an India-first app. `[trained-knowledge — MUST be verified by the Developer, not assumed: (a) whether pg_cron is enabled on project mefpfykuinasgkpfhmzk at all, (b) whether cron.schedule(jobname, schedule, command) upserts by name on the installed pg_cron version, (c) whether the migration's role may call it. Per BL-001's lesson an unverified platform claim that looks authoritative is the failure mode.]` The `DO` block is written so a missing extension produces a loud warning rather than a failed migration, and the `IF EXISTS` guard means the fallback path is a documented decision rather than a broken deploy.

**Fallback if `pg_cron` is unavailable:** a `purge-suggestion-logs` Edge Function that calls `purge_suggestion_logs()` as an RPC with the service-role key, scheduled the same way `cost-monitor`/`weekly-report` are. Which raises its own finding: **nothing in this repo configures a schedule for those two functions** `[VERIFIED 2026-07-30 — no cron config in supabase/config.toml, no schedule in .github/workflows, no supabase/functions/*/deno.json]`, so whether they run at all is unknown and lives only in someone's dashboard. Logged as `BL-113`; it directly determines whether the fallback path is real. **AC #6 ("a retention window is defined, documented, and enforced") is therefore not satisfiable by code review alone** — see §9 Q1.

Seed row and the purpose-limitation record:

```sql
INSERT INTO app_config (key, value, scope, description, updated_by) VALUES
  ('suggestion_log_retention_days', '{"days": 180}'::jsonb, 'server',
   'Rolling retention window (days) for suggestion_sessions and its cascaded suggestion_impressions/suggestion_outcomes rows. Enforced nightly by public.purge_suggestion_logs(). Clamped to [30, 730] in SQL; a missing or malformed value degrades to 180. Stated purpose limitation: suggestion-quality measurement and personalization only. Product-adjustable via UPDATE, no migration needed (BL-108).',
   'migration:013_suggestion_impressions');

COMMENT ON TABLE suggestion_impressions IS
  'One row per candidate outfit shown to a user (SS-033). Append-only; no client write path. '
  'PURPOSE LIMITATION: suggestion-quality measurement and personalization only. RETENTION: '
  'rolling window from app_config.suggestion_log_retention_days (default 180 days), enforced by '
  'public.purge_suggestion_logs(). India DPDP Act applicability is UNVERIFIED -- see BL-108.';

COMMENT ON TABLE suggestion_outcomes IS
  'User reactions to a suggestion_impressions row (SS-033): saved/worn/dismissed/shuffled_away/'
  'shared. Multiple rows per impression permitted; canonical order is '
  'COALESCE(client_occurred_at, created_at), created_at, id. Purged as a unit with its parent '
  'impression via ON DELETE CASCADE. Same purpose limitation and retention as '
  'suggestion_impressions.';
```

The DPDP point is stated as unverified **in the schema itself**, so the gap travels with the data instead of only living in a backlog row. `[trained-knowledge — MUST be verified against the current statutory text before the first production row is written]` India's DPDP Act imposes consent, purpose-limitation and storage-limitation obligations that plausibly cover per-user behavioural scoring data; neither the applicability nor the adequacy of a 180-day window has been checked against the statute. `BL-108` stays **Active** for exactly this reason.

New indexes on `suggestion_sessions`, each named to a query:

```sql
CREATE INDEX idx_suggestion_sessions_costed_created
  ON suggestion_sessions (created_at DESC) WHERE cost_incurred;   -- cost-monitor's daily billable count
CREATE INDEX idx_suggestion_sessions_created
  ON suggestion_sessions (created_at);                            -- weekly-report total + the purge's oldest-first scan
CREATE INDEX idx_suggestion_sessions_user_created
  ON suggestion_sessions (user_id, created_at DESC);              -- per-user session history; the RLS SELECT predicate's index
```

The first is a **partial** index matching `cost-monitor`'s filter exactly, so the fix in §3.1/§7.2 is an index-only count rather than a growing table scan every hour.

---

## 4. Concrete values to use, not invent

| Thing | Value | Source |
|---|---|---|
| Migration filename | `013_suggestion_impressions.sql` | raw ticket, Technical Notes (renumbered 2026-07-31) |
| Effort tiers | `E0`, `E1`, `E2`, `E3`, `E4` (`E2` = launch default) | `STYLING-ENGINE-V2.md` §6 |
| Plan tiers | `free`, `premium`, `premium_annual` | `001_initial.sql`'s `plan_tier` enum |
| Outcome types | `saved`, `worn`, `dismissed`, `shuffled_away`, `shared` | raw ticket AC #3 |
| Zero-cost reasons | `cache_hit`, `degraded_e0`, `rules_only`, `budget_denied`, `no_provider_call` | my enumeration of the ticket's edge cases — fixed here, do not extend without a migration |
| Retention window | `180` days rolling, clamped `[30, 730]` | user decision 2026-07-30, `BL-108` |
| Purge schedule | `0 22 * * *` UTC = 03:30 IST | my call (off-peak, India-first) |
| Candidate shape consumed | `ScoredCandidate{item_ids, category_labels, total_score, rule_scores[{rule,score,explanation}], gap_flags}` | `backend/services/styling_rules_types.py:148-157` — **already shipped, do not redefine** |
| Fingerprint | `sha256(":".join(sorted(item_ids)))`, lowercase hex, 64 chars | §5.3 |
| Config-snapshot hash | `sha256(json.dumps(values, sort_keys=True, separators=(",",":")).encode())`, lowercase hex | §5.3 |
| `ENGINE_VERSION` | `"rules-v1"` | my call — see below |
| Shared Supabase project | `mefpfykuinasgkpfhmzk` | `BL-110`, `SS-025-design.md` |

**`ENGINE_VERSION` is mine, and that is worth saying out loud.** No engine-version constant exists anywhere in the codebase today `[VERIFIED 2026-07-30 — no VERSION/version symbol in backend/services/styling_rules_engine.py]`. The format is `<engine>-v<major>`; the value ships as `"rules-v1"`, describing SS-027's rules engine, which is the only engine that exists. It lives as a module constant in `backend/services/suggestion_log_service.py` so there is exactly one definition. SS-035 bumps it when the tuning dial changes scoring behaviour — a version that never changes is worse than no version at all, because it makes two incomparable datasets look comparable.

---

## 5. Backend shape

### 5.1 Port (`backend/adapters/interfaces.py`, additions only)

```python
@dataclass(frozen=True)
class SuggestionSessionLog:
    user_id: str
    occasion: str | None = None            # normalised again by the 008 trigger -- see §6.3
    weather_data: dict[str, Any] | None = None
    tier: str | None = None                # snapshot of users.plan_tier at request time
    effort_tier: str | None = None         # 'E0'..'E4'
    engine_version: str | None = None
    config_snapshot_hash: str | None = None
    candidate_count: int = 0
    cache_key: str | None = None
    request_id: str | None = None          # joins SS-029's ai_cost_ledger.request_id
    latency_ms: int | None = None
    cost_incurred: bool = True             # default matches the column default: fail loud
    zero_cost_reason: str | None = None    # REQUIRED when cost_incurred is False


@dataclass(frozen=True)
class SuggestionImpressionLog:
    rank: int                              # 1-based; unique within a session
    item_ids: list[str]
    outfit_fingerprint: str                # 64-char lowercase hex, see §5.3
    total_score: float                     # [0.0, 1.0]
    rule_scores: list[dict[str, Any]] = field(default_factory=list)
    gap_flags: list[str] = field(default_factory=list)
    is_exploration: bool = False
    strategy: str | None = None


@dataclass(frozen=True)
class SuggestionOutcomeLog:
    impression_id: str
    outcome_type: str                      # one of the five AC values
    outfit_id: str | None = None
    dedupe_key: str | None = None
    client_occurred_at: str | None = None   # ISO-8601; clamped by the adapter, see §6.7
    metadata: dict[str, Any] = field(default_factory=dict)


class ISuggestionLogRepository(ABC):
    """(SS-033) ALWAYS uses service_role -- the second port in this file to do
    so after IAppConfigRepository, and for a different reason: these tables
    have NO write policy for any client role at all (design §3.5), because they
    are accounting-style data ABOUT a user rather than authored BY them, and
    the write can outlive the caller's JWT (it happens in a BackgroundTasks
    callback after the response was sent).

    NOTHING ON THIS PORT MAY RAISE. A logging failure must never fail the
    user's suggestion request (design §5.4). Failures are logged and swallowed;
    write methods return None and read methods return empty.
    """

    @abstractmethod
    async def log_session(
        self,
        session: SuggestionSessionLog,
        impressions: Sequence[SuggestionImpressionLog],
    ) -> str | None:
        """Write ONE session row and ALL of its impression rows, then return
        the new session id (or None on any failure). Session and impressions
        are one call, not two, so a caller structurally cannot half-log a
        request. MUST NEVER RAISE."""

    @abstractmethod
    async def log_outcome(self, outcome: SuggestionOutcomeLog) -> str | None:
        """Append one outcome row; returns its id, or None on failure or on a
        dedupe_key conflict (an already-recorded action -- not an error).
        MUST NEVER RAISE."""

    @abstractmethod
    async def recent_impressions(
        self, *, user_id: str, since: datetime, limit: int = 200
    ) -> list[dict[str, Any]]:
        """Recent impressions for anti-repetition / novelty scoring, newest
        first. Returns [] on failure -- 'no history' degrades to 'no
        repetition penalty', never to a failed suggestion request. MUST NEVER
        RAISE."""
```

`log_session` taking both the session and its impressions in one call is the single most important shape decision here: it is what makes "a request records exactly one session row and N impression rows" a property of the interface rather than a convention two callers must remember.

### 5.2 Adapter (`backend/adapters/suggestion_log_repository.py`)

Mirrors `SupabaseAppConfigRepository` exactly (`service_role` client via `acreate_client`, no `.postgrest.auth(jwt)` — the service-role key *is* the credential), with the module docstring recording the deviation in the same explicit style. Behaviour:

1. `INSERT` the session with `.select("id").single()` to get the generated `id` back.
2. Build all impression rows with that `session_id`, then **one batched `INSERT`** (a single PostgREST call for 5–8 rows, not N round-trips).
3. If step 1 fails: log `suggestion_session_log_failed` at ERROR, return `None`, attempt no impressions.
4. If step 2 fails: log `suggestion_impression_log_failed` at ERROR with the session id, return the session id anyway (the session row is real and the cost monitor must still see it). **Do not** attempt to delete the session to "keep things tidy" — a partial log is more truthful than a deleted one, and a delete could fail too.
5. Every method wraps its body in `try/except Exception`, logs, and returns `None`/`[]`. No exception escapes, ever.
6. `client_occurred_at` more than 5 minutes in the future is clamped to `now()` and logged at WARNING (`suggestion_outcome_clock_skew`) — a skewed client clock must not silently reorder the outcome sequence, and must not fail the write.

### 5.3 Service (`backend/services/suggestion_log_service.py`)

Pure, no I/O of its own beyond delegating to the port. Owns:

- `ENGINE_VERSION = "rules-v1"` (§4).
- `outfit_fingerprint(item_ids: Sequence[str]) -> str` = `hashlib.sha256(":".join(sorted(item_ids)).encode()).hexdigest()`. Order-independent by construction. Duplicate ids within one candidate are **not** de-duplicated (a genuine duplicate is a bug worth seeing in the data, not one worth hiding in a hash).
- `config_snapshot_hash(values: Mapping[str, Any]) -> str` = `hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()`. Computed from the **one** `AppConfigSnapshot` the request already holds (SS-026's "one request, one snapshot" rule — never call `.snapshot()` a second time to hash it).
- `impressions_from_candidates(candidates: Sequence[ScoredCandidate], *, exploration_ranks: Container[int] = ()) -> list[SuggestionImpressionLog]` — 1-based ranks in the order the engine returned them, `rule_scores` serialised via `model_dump()`, `is_exploration` set by rank membership.
- `log_suggestion(...)` — the single entry point SS-020 will call. Builds the session log (including `cost_incurred`/`zero_cost_reason`), maps candidates, delegates to `log_session`, and returns the session id or `None`. Wrapped in its own `try/except` so even a mapping bug (e.g. a malformed candidate) cannot propagate into the caller.

### 5.4 Log-and-continue, by construction rather than by discipline

Three layers, strongest first:

1. **Structural.** SS-020 will dispatch suggestion generation via `BackgroundTasks` (CLAUDE.md's "never call AI APIs synchronously"), so logging runs after the response was sent — there is no user request left to fail.
2. **Contractual.** Every `ISuggestionLogRepository` method is documented never-raising, the adapter wraps every body, and the service wraps its own mapping. §7.1 has a test that makes the repository raise and asserts the caller still gets its result.
3. **Design.** No caller ever *needs* the return value to proceed. `log_session` returning `None` means "no outcomes can be attached to this request" — degraded analytics, never a degraded suggestion.

Deliberately **no** durable queue or retry. `BL-056`/`BL-074` already own the in-memory-`BackgroundTasks`-has-no-retry gap and `BL-074`'s directive is to fix it once, centrally, rather than build a second one-off mechanism. Followed, same as SS-029 §4.3. The honest consequence: a dropped log row is permanently lost, and since impressions cannot be backfilled, that data is gone. Stated plainly rather than papered over.

---

## 6. Edge cases

Every case from the ticket, carried forward with its resolution, plus what the current codebase adds.

### From the ticket

1. **Log write fails but the suggestion succeeded** → never fails the request. §5.4's three layers; tested by `test_repository_raise_does_not_break_the_caller` (§7.1).
2. **A cache hit still records a session + impressions, with a zero-cost marker, but must be excluded from the cost proxy** → `cost_incurred = false`, `zero_cost_reason = 'cache_hit'`, enforced consistent by the paired CHECK (§3.1); `cost-monitor` filters on `cost_incurred` (§7.2). Cache effectiveness stays visible because the session row still exists and its reason is queryable.
3. **E0/degraded (both providers down, rules-only narration) still records impressions** → `effort_tier = 'E0'`, `cost_incurred = false`, `zero_cost_reason = 'degraded_e0'` (or `'rules_only'` when the engine ran but no LLM was called). This is the data that proves the offline path works, so it is logged identically to a paid path in every respect except the cost marker.
4. **The same candidate shown twice across two sessions → two rows, not a dedupe.** Nothing in the schema prevents it: `UNIQUE (session_id, rank)` is scoped to one session, and `outfit_fingerprint` is indexed but not unique. Repetition is the signal being measured; §7.1 has an explicit test that two sessions showing the same fingerprint produce two rows.
5. **An impression whose items are later deleted survives** → `item_ids UUID[]` with no foreign key at all (§3.3), so a `wardrobe_items` delete is structurally incapable of cascading here. Readers must tolerate ids that resolve to nothing.
6. **Dismiss then later save the same outfit → both recorded, ordered** → no unique constraint on `(impression_id, outcome_type)`; the canonical ordering is defined in §3.4 and asserted in §7.1.
7. **Retention purge must not orphan outcomes whose impression aged out** → purge deletes *sessions*; `ON DELETE CASCADE` removes impressions and their outcomes in the same transaction (§3.6). Orphaning is impossible, not merely avoided.

### Found in the current codebase

8. **`suggestion_sessions`' shipped RLS policy is `FOR ALL`, not read-only** (`001_initial.sql:172`) — a client can currently insert/update/delete its own session rows, and post-SS-033 a delete would cascade away its own impressions. Narrowed in §3.5; the one non-additive statement in the migration.
9. **SS-025's normalisation trigger already fires on `suggestion_sessions`** (`008:83-85`), rewriting `NEW.occasion` and logging unknown slugs to `occasion_unknown_tags`. The value read back may differ from the value written; the adapter must not assert round-trip equality, and an unknown occasion slug is written (not dropped) plus recorded — expected behaviour, not a defect. §7.1 asserts an alias round-trips to its canonical key.
10. **`suggestion_sessions.user_id` is nullable** (`001_initial.sql:99`, no `NOT NULL`). A session written without a user makes the `user_id`-derivation trigger raise, failing the impression insert. Correct behaviour — an ownerless impression row has no RLS predicate and would be invisible-or-leaky. The adapter's never-raises wrapper turns it into a logged error, and §7.1 tests it.
11. **`suggestion_sessions.suggestions` and `accepted_outfit_id` exist in the committed `mobile/types/supabase.ts`** (lines 367-395), so dropping them would invalidate a shipped type. §3.2's deprecate-don't-drop decision.
12. **No CI job runs Deno tests** (`BL-042`). The AC-mandated cost-monitor fixture test is a `deno test` file that CI will not execute. QA must run it locally and say so plainly rather than reporting a green CI as coverage (§7.3, §8).
13. **Neither `cost-monitor` nor `weekly-report` has a schedule defined anywhere in the repo** `[VERIFIED 2026-07-30]`, so the "schedule an Edge Function" fallback for the purge rests on an unverified assumption about the Supabase dashboard. `BL-113`.
14. **Three sibling Wave 1.5 migrations target the same live project** (`BL-110`). `supabase db diff --linked` will report their objects as drift. Report the exact diff; never loosen the CI filter (`BL-060`'s standing directive). §8.
15. **A future `plan_tier` value must not fail an audit-log write** → `tier` gets a shape regex, not a value enum (§3.1 decision 2).
16. **A client clock ahead of the server** would reorder outcomes → clamped in the adapter, logged, never rejected (§5.2 item 6).
17. **A retried outcome write** would double-count a save → optional `dedupe_key` + partial unique index; a conflict returns `None`, which the caller treats as success-already-recorded, not as an error (§3.4).

---

## 7. Test plan

Backend Pytest (+ `pytest-asyncio`), Deno for Edge Functions, per CLAUDE.md. Each AC is named against the test that covers it.

### 7.1 `backend/tests/test_suggestion_log_service.py` (new)

Fake `ISuggestionLogRepository` recording calls; no network.

| Test | Asserts | AC |
|---|---|---|
| `test_one_request_produces_exactly_one_session_and_n_impressions` | one `log_session` call, one session log, `len(impressions) == len(candidates)`, `candidate_count` matches | 1, 2 |
| `test_session_carries_occasion_weather_tier_effort_engine_and_config_hash` | all six AC-named fields populated from inputs | 1 |
| `test_impression_carries_item_ids_total_score_rule_breakdown_rank_and_exploration_flag` | the AC's five fields, mapped from a real `ScoredCandidate` | 2 |
| `test_ranks_are_one_based_and_follow_engine_order` | ranks `1..n` in the candidates' order | 2 |
| `test_exploration_ranks_flag_only_the_named_ranks` | `is_exploration` true only for the given ranks | 2 |
| `test_fingerprint_is_order_independent` | the same ids in three orders → one hash | — |
| `test_fingerprint_differs_for_different_item_sets` | one substituted id → different hash | — |
| `test_fingerprint_is_64_char_lowercase_hex` | matches the column's CHECK regex | 2 |
| `test_config_snapshot_hash_is_stable_across_key_order` | two dicts, same pairs, different insertion order → one hash | 1 |
| `test_config_snapshot_hash_changes_when_a_value_changes` | one changed value → different hash (otherwise the dial is unmeasurable) | 1 |
| `test_cache_hit_marks_cost_not_incurred_with_reason` | `cost_incurred=False`, `zero_cost_reason='cache_hit'` | 5 |
| `test_degraded_e0_marks_cost_not_incurred_and_still_logs_impressions` | impressions still written on the ₹0 path | 2, 5 |
| **`test_repository_raise_does_not_break_the_caller`** | repository raises → `log_suggestion` returns `None`, logs at ERROR, **does not propagate** | **7** |
| `test_malformed_candidate_does_not_propagate` | a candidate missing `rule_scores` → logged, no exception | 7 |
| `test_engine_version_constant_is_non_empty_and_versioned` | matches `^[a-z0-9_]+-v\d+$` (drift guard on §4's format) | 1 |
| `test_zero_cost_reason_required_when_cost_not_incurred` | service refuses to build a contradictory pair (mirrors the DB CHECK in Python so the failure is early and testable without a DB) | 5 |

### 7.2 `backend/tests/test_suggestion_log_repository.py` (new)

Fake `AsyncClient` builder, same style as `test_app_config_repository.py`/`test_occasion_repository.py`.

| Test | Asserts |
|---|---|
| `test_uses_service_role_key_not_anon_key` | pins §3.5's deviation so a later pass cannot "fix" it back to anon+JWT |
| `test_session_insert_then_batched_impression_insert` | exactly two PostgREST calls for 8 impressions, not nine |
| `test_impressions_carry_the_returned_session_id` | every row's `session_id` is the id the session insert returned |
| `test_session_insert_failure_returns_none_and_writes_no_impressions` | logs `suggestion_session_log_failed`, no impression call |
| `test_impression_insert_failure_still_returns_the_session_id` | §5.2 item 4; session is not rolled back or deleted |
| `test_log_session_never_raises_on_db_error` | the never-raises contract |
| `test_log_outcome_never_raises_and_returns_none_on_dedupe_conflict` | a conflict is success-already-recorded, not an error |
| `test_recent_impressions_returns_empty_list_on_db_error` | read failure degrades to no-penalty |
| `test_future_client_occurred_at_is_clamped_and_logged` | >5 min ahead → clamped to now, WARNING, write still happens |
| `test_outcome_row_includes_every_ac_named_field` | `impression_id`, `outcome_type`, ordering fields, metadata |

### 7.3 Edge Functions (Deno) — `supabase/functions/_shared/suggestionSessions.test.ts` + `cost-monitor/index.test.ts` (new)

`cost-monitor/index.ts` is refactored to the `get-upload-url/index.ts` seam (`export async function handleRequest(req, deps)` + `Deno.serve((req) => handleRequest(req, realDeps))`), because Deno has no `jest.mock()` for `esm.sh` imports and a fake Supabase client must be injected.

| Test | Asserts | AC |
|---|---|---|
| **`test_daily_count_excludes_a_cache_hit_session`** | fixture: 3 sessions today, one with `cost_incurred=false, zero_cost_reason='cache_hit'` → the billable count is **2**, not 3. **This is AC #5's literal requirement.** | **5** |
| `test_daily_count_excludes_a_degraded_e0_session` | the second ₹0 path | 5 |
| `test_billable_filter_is_applied_as_eq_cost_incurred_true` | the fake client records `.eq("cost_incurred", true)` — a structural guard against the filter being dropped later | 5 |
| `test_threshold_compares_against_the_billable_count_not_the_total` | 3 total / 2 billable with threshold 2 → **not** over limit | 5 |
| `test_slack_copy_names_the_billable_count_and_reports_the_total_separately` | the message cannot be misread as "all sessions" | 5 |
| `test_supabase_error_still_returns_500` | existing behaviour unchanged (regression guard) | — |
| `test_shared_helper_is_the_only_place_the_predicate_is_defined` | both functions import from `_shared/suggestionSessions.ts`; the string `cost_incurred` appears in neither `index.ts` | 5 |

`weekly-report/index.ts` change and its rationale: this function's `aiSessions` is an **engagement** metric ("AI outfit sessions"), not a cost figure, so the total is arguably the right number and blindly filtering it would silently change a reported business metric. The fix is additive — keep the total, add `billableAiSessions` via the shared helper, and render both rows in the email ("AI outfit sessions" / "of which billable"). A Deno test asserts both counts are queried and that the total is unfiltered. Recorded as a deliberate asymmetry with `cost-monitor`, not an oversight.

### 7.4 `backend/tests/test_db_schema.py` (modify — live-DB-gated, `BL-005`)

Add `suggestion_impressions` and `suggestion_outcomes` to `EXPECTED_TABLES`, plus:

- the nine new `suggestion_sessions` columns exist with the right types, and `cost_incurred` is `NOT NULL DEFAULT true`;
- the six new CHECK constraints exist by name, and the cost-marker consistency CHECK actually rejects `cost_incurred=false, zero_cost_reason=NULL`;
- `suggestions` and `accepted_outfit_id` both carry a `COMMENT` starting with `DEPRECATED` (the machine-checkable half of §3.2);
- RLS is enabled on both new tables, each has **exactly one** policy, it is `FOR SELECT`, and **zero** INSERT/UPDATE/DELETE policies exist for `anon`/`authenticated`;
- `suggestion_sessions` has policy `user_reads_own_sessions` `FOR SELECT` and **no** `user_owns_sessions` (the narrowing actually landed);
- all seven new indexes exist by name, and `idx_suggestion_sessions_costed_created` is partial;
- the `user_id` triggers exist and **override a deliberately wrong `user_id`** on insert (the leak guard — the most important assertion in this module);
- an impression insert for a session whose `user_id` is `NULL` raises;
- `suggestion_log_retention_days()` returns 180 with no config row, the clamp bounds for out-of-range rows, and 180 for a malformed row;
- `purge_suggestion_logs()` deletes a session older than the cutoff **and its impressions and outcomes**, leaves a session inside the window untouched, and orphans nothing;
- `array_length(item_ids,1) >= 1` and the fingerprint regex both reject bad input;
- `UNIQUE (session_id, rank)` rejects a duplicate rank; the partial dedupe index rejects a duplicate `dedupe_key` but permits two `NULL`s;
- deleting a `wardrobe_items` row leaves its impressions intact; deleting an `outfits` row nulls `outcome.outfit_id` and keeps the row.

**This module is `skipif`-guarded on a live `SUPABASE_DB_URL` + `psycopg2` (`BL-005`), so these will skip in CI.** QA must state that plainly and run §8's live verification instead of reporting a skip as a pass.

---

## 8. Manual / live verification QA must perform

1. **Serialize the push** (`BL-110`). Confirm with the operator that no sibling Wave 1.5 worktree is mid-`supabase db push` before running this ticket's. Code work stays parallel; the push does not.
2. Apply `013_suggestion_impressions.sql` via `supabase db push`, then run `supabase db diff --linked`. Expect sibling tickets' objects to appear as drift. **Report the exact diff output. Do not loosen the CI drift filter** (`BL-060`'s standing directive).
3. **RLS, all four directions, via `backend/scripts/ss033_verify_impression_logging.py`** (same shape as `ss015_verify_wear_history.py`: `httpx.Client`, `admin_headers()`/`user_headers()`, a `check()` accumulator, one throwaway user torn down at the end):
   - `service_role` writes a session + 5 impressions + 2 outcomes using the **real** `SupabaseSuggestionLogRepository`;
   - the owning user's `authenticated` `SELECT` returns exactly their own rows;
   - a **second** throwaway user's `SELECT` returns **zero rows** (not an error — RLS filters `SELECT`s rather than failing them, per `SS-026-design.md` §3.2's correction);
   - the owning user's `INSERT`, `UPDATE` and `DELETE` against all three tables each fail with a row-level-security error (`403`/`42501`) — including `suggestion_sessions`, which is the narrowing in §3.5 actually taking effect.
4. **Trigger integrity.** `service_role` inserts an impression with a deliberately wrong `user_id`; read it back and confirm the stored value is the session's owner. This is the leak guard, verified live rather than only in a skipped test.
5. **The cost-proxy fix, end to end.** Write three sessions for today (two billable, one `cache_hit`), invoke `cost-monitor` locally, and confirm it reports **2** billable against **3** total. Then run `deno test supabase/functions/` and record the result — CI will not run it (`BL-042`).
6. **Retention.** Confirm whether `pg_cron` is enabled on `mefpfykuinasgkpfhmzk` and whether `cron.schedule` succeeded (`SELECT * FROM cron.job WHERE jobname = 'purge_suggestion_logs'`). If it is not scheduled, **say so** — AC #6 is then unmet and §9 Q1 is a blocker, not a note. Separately: insert a session backdated past the window with impressions and outcomes, run `SELECT * FROM purge_suggestion_logs()`, and confirm all three rows are gone and an in-window session is untouched.
7. **Verify the two platform claims this design leans on**, and record them dated in the migration header per `docs/OPERATOR_RULEBOOK.md` §E: (a) `pg_cron` availability and `cron.schedule`'s upsert-by-jobname behaviour on the installed version; (b) that `service_role` bypasses RLS on these tables (proved empirically by item 3, not asserted).

---

## 9. Open questions / blockers

**Q1 — Is `pg_cron` actually available on this project? AC #6 depends on it.** "A retention window is defined, documented, and enforced" is the one AC that code alone cannot satisfy: the window is defined (`180`, in `app_config`), documented (in `COMMENT ON TABLE`, in this doc, and in the config row's description), and the *mechanism* ships (`purge_suggestion_logs()`), but **enforcement requires a scheduler that may not exist**. `[trained-knowledge — pg_cron is offered as an enableable extension on Supabase; NOT verified for this project this session, and this Architect pass has no web or dashboard access]`. The migration degrades to a loud `WARNING` rather than a failure, and the fallback is a scheduled Edge Function — which `BL-113` shows is itself on unverified ground. **The Developer must verify this before QA, and if `pg_cron` is unavailable the operator must decide between enabling it and wiring the Edge Function fallback.** Not a reason to hold the design, but it is the first thing to check.

**Q2 — DPDP Act applicability is unverified and must not ship to production unchecked.** `[trained-knowledge — MUST be verified against the current statutory text]` India's DPDP Act imposes consent, purpose-limitation and storage-limitation obligations that plausibly cover per-user behavioural scoring data at this volume (~7.3M rows/month at 10k users). This design does what an Architect can do — states the purpose limitation in the schema itself, makes the window enforceable and adjustable, cascades deletion from `users` so an account deletion erases the log — but **whether 180 days and this purpose statement are legally adequate is a question for a human with the statute, before the first production row is written.** `BL-108` stays **Active**; it is not resolved by this ticket. Note also that no consent surface exists anywhere in the app today for this collection.

**Q3 — Regenerating `mobile/types/supabase.ts` collides with the parallel worktrees.** The type file must eventually reflect the two new tables and nine new columns. But `supabase gen types` reads the *live* database, which by then also contains SS-034/035/036's objects (`BL-110`). Committing that output would import sibling tickets' tables into this ticket's diff and create a merge conflict in a generated file. **Directive:** regenerate after the serialized push, and commit **only if** the diff is confined to this ticket's objects. If it is not, leave the file untouched, say so in the worklog, and let the last Wave 1.5 ticket to merge regenerate once. Nothing in this ticket's ACs depends on the file (no mobile code reads these tables).

**Q4 — `ENGINE_VERSION`'s initial value is my call, and nobody owns bumping it yet.** `"rules-v1"` describes SS-027's engine because no version constant exists anywhere today. If it is never bumped it becomes actively misleading — two datasets from different scoring behaviour will look comparable. SS-035 (the tuning dial) is the natural owner; flagged so it does not fall through. Logged as `BL-114`.

**Q5 — Nothing writes these tables when this ticket merges.** By design (the ticket forbids touching `outfit_suggestion_service.py`; `BL-096`/`BL-102`). The consequence worth stating plainly: **the unbackfillable data does not start accumulating until SS-020 ships.** Every day between this merge and that one is still permanently lost, which is the proposal's own argument for urgency. SS-020 must be scoped to write impressions from day one. Also note `BL-096` remains live and unfixed in the file SS-020 will have to touch.

**Q6 — No user-facing read path exists, though RLS permits one.** Unlike `ai_cost_ledger` (SS-029, `service_role`-only), these tables grant `authenticated` a read-own-rows `SELECT`, because a "your suggestion history" surface is plausible later. Nothing consumes it — no `features/<domain>/*.queries.ts` hook is built here, since no AC asks for one. Flagged in case "queryable" was meant to imply an in-app surface, which would change scope.

**No conflict found between the ACs and CLAUDE.md.** The `service_role`-only write posture is the third documented instance of the `IAppConfigRepository`/`ICostLedger` pattern and is compliant with CLAUDE.md's Security section for the same reasons (backend-only; accounting data *about* a user, not authored by them; the write can outlive the caller's JWT), called out here rather than slipped in.

---

## 10. Backlog deltas

**Active-table resurfacing scan** (tags `infra`/`schema`/`ci`/`ai`, per the orchestrator's hand-off plus my own grep):

- **`BL-107`** (infra) — **Resolved by SS-033 / Architect.** The design adds `cost_incurred` + `zero_cost_reason` to `suggestion_sessions` with a paired consistency CHECK, filters `cost-monitor` to billable sessions through a shared `_shared/suggestionSessions.ts` predicate, adds the AC-mandated cache-hit fixture test, and makes the `weekly-report` change deliberately additive (total stays as the engagement metric, a billable count is added beside it). The row's own long-term note is carried forward in §3.1 decision 4: `request_id` is added now specifically so SS-029's `ai_cost_breakdown` can become the real source later, instead of a row count forever. **If the Developer descopes the Edge Function fix, this row must be re-opened, not left closed.**
- **`BL-108`** (infra) — **stays Active.** Half of it is addressed: the window is 180 days, product-adjustable via `app_config` with a SQL-side clamp and a 180 fallback, enforced by a batched cascade purge, with the purpose limitation recorded in `COMMENT ON TABLE` and in the config row. The other half — verifying DPDP Act obligations against the current statutory text, and confirming 180 is the right number — is explicitly not something this pass can close (§9 Q2). Note appended.
- **`BL-110`** (ci) — **stays Active.** The design accounts for it (§8 items 1-2 serialize the push, keep the code parallel, and require reporting the exact `db diff` output without loosening the filter; §9 Q3 extends the same caution to the generated types file), but the row's actual subject is that the mitigation is a convention rather than an enforced mechanism. A CI push-lock would resolve it; this ticket adds none. Note appended.
- **`BL-042`** (ci) — stays Active, note added: this ticket adds two more Deno test files that CI will not run, so the gap now covers an **AC-mandated** test rather than only best-effort coverage. Raises the priority of a Deno CI job.
- **`BL-096`** (ai) — stays Active, untouched. §2.3 explains why this ticket stays out of `outfit_suggestion_service.py`; `BL-102` is the precedent. Note added that SS-020 will have to fix it because SS-020 must touch that file to wire this substrate.
- **`BL-005`** (test) — stays Active, note added: `test_db_schema.py` gains this ticket's most security-relevant assertions (the `user_id`-derivation trigger's leak guard, zero write policies, the RLS narrowing) and they will all **skip** in CI. §8's live script is the compensating control.
- **`BL-037`** (infra) — stays Active, note added: does not block. Nothing here needs a deployed backend; the live verification runs the real adapter classes in a local script against the live project, the same pattern SS-026 used.

**New rows** (Active unless marked):

- **`BL-112`** (schema, Active) — `suggestion_sessions.suggestions` and `accepted_outfit_id` are deprecated by `COMMENT` but not dropped; the eventual CONTRACT migration needs `mobile/types/supabase.ts` regenerated first and should confirm no reader remains. Follows SS-025's `007`/`008`/`009` three-step precedent.
- **`BL-113`** (infra, Active) — **no schedule for any Edge Function exists anywhere in this repo** `[VERIFIED 2026-07-30]`: `cost-monitor` and `weekly-report` have no cron config in `supabase/config.toml`, no GitHub Actions schedule, and no per-function config, so whether they run at all is unknown and lives only in a dashboard. This directly determines whether SS-033's `pg_cron` fallback (a scheduled purge Edge Function) is a real option, and separately means the cost alert this ticket just fixed may never fire.
- **`BL-114`** (ai, Active) — `ENGINE_VERSION` ships as `"rules-v1"` (an Architect-chosen value; no version constant existed) with no owner for bumping it. If it never changes, datasets from different scoring behaviour become indistinguishable and the tuning dial's measurement is silently invalid. SS-035 is the natural owner.
- **`BL-115`** (schema, Parked) — no consent surface or user-facing "your suggestion history" / data-export path exists for the behavioural log these tables hold, even though RLS grants `authenticated` read-own-rows. Compounds `BL-108`'s DPDP question (data-principal rights) and `BL-106` (no operator-facing dashboard).

---

**Risk: high — confirmed, not downgraded.** Three independent one-way-door surfaces per `docs/OPERATOR_RULEBOOK.md` §C2: (1) a DB migration that **narrows a shipped RLS policy** (`user_owns_sessions` from `FOR ALL` to `SELECT`-only) and adds two tables whose write protection *is* the absence of a policy — a permissive write policy added later would let a client forge or erase its own behavioural record; (2) a **denormalised `user_id` behind an RLS predicate**, where one wrong value leaks one user's wardrobe contents to another, mitigated by a derivation trigger whose removal would reintroduce the leak silently; (3) an **unbackfillable, purpose-limited personal-data store** at ~7.3M rows/month whose retention enforcement depends on a scheduler this pass could not verify and whose DPDP posture is explicitly unverified. Any of the three fails quietly rather than loudly, which is exactly the class the full lane's gates exist to catch.
