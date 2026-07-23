# SS-005 — Design: Home Screen Shell + Bottom Tab Navigation

## Scope restatement

Build the 5-tab bottom navigation shell (Home, Wardrobe, Style, Discover, Profile) using Expo Router's `(tabs)` group with a fully custom tab bar (64px + safe-area inset, marigold active icon + dot indicator, muted inactive icon, haptic feedback, debounced presses), and flesh out the Home tab into a real (not placeholder) screen: a name-personalized greeting, a horizontally-scrollable 6-item occasion quick-select pill row that deep-links into the Style tab with that occasion pre-selected, an "Add your first item" wardrobe nudge, and a static "trending picks" placeholder section reserved for Epic 6. The other four tabs ship as styled empty states (illustration placeholder + heading + muted subtext) for this ticket, except Profile, which additionally gets one real, functioning entry point — "Edit Preferences" — wired to `router.push('/onboarding')`, closing BL-023's long-open gap now that a Profile tab finally exists to navigate from. This is a pure client-side navigation/UI ticket: no schema changes, no new writes, one new read (the user's `full_name` for the greeting).

## Current codebase state (verified, not assumed)

- `app/(tabs)/_layout.tsx` currently renders `<Slot />` (not `<Tabs>`) once the Auth Guard passes — its own comment states this is deliberate, left for this ticket to fill in. `app/(tabs)/index.tsx` is SS-008's disposable `Card`/`Text` smoke test, explicitly flagged for full replacement by this ticket.
- No `wardrobe.tsx`/`style.tsx`/`discover.tsx`/`profile.tsx` route files exist yet under `app/(tabs)/` — all four are net-new.
- `components/ui/Badge.tsx`'s `OccasionKey` covers only 4 of the DB's 12 `occasion_type` enum values (`wedding`, `office`, `festival`, `casual`) — **BL-008**, still open (see "Concrete values" below for the call this ticket makes).
- A **separate**, already-seeded reference table `occasion_types` (`supabase/migrations/003_onboarding_taxonomies.sql`) holds 9 rows including exactly the 6 keys this ticket's pills need (`office`, `wedding`, `festival`, `casual`, `date`, `party`) — distinct from the `occasion_type` enum used by `wardrobe_items`/`outfits` (which spells the same two concepts `wedding_guest`/`date_night`). This ticket reuses the reference table's naming for consistency with the already-shipped onboarding vocabulary the user has already seen, not the wardrobe-tagging enum.
- `react-native-safe-area-context` is a direct dependency but **`SafeAreaProvider` is not mounted anywhere in the app tree** (confirmed: no match for `SafeAreaProvider`/`useSafeAreaInsets` anywhere in `mobile/`). The custom tab bar's `useSafeAreaInsets()` call would throw at runtime without it — this ticket must add the provider to the root layout, not just consume the hook.
- `app.json` already sets `"orientation": "portrait"` and `"scheme": "stylesense"` — the ticket's portrait-lock edge case and the deep-link AC's prerequisite are already satisfied; no `app.json` change needed.
- `lucide-react-native` (named in the ticket's Technical Notes as an option) is **not** in `package.json`; only `@expo/vector-icons` is installed and is already the established icon pattern (`IconButton.tsx` imports `Ionicons` from it). This design uses `Ionicons`, not `lucide-react-native`, to avoid adding a new icon-library dependency for one ticket when an equivalent, already-used one exists.
- `features/auth/auth.store.ts`'s `Session` has no `full_name` — that field lives only in `public.users`, fetched via a new query (there is no existing "current user profile" hook to reuse; `onboarding.service.ts`'s `fetchOnboardingProgress` fetches it but is onboarding-domain-scoped, not appropriate to import from `features/home`).
- `app/(auth)/onboarding.tsx` already supports resumable/pre-filled re-entry via `useOnboardingProgressQuery` + `hydrateFromProgress` — no changes to onboarding are needed for BL-023's "Edit Preferences" entry point to work; a plain `router.push('/onboarding')` from Profile is sufficient. **Known caveat**, already tracked as **BL-030** (not this ticket's to fix): `showResumePrompt` in `onboarding.tsx` shows "Welcome back!" framing for *any* user with a non-null `full_name`, including a fully-onboarded user editing preferences — so tapping "Edit Preferences" will show the Resume prompt, not a dedicated "Edit" framing. Flagged again below in Edge Cases; out of scope here (it's onboarding-domain logic, not navigation-shell logic).
- `wardrobe_items` already exists as a full table in `types/supabase.ts`/`001_initial.sql`, but no ticket has built a wardrobe list/upload feature yet (Epic 2, not scheduled). This ticket therefore cannot meaningfully query "does this user have wardrobe items yet" — see "Concrete values" for the resulting nudge-visibility decision.

## Files to create/modify

### New — `mobile/features/navigation/` (new domain: tab-bar chrome, not owned by any single existing feature)

1. **`navigation.types.ts`** — `TabRouteName = 'index' | 'wardrobe' | 'style' | 'discover' | 'profile'`; `TabConfig { name: TabRouteName; label: string; activeIcon: IoniconName; inactiveIcon: IoniconName; accessibilityLabel: string }`.
2. **`navigation.constants.ts`** — the fixed `TAB_CONFIG: TabConfig[]` (5 entries, see "Concrete values").
3. **`components/CustomTabBar.tsx`** — the custom tab bar rendered via `<Tabs tabBar={...}>`. Reads React Navigation's standard `{ state, descriptors, navigation, insets }` tab-bar render-prop shape (Expo Router's `<Tabs>` forwards this from `@react-navigation/bottom-tabs`). Per tab: `Ionicons` icon (`activeIcon` in `colors.accent.marigold` when focused, `inactiveIcon` in `colors.text.muted` otherwise), a `Text variant="caption"` label, a 6px marigold dot below the icon only when focused. Debounces rapid presses (see "Edge cases"). Fires `Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light)` on every handled press.

### New — `mobile/features/home/`

4. **`home.types.ts`** — `OccasionPill { key: string; label: string; icon: string }`.
5. **`home.constants.ts`** — `OCCASION_PILLS: OccasionPill[]`, the fixed 6-item list (see "Concrete values"). Deliberately a hardcoded local constant, not DB-fetched — see "Concrete values" for why.
6. **`home.service.ts`** — `fetchUserFirstName(userId): Promise<string | null>` — `supabase.from('users').select('full_name').eq('id', userId).maybeSingle()`, returns `data?.full_name ?? null`; swallows errors internally the same way `checkOnboardingCompleted` does (fail safe to `null` → generic greeting, never crash the Home screen over a name lookup).
7. **`home.queries.ts`** — `useUserGreetingQuery(userId: string | undefined)`, wraps `fetchUserFirstName`, `enabled: Boolean(userId)`.
8. **`components/GreetingHeader.tsx`** — renders the time-of-day greeting + name (or generic fallback), reading `useUserGreetingQuery`.
9. **`components/OccasionPillRow.tsx`** — horizontal `ScrollView` (not `FlashList` — 6 fixed items is not a "large list" per CLAUDE.md's FlashList rule) of `Badge`s built from `OCCASION_PILLS`, each with `icon` (emoji) + `label`, `onPress` navigating to Style tab with the occasion param.
10. **`components/WardrobeNudgeCard.tsx`** — `Card` with heading copy + "Add your first item" `Button`, navigating to the Wardrobe tab.
11. **`components/TrendingPicksPlaceholder.tsx`** — static `Card`, "Trending Picks" heading + "Personalized picks are coming soon" muted subtext. No data fetch (Epic 6 not started).

### New — `mobile/components/ui/EmptyState.tsx` (+ export from `index.ts`)

12. Generic, reusable empty-state primitive (illustration placeholder = a large centered `Ionicons` glyph in `colors.text.muted`, heading `Text variant="heading"`, subtext `Text variant="caption" color="secondary"`, optional `children` slot for a CTA). Used by Wardrobe/Discover/Style/Profile tabs. This is a shared design-system primitive (not domain-specific), the same category as `Card`/`Badge` — fits `components/ui/`'s existing scope even though it's introduced by this ticket rather than SS-008.

### New — route files under `mobile/app/(tabs)/`

13. **`wardrobe.tsx`** — `<EmptyState icon="shirt-outline" heading="Your wardrobe is empty" subtext="Add your first item to get outfit suggestions." />`.
14. **`style.tsx`** — reads `useLocalSearchParams<{ occasion?: string }>()`. If `occasion` is present and matches a known `OCCASION_PILLS` key, heading becomes `"{Label} looks — coming soon"`; otherwise the same generic empty state as the other tabs (`"Nothing here yet"` / `"Outfit suggestions are on the way."`). This is the minimum needed to satisfy the AC ("navigates to the Style tab with that occasion pre-selected") without building real styling-AI functionality, which is out of scope (SS-006/SS-007, not this ticket).
15. **`discover.tsx`** — same generic `EmptyState` pattern as Wardrobe.
16. **`profile.tsx`** — **not** a bare empty state. Renders `Avatar` (initials, from the same greeting-name query) + heading "Profile" + an **"Edit Preferences" `Button`** whose `onPress` is `() => router.push('/onboarding')` (closes **BL-023**), plus a muted subtext noting more profile features are coming soon.

### Modified

17. **`mobile/app/(tabs)/_layout.tsx`** — replace the guarded `<Slot />` with a guarded `<Tabs screenOptions={{ headerShown: false }} tabBar={(props) => <CustomTabBar {...props} />}>` containing five `<Tabs.Screen name=... options={{ title: ... }} />` entries (`index`/`wardrobe`/`style`/`discover`/`profile`). The existing loading-Card / `<Redirect href="/login" />` guard logic above it is unchanged.
18. **`mobile/app/(tabs)/index.tsx`** — full rewrite: `GreetingHeader` + `OccasionPillRow` + `WardrobeNudgeCard` + `TrendingPicksPlaceholder`, composed in a `ScrollView` (the screen has more content than one viewport on small devices).
19. **`mobile/app/_layout.tsx`** — wrap the existing tree in `<SafeAreaProvider>` from `react-native-safe-area-context` (must be an ancestor of anything calling `useSafeAreaInsets()`, which nothing in the app currently mounts — see "Current codebase state").
20. **`mobile/components/ui/index.ts`** — add `EmptyState` export.
21. **`mobile/__tests__/app/(tabs)/_layout.test.tsx`** — extend the existing `expo-router` mock to also stub `Tabs`/`Tabs.Screen` (currently only mocks `Redirect`/`Slot`); update the "renders guarded child content" assertion from `<Slot />`'s `testID="slot"` to whatever the `Tabs` mock renders.
22. **`mobile/__tests__/app/(tabs)/index.test.tsx`** — full rewrite; the current file is an SS-008-era smoke test asserting the old placeholder `Card`/`Text` content, which no longer exists after this ticket.

## Concrete values to use, not invent

**Tab config** (`navigation.constants.ts`), `Ionicons` names chosen from the already-installed `@expo/vector-icons` set (filled = active, `-outline` = inactive, matching `IconButton.tsx`'s existing filled/ghost color convention):

| name (route file) | label | activeIcon | inactiveIcon |
|---|---|---|---|
| `index` | Home | `home` | `home-outline` |
| `wardrobe` | Wardrobe | `shirt` | `shirt-outline` |
| `style` | Style | `sparkles` | `sparkles-outline` |
| `discover` | Discover | `compass` | `compass-outline` |
| `profile` | Profile | `person` | `person-outline` |

**Tab bar colors/dimensions** (from `components/ui/tokens.ts`, transcribed, not invented):
- Background: `colors.bg.primary` (`#FAFAF7`, "warm off-white" per the ticket's own wording — matches this token's SS-008 naming, not a new value).
- Active icon + dot indicator: `colors.accent.marigold` (`#E8A420`).
- Inactive icon + label: `colors.text.muted` (`#9A9590`).
- Height: 64px content area (per AC) **plus** `insets.bottom` as additional `paddingBottom` (i.e. total rendered height = `64 + insets.bottom`, not 64px shrunk to fit) — this is the Architect's decision for *how* the 64px figure composes with safe-area insets, since the ticket states the number but not the composition.
- Dot indicator: 6px diameter circle, `colors.accent.marigold`, rendered only when `state.index === route's index` (i.e. only under the focused tab).
- Top border: 1px hairline, `colors.text.muted`, to separate the bar from scrollable content above it (Architect's decision — ticket doesn't specify, but a flush edge-to-edge bar with no content beneath it needs no separator on other edges).

**Occasion pills** (`home.constants.ts`) — fixed, hardcoded (not DB-fetched; see reasoning below), 6 entries per the raw ticket's AC verbatim, keys matching the already-seeded `occasion_types` reference table (`supabase/migrations/003_onboarding_taxonomies.sql`) rather than the `occasion_type` enum:

| key | label | icon |
|---|---|---|
| `office` | Office | 💼 |
| `casual` | Casual | ☀️ |
| `wedding` | Wedding | 💍 |
| `festival` | Festival | 🪔 |
| `date` | Date | ❤️ |
| `party` | Party | 🎉 |

Why hardcoded rather than fetched via `useOnboardingTaxonomiesQuery` (which already fetches all 9 `occasion_types` rows): this is a fixed, curated 6-item UI element the ticket's AC pins down verbatim (specific emoji, specific 6-of-9 subset, specific order) — not a product-editable list the way onboarding's Step 3 chip set is. Onboarding's own `onboarding.constants.ts` already establishes the precedent of hardcoding "structurally stable" option sets locally rather than fetching everything from the DB; this list is the same category. No loading/error state is needed for the pill row itself as a result — only the greeting name involves a network call.

**Badge styling for the 6 pills — BL-008 call for this ticket**: `Badge`'s `OccasionKey` only colors 4 of these 6 (`office`, `wedding`, `festival`, `casual`; `date` and `party` have no defined color). Per the same precedent SS-004's Architect already set for its analogous 9-chip gap (ship all-neutral rather than a patchy 4-colored/2-neutral set), **all 6 pills render with `Badge`'s neutral style (no `occasion` prop)** — only `icon` (emoji) + `label` + `onPress` are passed. This keeps the pill row visually consistent and doesn't invent colors for `date`/`party`. BL-008's row is updated below to note this second, now-resolved-the-same-way instance; the underlying token gap remains open.

**Greeting logic** (`GreetingHeader.tsx`): time-of-day text computed from the current hour **in `Asia/Kolkata`** (per CLAUDE.md's India-specific IST rule — do not use device-local time, which may differ for a traveling user), via `Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', hour: 'numeric', hourCycle: 'h23' })`:
- hour `< 12` → "Good morning"
- `12 <= hour < 17` → "Good afternoon"
- `hour >= 17` → "Good evening"

Full greeting: `"{greeting}, {firstName}!"` when a name is available (first word of `full_name`, matching `Avatar.tsx`'s own `getInitials` precedent of splitting on whitespace); `"{greeting}!"` (no name clause) when the query is loading, errored, or resolves to `null`/empty (e.g. a user who tapped "Skip" before Step 1 and never set a name) — never a blank/undefined string, never a loading spinner blocking the rest of the screen.

**Wardrobe nudge visibility**: always rendered (not conditional on an actual `wardrobe_items` count). No Wardrobe-domain query is built by this ticket — see "Current codebase state": the table exists but no upload/list feature does yet (Epic 2, unscheduled), so there is no real "has items" signal to query against yet without building throwaway wardrobe-domain scope inside a navigation-shell ticket. This is logged to the backlog (see below) as a known gap the eventual Wardrobe epic ticket must close (nudge should stop showing once a user has ≥1 item).

**"Add your first item" CTA target**: `router.push('/wardrobe')` (the Wardrobe tab's own empty state) — there is no dedicated upload/add-item screen yet. Logged to backlog alongside the nudge-visibility gap.

## Edge cases

Carried forward from the ticket, plus new ones found in this codebase pass:

- Android 3-button nav vs. gesture nav: `useSafeAreaInsets()`'s `bottom` value differs between the two automatically; the tab bar's `paddingBottom: insets.bottom` handles both without a platform branch. **Requires `SafeAreaProvider` to be mounted** (see file #19) — without it this hook throws, not just returns 0.
- Rapid tab switching: `CustomTabBar` tracks the last-handled-press timestamp in a `useRef`; any press within 400ms of the previous handled press is ignored before calling `navigation.navigate(...)` — a concrete, testable debounce window (the ticket names the requirement but not a duration).
- Portrait-lock: already satisfied by the existing `app.json` (`"orientation": "portrait"`) — no change needed.
- Pressing an already-focused tab: React Navigation's default `tabPress` behavior is a no-op re-navigation (stays on the same screen, doesn't reset its stack) — verify this is still true for the installed `expo-router@~56.2.11`/underlying `@react-navigation/bottom-tabs` version (see Open Questions — Expo v56 verification note) rather than assuming it from general React Navigation knowledge.
- Greeting query failure/slow network: falls back to the no-name greeting variant (see "Concrete values") rather than blocking the screen or showing an error banner — no user-facing error state is needed here (this is decorative personalization, not a form/transaction; **BL-007 does not apply** — there's no validation/error surface on this screen that needs a semantic error color).
- User with no `full_name` set (skipped onboarding before Step 1, or declined at Step 1 and later hit "Skip"): greeting renders without a name clause, not `"Good morning, !"` or `"Good morning, undefined!"`.
- Style tab reached with an unrecognized/garbage `occasion` query param (e.g. manually-typed deep link `stylesense://style?occasion=xyz`): falls back to the generic empty-state copy rather than rendering `"undefined looks — coming soon"` — the param is validated against `OCCASION_PILLS`' known keys before use.
- Profile → "Edit Preferences" for an already-fully-onboarded user: reaches `/onboarding`, which (per **BL-030**, already logged, not this ticket's to fix) will show the `ResumePrompt`'s "Welcome back!" framing rather than a dedicated "edit" framing, because `showResumePrompt` only checks for a non-null `full_name`, not `onboarding_completed`. The user's actual saved answers do still pre-fill correctly (fix pass 5) — only the *framing* is slightly off, a known open UX question.
- `EmptyState`'s illustration placeholder is a static icon glyph, not a real illustration asset (none exist in this repo) — matches the ticket's own wording ("illustration placeholder"), not a gap this ticket introduces.
- Web (this is a web-first Expo app): the custom tab bar must render correctly under `react-native-web` too — `Ionicons`/`Pressable`/`expo-haptics` all already have web-safe behavior elsewhere in this codebase (`IconButton.tsx` uses the same `Ionicons`; `expo-haptics` no-ops silently on web per its own docs, already an implicit dependency of no other ticket flagging an issue with it).

## Test plan

- `mobile/__tests__/features/navigation/components/CustomTabBar.test.tsx`
  - renders all 5 tab labels/icons from `TAB_CONFIG`.
  - focused tab renders its `activeIcon` + marigold dot indicator; unfocused tabs render `inactiveIcon`, no dot, muted color.
  - pressing a tab calls `navigation.navigate` with that tab's route name.
  - pressing the same tab twice within 400ms only calls `navigation.navigate` once (debounce).
  - pressing a tab calls `Haptics.impactAsync` (mocked).
  - tab bar's rendered height/padding reflects a non-zero `insets.bottom` passed via props (safe-area composition).
- `mobile/__tests__/features/home/home.service.test.ts`
  - `fetchUserFirstName` selects `full_name` from `users`, filtered by `eq('id', userId)`.
  - resolves `null` (not throw) when the row is missing or the query errors.
- `mobile/__tests__/features/home/home.queries.test.tsx`
  - `useUserGreetingQuery` is `enabled: false` when `userId` is `undefined`; fires when defined.
- `mobile/__tests__/features/home/components/GreetingHeader.test.tsx`
  - renders `"Good morning/afternoon/evening, {name}!"` for each of the 3 IST hour bands (mock `Date`/`Intl` or inject a fixed hour).
  - renders the no-name variant when the query resolves `null`, is `isLoading`, or `isError` — never renders `undefined`/blank interpolation.
- `mobile/__tests__/features/home/components/OccasionPillRow.test.tsx`
  - renders exactly 6 pills with the labels/icons from `OCCASION_PILLS`, in the fixed order.
  - every pill renders via `Badge`'s neutral style (no `occasion` prop passed) — regression guard for the BL-008 call.
  - tapping a pill navigates to `/style` with that pill's `key` as the `occasion` param.
- `mobile/__tests__/features/home/components/WardrobeNudgeCard.test.tsx`
  - renders the "Add your first item" CTA; tapping it navigates to `/wardrobe`.
- `mobile/__tests__/components/ui/EmptyState.test.tsx`
  - renders the given icon/heading/subtext; renders optional `children` (CTA slot) only when provided.
- `mobile/__tests__/app/(tabs)/wardrobe.test.tsx` / `discover.test.tsx`
  - renders the expected `EmptyState` heading/subtext for each tab.
- `mobile/__tests__/app/(tabs)/style.test.tsx`
  - with a valid `occasion` param, renders `"{Label} looks — coming soon"`.
  - with no param, or an unrecognized param, renders the generic empty-state copy (not `"undefined looks…"`).
- `mobile/__tests__/app/(tabs)/profile.test.tsx`
  - renders the "Edit Preferences" button; tapping it calls `router.push('/onboarding')` (BL-023 regression guard).
- `mobile/__tests__/app/(tabs)/index.test.tsx` (rewritten)
  - renders `GreetingHeader`, `OccasionPillRow`, `WardrobeNudgeCard`, `TrendingPicksPlaceholder` (composition smoke test).
- `mobile/__tests__/app/(tabs)/_layout.test.tsx` (updated)
  - existing loading/redirect assertions unchanged; the "guarded content" assertion now checks for the mocked `Tabs` output instead of `Slot`'s.

## Open questions / blockers

1. **Expo Router `<Tabs>`/custom `tabBar` API — needs Developer verification against the actually-installed version, not trained knowledge.** `mobile/AGENTS.md` explicitly states "Expo HAS CHANGED — read the exact versioned docs at https://docs.expo.dev/versions/v56.0.0/ before writing any code." This design's `<Tabs tabBar={(props) => <CustomTabBar {...props} />}>` shape, the `{ state, descriptors, navigation, insets }` render-prop signature, and the "pressing the focused tab is a no-op" assumption are all [trained-knowledge / inference], not `[VERIFIED]` against `expo-router@~56.2.11`'s actual current API surface (per `docs/OPERATOR_RULEBOOK.md` §E, since this is load-bearing for the whole ticket) — I have no web-fetch tool available in this pass to check the versioned docs directly. **The Developer phase must read the installed package's own type definitions (`node_modules/expo-router/build/...`) and/or the versioned docs before implementing**, and flag back if the actual API differs materially from what's assumed here (e.g. if `tabBar` is not a valid `<Tabs>` prop in this version and a different customization mechanism — `screenOptions.tabBarButton` per-screen, or wrapping with `@react-navigation/bottom-tabs` directly — is required instead).
2. **Deep linking (`stylesense://wardrobe`) is assumed to work automatically** from Expo Router's file-based routing + the already-set `"scheme": "stylesense"` in `app.json`, with no additional linking config. This is [inference] from Expo Router's documented convention (route-group folders in parens are excluded from the URL), not verified against a real device/simulator test (compounds with the already-logged **BL-013**, "Expo dev server unreachable from phone on same WiFi" — deep-link testing needs the same on-device access BL-013 blocks). Flag to QA/manual verification once BL-013 is unblocked.
3. **BL-023 — resolved by this design**: Profile tab's "Edit Preferences" button (`router.push('/onboarding')`) makes the AC reachable end-to-end. Moved to Resolved below.
4. **BL-008 — still open**, but this ticket's specific instance of it (6 pills, 2 uncolored) is resolved the same way SS-004 resolved its instance (all-neutral). The underlying "product needs to pick 8 more occasion colors" decision remains outstanding for whoever eventually needs colored badges for `date_night`/`travel`/`puja`/etc.
5. **New backlog item**: no live "does this user have wardrobe items" signal exists yet for the Home screen's wardrobe-nudge visibility, and no "add item" upload flow exists for its CTA to land on — both are deferred to the (unscheduled) Wardrobe epic. Logged as **BL-031** below.
6. **BL-030** (already logged): confirmed still applicable and unresolved by this ticket — Profile → Edit Preferences will surface the "Welcome back!" framing for a fully-onboarded user. Not fixed here (onboarding-domain logic, out of this ticket's scope).

## Risk classification

`Risk: low` — this ticket is purely client-side navigation/UI (tab shell, empty states, one read-only query for a display name). No schema/migration changes, no writes, no auth/payment/RLS/secrets surface, nothing external-facing beyond a deep-link scheme that's already configured. The one non-trivial technical uncertainty (Expo Router's exact v56 `<Tabs>` customization API) is a correctness risk to flag for Developer verification, not a one-way-door risk — worst case it's a same-ticket implementation fix, not a rollback of shipped data or a security gap.
