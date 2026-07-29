export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.5"
  }
  graphql_public: {
    Tables: {
      [_ in never]: never
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      graphql: {
        Args: {
          extensions?: Json
          operationName?: string
          query?: string
          variables?: Json
        }
        Returns: Json
      }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
  public: {
    Tables: {
      colour_palette: {
        Row: {
          active: boolean
          hex: string
          key: string
          label: string
          sort_order: number
        }
        Insert: {
          active?: boolean
          hex: string
          key: string
          label: string
          sort_order: number
        }
        Update: {
          active?: boolean
          hex?: string
          key?: string
          label?: string
          sort_order?: number
        }
        Relationships: []
      }
      occasion_aliases: {
        Row: {
          alias: string
          created_at: string
          occasion_key: string
        }
        Insert: {
          alias: string
          created_at?: string
          occasion_key: string
        }
        Update: {
          alias?: string
          created_at?: string
          occasion_key?: string
        }
        Relationships: [
          {
            foreignKeyName: "occasion_aliases_occasion_key_fkey"
            columns: ["occasion_key"]
            isOneToOne: false
            referencedRelation: "occasions"
            referencedColumns: ["key"]
          },
        ]
      }
      occasion_unknown_tags: {
        Row: {
          first_seen_at: string
          last_seen_at: string
          occurrences: number
          sample_source: string | null
          sample_user_id: string | null
          slug: string
        }
        Insert: {
          first_seen_at?: string
          last_seen_at?: string
          occurrences?: number
          sample_source?: string | null
          sample_user_id?: string | null
          slug: string
        }
        Update: {
          first_seen_at?: string
          last_seen_at?: string
          occurrences?: number
          sample_source?: string | null
          sample_user_id?: string | null
          slug?: string
        }
        Relationships: []
      }
      occasions: {
        Row: {
          badge_color: string
          created_at: string
          culture_scope: string[] | null
          date_rule: Json | null
          formality: number
          is_active: boolean
          key: string
          kind: string
          label: string
          labels_i18n: Json
          parent_key: string | null
          region_scope: string[] | null
          sort_order: number
          styling_rules: Json
          tier_gate: string
        }
        Insert: {
          badge_color: string
          created_at?: string
          culture_scope?: string[] | null
          date_rule?: Json | null
          formality: number
          is_active?: boolean
          key: string
          kind: string
          label: string
          labels_i18n?: Json
          parent_key?: string | null
          region_scope?: string[] | null
          sort_order?: number
          styling_rules?: Json
          tier_gate?: string
        }
        Update: {
          badge_color?: string
          created_at?: string
          culture_scope?: string[] | null
          date_rule?: Json | null
          formality?: number
          is_active?: boolean
          key?: string
          kind?: string
          label?: string
          labels_i18n?: Json
          parent_key?: string | null
          region_scope?: string[] | null
          sort_order?: number
          styling_rules?: Json
          tier_gate?: string
        }
        Relationships: [
          {
            foreignKeyName: "occasions_parent_key_fkey"
            columns: ["parent_key"]
            isOneToOne: false
            referencedRelation: "occasions"
            referencedColumns: ["key"]
          },
        ]
      }
      outfits: {
        Row: {
          ai_generated: boolean | null
          ai_reasoning: string | null
          avatar_image_url: string | null
          created_at: string | null
          id: string
          item_ids: string[] | null
          last_worn_at: string | null
          name: string | null
          occasion: string | null
          season: string | null
          user_id: string | null
          user_rating: number | null
          worn_count: number | null
        }
        Insert: {
          ai_generated?: boolean | null
          ai_reasoning?: string | null
          avatar_image_url?: string | null
          created_at?: string | null
          id?: string
          item_ids?: string[] | null
          last_worn_at?: string | null
          name?: string | null
          occasion?: string | null
          season?: string | null
          user_id?: string | null
          user_rating?: number | null
          worn_count?: number | null
        }
        Update: {
          ai_generated?: boolean | null
          ai_reasoning?: string | null
          avatar_image_url?: string | null
          created_at?: string | null
          id?: string
          item_ids?: string[] | null
          last_worn_at?: string | null
          name?: string | null
          occasion?: string | null
          season?: string | null
          user_id?: string | null
          user_rating?: number | null
          worn_count?: number | null
        }
        Relationships: [
          {
            foreignKeyName: "outfits_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
      shopping_wishlist: {
        Row: {
          affiliate_url: string | null
          created_at: string | null
          current_price: number | null
          id: string
          image_url: string | null
          last_checked_at: string | null
          platform: string | null
          product_name: string | null
          product_url: string
          target_price: number | null
          user_id: string | null
        }
        Insert: {
          affiliate_url?: string | null
          created_at?: string | null
          current_price?: number | null
          id?: string
          image_url?: string | null
          last_checked_at?: string | null
          platform?: string | null
          product_name?: string | null
          product_url: string
          target_price?: number | null
          user_id?: string | null
        }
        Update: {
          affiliate_url?: string | null
          created_at?: string | null
          current_price?: number | null
          id?: string
          image_url?: string | null
          last_checked_at?: string | null
          platform?: string | null
          product_name?: string | null
          product_url?: string
          target_price?: number | null
          user_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "shopping_wishlist_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
      social_posts: {
        Row: {
          caption: string | null
          challenge_id: string | null
          created_at: string | null
          id: string
          image_url: string
          is_public: boolean | null
          likes_count: number | null
          occasion: string | null
          outfit_id: string | null
          saves_count: number | null
          user_id: string | null
        }
        Insert: {
          caption?: string | null
          challenge_id?: string | null
          created_at?: string | null
          id?: string
          image_url: string
          is_public?: boolean | null
          likes_count?: number | null
          occasion?: string | null
          outfit_id?: string | null
          saves_count?: number | null
          user_id?: string | null
        }
        Update: {
          caption?: string | null
          challenge_id?: string | null
          created_at?: string | null
          id?: string
          image_url?: string
          is_public?: boolean | null
          likes_count?: number | null
          occasion?: string | null
          outfit_id?: string | null
          saves_count?: number | null
          user_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "social_posts_outfit_id_fkey"
            columns: ["outfit_id"]
            isOneToOne: false
            referencedRelation: "outfits"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "social_posts_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
      style_keywords: {
        Row: {
          active: boolean
          key: string
          label: string
          sort_order: number
        }
        Insert: {
          active?: boolean
          key: string
          label: string
          sort_order: number
        }
        Update: {
          active?: boolean
          key?: string
          label?: string
          sort_order?: number
        }
        Relationships: []
      }
      suggestion_sessions: {
        Row: {
          accepted_outfit_id: string | null
          cache_key: string | null
          created_at: string | null
          id: string
          occasion: string | null
          suggestions: Json | null
          user_id: string | null
          weather_data: Json | null
        }
        Insert: {
          accepted_outfit_id?: string | null
          cache_key?: string | null
          created_at?: string | null
          id?: string
          occasion?: string | null
          suggestions?: Json | null
          user_id?: string | null
          weather_data?: Json | null
        }
        Update: {
          accepted_outfit_id?: string | null
          cache_key?: string | null
          created_at?: string | null
          id?: string
          occasion?: string | null
          suggestions?: Json | null
          user_id?: string | null
          weather_data?: Json | null
        }
        Relationships: [
          {
            foreignKeyName: "suggestion_sessions_accepted_outfit_id_fkey"
            columns: ["accepted_outfit_id"]
            isOneToOne: false
            referencedRelation: "outfits"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "suggestion_sessions_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
      user_avatars: {
        Row: {
          avatar_url: string | null
          generated_at: string | null
          height_cm: number | null
          id: string
          source_photo_url: string | null
          user_id: string | null
        }
        Insert: {
          avatar_url?: string | null
          generated_at?: string | null
          height_cm?: number | null
          id?: string
          source_photo_url?: string | null
          user_id?: string | null
        }
        Update: {
          avatar_url?: string | null
          generated_at?: string | null
          height_cm?: number | null
          id?: string
          source_photo_url?: string | null
          user_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "user_avatars_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: true
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
      users: {
        Row: {
          body_type: string | null
          city: string | null
          created_at: string | null
          email: string | null
          full_name: string | null
          gender: string | null
          id: string
          language: string | null
          last_active_at: string | null
          onboarding_completed: boolean
          phone: string | null
          plan_expires_at: string | null
          plan_tier: Database["public"]["Enums"]["plan_tier"] | null
          razorpay_customer_id: string | null
          skin_tone: string | null
          style_preferences: Json | null
          style_score: number | null
        }
        Insert: {
          body_type?: string | null
          city?: string | null
          created_at?: string | null
          email?: string | null
          full_name?: string | null
          gender?: string | null
          id?: string
          language?: string | null
          last_active_at?: string | null
          onboarding_completed?: boolean
          phone?: string | null
          plan_expires_at?: string | null
          plan_tier?: Database["public"]["Enums"]["plan_tier"] | null
          razorpay_customer_id?: string | null
          skin_tone?: string | null
          style_preferences?: Json | null
          style_score?: number | null
        }
        Update: {
          body_type?: string | null
          city?: string | null
          created_at?: string | null
          email?: string | null
          full_name?: string | null
          gender?: string | null
          id?: string
          language?: string | null
          last_active_at?: string | null
          onboarding_completed?: boolean
          phone?: string | null
          plan_expires_at?: string | null
          plan_tier?: Database["public"]["Enums"]["plan_tier"] | null
          razorpay_customer_id?: string | null
          skin_tone?: string | null
          style_preferences?: Json | null
          style_score?: number | null
        }
        Relationships: []
      }
      wardrobe_item_wears: {
        Row: {
          created_at: string
          id: string
          item_id: string
          user_id: string
          worn_on: string
        }
        Insert: {
          created_at?: string
          id?: string
          item_id: string
          user_id: string
          worn_on: string
        }
        Update: {
          created_at?: string
          id?: string
          item_id?: string
          user_id?: string
          worn_on?: string
        }
        Relationships: [
          {
            foreignKeyName: "wardrobe_item_wears_item_fk"
            columns: ["item_id", "user_id"]
            isOneToOne: false
            referencedRelation: "wardrobe_items"
            referencedColumns: ["id", "user_id"]
          },
        ]
      }
      wardrobe_items: {
        Row: {
          ai_tags: Json | null
          brand: string | null
          category: Database["public"]["Enums"]["wardrobe_category"] | null
          color_primary: string | null
          color_secondary: string | null
          cost_per_wear: number | null
          created_at: string | null
          fabric: string | null
          id: string
          image_clean_url: string | null
          image_url: string
          is_favourite: boolean | null
          last_worn_at: string | null
          occasion_tags: string[] | null
          pattern: string | null
          processing_status: Database["public"]["Enums"]["wardrobe_processing_status"]
          purchase_date: string | null
          purchase_price: number | null
          season_tags: string[] | null
          subcategory: string | null
          thumbnail_url: string | null
          user_id: string | null
          user_notes: string | null
          wear_count: number | null
        }
        Insert: {
          ai_tags?: Json | null
          brand?: string | null
          category?: Database["public"]["Enums"]["wardrobe_category"] | null
          color_primary?: string | null
          color_secondary?: string | null
          cost_per_wear?: number | null
          created_at?: string | null
          fabric?: string | null
          id?: string
          image_clean_url?: string | null
          image_url: string
          is_favourite?: boolean | null
          last_worn_at?: string | null
          occasion_tags?: string[] | null
          pattern?: string | null
          processing_status?: Database["public"]["Enums"]["wardrobe_processing_status"]
          purchase_date?: string | null
          purchase_price?: number | null
          season_tags?: string[] | null
          subcategory?: string | null
          thumbnail_url?: string | null
          user_id?: string | null
          user_notes?: string | null
          wear_count?: number | null
        }
        Update: {
          ai_tags?: Json | null
          brand?: string | null
          category?: Database["public"]["Enums"]["wardrobe_category"] | null
          color_primary?: string | null
          color_secondary?: string | null
          cost_per_wear?: number | null
          created_at?: string | null
          fabric?: string | null
          id?: string
          image_clean_url?: string | null
          image_url?: string
          is_favourite?: boolean | null
          last_worn_at?: string | null
          occasion_tags?: string[] | null
          pattern?: string | null
          processing_status?: Database["public"]["Enums"]["wardrobe_processing_status"]
          purchase_date?: string | null
          purchase_price?: number | null
          season_tags?: string[] | null
          subcategory?: string | null
          thumbnail_url?: string | null
          user_id?: string | null
          user_notes?: string | null
          wear_count?: number | null
        }
        Relationships: [
          {
            foreignKeyName: "wardrobe_items_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      occasion_is_known: { Args: { p_slug: string }; Returns: boolean }
      occasion_log_unknown: {
        Args: { p_slug: string; p_src: string; p_uid: string }
        Returns: undefined
      }
      occasion_normalize_array: {
        Args: { p_raw: string[]; p_src: string; p_uid: string }
        Returns: string[]
      }
      occasion_normalize_one: { Args: { p_raw: string }; Returns: string }
      occasion_normalize_shape: { Args: { p_raw: string }; Returns: string }
      sync_wardrobe_item_wear_stats: {
        Args: { target_item_id: string }
        Returns: undefined
      }
    }
    Enums: {
      plan_tier: "free" | "premium" | "premium_annual"
      wardrobe_category:
        | "western_top"
        | "western_bottom"
        | "western_dress"
        | "western_outerwear"
        | "ethnic_kurta"
        | "ethnic_saree"
        | "ethnic_lehenga"
        | "ethnic_anarkali"
        | "ethnic_salwar_kameez"
        | "ethnic_dupatta"
        | "ethnic_sherwani"
        | "indo_western"
        | "footwear_formal"
        | "footwear_casual"
        | "footwear_ethnic"
        | "footwear_sports"
        | "accessory_bag"
        | "accessory_jewellery"
        | "accessory_watch"
        | "accessory_belt"
        | "accessory_scarf"
      wardrobe_processing_status:
        | "uploaded"
        | "bg_processing"
        | "bg_removed"
        | "bg_pending"
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  graphql_public: {
    Enums: {},
  },
  public: {
    Enums: {
      plan_tier: ["free", "premium", "premium_annual"],
      wardrobe_category: [
        "western_top",
        "western_bottom",
        "western_dress",
        "western_outerwear",
        "ethnic_kurta",
        "ethnic_saree",
        "ethnic_lehenga",
        "ethnic_anarkali",
        "ethnic_salwar_kameez",
        "ethnic_dupatta",
        "ethnic_sherwani",
        "indo_western",
        "footwear_formal",
        "footwear_casual",
        "footwear_ethnic",
        "footwear_sports",
        "accessory_bag",
        "accessory_jewellery",
        "accessory_watch",
        "accessory_belt",
        "accessory_scarf",
      ],
      wardrobe_processing_status: [
        "uploaded",
        "bg_processing",
        "bg_removed",
        "bg_pending",
      ],
    },
  },
} as const
