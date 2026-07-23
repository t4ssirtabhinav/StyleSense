import type { OccasionPill } from './home.types';

// Fixed, hardcoded (not DB-fetched) — see docs/tickets/SS-005-design.md's
// "Concrete values" section for why: a curated 6-of-9 subset with specific
// emoji/order the ticket's AC pins down verbatim, not a product-editable
// list the way onboarding's Step 3 chip set is.
//
// BL-008 call for this ticket: Badge's OccasionKey only colours 4 of these 6
// (office/wedding/festival/casual — date/party have no defined colour). Per
// SS-004's precedent for the same gap, all 6 pills render with Badge's
// neutral style — no `occasion` prop is ever passed from OccasionPillRow.
export const OCCASION_PILLS: OccasionPill[] = [
  { key: 'office', label: 'Office', icon: '💼' },
  { key: 'casual', label: 'Casual', icon: '☀️' },
  { key: 'wedding', label: 'Wedding', icon: '💍' },
  { key: 'festival', label: 'Festival', icon: '🪔' },
  { key: 'date', label: 'Date', icon: '❤️' },
  { key: 'party', label: 'Party', icon: '🎉' },
];
