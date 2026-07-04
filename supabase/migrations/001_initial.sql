-- ============================================================
-- StyleSense — Initial DB Schema
-- Apply via: Supabase Dashboard → SQL Editor → Run
-- ============================================================

-- ENUMS (must be created before tables that reference them)
CREATE TYPE wardrobe_category AS ENUM (
  'western_top', 'western_bottom', 'western_dress', 'western_outerwear',
  'ethnic_kurta', 'ethnic_saree', 'ethnic_lehenga', 'ethnic_anarkali',
  'ethnic_salwar_kameez', 'ethnic_dupatta', 'ethnic_sherwani', 'indo_western',
  'footwear_formal', 'footwear_casual', 'footwear_ethnic', 'footwear_sports',
  'accessory_bag', 'accessory_jewellery', 'accessory_watch',
  'accessory_belt', 'accessory_scarf'
);

CREATE TYPE plan_tier AS ENUM ('free', 'premium', 'premium_annual');

CREATE TYPE occasion_type AS ENUM (
  'office', 'casual', 'date_night', 'wedding_guest', 'festival',
  'puja', 'party', 'travel', 'workout', 'beach', 'formal_event', 'college'
);

-- USERS
CREATE TABLE users (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email               TEXT UNIQUE,
  phone               TEXT UNIQUE,                          -- India: phone-first auth
  full_name           TEXT,
  city                TEXT,                                 -- For weather API
  language            TEXT DEFAULT 'en',                   -- 'en' | 'hi' | 'ta' etc
  gender              TEXT,
  body_type           TEXT,                                 -- For avatar generation
  skin_tone           TEXT,                                 -- For makeup suggestions
  style_preferences   JSONB DEFAULT '{}',                  -- {styles:[], colours:[], brands:[]}
  plan_tier           plan_tier DEFAULT 'free',
  plan_expires_at     TIMESTAMPTZ,
  razorpay_customer_id TEXT,
  style_score         INTEGER DEFAULT 0,
  created_at          TIMESTAMPTZ DEFAULT now(),
  last_active_at      TIMESTAMPTZ DEFAULT now()
);

-- WARDROBE ITEMS (core table)
CREATE TABLE wardrobe_items (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
  image_url       TEXT NOT NULL,                            -- Original R2 URL
  image_clean_url TEXT,                                     -- BG-removed R2 URL
  thumbnail_url   TEXT,
  category        wardrobe_category NOT NULL,
  subcategory     TEXT,                                     -- e.g. 'anarkali' within ethnic
  color_primary   TEXT,                                     -- hex or named colour
  color_secondary TEXT,
  pattern         TEXT,                                     -- solid/stripes/floral/block_print etc
  fabric          TEXT,                                     -- cotton/silk/chiffon etc
  occasion_tags   occasion_type[],                         -- multiple occasions
  season_tags     TEXT[],                                   -- summer/winter/monsoon/all
  brand           TEXT,
  purchase_price  INTEGER,                                  -- in paise
  purchase_date   DATE,
  last_worn_at    DATE,
  wear_count      INTEGER DEFAULT 0,
  cost_per_wear   NUMERIC GENERATED ALWAYS AS (
    CASE WHEN wear_count > 0
      THEN purchase_price::numeric / wear_count
      ELSE purchase_price
    END
  ) STORED,
  ai_tags         JSONB DEFAULT '{}',                       -- raw AI response cached
  user_notes      TEXT,
  is_favourite    BOOLEAN DEFAULT false,
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_wardrobe_user_id  ON wardrobe_items(user_id);
CREATE INDEX idx_wardrobe_category ON wardrobe_items(category);
CREATE INDEX idx_wardrobe_occasions ON wardrobe_items USING GIN(occasion_tags);

-- OUTFITS (AI-generated or user-curated)
CREATE TABLE outfits (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
  name            TEXT,
  item_ids        UUID[],                                   -- array of wardrobe_item IDs
  occasion        occasion_type,
  season          TEXT,
  ai_generated    BOOLEAN DEFAULT false,
  ai_reasoning    TEXT,                                     -- why AI suggested this
  user_rating     SMALLINT,                                 -- 1-5
  worn_count      INTEGER DEFAULT 0,
  last_worn_at    DATE,
  avatar_image_url TEXT,                                   -- cached try-on image
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- OUTFIT SUGGESTIONS (AI sessions)
CREATE TABLE suggestion_sessions (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID REFERENCES users(id),
  occasion            occasion_type,
  weather_data        JSONB,
  suggestions         JSONB,                               -- array of outfit combos from AI
  accepted_outfit_id  UUID REFERENCES outfits(id),
  cache_key           TEXT,                               -- for Redis invalidation
  created_at          TIMESTAMPTZ DEFAULT now()
);

-- USER AVATAR
CREATE TABLE user_avatars (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID REFERENCES users(id) UNIQUE,
  source_photo_url TEXT,
  avatar_url       TEXT,                                   -- generated base avatar
  height_cm        INTEGER,
  generated_at     TIMESTAMPTZ
);

-- SOCIAL POSTS (OOTD)
CREATE TABLE social_posts (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID REFERENCES users(id),
  outfit_id   UUID REFERENCES outfits(id),
  image_url   TEXT NOT NULL,
  caption     TEXT,
  occasion    occasion_type,
  likes_count  INTEGER DEFAULT 0,
  saves_count  INTEGER DEFAULT 0,
  is_public   BOOLEAN DEFAULT true,
  challenge_id UUID,
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- SHOPPING WISHLIST (for price alerts + affiliate)
CREATE TABLE shopping_wishlist (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID REFERENCES users(id),
  product_url     TEXT NOT NULL,
  platform        TEXT,                                    -- 'myntra'|'nykaa'|'ajio'|'meesho'
  product_name    TEXT,
  image_url       TEXT,
  current_price   INTEGER,                                 -- in paise
  target_price    INTEGER,
  affiliate_url   TEXT,
  last_checked_at TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- ROW LEVEL SECURITY — users can only access their own data
-- ============================================================
ALTER TABLE users              ENABLE ROW LEVEL SECURITY;
ALTER TABLE wardrobe_items     ENABLE ROW LEVEL SECURITY;
ALTER TABLE outfits            ENABLE ROW LEVEL SECURITY;
ALTER TABLE suggestion_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_avatars       ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_posts       ENABLE ROW LEVEL SECURITY;
ALTER TABLE shopping_wishlist  ENABLE ROW LEVEL SECURITY;

-- Users can read/update their own profile
CREATE POLICY "user_owns_profile" ON users
  FOR ALL USING (auth.uid() = id);

-- Wardrobe: fully private to owner
CREATE POLICY "user_owns_wardrobe" ON wardrobe_items
  FOR ALL USING (auth.uid() = user_id);

-- Outfits: fully private to owner
CREATE POLICY "user_owns_outfits" ON outfits
  FOR ALL USING (auth.uid() = user_id);

-- Suggestion sessions: private to owner
CREATE POLICY "user_owns_sessions" ON suggestion_sessions
  FOR ALL USING (auth.uid() = user_id);

-- Avatars: private to owner
CREATE POLICY "user_owns_avatar" ON user_avatars
  FOR ALL USING (auth.uid() = user_id);

-- Social posts: public posts readable by all auth'd users, write by owner
CREATE POLICY "social_posts_public_read" ON social_posts
  FOR SELECT USING (is_public = true);

CREATE POLICY "social_posts_owner_write" ON social_posts
  FOR ALL USING (auth.uid() = user_id);

-- Wishlist: private to owner
CREATE POLICY "user_owns_wishlist" ON shopping_wishlist
  FOR ALL USING (auth.uid() = user_id);
