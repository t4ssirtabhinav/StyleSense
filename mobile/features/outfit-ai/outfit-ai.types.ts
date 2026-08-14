// SS-023 — request/response types mirroring backend/routers/outfit_suggestions.py's
// Pydantic models verbatim (design doc §1's "Concrete values"). No `any`;
// nothing inline in components (CLAUDE.md: "All API response types live in
// types/ — never inline any-shaped objects" — this domain's own
// <domain>.types.ts is the equivalent home, per the feature-folder
// convention every other domain in this repo already follows).

export type SeasonTag = 'summer' | 'winter' | 'monsoon' | 'all';
export type RationaleLanguage = 'en' | 'hi';
export type OutcomeType = 'saved' | 'dismissed' | 'worn' | 'shared';

// SS-022 — mirrors backend/services/weather_rules.py's WeatherCondition
// Literal and backend/routers/outfit_suggestions.py's WeatherResponse
// verbatim. Closed set shared by backend and mobile.
export type WeatherCondition =
  | 'clear'
  | 'partly_cloudy'
  | 'cloudy'
  | 'fog'
  | 'drizzle'
  | 'rain'
  | 'heavy_rain'
  | 'thunderstorm'
  | 'snow';

export interface WeatherResponse {
  city: string;
  temp_c: number;
  condition: WeatherCondition;
  humidity: number;
  is_heavy_rain: boolean;
}

export interface GeneratePortfolioRequest {
  occasion: string;
  season?: SeasonTag | null;
  as_of?: string | null;
  style_preferences_override?: Record<string, unknown> | null;
  /** The regenerate mechanism (design §4) — every fingerprint the caller
   * has already been SHOWN in this session (not merely dismissed — a
   * swiped-right card should not come back either). Capped at 60,
   * FIFO-truncated client-side (outfit-ai.store.ts) before this is built. */
  exclude_fingerprints: string[];
}

export interface PortfolioItemResponse {
  item_ids: string[];
  category_labels: Record<string, string>;
  total_score: number;
  rationale: string;
  rationale_language: RationaleLanguage;
  is_exploration: boolean;
  gap_flags: string[];
  /** 1-based, exactly the rank suggestion_impressions.rank was logged
   * with — the join key /outfit-suggestions/outcome resolves on. */
  rank: number;
  /** 64-char lowercase hex. */
  outfit_fingerprint: string;
}

export interface GapReport {
  excluded_missing_color_or_category: number;
  missing_slots: string[];
  /** (SS-022) True when a heavy-rain white/silk exclusion would have
   * emptied the eligible pool and was relaxed — a monsoon user whose
   * wardrobe is mostly white/silk still gets suggestions. */
  weather_exclusions_relaxed: boolean;
}

export interface GeneratePortfolioResponse {
  portfolio: PortfolioItemResponse[];
  limited_options: boolean;
  gap_report: GapReport;
  engine_version: string;
  effort_tier: string;
  cache_hit: boolean;
  generated_at: string;
  /** `null` when session logging failed server-side — the deck still
   * renders, but outcomes cannot be recorded for this batch. */
  session_id: string | null;
  /** RESOLVED canonical key (post-alias) — badge/persist against THIS,
   * not the raw string the user tapped. */
  occasion_key: string;
  /** (SS-022) `null` when the user has no usable city or Open-Meteo was
   * unreachable — never blocks the deck rendering. */
  weather: WeatherResponse | null;
}

export interface RecordOutcomeRequest {
  session_id: string;
  rank: number;
  outcome_type: OutcomeType;
  client_occurred_at?: string | null;
  name?: string | null;
}

export interface RecordOutcomeResponse {
  outfit_id: string | null;
  outcome_recorded: boolean;
  already_saved: boolean;
}
