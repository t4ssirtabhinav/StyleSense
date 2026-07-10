# SS-008 — Design: Design System Foundation (UI Kit)

## Scope restatement

This ticket builds the foundational `components/ui/` design-system kit — nine components (Button, Text, Card, Badge/Chip, Avatar, BottomSheet, Input, IconButton, Skeleton) plus a `tokens.ts` source of truth for colours, typography, spacing and radii — wired into NativeWind's Tailwind config and Expo's font-loading pipeline, so that every subsequent screen ticket (SS-003 Phone OTP Auth, SS-004 Onboarding Wizard, SS-005 Home Shell) can satisfy CLAUDE.md's "never use raw `View`/`Text`, never use `StyleSheet.create`" rules by importing from `components/ui/index.ts` instead. This is a from-scratch build (no `mobile/components/` directory exists yet), and it is the first ticket to run through the 4-phase pipeline, so this design doc also has to fix the exact component API surface (props/variants) other tickets will code against, and decide whether `mobile/app/index.tsx`'s existing raw `View`/`Text` usage gets migrated now or deferred to SS-005.

## Current codebase state (verified, not assumed)

- `mobile/components/` does not exist yet — nothing to migrate, this is greenfield.
- `mobile/tailwind.config.js` already has a flat `theme.extend.colors` block: `brand: '#E8A420'`, `dark: '#1A1714'`, `peacock: '#0D6B6E'`, `emerald: '#2D6A4F'`, `rose: '#C45B7C'` — these are the same hex values as `accent.marigold`/`bg.dark`/`accent.peacock`/`accent.emerald`/`accent.rose` in the ticket's token spec, confirming the ticket's own reconciliation note. No `fontFamily`, `spacing`, or `borderRadius` extensions exist yet.
- `mobile/app/index.tsx` (13 lines) uses raw `View`/`Text` with `bg-white`, `text-dark`, `text-peacock` classes — pre-dates the new rule, as the ticket's Status note says.
- `mobile/app/_layout.tsx` (7 lines) is a bare `<Stack screenOptions={{ headerShown: false }} />` — no font loading, no `GestureHandlerRootView`, no `BottomSheetModalProvider`, no auth/Sentry wiring yet.
- `mobile/babel.config.js`: `babel-preset-expo` + `nativewind/babel` only. `metro.config.js` wires `withNativeWind(config, { input: './global.css' })`. `global.css` has the three standard `@tailwind` directives. This part of the pipeline is complete and needs no changes.
- `mobile/jest.config.js` already has `collectCoverageFrom: ['features/**/*.{ts,tsx}', 'components/ui/**/*.{ts,tsx}']` — the coverage config already anticipates this ticket's output; no jest config changes needed.
- `mobile/package.json` dependencies relevant to this ticket:
  - **Already present** (do not re-add): `@gorhom/bottom-sheet@^5.2.14`, `react-native-reanimated@^4.5.0`, `react-native-worklets@0.8.3`, `react-native-gesture-handler@^3.0.2`, `react-native-safe-area-context@~5.7.0`, `react-native-svg@^15.15.5`, `expo-image@^56.0.11`, `nativewind@^4.2.6`, `tailwindcss@^3.4.19`. `@react-native-masked-view/masked-view` is present transitively in `node_modules` (pulled in by `@gorhom/bottom-sheet`'s dependency tree) but is **not** a direct `package.json` dependency — do not import it directly without adding it explicitly first.
  - **Missing, must be added** (see "Concrete values" and "Open questions" below): `expo-font`, five `@expo-google-fonts/*` packages, and an icon library (`@expo/vector-icons`, needed by `IconButton` here and by SS-005's tab bar icons). None of these exist in `package.json` or `node_modules` today — verified via glob, zero matches.
- `mobile/biome.json` has `noExplicitAny: "error"` already enabled — every new component must be fully typed, no `any`, consistent with CLAUDE.md.

## Files to create/modify

### New files — `components/ui/`

1. **`mobile/components/ui/tokens.ts`** — transcribes the ticket's exact token block (colours, typography, spacing, radii) verbatim as the single TS source of truth. Re-exported via `index.ts` so consumers can do `import { colors, spacing } from 'components/ui'` for non-className use-cases (e.g. `FlashList estimatedItemSize`, Reanimated shared values, Skeleton dimensions).
2. **`mobile/components/ui/Text.tsx`** — 5 variants: `display | heading | body | caption | mono`.
3. **`mobile/components/ui/Button.tsx`** — 3 colour variants (`primary | secondary | ghost`) + `disabled` and `loading` boolean props (see reconciliation note below).
4. **`mobile/components/ui/Card.tsx`** — 3 variants: `elevated | flat | outlined`.
5. **`mobile/components/ui/Badge.tsx`** — occasion-colour-coded chip, doubles as a selectable pill for SS-004/SS-005.
6. **`mobile/components/ui/Avatar.tsx`** — image avatar with initials fallback, uses `expo-image`.
7. **`mobile/components/ui/BottomSheet.tsx`** — thin wrapper around `@gorhom/bottom-sheet`'s `BottomSheetModal`.
8. **`mobile/components/ui/Input.tsx`** — 4 variants: `text | phone | search | otp` (see detailed API below — this is the file SS-003 depends on most).
9. **`mobile/components/ui/IconButton.tsx`** — icon-only pressable, wraps `@expo/vector-icons` `Ionicons`.
10. **`mobile/components/ui/Skeleton.tsx`** — shimmer placeholder, variants `card | listItem | circle | text`.
11. **`mobile/components/ui/index.ts`** — re-exports every component above plus `tokens.ts`'s named exports. This is the only import surface other domains should use (`import { Button, Text, Input } from '../../components/ui'`).

### New supporting files

12. **`mobile/lib/fonts.ts`** — exports a single `fontAssets` object (the exact `@expo-google-fonts` imports mapped to the family-constant keys `useFonts` expects), imported once by `_layout.tsx`. Centralising this avoids every screen needing to know the raw font-constant names.
13. **`mobile/app/dev-ui-kit.tsx`** — the ticket's required "Storybook-style test screen", a plain Expo Router route (reachable at `/dev-ui-kit` since the app is web-first) rendering every component/variant combination. Not linked from any tab bar or nav; dev-only by convention, not by build-time exclusion (see Open Questions).

### Modified files

14. **`mobile/tailwind.config.js`** — extend `theme.extend` with `fontFamily`, `spacing`, `borderRadius`, and additional flattened colour keys (existing `brand`/`dark`/`peacock`/`emerald`/`rose` keys stay untouched for backward compatibility — nothing currently using them breaks).
15. **`mobile/app/_layout.tsx`** — add `useFonts(fontAssets)` from `expo-font`, wrap the tree in `GestureHandlerRootView` (required by `react-native-gesture-handler`, a peer dep of `@gorhom/bottom-sheet`) and `BottomSheetModalProvider` (required once, at root, per `@gorhom/bottom-sheet` v5 docs, for any screen to use `BottomSheetModal`), and log `fontError` to Sentry per the ticket's edge case. Do **not** gate rendering on `fontsLoaded` (see rationale in Edge Cases below — avoids the "blank screen" failure mode by design, not by adding a splash-screen dependency).
16. **`mobile/package.json`** — add the six missing dependencies listed in "Concrete values" below. (The Architect is flagging these; actually running `npm install` is the Developer's execution step, per this ticket's own instruction not to invent — these package names/versions are standard, well-known Expo SDK 56-compatible packages, not invented values.)
17. **`mobile/app/index.tsx`** — **decision: migrate now, in this ticket's scope.** See dedicated section below.

### New test files

18. `mobile/__tests__/components/ui/tokens.test.ts`
19. `mobile/__tests__/components/ui/Button.test.tsx`
20. `mobile/__tests__/components/ui/Text.test.tsx`
21. `mobile/__tests__/components/ui/Card.test.tsx`
22. `mobile/__tests__/components/ui/Badge.test.tsx`
23. `mobile/__tests__/components/ui/Avatar.test.tsx`
24. `mobile/__tests__/components/ui/Input.test.tsx`
25. `mobile/__tests__/components/ui/IconButton.test.tsx`
26. `mobile/__tests__/components/ui/Skeleton.test.tsx`
27. `mobile/__tests__/components/ui/BottomSheet.test.tsx`
28. `mobile/__tests__/app/index.test.tsx` (updated/added, covers the migrated home screen)

No `features/<domain>/` files are implicated — this ticket is pure `components/ui/` + app-shell wiring, no domain logic, no Supabase calls.

## `mobile/app/index.tsx` migration decision

The ticket's own Status note says migrating this file can happen here or be flagged for SS-005. **Decision: migrate it now**, for three reasons: (1) it is 13 lines and trivial — low cost; (2) it is the single best smoke test that `Button`/`Text`/`Card` actually render correctly end-to-end before three dependent tickets start consuming them; (3) leaving known-non-compliant code in the tree while simultaneously introducing the rule that forbids it is an avoidable inconsistency for a reviewer to trip over. **Caveat to flag to the Developer:** SS-005 ("Home Screen Shell") will very likely replace this file's *entire contents* with the real home screen (greeting, occasion pills, wardrobe nudge) once it lands — so treat this migration as a thin, disposable proof that the new `Text`/`Card` components work, not as an investment worth polishing. Suggested migrated content: wrap the existing three lines of text in a `Card variant="flat"` with `Text variant="heading"` for "StyleSense" and `Text variant="body"` for the two status lines, replacing `bg-white`/`text-dark`/`text-peacock` with the new token-driven classes.

## Concrete values to use, not invent

### Design tokens (verbatim from the ticket — do not restyle)

```ts
// mobile/components/ui/tokens.ts
export const colors = {
  bg: {
    primary: '#FAFAF7',
    secondary: '#F4F2ED',
    dark: '#1A1714',
  },
  accent: {
    marigold: '#E8A420',
    peacock: '#0D6B6E',
    rose: '#C45B7C',
    emerald: '#2D6A4F',
  },
  text: {
    primary: '#1A1714',
    secondary: '#5A5550',
    muted: '#9A9590',
  },
  occasion: {
    wedding: '#D4A574',
    office: '#4A7FA5',
    festival: '#E8A420',
    casual: '#78A878',
  },
} as const;

export const typography = {
  display: 'Playfair Display',
  heading: 'Poppins',
  body: 'DM Sans',
  mono: 'JetBrains Mono',
  hindi: 'Noto Sans Devanagari',
} as const;

export const spacing = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32, xxl: 48 } as const;
export const radii = { sm: 8, md: 12, lg: 16, xl: 24, pill: 100 } as const;
```

Reconciliation with the existing repo colours (ticket's own note, confirmed against `mobile/tailwind.config.js`): `brand` (#E8A420) = `accent.marigold`; `dark` (#1A1714) = `bg.dark` = `text.primary`; `peacock` (#0D6B6E) = `accent.peacock`; `emerald` (#2D6A4F) = `accent.emerald`; `rose` (#C45B7C) = `accent.rose`. Keep the existing flat keys in `tailwind.config.js` untouched; add the new nested/flattened keys alongside them, do not delete or rename the existing ones (nothing currently depends on them yet, but no reason to churn `app/index.tsx`'s existing classes twice in one ticket).

### `tailwind.config.js` — exact extension to add

Tailwind class names generated from nested objects stutter the prefix (e.g. `colors.bg.primary` → class `bg-bg-primary`, `colors.text.primary` → class `text-text-primary`). To avoid this, the Tailwind theme layer uses **flattened, renamed keys** that map 1:1 to `tokens.ts`'s nested values — `tokens.ts` stays verbatim per the ticket, `tailwind.config.js` is presentation-layer only:

```js
theme: {
  extend: {
    colors: {
      // existing — unchanged
      brand: '#E8A420',
      dark: '#1A1714',
      peacock: '#0D6B6E',
      emerald: '#2D6A4F',
      rose: '#C45B7C',
      // new — flattened from tokens.ts to avoid `bg-bg-*`/`text-text-*` stutter
      surfacePrimary: '#FAFAF7',      // = colors.bg.primary
      surfaceSecondary: '#F4F2ED',    // = colors.bg.secondary
      textPrimary: '#1A1714',         // = colors.text.primary (dupes `dark`, kept for discoverability)
      textSecondary: '#5A5550',       // = colors.text.secondary
      textMuted: '#9A9590',           // = colors.text.muted
      occasionWedding: '#D4A574',
      occasionOffice: '#4A7FA5',
      occasionFestival: '#E8A420',    // dupes `brand`/`occasionFestival` intentionally — same colour, different semantic name
      occasionCasual: '#78A878',
    },
    fontFamily: {
      display: ['PlayfairDisplay_400Regular'],
      'display-bold': ['PlayfairDisplay_700Bold'],
      heading: ['Poppins_400Regular'],
      'heading-semibold': ['Poppins_600SemiBold'],
      body: ['DMSans_400Regular'],
      'body-medium': ['DMSans_500Medium'],
      mono: ['JetBrainsMono_400Regular'],
      'mono-bold': ['JetBrainsMono_700Bold'],
      hindi: ['NotoSansDevanagari_400Regular'],
    },
    spacing: { xs: '4px', sm: '8px', md: '16px', lg: '24px', xl: '32px', xxl: '48px' },
    borderRadius: { sm: '8px', md: '12px', lg: '16px', xl: '24px', pill: '100px' },
  },
}
```

Note `pill: '100px'` transcribes the ticket's literal `radii.pill = 100` value — do not invent `9999px`; 100px still renders fully pill-shaped for any chip/button under ~200px tall, which covers every component in this ticket.

### Font loading — packages to add and exact family-constant names

The ticket names 5 typefaces but gives no specific weights; `expo-font`/Google Fonts require a distinct package+constant per weight (React Native does not synthesize bold from a single regular-weight custom font file). Decision (flagged for confirmation, not fixed by the ticket): load one Regular + one heavier weight per family, sufficient for the 5 `Text` variants plus a bold/semibold accent option:

```json
// mobile/package.json — dependencies to add
"expo-font": "~14.0.9",
"@expo-google-fonts/playfair-display": "^0.4.1",
"@expo-google-fonts/poppins": "^0.4.1",
"@expo-google-fonts/dm-sans": "^0.4.1",
"@expo-google-fonts/jetbrains-mono": "^0.4.1",
"@expo-google-fonts/noto-sans-devanagari": "^0.4.1",
"@expo/vector-icons": "^15.0.2"
```

(Exact semver ranges must be pinned to whatever the Developer's `npx expo install` resolves for Expo SDK 56 — the above are illustrative, not to be hand-typed without letting `expo install` reconcile them against the installed `expo@~56.0.12`.)

```ts
// mobile/lib/fonts.ts
import {
  PlayfairDisplay_400Regular,
  PlayfairDisplay_700Bold,
} from '@expo-google-fonts/playfair-display';
import { Poppins_400Regular, Poppins_600SemiBold } from '@expo-google-fonts/poppins';
import { DMSans_400Regular, DMSans_500Medium } from '@expo-google-fonts/dm-sans';
import {
  JetBrainsMono_400Regular,
  JetBrainsMono_700Bold,
} from '@expo-google-fonts/jetbrains-mono';
import { NotoSansDevanagari_400Regular } from '@expo-google-fonts/noto-sans-devanagari';

export const fontAssets = {
  PlayfairDisplay_400Regular,
  PlayfairDisplay_700Bold,
  Poppins_400Regular,
  Poppins_600SemiBold,
  DMSans_400Regular,
  DMSans_500Medium,
  JetBrainsMono_400Regular,
  JetBrainsMono_700Bold,
  NotoSansDevanagari_400Regular,
} as const;
```

### Component API surface (fixed by this design doc — other tickets code against this exactly)

**`Text`** (`mobile/components/ui/Text.tsx`):
```ts
type TextVariant = 'display' | 'heading' | 'body' | 'caption' | 'mono';
type TextColor = 'primary' | 'secondary' | 'muted' | 'marigold' | 'peacock' | 'rose' | 'emerald';
interface TextProps extends React.ComponentProps<typeof RNText> {
  variant?: TextVariant;      // default 'body'
  color?: TextColor;          // default 'primary'
  script?: 'latin' | 'devanagari'; // default 'latin'; 'devanagari' forces the Noto Sans Devanagari family regardless of variant, for future Hindi-locale content
  weight?: 'regular' | 'bold'; // maps to the *-bold font-family variant where loaded (display, heading→semibold, mono); 'caption'/'body' only has regular+medium, falls back to medium for weight='bold'
}
```
Variant → font mapping: `display` → Playfair Display, `heading` → Poppins, `body` → DM Sans, `caption` → DM Sans (smaller size, `color='muted'` default), `mono` → JetBrains Mono. `hindi` from the ticket's typography tokens is **not** a 6th `Text` variant — it's exposed via `script="devanagari"` as an override on top of any variant, since the ticket's Text AC only lists 5 variants.

**`Button`** (`mobile/components/ui/Button.tsx`):
```ts
type ButtonVariant = 'primary' | 'secondary' | 'ghost';
interface ButtonProps {
  variant?: ButtonVariant;   // default 'primary'
  disabled?: boolean;
  loading?: boolean;         // shows spinner, disables press, keeps variant's colours at reduced opacity
  fullWidth?: boolean;
  icon?: React.ReactNode;    // leading icon slot
  onPress: () => void;
  children: React.ReactNode;
  accessibilityLabel?: string;
}
```
**Reconciliation note:** the ticket literally lists "primary/secondary/ghost/disabled" as "4 variants," but `disabled` is a state (any of the 3 colour variants can be disabled), not a 4th colour scheme — there is no separate "disabled-coloured" button design implied anywhere else in the ticket. Modelled as `disabled?: boolean` composing with `variant`, not `variant: 'primary'|'secondary'|'ghost'|'disabled'`. Flagging this explicitly since it's a literal-wording vs. intent judgment call — see Open Questions.
Colour mapping (Architect's decision — the ticket fixes the hex values but not which variant uses which): `primary` = bg `accent.marigold` / text `text.primary` (dark text on marigold for contrast — marigold is too light for legible white text); `secondary` = 1px border `accent.peacock`, transparent bg, text `accent.peacock`; `ghost` = no border/bg, text `accent.peacock`, minimal padding. `disabled` (any variant) = bg/border `text.muted`, text white, non-interactive.

**`Card`** (`mobile/components/ui/Card.tsx`):
```ts
type CardVariant = 'elevated' | 'flat' | 'outlined';
interface CardProps {
  variant?: CardVariant;  // default 'flat'
  className?: string;     // additive only (padding/margin/width) — do not use to override variant's bg/border/radius
  children: React.ReactNode;
}
```
Radius-per-variant (Architect's decision, ticket doesn't fix this mapping — chosen to make the 3 variants visually/testably distinct per the AC "3 variants with correct radii"): `elevated` = radius `lg` (16px), shadow, bg `surfacePrimary`; `flat` = radius `md` (12px), no shadow, bg `surfaceSecondary`; `outlined` = radius `sm` (8px), 1px border `text.muted`, bg `surfacePrimary`.

**`Badge`** (`mobile/components/ui/Badge.tsx`):
```ts
type OccasionKey = 'wedding' | 'office' | 'festival' | 'casual';
interface BadgeProps {
  label: string;                        // truncated to 20 chars + '…' if longer (ticket edge case)
  occasion?: OccasionKey;                // colour-codes bg/text; omit for neutral grey badge
  selected?: boolean;                    // toggled/active visual state, for SS-004/SS-005 multi-select pills
  icon?: string;                         // emoji or short icon slot, e.g. "💼" for SS-005's occasion pills
  onPress?: () => void;                  // if present, renders as Pressable (chip); otherwise static (badge)
}
```
Occasion colour → text-colour pairing (Architect's decision): `wedding` (#D4A574, light gold) and `festival` (#E8A420, marigold) use dark text (`text.primary`) for contrast; `office` (#4A7FA5, blue) and `casual` (#78A878, green) use white text.
**Gap found (flag to Product, not silently resolved):** SS-002's `occasion_type` enum has 12 values (`office, casual, date_night, wedding_guest, festival, puja, party, travel, workout, beach, formal_event, college`), but this ticket's occasion colour tokens define only 4 (`wedding, office, festival, casual`). SS-004 (9 occasion options in Step 3) and SS-005 (6 occasion pills including "Date" and "Party") will need colours for occasions this ticket doesn't define. `Badge`'s `occasion` prop is typed to only the 4 known keys; any of the other 8 occasion values must fall back to the neutral/grey badge styling until Product defines the remaining colours — see Open Questions.

**`Avatar`** (`mobile/components/ui/Avatar.tsx`):
```ts
type AvatarSize = 'sm' | 'md' | 'lg'; // 32px / 48px / 64px
interface AvatarProps {
  uri?: string;      // rendered via expo-image; if absent, falls back to initials
  name?: string;     // used to derive up to 2 initials when uri is absent/fails to load
  size?: AvatarSize; // default 'md'
}
```
Always circular (`borderRadius: pill`). Must use `expo-image`'s `<Image>` per CLAUDE.md, never RN `Image`.

**`BottomSheet`** (`mobile/components/ui/BottomSheet.tsx`):
```ts
interface AppBottomSheetProps {
  snapPoints?: Array<string | number>; // default ['30%', '60%', '90%'] per AC
  children: React.ReactNode;
  onDismiss?: () => void;
  enablePanDownToClose?: boolean; // default true
}
// Exposes an imperative ref, matching @gorhom/bottom-sheet v5's BottomSheetModal pattern:
export type AppBottomSheetRef = { present: () => void; dismiss: () => void };
```
Requires `<GestureHandlerRootView>` + `<BottomSheetModalProvider>` wrapping the app root (added to `_layout.tsx` in this ticket — see Files to modify). Consumers (SS-003 for a country-code picker, SS-004/SS-005 for any modal pickers) call `ref.current?.present()` to open.

**`Input`** (`mobile/components/ui/Input.tsx`) — **the component SS-003 depends on most; API fixed here, boundaries made explicit:**
```ts
type InputVariant = 'text' | 'phone' | 'search' | 'otp';
interface InputProps {
  variant?: InputVariant;         // default 'text'
  value: string;
  onChangeText: (text: string) => void;
  label?: string;
  placeholder?: string;
  error?: string;                 // renders inline below the field; for variant='otp' also triggers a Reanimated shake on the box row when it transitions from falsy→truthy
  disabled?: boolean;
  autoFocus?: boolean;
  // phone variant only
  countryCode?: string;           // default '+91'; rendered as a static prefix chip
  onCountryCodePress?: () => void;// tap handler for the prefix chip — SS-008 does NOT provide the picker UI itself
  // otp variant only
  length?: number;                // default 6
  onComplete?: (code: string) => void; // fires once value.length === length
  // search variant only
  onClear?: () => void;           // shows a trailing clear (X) icon when value is non-empty
}
```
**What SS-008 provides for phone/OTP vs. what SS-003 must build itself:**
- `variant='phone'`: SS-008 provides the visual chrome only — a static `+91` prefix chip, the text field, and an `onCountryCodePress` callback slot. SS-008 does **not** provide a country list, a country picker (SS-003 can build one using SS-008's own `BottomSheet`), or phone-number validation (10-digit, starts with 6/7/8/9) — that is SS-003's business logic entirely.
- `variant='otp'`: SS-008 provides the 6-box visual layout (single hidden `TextInput`, `keyboardType='number-pad'`, `maxLength={length}`, mapped to `length` visible boxes), auto-focus-on-mount, native paste-fills-all-boxes behaviour (free, since a single underlying `TextInput` receives pasted text as one `onChangeText` call), the `onComplete` callback for auto-submit, and the shake-on-error animation (via `react-native-reanimated`, already installed). SS-008 does **not** provide: the actual `supabase.auth.verifyOtp(...)` call, the 30-second resend-cooldown timer/UI, or SMS auto-read (`expo-sms-retriever` or equivalent) — all entirely SS-003's responsibility. SS-008 has zero SMS-related code.
- `variant='search'`: text field + leading/trailing search icon + `onClear`. No debouncing/query logic — that belongs to whichever `features/<domain>/*.queries.ts` consumes it.

**`IconButton`** (`mobile/components/ui/IconButton.tsx`):
```ts
interface IconButtonProps {
  icon: React.ComponentProps<typeof Ionicons>['name']; // from @expo/vector-icons
  onPress: () => void;
  size?: 'sm' | 'md' | 'lg';
  variant?: 'filled' | 'ghost'; // filled = bg accent.peacock, white icon; ghost = transparent, icon in text.primary
  disabled?: boolean;
  accessibilityLabel: string; // required, not optional — no icon-only button ships without an a11y label
}
```

**`Skeleton`** (`mobile/components/ui/Skeleton.tsx`):
```ts
type SkeletonVariant = 'card' | 'listItem' | 'circle' | 'text';
interface SkeletonProps {
  variant?: SkeletonVariant; // default 'text'
  width?: number | string;
  height?: number | string;
}
```
Shimmer implementation (Architect's decision, ticket doesn't specify technique): an opacity-pulse (`0.4 ↔ 1.0`, `withRepeat(withTiming(...))`) via `react-native-reanimated`, already installed — no new dependency required. A richer gradient-sweep shimmer is possible later using the already-installed `react-native-svg`'s `LinearGradient`, but is **not** required for this ticket's AC ("shimmer animation matching card and list item shapes" is satisfied by the pulse approach) — flagged as an optional future enhancement, not built now.

## Edge cases

Carried forward from the ticket:
- **Font loading failure → system font fallback, not blank screen; log to Sentry.** Implementation: do **not** gate `_layout.tsx`'s render tree on `fontsLoaded` (i.e. never `return null` while waiting). Call `useFonts(fontAssets)`, and if `fontError` is set, call `Sentry.captureException(fontError)` in a `useEffect` — but render the full tree immediately regardless. React Native already falls back to the OS default font automatically when a requested custom `fontFamily` isn't registered, so this is true graceful degradation with zero extra blank-screen-avoidance logic needed, and avoids introducing an `expo-splash-screen` dependency that isn't currently installed.
- **Long text in Badge/Chip: truncate at 20 chars with ellipsis.** Implemented as a plain JS slice in `Badge.tsx`, not a CSS `line-clamp` (RN Text doesn't support that reliably cross-platform); test with a 25-char label asserting the rendered text ends in `…` and is exactly 21 chars including the ellipsis.
- **BottomSheet on Android (Samsung One UI, Xiaomi MIUI, stock Android).** Cannot be device-tested by the Architect or in CI — flagged as a manual QA step for the Developer/QA phase (see Open Questions), not something a unit test can cover.

New edge cases found from the current codebase state:
- **Missing dependencies.** `expo-font`, all five `@expo-google-fonts/*` packages, and `@expo/vector-icons` are not in `package.json` or `node_modules` today (verified by direct file glob, zero matches) — this ticket cannot be built until the Developer runs the installs. This is the single biggest concrete gap this Architect pass found; see Open Questions.
- **No semantic "error"/"danger" colour exists in the given token set.** `Input`'s `error` state and any future form-validation UI need a red/error colour, but the ticket's tokens only include `accent.rose` (#C45B7C, explicitly scoped as "Beauty/makeup module accent," not a semantic error colour) — reusing it for form errors would be a category error in the design system. Flagged in Open Questions rather than inventing a new hex value.
- **`GestureHandlerRootView` / `BottomSheetModalProvider` don't exist anywhere in the app yet.** Any component using `@gorhom/bottom-sheet` (this ticket's `BottomSheet.tsx`, and anything SS-003/SS-004 build on top of it) will crash or silently fail to render at runtime without this root-level wrapping. This ticket must add it to `_layout.tsx`, not defer it — there is no other place in the current tree where it could go.
- **Tailwind nested-object colour keys stutter class names** (`bg-bg-primary`, `text-text-primary`) — resolved by flattening the Tailwind-layer keys as documented above; `tokens.ts` itself stays nested/verbatim per the ticket.
- **`react-native-worklets` (0.8.3) + Reanimated v4 babel wiring**: confirmed `babel-preset-expo`'s bundled config already references the Reanimated/worklets babel plugin (checked `node_modules/babel-preset-expo/build/index.js`), so no manual `babel.config.js` edit is needed for Reanimated-driven animations (`Skeleton`'s shimmer, `Input`'s shake) — flagging that this was verified, not assumed.
- **`mobile/app/dev-ui-kit.tsx` ships in the production bundle** since Expo Router has no built-in "dev-only route" exclusion — it will be reachable at `/dev-ui-kit` in a production build too, just unlinked from nav. Acceptable for MVP (not a security-sensitive screen), but flagged as an open question below in case Product wants it excluded from prod builds entirely.

## Test plan

- `mobile/__tests__/components/ui/tokens.test.ts`
  - asserts `colors.bg.primary === '#FAFAF7'`, `colors.accent.marigold === '#E8A420'`, and one value from each of `accent`/`text`/`occasion` — guards against silent drift from the ticket's transcribed hex values.
  - asserts `spacing` and `radii` objects have exactly the 6/5 keys specified with the exact numeric values (4/8/16/24/32/48 and 8/12/16/24/100).
- `mobile/__tests__/components/ui/Button.test.tsx`
  - renders `variant="primary"` and asserts it has the marigold background class and dark text class.
  - renders `variant="secondary"` and `variant="ghost"` and asserts each has visually distinct styling (border vs. no border).
  - renders with `loading` and asserts the spinner is present and `onPress` is not called when pressed while loading.
  - renders with `disabled` and asserts `onPress` is not invoked on press.
- `mobile/__tests__/components/ui/Text.test.tsx`
  - renders each of the 5 variants and asserts the resolved `className`/style references the correct `fontFamily` token per variant.
  - renders `script="devanagari"` and asserts it overrides to the Noto Sans Devanagari family regardless of `variant`.
- `mobile/__tests__/components/ui/Card.test.tsx`
  - renders each of the 3 variants and asserts each resolves to a different `borderRadius` value per the mapping documented above.
- `mobile/__tests__/components/ui/Badge.test.tsx`
  - renders with each of the 4 `occasion` keys and asserts the correct bg/text colour pairing per occasion.
  - renders with a 25-character `label` and asserts the rendered text is truncated to 20 chars + `…`.
  - renders with `onPress` set and asserts it's touchable (`fireEvent.press` calls the handler); renders without `onPress` and asserts it is not interactive.
- `mobile/__tests__/components/ui/Avatar.test.tsx`
  - renders with `uri` set and asserts an `expo-image` `Image` is rendered (not RN `Image`).
  - renders with no `uri` and a `name` and asserts initials are derived and shown instead.
- `mobile/__tests__/components/ui/Input.test.tsx`
  - `variant="phone"`: asserts the `+91` prefix renders by default and `onCountryCodePress` fires on tap.
  - `variant="otp"`, `length=6`: typing 6 digits into the hidden input calls `onComplete` with the full string; typing fewer than 6 does not call it.
  - `variant="otp"`: setting `error` to a non-empty string triggers the shake animation (assert the animated style's transform value changes, or that a shake-triggering ref/callback fires, depending on final implementation).
  - `variant="search"`: asserts `onClear` fires and clears the field when the clear icon is pressed, and that the clear icon is hidden when `value` is empty.
  - `variant="text"`: asserts `error` text renders below the field when set.
- `mobile/__tests__/components/ui/IconButton.test.tsx`
  - asserts `onPress` fires, asserts `disabled` prevents `onPress`, and asserts an error/type-check that `accessibilityLabel` is required (compile-time — a runtime test can assert the prop is passed through to the underlying `Pressable`'s `accessibilityLabel`).
- `mobile/__tests__/components/ui/Skeleton.test.tsx`
  - renders each of the 4 variants and asserts each renders with the expected default width/height for `card` vs `listItem` shapes.
  - asserts the shimmer animation is driven by a Reanimated shared value (smoke test — e.g. that the component doesn't throw when reanimated's test mock/mocked timers advance).
- `mobile/__tests__/components/ui/BottomSheet.test.tsx`
  - asserts default `snapPoints` is `['30%', '60%', '90%']` when not overridden.
  - asserts calling `ref.current.present()` / `.dismiss()` doesn't throw (full gesture behaviour can't be meaningfully unit-tested with RNTL/jest — device-level BottomSheet gesture testing on Samsung/Xiaomi/stock Android is a manual QA step, not a unit test, per the ticket's own edge case).
- `mobile/__tests__/app/index.test.tsx`
  - renders the migrated home screen and asserts it contains no raw `View`/`Text` — i.e. asserts the rendered tree uses the new `Card`/`Text` components (smoke test that the migration didn't silently keep raw RN primitives).

## Open questions / blockers

1. **Missing dependencies must be installed before any component code can run.** `expo-font`, `@expo-google-fonts/playfair-display`, `@expo-google-fonts/poppins`, `@expo-google-fonts/dm-sans`, `@expo-google-fonts/jetbrains-mono`, `@expo-google-fonts/noto-sans-devanagari`, and `@expo/vector-icons` are not present in `package.json` or `node_modules` (confirmed via direct glob search, not assumed). This is a same-ticket blocker, not a downstream one — the Developer phase must run `npx expo install expo-font @expo/vector-icons @expo-google-fonts/playfair-display @expo-google-fonts/poppins @expo-google-fonts/dm-sans @expo-google-fonts/jetbrains-mono @expo-google-fonts/noto-sans-devanagari` (letting `expo install` pick SDK-56-compatible versions) before `Text.tsx`/`IconButton.tsx`/`_layout.tsx` will compile.
2. **No semantic error/danger colour exists in the ticket's token set.** `accent.rose` is explicitly scoped to the beauty/makeup module, not general form errors. Recommend the user/Product confirm a dedicated error colour (a conventional choice would be something like `#C0392B` or reusing Material red `#D32F2F`) before `Input`'s error state and any future validation UI is styled — this Architect pass deliberately does **not** invent one, per this pipeline's own rule against inventing token values.
3. **Occasion colour coverage gap: 4 tokens vs. 12 `occasion_type` enum values.** SS-004 (9 occasion options) and SS-005 (6 occasion pills, including "Date" and "Party" which have no defined colour) will hit this gap directly. Recommend Product/design extend `colors.occasion` to cover all 12 `occasion_type` values (or explicitly decide a neutral fallback is acceptable) before SS-004/SS-005 reach their own Architect passes — flagging here rather than silently picking 8 more hex values myself.
4. **Button's "4 variants" wording vs. modelled API.** Reconciled `disabled` as a boolean state composing with 3 colour variants (`primary/secondary/ghost`) rather than a literal 4th `variant` value, since no distinct "disabled" visual design exists independent of the other 3. Flagging this interpretation explicitly in case the ticket author intended a literal 4-way `variant` union — low risk either way since the AC's observable behaviour (a visibly disabled button state exists) is satisfied either way.
5. **`mobile/app/dev-ui-kit.tsx` ships in production bundles** (Expo Router has no dev-only route exclusion mechanism). Acceptable for MVP; flagging in case Product wants this gated behind `__DEV__` or removed before the first production build.
6. **BottomSheet device-matrix testing (Samsung One UI, Xiaomi MIUI, stock Android)** cannot be performed by any agent in this pipeline — no physical/emulated Android devices are available to the Architect or (presumably) the Developer sandbox. This must be tracked as a manual QA step by the user before this ticket is considered fully verified on Android, separate from the automated test suite above.
7. **Font weight selection (Regular + one heavier weight per family) is an Architect judgement call**, since the ticket names typefaces but not weights. If Product/design later wants additional weights (e.g. DM Sans Bold for a specific screen), that's an additive change to `lib/fonts.ts` and `tailwind.config.js`'s `fontFamily` map, not a breaking one — flagging so the Developer doesn't over-fetch every available Google Fonts weight up front.
