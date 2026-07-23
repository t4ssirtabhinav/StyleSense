// SS-005 (Home Screen Shell + Bottom Tab Navigation).

export interface OccasionPill {
  /** Matches supabase/migrations/003_onboarding_taxonomies.sql's
   * occasion_types reference table naming, not the differently-spelled
   * occasion_type DB enum used by wardrobe_items/outfits. */
  key: string;
  label: string;
  /** Emoji, not an Ionicons name — matches Badge's existing `icon` slot. */
  icon: string;
}
