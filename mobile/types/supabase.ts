// AUTO-GENERATED — regenerate after schema changes:
//   supabase login
//   supabase link --project-ref mefpfykuinasgkpfhmzk
//   supabase gen types typescript --linked > mobile/types/supabase.ts

export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[]

export type WardrobeCategory =
  | 'western_top' | 'western_bottom' | 'western_dress' | 'western_outerwear'
  | 'ethnic_kurta' | 'ethnic_saree' | 'ethnic_lehenga' | 'ethnic_anarkali'
  | 'ethnic_salwar_kameez' | 'ethnic_dupatta' | 'ethnic_sherwani' | 'indo_western'
  | 'footwear_formal' | 'footwear_casual' | 'footwear_ethnic' | 'footwear_sports'
  | 'accessory_bag' | 'accessory_jewellery' | 'accessory_watch'
  | 'accessory_belt' | 'accessory_scarf'

export type PlanTier = 'free' | 'premium' | 'premium_annual'

export type OccasionType =
  | 'office' | 'casual' | 'date_night' | 'wedding_guest' | 'festival'
  | 'puja' | 'party' | 'travel' | 'workout' | 'beach' | 'formal_event' | 'college'

export interface Database {
  public: {
    Tables: {
      users: {
        Row: {
          id: string
          email: string | null
          phone: string | null
          full_name: string | null
          city: string | null
          language: string
          gender: string | null
          body_type: string | null
          skin_tone: string | null
          style_preferences: Json
          plan_tier: PlanTier
          plan_expires_at: string | null
          razorpay_customer_id: string | null
          style_score: number
          created_at: string
          last_active_at: string
        }
        Insert: Omit<Database['public']['Tables']['users']['Row'], 'id' | 'created_at' | 'last_active_at'> & {
          id?: string
          created_at?: string
          last_active_at?: string
        }
        Update: Partial<Database['public']['Tables']['users']['Insert']>
      }
      wardrobe_items: {
        Row: {
          id: string
          user_id: string
          image_url: string
          image_clean_url: string | null
          thumbnail_url: string | null
          category: WardrobeCategory
          subcategory: string | null
          color_primary: string | null
          color_secondary: string | null
          pattern: string | null
          fabric: string | null
          occasion_tags: OccasionType[] | null
          season_tags: string[] | null
          brand: string | null
          purchase_price: number | null
          purchase_date: string | null
          last_worn_at: string | null
          wear_count: number
          cost_per_wear: number | null
          ai_tags: Json
          user_notes: string | null
          is_favourite: boolean
          created_at: string
        }
        Insert: Omit<Database['public']['Tables']['wardrobe_items']['Row'], 'id' | 'cost_per_wear' | 'created_at'> & {
          id?: string
          created_at?: string
        }
        Update: Partial<Database['public']['Tables']['wardrobe_items']['Insert']>
      }
      outfits: {
        Row: {
          id: string
          user_id: string
          name: string | null
          item_ids: string[] | null
          occasion: OccasionType | null
          season: string | null
          ai_generated: boolean
          ai_reasoning: string | null
          user_rating: number | null
          worn_count: number
          last_worn_at: string | null
          avatar_image_url: string | null
          created_at: string
        }
        Insert: Omit<Database['public']['Tables']['outfits']['Row'], 'id' | 'created_at'> & {
          id?: string
          created_at?: string
        }
        Update: Partial<Database['public']['Tables']['outfits']['Insert']>
      }
      suggestion_sessions: {
        Row: {
          id: string
          user_id: string
          occasion: OccasionType | null
          weather_data: Json | null
          suggestions: Json | null
          accepted_outfit_id: string | null
          cache_key: string | null
          created_at: string
        }
        Insert: Omit<Database['public']['Tables']['suggestion_sessions']['Row'], 'id' | 'created_at'> & {
          id?: string
          created_at?: string
        }
        Update: Partial<Database['public']['Tables']['suggestion_sessions']['Insert']>
      }
      user_avatars: {
        Row: {
          id: string
          user_id: string
          source_photo_url: string | null
          avatar_url: string | null
          height_cm: number | null
          generated_at: string | null
        }
        Insert: Omit<Database['public']['Tables']['user_avatars']['Row'], 'id'> & { id?: string }
        Update: Partial<Database['public']['Tables']['user_avatars']['Insert']>
      }
      social_posts: {
        Row: {
          id: string
          user_id: string
          outfit_id: string | null
          image_url: string
          caption: string | null
          occasion: OccasionType | null
          likes_count: number
          saves_count: number
          is_public: boolean
          challenge_id: string | null
          created_at: string
        }
        Insert: Omit<Database['public']['Tables']['social_posts']['Row'], 'id' | 'created_at'> & {
          id?: string
          created_at?: string
        }
        Update: Partial<Database['public']['Tables']['social_posts']['Insert']>
      }
      shopping_wishlist: {
        Row: {
          id: string
          user_id: string
          product_url: string
          platform: string | null
          product_name: string | null
          image_url: string | null
          current_price: number | null
          target_price: number | null
          affiliate_url: string | null
          last_checked_at: string | null
          created_at: string
        }
        Insert: Omit<Database['public']['Tables']['shopping_wishlist']['Row'], 'id' | 'created_at'> & {
          id?: string
          created_at?: string
        }
        Update: Partial<Database['public']['Tables']['shopping_wishlist']['Insert']>
      }
    }
    Enums: {
      wardrobe_category: WardrobeCategory
      plan_tier: PlanTier
      occasion_type: OccasionType
    }
  }
}
