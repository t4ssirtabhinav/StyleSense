// SS-023 — copy strings (design §5, "fixed, use verbatim"), deck size, and
// the regenerate exclusion cap. One place so a future copy change doesn't
// need to be hunted down across 8 components.

import type { WeatherCondition } from './outfit-ai.types';

export const OCCASION_SCREEN_HEADING = "What's the occasion?";
export const GET_SUGGESTIONS_CTA = 'Get suggestions';
export const LOADING_COPY = 'Styling three looks for you…';
export const REGENERATE_CTA = 'Not quite right — regenerate';

export const ZERO_WARDROBE_HEADING = 'Add a few pieces first';
export const ZERO_WARDROBE_SUBTEXT =
  'We need at least a top and a bottom to style a look.';
export const ZERO_WARDROBE_CTA = 'Add items';

export const EXHAUSTED_AFTER_REGENERATE_COPY =
  "That's every look we can build from your wardrobe right now";

export const ACCEPT_CONFIRMATION_COPY = 'Saved to your outfits';
export const ALREADY_SAVED_COPY = 'Already in your outfits';
export const ALREADY_LOGGED_TODAY_COPY = 'Already logged for today';
export const WORE_THIS_TODAY_CTA = 'Wore this today';
export const SHARE_CTA = 'Share';

export const BACKEND_UNREACHABLE_COPY =
  "Couldn't reach the stylist. Try again in a moment.";
export const RETRY_CTA = 'Retry';
export const BACK_TO_OCCASIONS_CTA = 'Back to occasions';

export const OUTFIT_SAVE_DEGRADED_COPY =
  "Couldn't save that one — try regenerating.";

export const ITEM_NO_LONGER_IN_WARDROBE_COPY = 'No longer in your wardrobe';

// SS-024 — FootwearSection copy (design §4.3, "the Architect's own authored
// copy — no design doc pins them", flagged as such rather than mistaken for
// transcribed values).
export const FOOTWEAR_SECTION_HEADING = 'Best footwear for this outfit';
export const MISSING_FOOTWEAR_HEADING = 'No footwear in your wardrobe yet';
export const MISSING_FOOTWEAR_SUBTEXT =
  'Add a pair and your outfits will be complete.';
export const FOOTWEAR_MISMATCH_HEADING = 'These are a casual match';
export const FOOTWEAR_MISMATCH_SUBTEXT =
  'This is the only footwear you own for this occasion. Formal or ethnic footwear would suit it better.';
export const ADD_FOOTWEAR_CTA = 'Add footwear';

// `SuggestionSkeletonDeck`'s 3 skeletons are a visual constant, not a data
// assumption — the response may legitimately carry 1 or 2 candidates
// (`limited_options`), and the deck component must never hardcode 3
// anywhere else (design edge cases).
export const SKELETON_DECK_SIZE = 3;

// The regenerate mechanism's cap (design §4) — mirrors the backend's
// `max_length=60` on `exclude_fingerprints`, FIFO-truncated client-side
// before every request so the payload never needs server-side truncation
// in the common case.
export const EXCLUDE_FINGERPRINTS_CAP = 60;

export function scoreBadgeLabel(totalScore: number): string {
  return `${Math.round(totalScore * 100)}% match`;
}

// SS-022 — the weather chip's copy (design §7, "fixed, use verbatim").
export const WEATHER_CHIP_PREFIX = 'Dressing for';

export const WEATHER_CONDITION_LABELS: Record<WeatherCondition, string> = {
  clear: 'clear',
  partly_cloudy: 'partly cloudy',
  cloudy: 'cloudy',
  fog: 'foggy',
  drizzle: 'drizzly',
  rain: 'rainy',
  heavy_rain: 'heavy rain',
  thunderstorm: 'thunderstorms',
  snow: 'snow',
};
