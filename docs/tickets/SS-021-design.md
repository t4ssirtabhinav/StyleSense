# SS-021 — Style Score Calculation + Display — Design

Ticket: `docs/tickets/raw/SS-021.md` · Branch: `feature/SS-021-style-score-calc-display`
Architect pass: 2026-08-10 (fresh — the earlier pass on the stale 2026-07-28 branch is gone and is not resumed; two of its conclusions are re-derived below against today's facts).

---

## 1. Scope restatement

Give the user a single 0–100 "style score" derived from four dimensions of their own wardrobe data — how many garment categories they own (`wardrobe_variety`), how many of the live occasion registry's occasions their items are tagged for (`occasion_coverage`), how cheap their clothes are per wear (`cost_efficiency`, off SS-015's `GENERATED cost_per_wear` column), and how active they've been this month (`activity`, off SS-023's now-real `outfits` table plus `wardrobe_item_wears`) — and render it as a circular progress widget on Home (compact) and Profile (full). Free users see the total only; premium users additionally see the four sub-scores with an improvement tip on each. The score is shareable; per `BL-141`'s already-signed-off precedent the share ships as text/deep-link behind a capability seam, not a PNG. The score is recomputed on read and refreshed by cache invalidation whenever an item is added/edited, a wear is logged, or an outfit is saved.

---

## 2. Architecture decision (deviation from the ticket's stated shape) — READ FIRST

The raw ticket says "Supabase Edge Function computes a style score". **This design does not ship an Edge Function.** It computes the score in a pure, unit-tested TypeScript module on the client, fed by four narrow RLS-scoped PostgREST reads. No migration, no new endpoint, no new auth surface.

Reasoning, in the order it actually mattered:

1. **Every input to this score is data the caller already owns and can already read.** `wardrobe_items`, `wardrobe_item_wears`, `outfits` and `users` are all RLS-scoped `auth.uid() = user_id` (`001_initial.sql:160-177`, `006_wardrobe_item_wears.sql:38-41`). An Edge Function would re-derive, from data the client can fetch directly, a number the client could compute itself. It adds a network hop and a deployment surface, and protects nothing.
2. **The premium gate here is a product gate, not a security boundary.** Unlike SS-010's `get-upload-url` (which gates a *server-minted* resource — the presigned URL — and therefore must enforce the cap server-side), withholding the four sub-scores withholds an arithmetic function of the user's own rows. A user determined to see their own sub-scores can compute them from data PostgREST already hands them. Putting `plan_tier` gating server-side would buy the appearance of enforcement, not enforcement. See Open Question #2 — this needs explicit sign-off, not a silent Architect call.
3. **An Edge Function inherits four open backlog rows for no benefit**: `BL-069` (no deployed-env smoke check; two production-only defects shipped undetected within two days), `BL-042` (no CI job runs Deno tests at all), `BL-045` (no invocation rate limiting), and the `verify_jwt = false` + hand-rolled CORS + hand-rolled `auth.getUser()` pattern `get-upload-url` had to grow. That is the surface the prior pass correctly called `Risk: high` — and the cheapest way to not have a high-risk surface is to not build one.
4. **A Postgres RPC (the middle option) was also rejected**, though it was close. It would give real server-side gating for free via RLS, but it puts the entire scoring formula in SQL, where this repo's only DB-level test harness (`backend/tests/test_db_schema.py`) is `pytest.importorskip`'d and `skipif`'d without `SUPABASE_DB_URL` — i.e. **the maths would ship with zero CI coverage**. It also adds a migration to a `Risk: high` lane and re-enters `BL-060`'s `db diff` territory. For a formula whose constants are explicitly placeholders needing calibration (Open Question #3), untestable-in-CI is the wrong trade.
5. **The estimate corroborates it.** The ticket is `[1 pt] Est: 3h`. An Edge Function with its own auth, CORS, Deno tests and a post-deploy smoke check is not a 3h ticket; this is.

What is genuinely given up, recorded rather than hidden: there is no server-authoritative score. The moment a feature needs one (a social leaderboard, a verified shared score-card, a server-side badge), it needs a server-side computation. That is logged as **`BL-144`**, not assumed away. `users.style_score` (`001_initial.sql:38`) stays at its `DEFAULT 0` with no writer — this ticket deliberately does not write it, because a client-written "authoritative" score is worse than an unwritten one.

**This deviation is Open Question #1 and needs sign-off before Developer starts** — see §10. Despite the `Risk: med` classification in §12, the orchestrator should pause here rather than auto-chaining.

---

## 3. `activity` is a real dimension, not a stub (re-decided against today's schema)

The prior pass stubbed `activity` (`score: null`, `ACTIVITY_ENABLED = false`) because `outfits` had no writer and querying it would always return 0. **That premise is dead.** Verified in this worktree:

- `supabase/migrations/020_outfits_first_writer.sql` (SS-023, merged 2026-08-10) makes `outfits` a real written table: `user_id` is now `NOT NULL`, `items_snapshot` is populated at save time, `idx_outfits_user_created ON outfits (user_id, created_at DESC)` exists — an index that only makes sense because "this user's recent outfits" is now a real query.
- The writer is `POST /outfit-suggestions/outcome` (`backend/routers/outfit_suggestions.py`), reached from `mobile/features/outfit-ai/components/AcceptedOutfitPanel.tsx` via `useRecordOutcomeMutation`. Swipe-right → `outcome_type: 'accepted'` → an `outfits` row.
- "Wore this today" (`outcome_type: 'worn'`) writes `wardrobe_item_wears` with `outfit_id` / `occasion_key` populated — columns added by `supabase/migrations/015_wear_occasion_awareness.sql` (SS-035).

So `activity` ships computed. Two deliberate refinements over the ticket's literal "outfits saved this month":

- **Wears count too, at half weight.** `outfits` rows only come from the AI-suggestion swipe flow. A user who diligently logs "Mark Worn" from `ItemDetailSheet` but doesn't use suggestions would score 0 on a dimension explicitly meant to measure engagement. Both tables are now real and written, so both count: `points = 2 × outfits_this_month + 1 × wears_this_month`. Flagged as a (minor) deviation from the ticket's wording in §9.
- **"This month" means the IST calendar month**, per CLAUDE.md's India-Specific rules — not the device's local month and not UTC. Implemented once, in a pure tested helper (§5.4).

Note `outfits` is the one table here where a user can have rows but an *empty* wardrobe is impossible in practice (an outfit references items) — but the code must not assume that: `item_ids` has no foreign key by design (`020:42-48`), so a saved outfit outlives the deletion of every item in it.

---

## 4. Files to create / modify

### Create — `mobile/features/style-score/` (new domain, standard `features/<domain>/` layout)

| Path | Contents |
|---|---|
| `style-score.types.ts` | `StyleScoreDimension`, `StyleScoreInputs`, `StyleScoreDimensionResult`, `StyleScoreResult`, `StyleScoreSummary` (§5.1). No `any`. |
| `style-score.constants.ts` | Every weight, target, threshold and copy string in §6, exported `as const`. The **only** place a magic number for this feature may live. |
| `style-score.compute.ts` | `computeStyleScore(inputs: StyleScoreInputs): StyleScoreResult` — pure, synchronous, no `Date`, no network, no imports outside `./style-score.constants` + `./style-score.types`. This is the testable core. |
| `style-score.date.ts` | `getIstMonthStart(now: Date): { isoTimestamp: string; isoDate: string }` — pure. The single place the IST month boundary is expressed. |
| `style-score.service.ts` | The four Supabase reads (§5.2). The only file in this domain that imports `lib/supabase`. |
| `style-score.queries.ts` | `styleScoreQueryKey(userId)`, `useStyleScoreQuery(userId)`. The only file components import from for data. |
| `components/StyleScoreRing.tsx` | Ring + centred numeral. Presentational only, no query. |
| `components/StyleScoreBreakdown.tsx` | Four sub-score rows + tips (premium) or the locked upsell (free). Presentational only. |
| `components/StyleScoreCard.tsx` | The one composed entry point. Owns `useStyleScoreQuery`; handles loading / error / empty / ok. `variant: 'compact' \| 'full'`. |
| `share/styleScoreCardExport.ts` | Capability seam, mirroring SS-023's `outfitCardExport.ts` exactly (§7). |
| `share/styleScoreCardExport.native.ts` | `export * from './styleScoreCardExport';` |
| `share/styleScoreCardExport.web.ts` | `export * from './styleScoreCardExport';` |

### Create — shared

| Path | Contents |
|---|---|
| `mobile/components/ui/CircularProgress.tsx` | New design-system primitive (§5.5). `components/ui/` has `ProgressBar` (linear) but nothing circular. |
| `mobile/lib/share/shareableCard.types.ts` | `export type ShareableCard = { kind: 'image'; uri: string } \| { kind: 'text'; body: string };` — the one generalisation of SS-023's seam (§7). |

### Modify

| Path | Change |
|---|---|
| `mobile/app/(tabs)/index.tsx` | Insert `<StyleScoreCard variant="compact" />` between `<GreetingHeader />` and `<OccasionPillRow />`. No other change. |
| `mobile/app/(tabs)/profile.tsx` | Insert `<StyleScoreCard variant="full" />` under the `Avatar`/heading, above the "Edit Preferences" button. No other change. |
| `mobile/components/ui/index.ts` | `export { CircularProgress }` + `export type { CircularProgressProps }`, alphabetical (between `Card` and `EmptyState`). |
| `mobile/features/outfit-ai/share/outfitCardExport.ts` | **One line only**: replace the inline `ShareableCard` union with `export type { ShareableCard } from '../../../lib/share/shareableCard.types';`. Public export surface is byte-compatible (`import type { ShareableCard } from './outfitCardExport'` keeps working), so SS-023's shipped tests must pass **unmodified** — that is the check that this generalisation was safe. Do not touch anything else in this file or its `.native`/`.web` siblings. |
| `mobile/features/wardrobe/wardrobe.queries.ts` | Extend the existing private `useInvalidateWardrobeGridQueries()` (line ~325) to also invalidate `styleScoreQueryKey(userId)`. This single edit covers tag-save, favourite, delete, wear log/edit/delete and details-save — every wardrobe path that can move the score. Do not add per-hook invalidation. |
| `mobile/features/outfit-ai/outfit-ai.queries.ts` | Add `onSuccess` to `useRecordOutcomeMutation` invalidating `styleScoreQueryKey(userId)` (userId from `useAuthStore`). This is the "score updates after each outfit saved" half of AC #1. |
| `mobile/constants/analyticsEvents.ts` | Add `STYLE_SCORE_SHARED: 'style_score_shared'` to `ANALYTICS_EVENTS` and `style_score_shared: { channel?: string }` to `AnalyticsEventProperties`. A 14th event, additive; deliberately **not** reusing `outfit_shared`, which is a funnel metric for a different object. Does not resolve any of `BL-049`'s 8 remaining uncalled events. |
| `mobile/jest.config.js` | Only if §5.5's verification requires it — add `react-native-svg` to `transformIgnorePatterns`' allowlist. Report whether it was needed. |

Explicitly **not** modified: `supabase/migrations/**` (no migration), `supabase/functions/**` (no Edge Function), `supabase/config.toml`, `backend/**`, `mobile/types/supabase.ts` (no schema change ⇒ no regeneration), `users.style_score`.

---

## 5. Contracts

### 5.1 Types (`style-score.types.ts`)

```ts
export type StyleScoreDimension =
  | 'wardrobe_variety'
  | 'occasion_coverage'
  | 'cost_efficiency'
  | 'activity';

/** Everything computeStyleScore needs. Deliberately flat, serialisable and
 *  free of Date/Supabase types so the whole formula is testable from a
 *  literal object. */
export interface StyleScoreInputs {
  itemCount: number;
  distinctCategories: number;
  /** Occasion keys appearing in at least one item's occasion_tags. May
   *  contain unknown/retired slugs (SS-025 never drops them). */
  coveredOccasionKeys: string[];
  /** occasions.key WHERE is_active — the denominator. */
  activeOccasionKeys: string[];
  /** cost_per_wear (WHOLE RUPEES — BL-075) for qualifying items only. */
  costPerWearValues: number[];
  outfitsThisMonth: number;
  wearsThisMonth: number;
}

export interface StyleScoreDimensionResult {
  dimension: StyleScoreDimension;
  label: string;
  /** 0-100 integer, or null = not enough data (excluded from the total). */
  score: number | null;
  weight: number;
  /** Improvement tip, present only when score !== null && score < threshold. */
  tip: string | null;
}

export interface StyleScoreResult {
  /** 0-100 integer. ALWAYS a number — never null, never NaN. */
  total: number;
  state: 'ok' | 'empty_wardrobe';
  /** Always all four dimensions, in the declared order. */
  breakdown: StyleScoreDimensionResult[];
}

export interface StyleScoreSummary extends StyleScoreResult {
  isPremium: boolean;
}
```

### 5.2 Reads (`style-score.service.ts`)

`fetchStyleScoreInputs(userId: string, now: Date, activeOccasionKeys: string[]): Promise<StyleScoreInputs>` — one `Promise.all` of three queries; `activeOccasionKeys` is passed in (see below), not fetched here.

| Query | Exact shape |
|---|---|
| Items | `supabase.from('wardrobe_items').select('category, occasion_tags, cost_per_wear, purchase_price, wear_count').limit(STYLE_SCORE_MAX_ITEMS)` |
| Outfits this month | `supabase.from('outfits').select('id', { count: 'exact', head: true }).gte('created_at', istMonthStart.isoTimestamp)` |
| Wears this month | `supabase.from('wardrobe_item_wears').select('id', { count: 'exact', head: true }).gte('worn_on', istMonthStart.isoDate)` |

- No `.eq('user_id', ...)` filters: RLS already scopes all three to `auth.uid()`, and adding a client-supplied predicate would imply the client is the thing enforcing it. (`userId` is still the query *key*, so an account switch on one device can't serve a stale cache — `wardrobe.queries.ts`' established convention.)
- `select('*')` is banned here — the wardrobe grid's `fetchWardrobeItems` already does that on its own tab; this must stay narrow because it runs on Home.
- `activeOccasionKeys` comes from the app's **single** taxonomy fetcher, `useOccasionTaxonomy()` (re-exported through `features/wardrobe/wardrobe.queries.ts`'s `useOccasionOptions`, itself `onboarding.taxonomies.service.ts`'s `fetchOnboardingTaxonomies`, which already filters `is_active = true` and is AsyncStorage-cached). **Do not add a second `occasions` fetcher** — that is the explicit standing instruction on that file and `BL-089`'s subject.
- `plan_tier` comes from the existing `fetchUserPlanTier(userId)` in `features/auth/auth.service.ts`. It fails safe to `null`; **`null` must be treated as free** (fail closed on premium content), matching `FreeTierBanner`'s `PREMIUM_TIERS.includes(planTier)` shape. Premium = `'premium' | 'premium_annual'`.
- Every read is inside `try/catch` at the query layer; a failure surfaces as the hook's `isError`, never a fabricated `0`.

### 5.3 Hook (`style-score.queries.ts`)

```ts
export function styleScoreQueryKey(userId: string | undefined) {
  return ['style-score', 'summary', userId] as const;
}

export function useStyleScoreQuery(userId: string | undefined):
  UseQueryResult<StyleScoreSummary>;
```

- `enabled: Boolean(userId) && Boolean(activeOccasionKeys)` (taxonomy must have resolved first).
- `staleTime: STYLE_SCORE_STALE_TIME_MS`.
- `queryFn` = `fetchStyleScoreInputs(...)` + `fetchUserPlanTier(...)` → `computeStyleScore(inputs)` → `{ ...result, isPremium }`. The compute step is synchronous and never throws.
- `now` is `new Date()` captured inside `queryFn` (not module scope — a long-lived app must not pin the month boundary at bundle-eval time).

### 5.4 IST month boundary (`style-score.date.ts`)

```ts
export const IST_OFFSET_MINUTES = 330; // UTC+05:30, no DST — fixed by definition
export function getIstMonthStart(now: Date): { isoTimestamp: string; isoDate: string };
```

Returns the first instant of the current **IST** calendar month, expressed two ways: `isoTimestamp` (a UTC ISO-8601 string, for the `TIMESTAMPTZ` comparison against `outfits.created_at`) and `isoDate` (`YYYY-MM-01`, for the `DATE` comparison against `wardrobe_item_wears.worn_on`). Implemented by shifting into IST, truncating to the month in UTC-space, then shifting back — never with `toLocaleString`, whose ICU availability varies across Hermes/web. `Asia/Kolkata` has had no DST in the modern era, so a fixed +05:30 offset is correct and does not need a timezone database. *[trained-knowledge; the offset is also the fixed constant `backend/services/ist_window.py` already relies on.]*

### 5.5 `CircularProgress` (`components/ui/CircularProgress.tsx`)

```ts
export interface CircularProgressProps {
  /** 0-100. NaN → 0; out-of-range clamped, exactly like ProgressBar.tsx. */
  progress: number;
  size?: number;         // default CIRCULAR_PROGRESS_SIZE_DEFAULT (120)
  strokeWidth?: number;  // default CIRCULAR_PROGRESS_STROKE_DEFAULT (10)
  trackColor?: string;   // default colors.bg.secondary
  fillColor?: string;    // default colors.accent.marigold
  children?: ReactNode;  // centred content (the numeral)
  testID?: string;       // default 'circular-progress'
}
```

- Follows `ProgressBar.tsx`'s conventions verbatim: token-driven colours from `./tokens`, NativeWind for anything static, clamp helper with the same NaN behaviour. **No `StyleSheet.create`.**
- Rendered with `react-native-svg` (`Svg` + two `Circle`s, arc via `strokeDasharray`/`strokeDashoffset`, `-90°` rotation so 0% starts at 12 o'clock). Inner fill circle carries `testID="circular-progress-fill"`.
- Accessibility: `accessibilityRole="progressbar"`, `accessibilityValue={{ min: 0, max: 100, now: clamped }}` — the score is the screen's headline number and must be readable by a screen reader without depending on the visual ring.
- **Verification the Developer owes (do not assume):** `react-native-svg@^15.15.5` is in `mobile/package.json` but **is not imported anywhere in this repo today** — this is its first production use. Confirm (a) it renders under `jest-expo` (the current `transformIgnorePatterns` override in `jest.config.js` does not allowlist it) and (b) it renders under `npx expo start --web`. If either fails and can't be fixed by an allowlist entry: ship the same props/testIDs/a11y contract but render the existing `ProgressBar` beneath the centred numeral instead of a ring, state plainly in the worklog that the widget is linear-not-circular, and leave `BL-146` open. **Do not silently drop the widget, and do not add a new dependency to make a ring happen** — a new package on a 1-point ticket is out of scope.

### 5.6 Presentational components

| Component | Props | Behaviour |
|---|---|---|
| `StyleScoreRing` | `{ total: number; size?: number; caption?: string; testID? }` | `CircularProgress` with `<Text variant="display">{total}</Text>` centred and a `/100` caption. Single fill colour (`accent.marigold`) at every value — **no red/amber/green banding**, because no semantic status colours exist in the token set (`BL-007`) and inventing them here is exactly what that row forbids. |
| `StyleScoreBreakdown` | `{ breakdown: StyleScoreDimensionResult[]; isPremium: boolean; testID? }` | Premium: one row per dimension — label, `score ?? '—'`, a `ProgressBar` at that sub-score, and `tip` beneath when present. Free: renders `STYLE_SCORE_LOCKED_COPY` + an "Upgrade" `Button` and **fires `PREMIUM_PAYWALL_VIEWED` with `{ source: 'style_score' }`** (an already-defined event with an already-defined `source` property — wiring it here costs nothing and is the correct owner). Sub-scores must not be rendered in any form (not hidden text, not blurred real values) when `isPremium` is false. |
| `StyleScoreCard` | `{ variant: 'compact' \| 'full'; testID? }` | Owns the query. All four states handled per CLAUDE.md: **loading** → `Skeleton`; **error** → `Text` + retry `Button` calling `refetch()`, never a fake `0`; **empty** (`state === 'empty_wardrobe'`) → ring at `0` plus `STYLE_SCORE_EMPTY_COPY` and a `router.push('/wardrobe')` CTA; **ok** → ring, plus (only when `variant === 'full'`) `StyleScoreBreakdown` and the Share button. `compact` renders ring + total only — no breakdown, no share, no upsell (Home is not a paywall surface). Renders nothing when there is no session. |

Navigation is `router.push` from `expo-router`; images (none here) would be `expo-image`; no `FlatList` anywhere (the breakdown is a fixed 4 rows).

---

## 6. Concrete values — use these, do not invent alternatives

All of the following live in `style-score.constants.ts`.

### 6.1 Weights (sum 100)

| Dimension | Constant | Weight |
|---|---|---|
| `wardrobe_variety` | `STYLE_SCORE_WEIGHTS.wardrobe_variety` | `30` |
| `occasion_coverage` | `STYLE_SCORE_WEIGHTS.occasion_coverage` | `30` |
| `cost_efficiency` | `STYLE_SCORE_WEIGHTS.cost_efficiency` | `20` |
| `activity` | `STYLE_SCORE_WEIGHTS.activity` | `20` |

### 6.2 Per-dimension formulas

```
wardrobe_variety   = 100 * min(1, distinctCategories / VARIETY_TARGET_DISTINCT_CATEGORIES)
                     VARIETY_TARGET_DISTINCT_CATEGORIES = 8   (of the 21 wardrobe_category enum values)
                     null when itemCount === 0

occasion_coverage  = 100 * coveredActiveCount / activeOccasionKeys.length
                     coveredActiveCount = |coveredOccasionKeys ∩ activeOccasionKeys|
                     null when itemCount === 0 OR activeOccasionKeys.length === 0

cost_efficiency    = 100 * clamp((POOR - avg) / (POOR - EXCELLENT), 0, 1)
                     avg  = mean(costPerWearValues)
                     COST_PER_WEAR_EXCELLENT_RUPEES = 100    → 100
                     COST_PER_WEAR_POOR_RUPEES      = 2000   → 0
                     null when costPerWearValues.length === 0

activity           = 100 * min(1, points / ACTIVITY_TARGET_POINTS)
                     points = ACTIVITY_OUTFIT_POINTS * outfitsThisMonth
                            + ACTIVITY_WEAR_POINTS   * wearsThisMonth
                     ACTIVITY_OUTFIT_POINTS = 2, ACTIVITY_WEAR_POINTS = 1,
                     ACTIVITY_TARGET_POINTS = 16
                     null when itemCount === 0 (otherwise 0 is a real answer)
```

- All 21 `wardrobe_category` enum values count equally toward variety. Ethnic categories are **not** special-cased and **not** bonus-weighted — CLAUDE.md's "ethnic wear is first-class, not an edge case" is satisfied by them being ordinary members of the same denominator, and any weighting beyond that is a product decision nobody has made.
- `cost_per_wear` is read from the `GENERATED` column, never recomputed from `purchase_price / wear_count` (ticket Technical Note; `BL-004`). Its unit is **whole rupees**, per `BL-075`'s recorded precedent (SS-014's `ItemDetailSheet` and SS-015's AC both treat it that way) — do not re-open that decision here.
- Qualifying item for `costPerWearValues`: `purchase_price !== null && purchase_price > 0 && wear_count >= 1 && cost_per_wear !== null`. The `> 0` guard stops a ₹0 / gifted item scoring a free 100.

### 6.3 Total

```
contributing = breakdown entries with score !== null
total = contributing.length === 0
      ? 0
      : round( Σ(weight_i × score_i) / Σ(weight_i) )     // over contributing only
```

Weight renormalisation over non-null dimensions is load-bearing, not a nicety: `purchase_price` is optional and most real users will never enter it, so scoring a missing dimension as `0` would permanently cap everyone's total at 80 for data they were never asked for. Sub-scores are computed at float precision and only rounded for display/`breakdown`; the total is rounded once, at the end. `total` is clamped to `[0, 100]` and `Number.isFinite`-guarded.

### 6.4 Thresholds and copy

| Constant | Value |
|---|---|
| `STYLE_SCORE_TIP_THRESHOLD` | `70` — tips render only for a dimension scoring below this |
| `STYLE_SCORE_STALE_TIME_MS` | `60_000` |
| `STYLE_SCORE_MAX_ITEMS` | `2000` |
| `CIRCULAR_PROGRESS_SIZE_DEFAULT` / `_STROKE_DEFAULT` | `120` / `10` |
| `STYLE_SCORE_LABELS.wardrobe_variety` | `'Wardrobe Variety'` |
| `STYLE_SCORE_LABELS.occasion_coverage` | `'Occasion Coverage'` |
| `STYLE_SCORE_LABELS.cost_efficiency` | `'Cost Efficiency'` |
| `STYLE_SCORE_LABELS.activity` | `'Activity'` |
| `STYLE_SCORE_TIPS.wardrobe_variety` | `'Add pieces from categories you are missing — ethnic wear, footwear and accessories all count.'` |
| `STYLE_SCORE_TIPS.occasion_coverage` | `'Tag your items with more occasions so we can style you for everything from Office to Wedding Guest.'` |
| `STYLE_SCORE_TIPS.cost_efficiency` | `'Wear what you already own and log it — every wear lowers your cost per wear.'` |
| `STYLE_SCORE_TIPS.activity` | `'Save an outfit or log what you wore today to keep your score moving.'` |
| `STYLE_SCORE_ALL_GOOD_COPY` | `'Your wardrobe is in great shape. Keep it up!'` |
| `STYLE_SCORE_EMPTY_COPY` | `'Add your first item to start building your style score.'` |
| `STYLE_SCORE_LOCKED_COPY` | `'Unlock your 4 sub-scores and personalised tips with Premium.'` |
| `STYLE_SCORE_ERROR_COPY` | `'We could not calculate your style score right now.'` |
| `STYLE_SCORE_TITLE` | `'Style Score'` |
| `STYLE_SCORE_SHARE_CTA` | `'Share Score'` |

No currency is rendered by this feature, so no `₹` formatting is needed. No colour swatches are rendered, so **`BL-022` (no final 12-swatch palette) is not applicable** to this ticket.

---

## 7. AC #4 (shareable score card) — settled by precedent, not re-decided

`BL-141` records the user's 2026-08-07 decision, taken for SS-023 **and SS-021 together**: no verified client-side image-export path exists (`react-native-view-shot` isn't installed, no DOM-capture path verified), so both tickets ship a text/deep-link fallback behind a capability seam and `BL-141` tracks the one verification spike that unblocks real PNG export for both. **That decision is applied here as-is — it is not an open question and must not be re-asked.**

Implementation mirrors `mobile/features/outfit-ai/share/outfitCardExport.ts` exactly:

```ts
// mobile/features/style-score/share/styleScoreCardExport.ts
import type { ShareableCard } from '../../../lib/share/shareableCard.types';

export interface StyleScoreShareInput { total: number; }

export function buildStyleScoreShareText(input: StyleScoreShareInput): string {
  return `My StyleSense style score is ${input.total}/100. How does your wardrobe score?`;
}

export async function exportStyleScoreCard(
  input: StyleScoreShareInput,
): Promise<ShareableCard> {
  return { kind: 'text', body: buildStyleScoreShareText(input) };
}
```

with `.native.ts` / `.web.ts` each doing `export * from './styleScoreCardExport';`, so Metro's platform-extension resolution picks the right one and a future image-export ticket changes only the platform files, never the exported type contract.

The seam is generalised by exactly one step — `ShareableCard` moves to `mobile/lib/share/shareableCard.types.ts` and SS-023's file re-exports it — so the two seams can never drift into two different notions of "a shareable card". Nothing else about SS-023's seam is touched; its existing tests passing unmodified is the regression check.

Share handler (in `StyleScoreCard`, `variant === 'full'`): `await exportStyleScoreCard({ total })` → `Share.share({ message: card.body })` inside `try/catch` → `track(ANALYTICS_EVENTS.STYLE_SCORE_SHARED, { channel })`, reading `activityType` defensively exactly as `AcceptedOutfitPanel.handleShare` does. A cancelled or unsupported share sheet is swallowed silently — it is an optional, reversible action. **Known gap carried forward, not fixed here:** React Native's `Share` is a native-only API and is a no-op/throw under `react-native-web`, so on this web-first app's primary target the button currently does nothing visible. SS-023 shipped with the same gap; logged as `BL-147` rather than fixed inside a 1-point ticket.

---

## 8. Edge cases

Carried forward from the ticket, plus what the current codebase adds.

**From the raw ticket**

1. *New user, empty wardrobe* — `itemCount === 0` ⇒ all four sub-scores `null`, `total = 0`, `state = 'empty_wardrobe'`, card renders the ring at 0 with `STYLE_SCORE_EMPTY_COPY` and an add-items CTA. No division anywhere is reached with a zero denominator (each is guarded by a null-return before the divide, not by an `isNaN` mop-up afterwards).
2. *`activity` has no data source* — **obsolete**, see §3. `outfits` has a real writer as of SS-023/migration 020. Recorded here so a future reader knows the ticket's own edge-case text was superseded, not overlooked.

**New, from the current codebase**

3. **No item has a `purchase_price`** — `costPerWearValues` is empty ⇒ `cost_efficiency = null` ⇒ excluded from the total via renormalisation (§6.3), *not* scored 0. This is the common case, not a rare one.
4. **`purchase_price = 0`** (gift / not recorded as null) — excluded by the `> 0` guard; otherwise it would compute `cost_per_wear = 0` and hand out a free 100.
5. **Items exist but none are tagged with any occasion** — `occasion_coverage = 0` (a real, actionable zero), not `null`. Only an empty wardrobe or an empty registry nulls it.
6. **The occasions registry is unreachable or returns 0 active rows** — `activeOccasionKeys.length === 0` ⇒ `occasion_coverage = null` (guards the divide) and the total renormalises over the other three. The taxonomy fetcher's AsyncStorage last-known-good cache (SS-025) makes this rare but not impossible on a first-ever offline launch.
7. **Unknown / retired occasion slugs on an item** — `occasion_tags` legitimately holds slugs that aren't in `occasions` (SS-025 never drops an unknown tag; `occasion_unknown_tags` records it). Coverage counts only the intersection with `activeOccasionKeys`, so an unknown slug can neither inflate coverage nor push it above 100%.
8. **Duplicate occasion slugs across items** — coverage counts *distinct* keys; build the covered set with a `Set`, never by summing per-item tag counts.
9. **Saved outfit whose items were later deleted** — `outfits.item_ids` has no FK by design (`020:42-48`), so the row survives. `activity` counts `outfits` rows and must not join to `wardrobe_items`; a deleted-item outfit still counts, which is correct (the activity happened).
10. **A wear whose outfit was deleted** — `wardrobe_item_wears.outfit_id` is `ON DELETE SET NULL`, never `CASCADE` (`015:140-144`), so the wear row survives and still counts. Do not filter wears by `outfit_id IS NOT NULL`.
11. **Multi-occasion same-day wears** — SS-035 widened the uniqueness key to `(item_id, worn_on, occasion_key) NULLS NOT DISTINCT`, so one item can legitimately have two wear rows on one day. `activity` counts rows, so a two-occasion day counts twice. Accepted and intended (it *was* more activity); noted because it is the same subtlety `BL-075`'s SS-035 re-scan flagged for `wear_count`.
12. **Very large wardrobe** — `STYLE_SCORE_MAX_ITEMS = 2000` caps the payload (premium wardrobes are uncapped). Variety and coverage saturate long before 2000 items, so truncation cannot change the score in practice; `cost_efficiency`'s average is over the first 2000, which is a documented approximation, not a bug.
13. **IST month rollover** — the score visibly drops at 00:00 IST on the 1st as `activity` resets. Expected behaviour of a "this month" metric; called out so QA doesn't file it. `staleTime` is 60s, so the rollover appears within a minute of a foreground refetch.
14. **Wrong device clock** — the month boundary is computed from device time against server-stored data. A badly-skewed clock yields a wrong activity window. Accepted (the alternative is a server round-trip purely to learn the date); no correction attempted.
15. **`plan_tier` lookup fails** — `fetchUserPlanTier` fails safe to `null`; `null` ⇒ treated as **free**. Premium content is fail-closed, never fail-open.
16. **`plan_expires_at` in the past** — `users.plan_expires_at` exists but no shipped code consults it; this ticket follows the existing `FreeTierBanner`/`get-upload-url` precedent of gating on `plan_tier` alone rather than inventing a second, inconsistent expiry rule. Noted as a repo-wide inconsistency, not fixed here.
17. **No session / signed out** — hook is `enabled: false`, card renders nothing. No flash of a `0` score.
18. **Account switch on one device** — `userId` is in the query key, so the previous account's score can never be served from cache.
19. **Query error** — `isError` renders `STYLE_SCORE_ERROR_COPY` + retry. Never a fabricated `0`, which would be indistinguishable from a real empty wardrobe.
20. **Concurrency / staleness** — the score is derived-on-read, so there is no cache to go stale and no read-then-write race of the `BL-036`/`BL-066` class. This is a positive consequence of §2's decision worth stating explicitly.
21. **`NaN` / `Infinity` inputs** — `computeStyleScore` guards every arithmetic result with `Number.isFinite` and falls back to `0` for the dimension rather than propagating `NaN` into the ring's `strokeDashoffset` (where it renders as an invisible or full arc, silently).

---

## 9. Test plan

Jest + React Native Testing Library, `jest-expo` preset. Paths mirror the existing `mobile/__tests__/**` convention. Every acceptance criterion maps to at least one row below.

### `mobile/__tests__/features/style-score/style-score.compute.test.ts` (the core — most of the coverage lives here)

- returns `total: 0`, `state: 'empty_wardrobe'` and all four `score: null` for `itemCount: 0` (AC: defined value on an empty wardrobe; ticket edge case #1)
- scores `wardrobe_variety` as `100` at exactly `VARIETY_TARGET_DISTINCT_CATEGORIES` distinct categories and stays `100` above it (no >100)
- scores `wardrobe_variety` proportionally below target (e.g. 4/8 → 50)
- counts an ethnic category identically to a western one toward variety (no special-casing)
- scores `occasion_coverage` as `covered / active × 100` using only the intersection with `activeOccasionKeys`
- ignores an unknown/retired occasion slug in `coveredOccasionKeys` so coverage cannot exceed 100
- counts a duplicated occasion slug across two items once
- returns `occasion_coverage: null` when `activeOccasionKeys` is empty (no divide-by-zero)
- scores `cost_efficiency` `100` at or below `COST_PER_WEAR_EXCELLENT_RUPEES`, `0` at or above `COST_PER_WEAR_POOR_RUPEES`, and linearly between
- returns `cost_efficiency: null` for an empty `costPerWearValues` and renormalises the total over the remaining three weights (asserts a specific total, not just "not NaN")
- scores `activity` from `2 × outfits + 1 × wears`, capping at `100` beyond `ACTIVITY_TARGET_POINTS`
- scores `activity: 0` (not `null`) for a non-empty wardrobe with no outfits and no wears this month
- computes the weighted total over all four dimensions to an exact expected integer for a fully-populated fixture
- attaches a `tip` only to dimensions scoring below `STYLE_SCORE_TIP_THRESHOLD`, and `null` above it
- returns a finite, clamped `0..100` total for hostile inputs (`NaN`, `Infinity`, negative counts)
- always returns all four dimensions in the declared order regardless of which are null

### `mobile/__tests__/features/style-score/style-score.date.test.ts`

- returns the 1st of the current IST month at 00:00 IST as a UTC `isoTimestamp` (asserted for a UTC instant that falls in a *different* month in UTC than in IST — e.g. `2026-07-31T20:00:00Z` → August in IST)
- returns `isoDate` as `YYYY-MM-01` matching the same IST month
- is stable across a January boundary (year rollover)

### `mobile/__tests__/features/style-score/style-score.service.test.ts`

- issues exactly three Supabase queries and selects only the five named `wardrobe_items` columns (asserts the `select` argument string — guards against a `select('*')` regression on a Home-screen query)
- filters the outfits count by `created_at >= istMonthStart.isoTimestamp` and the wears count by `worn_on >= istMonthStart.isoDate`
- adds no client-side `user_id` filter to any of the three queries (RLS is the boundary)
- derives `distinctCategories` and `coveredOccasionKeys` correctly from a mixed item fixture
- excludes items with `purchase_price` null, `0`, or `wear_count: 0` from `costPerWearValues`
- propagates a Supabase error by rejecting (so the hook reports `isError`) rather than returning zeroed inputs

### `mobile/__tests__/features/style-score/style-score.queries.test.tsx`

- is disabled and issues no request when `userId` is undefined
- returns `isPremium: true` for `plan_tier: 'premium'` and `'premium_annual'`
- returns `isPremium: false` when `fetchUserPlanTier` resolves `null` (fail-closed)
- includes `userId` in the query key so two users cannot share a cache entry

### `mobile/__tests__/features/style-score/components/StyleScoreCard.test.tsx`

- renders a `Skeleton` while loading, and the error copy + a working retry button on error (never a `0`)
- renders the empty-wardrobe copy and the add-items CTA for `state: 'empty_wardrobe'`
- `variant="compact"` renders the total but no breakdown, no upsell and no share button
- `variant="full"` renders the breakdown and the share button
- free user sees the total and the locked upsell, and **no** sub-score value appears anywhere in the tree (AC: free users see the total only)
- premium user sees all four sub-score values with their labels (AC: premium sees 4 sub-scores)
- share button calls `exportStyleScoreCard`, passes the resulting text to `Share.share`, and tracks `style_score_shared` (AC #4, text fallback)
- a rejected/cancelled `Share.share` does not throw or unmount the card

### `mobile/__tests__/features/style-score/components/StyleScoreBreakdown.test.tsx`

- renders a tip for a dimension below the threshold and no tip above it (AC: improvement tips)
- renders `'—'` rather than `0` for a `null` sub-score
- fires `premium_paywall_viewed` with `{ source: 'style_score' }` exactly once when rendered for a free user

### `mobile/__tests__/features/style-score/share/styleScoreCardExport.test.ts`

- `buildStyleScoreShareText` includes the total and the `/100` framing
- `exportStyleScoreCard` resolves `{ kind: 'text' }` (asserts the deferral is deliberate, so a future PNG change is a visible test change — same shape as SS-023's seam test)

### `mobile/__tests__/components/ui/CircularProgress.test.tsx`

- clamps out-of-range and `NaN` progress exactly like `ProgressBar` (0 / 100 / 0)
- exposes `accessibilityRole="progressbar"` with `accessibilityValue.now` equal to the clamped progress
- renders its `children` centred in the ring
- renders a longer filled arc for a higher progress value (asserts the `strokeDashoffset` relationship, not a pixel snapshot)

### Regression / integration

- `mobile/__tests__/app/(tabs)/index.test.tsx` — **modify**: Home still renders its four existing sections and now also renders `style-score-card`
- `mobile/__tests__/app/(tabs)/profile.test.tsx` — **modify**: Profile still renders the Edit Preferences button and now also renders `style-score-card`
- `mobile/__tests__/features/wardrobe/wardrobe.queries.test.tsx` — **modify**: a wardrobe grid mutation now also invalidates `['style-score','summary',userId]` (AC: score updates after an item is added)
- `mobile/__tests__/features/outfit-ai/outfit-ai.queries.test.tsx` — **modify**: `useRecordOutcomeMutation` success invalidates `['style-score','summary',userId]` (AC: score updates after an outfit is saved)
- `mobile/__tests__/features/outfit-ai/share/outfitCardExport.test.ts` — **must pass byte-unmodified** after the `ShareableCard` type move. If it needs editing, the generalisation was not safe and should be reverted to a local type in the style-score seam.

### Not covered by automated tests (state plainly in the worklog, do not claim otherwise)

- Real rendering of the ring under `expo start --web` and on a device — manual, per §5.5.
- That the four aggregate reads agree with what the live DB holds — there is no CI-runnable DB harness (`backend/tests/test_db_schema.py` is skipped without `SUPABASE_DB_URL`). QA should do one manual spot-check against a real account and record the numbers.

---

## 10. Open questions / blockers

**#1 — [LOAD-BEARING · BLOCKS DEVELOPER] No Edge Function.** §2 replaces the ticket's stated "Supabase Edge Function computes a style score" with client-side computation over RLS-scoped reads. Recommended default: **proceed as designed.** If the user wants a server-authoritative score now (rather than when `BL-144` is triggered by a social/leaderboard feature), the right shape is a `SECURITY INVOKER` Postgres function returning the aggregate *inputs* — keeping the maths in the tested TS module — and that is a different, larger ticket with a migration and a `Risk: high` lane. This is the one question the orchestrator should pause on despite the `med` classification.

**#2 — [LOAD-BEARING] Premium gating is a UX gate, not a security boundary.** A free user who modifies the client can see their own four sub-scores. §2.2 argues that's acceptable because they are an arithmetic function of rows PostgREST already serves that user. Confirm this is the intended posture for premium *display* features generally, since it will set the precedent for every future "premium sees more detail about their own data" feature. If the answer is "no, premium detail must be server-withheld", #1's answer changes too and this ticket grows a server surface.

**#3 — Every scoring constant in §6 is an Architect invention with no product sign-off.** Nothing upstream pins the weights (30/30/20/20), the variety target (8 categories), the cost-per-wear band (₹100 excellent → ₹2000 poor), the activity target (16 points/month) or the tip threshold (70). They are deliberately all in one `as const` file so recalibration is a one-file diff with no logic change. Non-blocking — but the numbers users see are a product decision, and nobody has made it. Logged as `BL-145`.

**#4 — `activity` counts wears as well as outfits**, at half weight (§3). This is a deliberate widening of the ticket's literal "outfits saved this month" so that users of the "Mark Worn" flow aren't scored 0 on engagement. Easily reverted by setting `ACTIVITY_WEAR_POINTS = 0`. Non-blocking; flagged so it isn't discovered as a surprise at QA.

**#5 — `users.style_score` stays unwritten.** The column has existed since `001_initial.sql` with `DEFAULT 0` and has never had a writer. This ticket deliberately does not become one (§2). Non-blocking; logged as `BL-144`.

**Not open questions** (settled, recorded so they aren't re-litigated):
- AC #4's image export → text fallback behind a seam: settled by `BL-141`, user sign-off 2026-08-07, applied verbatim (§7).
- `cost_per_wear` / `purchase_price` unit → **whole rupees**: settled by `BL-075`'s shipped-consumer precedent (§6.2).
- `BL-022` (12-swatch palette) → **not applicable**; this feature renders no colour swatches (§6.4).
- `activity` stubbing → **obsolete**; `outfits` has a real writer as of SS-023 (§3).

**Dependency check:** the ticket declares `Depends on: SS-002, SS-015`. Both shipped. SS-023 (merged 2026-08-10, this branch's base) is a *de facto* new dependency for `activity` — without it `outfits` is empty and `activity` degrades to counting wears only, which is still a defined, non-crashing value. No blocker.

---

## 11. Backlog deltas (for the orchestrator to apply — this pass does not edit `docs/BACKLOG.md`)

`docs/BACKLOG.md` on `develop` reserves new IDs from **`BL-144`**.

**Add to Active:**

| ID | Title | Tag | Source | Description |
|---|---|---|---|---|
| `BL-144` | No server-authoritative style score; `users.style_score` has no writer | schema | SS-021 / Architect | SS-021 computes the style score client-side on read from RLS-scoped queries (design §2), deliberately shipping no Edge Function and no RPC. `users.style_score` (`001_initial.sql:38`, `INTEGER DEFAULT 0`) therefore still has no writer and is not a trustworthy value for any consumer. Acceptable while the score is a private, self-reported number. **Becomes blocking the moment a feature needs a score that the user cannot fabricate** — a social leaderboard, a verified shared score-card, a server-issued badge, or any cross-user comparison (Epic 4). The right shape then is a `SECURITY INVOKER` Postgres function returning the aggregate *inputs* (keeping the formula in the already-tested TS module) plus a write to `users.style_score`; that needs a migration and a `Risk: high` lane. Decide "populate it or drop it" at that point rather than leaving a permanently-zero column in the schema. |
| `BL-145` | Style-score weights, targets and thresholds are uncalibrated Architect defaults | ai | SS-021 / Architect | Nothing upstream (HLD/LLD, epics doc, raw ticket) pins any number in SS-021's scoring formula. The Architect chose weights 30/30/20/20, `VARIETY_TARGET_DISTINCT_CATEGORIES = 8`, a cost-per-wear band of ₹100 (excellent) → ₹2000 (poor), `ACTIVITY_TARGET_POINTS = 16` (`2 × outfits + 1 × wears` per IST month) and a tip threshold of 70. All live in `mobile/features/style-score/style-score.constants.ts` so recalibration is a one-file, no-logic diff. Needs a product decision and, ideally, calibration against real wardrobe data once any exists — the score is the most visible number in the app and a badly-scaled one either demotivates every user or is trivially maxed. |
| `BL-146` | `react-native-svg` is a first-time production import; Jest/web support unverified | infra | SS-021 / Architect | `react-native-svg@^15.15.5` is in `mobile/package.json` and `package-lock.json` but is imported by **zero** files in this repo. SS-021's `components/ui/CircularProgress.tsx` is its first real use. Two unverified things: (a) `mobile/jest.config.js` overrides `transformIgnorePatterns` with an explicit allowlist that does not include `react-native-svg`, so it may need adding; (b) its `react-native-web` rendering path has never been exercised in this web-first app. The design specifies a documented fallback (linear `ProgressBar` behind the same props/testIDs/a11y contract) rather than adding a new dependency. Keep open if the fallback is taken — the ticket's AC says *circular* progress widget. |
| `BL-147` | React Native `Share` is a no-op on web — both share buttons do nothing on the primary target | infra | SS-021 / Architect | SS-023's `AcceptedOutfitPanel.handleShare` and SS-021's style-score share both call `Share.share()` from `react-native` inside a `try/catch`. `Share` is a native-only module; under `react-native-web` it is unimplemented, so on the web build (this app's web-first primary target) the button silently does nothing — the `catch` swallows it and the user gets no feedback. Distinct from `BL-141`, which is about *image* export; this is about the share *transport* on web, and would still be broken if PNG export existed. Fix is a small web branch in each seam's `.web.ts` (`navigator.share` where available, clipboard-copy + toast otherwise). Not fixed inside a 1-point ticket. |

**Unchanged / re-scanned:**
- `BL-141` (infra) — stays **Active**, unchanged. Its 2026-08-07 decision is applied verbatim (§7); this ticket is the second consumer of it, confirming the row's "both tickets" framing. Not resolved — the verification spike still hasn't happened.
- `BL-075` (schema) — stays **Active**, unchanged. SS-021 follows the recorded whole-rupees precedent for `cost_per_wear` and adds no new money column, so it neither resolves nor extends the row.
- `BL-022` (tokens) — stays **Active**, unchanged. Not applicable to this ticket (no colour swatches rendered).
- `BL-007` (tokens) — reaffirmed, not resolved: the absence of semantic status colours is why the score ring uses a single `accent.marigold` fill instead of red/amber/green banding (§5.6).
- `BL-049` (infra) — unchanged; SS-021 adds a **new** 14th event (`style_score_shared`) and wires the pre-existing `premium_paywall_viewed` with `source: 'style_score'`. That is one of BL-049's 8 remaining events getting a real call site — the orchestrator may want to note it on the row, but the other 7 are untouched.
- No Active row is resolved by this ticket.

---

## 12. Risk classification

**Risk: med** — additive, read-only UI over data the caller already owns: no migration, no RLS change, no new endpoint, no secret, no auth code, no money movement, no irreversible or external-facing action; every write path it touches is a React Query cache invalidation.

Why this **revises** the prior pass's `Risk: high` rather than inheriting it: that classification was correct *for that design*. A new internet-reachable Edge Function running `verify_jwt = false` with hand-rolled JWT verification and server-side `plan_tier` gating is unambiguously a one-way door under `docs/OPERATOR_RULEBOOK.md` §C2 — it is auth surface, it is external-facing, and `BL-069` documents two production-only defects that exact surface already shipped. This design removes the surface instead of hardening it, so the risk it was classifying no longer exists. Classifying `high` anyway would be inheriting a label rather than reasoning about the artefact.

Why `med` and not `low`: it touches premium/tier gating (money-adjacent, even as a display gate), it renders a number users will treat as authoritative, and it makes the first production use of a previously-unused native dependency. None of those is a one-way door, but none is a placeholder screen either.

**Process note that overrides the lane:** `med` puts this on the fast lane, but Open Questions #1 and #2 are genuine architecture decisions that deviate from the ticket's stated shape and set a precedent for future premium features. **The orchestrator should pause for sign-off on those two before invoking the Developer**, then fast-lane the rest. This is a request for one gate on a specific question, not a re-classification — inflating the `Risk:` line to buy a gate would corrupt the signal the rulebook relies on.
