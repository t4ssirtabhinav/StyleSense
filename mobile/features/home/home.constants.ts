import type { OccasionPill } from './home.types';

// Fixed, hardcoded (not DB-fetched) — see docs/tickets/SS-005-design.md's
// "Concrete values" section for why: a curated 6-item subset with specific
// emoji/order the ticket's AC pins down verbatim, not a product-editable
// list the way the occasion registry is. Emoji are not a registry column,
// which is the other half of why this stays here.
//
// (SS-025) The KEYS are now canonical `occasions.key` slugs — `wedding` ->
// `wedding_guest` and `date` -> `date_night` — so a pill navigates to the
// same identity the wardrobe, the AI and the DB all use. Emoji, labels,
// order and the 6-item curation are unchanged from what SS-005 pinned.
// Legacy deep links carrying the old `?occasion=wedding`/`date` keys still
// resolve: app/(tabs)/style.tsx runs the param through the registry's alias
// map first.
//
// BL-008 is RESOLVED as of SS-025: `occasions.badge_color` is NOT NULL with
// a CHECK against Badge's four occasion tokens, so every pill has a colour
// by construction rather than 4-of-6 being coloured and the rest neutral.
// OccasionPillRow passes `occasion={badgeColor(pill.key)}`, which is
// undefined (neutral) only while the taxonomy query is still resolving.
export const OCCASION_PILLS: OccasionPill[] = [
  { key: 'office', label: 'Office', icon: '💼' },
  { key: 'casual', label: 'Casual', icon: '☀️' },
  { key: 'wedding_guest', label: 'Wedding', icon: '💍' },
  { key: 'festival', label: 'Festival', icon: '🪔' },
  { key: 'date_night', label: 'Date', icon: '❤️' },
  { key: 'party', label: 'Party', icon: '🎉' },
];
