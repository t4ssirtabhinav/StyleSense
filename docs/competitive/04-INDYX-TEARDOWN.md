# Indyx — Screen-by-Screen Teardown

> 87 screenshots analysed in serial order (`IMG_7785` → `IMG_7873`).
> **Indyx is a fundamentally different animal from Fits.** Fits is a consumer AI toy with a social layer. Indyx is a
> **premium editorial wardrobe system with a human-stylist marketplace bolted on**. Where Fits sells credits, Indyx
> sells *membership* + *human styling sessions*. Read this teardown for **information architecture, data depth,
> analytics and business model** — not for the playful interaction patterns (those come from Fits).

---

## 0. Positioning & brand read

- Wordmark: `INDYX` in a high-contrast fashion serif with a hairline rule and the italic word **Insider** beneath — literally a magazine masthead.
- Palette: warm off-white / bone (`#F2F1E6`-ish) page, deep forest green (`#12332B`) primary, taupe/khaki accents, blush pink highlights. **No pure white, no pure black.**
- Type: all-caps letter-spaced sans for navigation and labels; an **italic serif for emotional copy** ("*Fall back in love with your wardrobe.*", "*Fashion is more fun with friends.*", "*We don't guess at your style. We see it (in your closet).*").
- Voice: aspirational, calm, anti-consumption. Tagline energy: *"The closet you have isn't the problem — it's the unlock."*
- **Takeaway for us:** Indyx proves a wardrobe app can look like *Kinfolk* rather than *Duolingo*. It is the aesthetic ceiling of the category. Fits is the interaction ceiling.

---

## PART 1 — GLOBAL NAVIGATION

**Five-tab bottom bar** (line icons, label under, active = filled/dark):
| Tab | Icon | Purpose |
|---|---|---|
| **Today** | calendar page showing `12` | daily planner / what am I wearing |
| **Connect** | node graph | social / friends' closets |
| **Wardrobe** | the `∩` monogram | items, outfits, collections |
| **Style** | coat hanger | Lookbook + human Stylists marketplace |
| **Profile** | person | account, analytics, membership |

Compare with Fits' 3 slots. Indyx exposes more surface, which fits a power-user/premium product; Fits hides everything behind Home.

---

## PART 2 — TODAY (planner-first home)

### 2.1 Today, empty — `IMG_7785`
- Masthead `INDYX Insider` + top-right: **calendar icon** and a **2-state segmented toggle: 👕 (flat/item view) | 🧍 (on-body view)** — a global rendering preference, not a per-outfit one.
- Date band: `WEDNESDAY / AUG 12` on the left; on the right a yellow `!` chip + **"Share location for local weather"** — a *deferred, inline* permission nudge rather than a blocking dialog. (Contrast Fits' pre-permission priming screen.)
- **Week strip**: SUN–SAT with dates, current day highlighted with a filled taupe block (full-height, not a circle).
- Body: "**What are you wearing today?**" + three stacked CTAs:
  - **ADD OUTFITS** (filled forest green, all-caps)
  - **ADD ITEMS** (light fill)
  - **ADD SELFIES** (light fill)
- **The home screen's primary question is a logging prompt, not a suggestion.** Indyx optimises for *data capture*; Fits optimises for *dopamine*. That is the single biggest strategic difference between them.

### 2.2 Wardrobe, empty — `IMG_7786`
- Top icon rail: 🔔 notifications · 📋 checklist · 📊 analytics · ⚙️ settings (all in circular outline buttons).
- **Three-segment tab bar with live counts**: `ITEMS (0)` | `OUTFITS (0)` | `COLLECTIONS (0)`.
- Search field: "Search brand, category, hashta…" — **brand and hashtag are first-class search dimensions.**
- Three circular tool buttons right of search: **multi-select cursor**, **display/layout toggle (the `∩` glyph)**, **filter**.
- Empty state: "Let's figure out what to wear tomorrow." with two garment photos and a ✨-shirt glyph between them; copy:
  > *"Planning your outfits on Indyx takes the chaos out of your morning routine so you feel calm and confident. Upload a bottom that you might want to wear tomorrow and let's get started indexing your closet."*
- **A dark rounded-square `+` FAB** floats above the tab bar.
- Note the onboarding instruction is *specific* ("upload **a bottom**") — a single concrete first action rather than "add your clothes". Good conversion practice.

### 2.3 Notifications — `IMG_7787`
Standard empty state: "You're all caught up!" + "Enable Push Notifications to get real-time updates on your wardrobe, new outfits, and the latest features." + underlined "**Tap here**" link.

---

## PART 3 — SETTINGS & DATA MODEL SIGNALS

### 3.1 Wardrobe settings — `IMG_7788`
Rows (icon · TITLE · description · value):
| Row | Description | Value |
|---|---|---|
| 🔒 **PRIVACY** | Control the share-ability of your wardrobe | `Closed` |
| 🅢 **CUSTOM DISPLAY** | Customize how your wardrobe shows up | ▣ *Insider* (premium-gated) |
| 🏷 **OUTFIT TAGS** | Organize via personalized hashtags | `0 tags` |
| 📍 **LOCATIONS** | **Manage inventory in multiple homes** | `0 locations` |
| 💵 **CURRENCY** | Update the display symbol for local currency | `USD $` |
| 📅 **CALENDAR START** | Set week start and default calendar view | |
| 🌡 **TEMPERATURE** | Choose between Fahrenheit or Celsius | |
| 🧹 **CLEAR CACHE** | Remove temporary files; your wardrobe will not be affected | |

**Two standouts:**
- **LOCATIONS — "manage inventory in multiple homes"**. This is a genuinely premium-user feature (city flat + parents' house + storage). For India it maps *perfectly* onto a real behaviour: **wedding/festival wear stored at parents' home, daily wear in the city**. Nobody else has this.
- **OUTFIT TAGS as personalised hashtags** — user-defined taxonomy on top of the fixed one. This is how power users actually organise ("#officeparty", "#travelcapsule").

### 3.2 Privacy / Open Closet — `IMG_7792`
- Editorial hero photo, italic serif headline "*Fashion is more fun with friends.*"
- **OPEN CLOSET** explainer: "Open your closet to share your wardrobe with friends. Indyx Insiders can choose to be **featured** to other Indyx users. You still always control the privacy of each individual item and outfit."
- **Three-state control rendered as both segmented buttons AND a slider**: `CLOSED` | `OPEN` | `FEATURED`, with a live caption ("Your closet is closed. Only you can see your wardrobe.").
- The dual control (buttons + slider) is redundant but communicates *a spectrum* rather than a switch. Same information-design instinct as Fits' recommendation-breadth halo.

---

## PART 4 — STYLE TAB (the human-stylist marketplace)

### 4.1 Style → Stylists — `IMG_7789`, `IMG_7790`
Two segments: **The Lookbook** | **Stylists**. The Stylists tab is a full marketing page:
- Editorial hero (clothes on a rail, dark overlay): *"Fall back in love with your wardrobe."* / "The closet you have isn't the problem — it's the unlock. You just need to see it with fresh eyes."
- Alternating illustration + copy cards:
  - **"Choose your stylist"** — "decide whether you want a quick **3-look mini** or a full **10-look deep dive** — all grounded in your real closet."
  - **"Share what matters"** — "Link your inspo and tell us what you're dressing for. Let us know if you'd like to see **shopping recs that unlock new possibilities** or **wardrobe-only styling**."
  - **"Watch your closet come to life"** — "Your stylist studies your wardrobe and builds outfits, **each with notes that explain the why** — giving you a guide to getting more out of every piece and ideas to keep building on."
- Manifesto block: *"We don't guess at your style. We see it (in your closet)."* / "No endless quizzes, just precise, personalized advice."
- **More Info ›** row, then **Featured Stylists**.

**Business read — this is Indyx's moat:**
1. **Human stylists working inside your indexed wardrobe** is a service business with real gross margin, sold as SKUs (3-look mini / 10-look deep dive).
2. The wardrobe index is the *input good* that makes the service cheap to deliver — a stylist doesn't need a call, they browse your closet.
3. It is a direct swipe at quiz-based competitors ("no endless quizzes") — and, notably, at AI-first apps: the pitch is *a human saw your actual clothes*.
4. **"each with notes that explain the why"** — explanation is the deliverable. (Our `ReasoningDisclosure` component is aiming at the same value, from the AI side.)

### 4.2 Profile hub — `IMG_7791`
- Avatar placeholder ("CHOOSE IMAGE", rounded-square not circle), `@handle`, italic-serif real name.
- **Three stat columns: `0 ITEMS · 0 OUTFITS · 0 COLLECTIONS`.**
- Forest-green pill: **`$0.00 LOOKBOOK CREDIT`** — store credit toward stylist sessions.
- Menu rows:
  - **INSIDER MEMBERSHIP** — Unlock premium features and exclusive access
  - **OPEN CLOSET** — Manage your public wardrobe profile
  - **WARDROBE ANALYTICS** — *Know your wardrobe composition, usage and investment*
  - **STYLE HUB** — Everything you need to refine your style
  - **REFERRAL** — Invite your friends and earn Indyx credit
  - **THE GIFT CREDIT** — *"Completely personal and never destined for the landfill"*
  - **CONTACT US**
- **`THE GIFT CREDIT`** is a lovely commerce idea: gift someone a styling session instead of clothes. Anti-waste positioning *and* a viral loop.
- Note the vocabulary: *composition, usage, investment* — they talk to the user as an asset owner, not a shopper.

---

### 4.3 Privacy states in full — `IMG_7793` (FEATURED), `IMG_7794` (OPEN)
- **OPEN**: "Other Indyx users can find your profile via search. **Long-press any item or outfit and mark as 'private'** to keep it to yourself."
- **FEATURED**: "Your profile is **actively promoted** to other Indyx users, making it more visible."
- Both states reveal a **public web link**: `https://opencloset.myindyx.com/user…` with a forest-green **SHARE** button.
- **Item-level private override on top of a global closet state** is the right privacy model, and the **public web closet URL** is a free SEO/virality surface that a mobile-only app doesn't get. Worth stealing.

---

## PART 5 — STYLE HUB (the profile-building machine)

### 5.1 Style Hub menu — `IMG_7795`
Four full-bleed editorial rows (photo on the left half, colour block + right-aligned all-caps title + description on the right):
| Module | Description |
|---|---|
| **STYLE PREFERENCES** (dark green) | "Help your stylist get to know you and your **unique style challenges**" |
| **STYLE QUIZ** (olive) | "Discover your **leading and supporting style archetypes**" |
| **STYLE WORDS** (blush/grey) | "Share how you best describe your personal style **in words**" |
| **STYLE WORKSHOP** (white) | "Embark on an **eight-week journey** to define your true personal style" |

**This is a far deeper profiling stack than any competitor.** Note the layering: a *form* (preferences), a *quiz* (archetypes), a *free-text self-description* (words), and a *course* (workshop). Each captures a different kind of signal, and the 8-week workshop is both a retention mechanic and a premium SKU.

### 5.2 Style Preferences intro — `IMG_7796`
- Full-bleed hero photo, then italic-serif copy:
  > "Help us get to know *you* and your unique *style challenges*.
  > This information will be **shared with your stylist** when you book one of our expert styling services.
  > Not ready to book yet? No problem! Set your preferences now and you'll get the chance to update them when you're ready."
- Forest-green **`START →`** pill.
- **The data collection is explicitly justified by the service.** Users hand over detailed information because a human will read it. An AI-only app has to work harder to earn the same disclosure — which is exactly why Fits attaches a "why we ask" line to every question.

### 5.3 Style Words — `IMG_7797`
- "**WHAT ARE YOUR STYLE WORDS?**" → three free-text fields: *Enter first word* / *second* / *third*.
- Fallback band: "Don't know where to start? We are here to help!" → cross-links to **STYLE QUIZ** and **STYLE WORKSHOP**.
- Three words is a well-chosen constraint (the classic stylist exercise). And they handle the blank-page problem by routing to the quiz.

---

## PART 6 — WARDROBE STRUCTURE

### 6.1 Outfits tab, empty — `IMG_7799`
- Search placeholder widens to "Search **name, brand, category, t**…" (t = tags).
- Empty copy: "You do not have any outfits yet. Please catalog a few items and press the '+' below to create your first outfit."
- Note the verb: **"catalog"**. Indyx consistently uses librarian language — *index, catalog, inventory, composition, investment*.

### 6.2 Collections tab, empty — `IMG_7800`
- Search: "Search collection type or name".
- **Four typed collection folders as coloured cards** with icons and italic-serif labels:
  | Folder | Colour | Icon |
  |---|---|---|
  | **Packing** | forest green | suitcase |
  | **Wishlists** | taupe | tag/label |
  | **Inspiration** | olive | lightbulb |
  | **Capsules** | butter yellow | 2×2 grid |
- Copy: "You can use Collections to make a packing, shopping, or **capsule** list."
- **Indyx has four collection types to Fits' three; the extra one is `Capsules`** — capsule wardrobes are a core concept for the intentional-dressing audience, and `Inspiration` is a place to store *aspirational* images that aren't owned items (Pinterest-style).

---

---

## PART 7 — ITEM INGESTION ("CREATE ITEM")

### 7.1 Create Item — image stage — `IMG_7801`, `IMG_7806`
- Title `CREATE ITEM`. Full-width cut-out preview on white.
- **`SD | HD` toggle** bottom-left of the image — the user chooses image resolution (storage/quality trade-off exposed as a control).
- **✨ shirt glyph + "Enhance"** floating bottom-right.
- Two-up action bar: **↻ ROTATE** · **📷 RETAKE**.
- Then the form begins inline: `Brand *` (required, auto-filled **"Spykar"** — an Indian denim brand, so their brand catalogue already has Indian coverage), `Size` (`32`).
- Forest-green **`UPLOAD →`** pill pinned at the bottom.
- **Brand is a required field.** That's a strong statement about what the product is for (investment tracking, resale, analytics) and it's what makes their brand-level analytics possible.

### 7.2 Create Item — taxonomy — `IMG_7802`, `IMG_7803`
Two-level required taxonomy rendered as **2-column outlined pill grids** (selected = filled forest green):
- **Category \*** (10): TOP · BOTTOM · OUTERWEAR · ONE PIECE · BAG · SHOES · ACCESSORY · JEWELRY · SWIM · OTHER
- **Subcategory \*** (contextual to Category; for BOTTOM): DENIM · LEGGINGS · OTHER · PANTS · SHORTS · SKIRT · SWEATPANTS · TIGHTS
- **Color(s)** — *plural*: a 7-column grid of **rounded-square** swatches (~21): black, dark brown, blue (selected, ring), purple, pink, orange, green, yellow, red, grey, blush, white-pink, mauve, ochre…
- **Multi-colour per item** is more correct than Fits' single colour (a printed kurta genuinely is three colours), and it makes colour-based outfit rules much better.
- **Only 10 categories × ~8 subcategories ≈ 80 leaf types** — comparable depth to Fits but flatter, and notably it separates **BAG / JEWELRY / ACCESSORY** into three top-level buckets.

### 7.3 Enhance Image (Insider-gated) — `IMG_7804`, `IMG_7805`
- Title `ENHANCE IMAGE`. Persistent dark banner: "**Enhanced Flatlays is an Insider feature. Your free preview of Insider ends in 14 days.**"
- Processing state: the raw photo washed out with a shimmer + copy "**Think: a professional product shot, in under 10 seconds**". `SAVE` disabled.
- Result state: the enhanced flat-lay large, with the **original as a small inset thumbnail bottom-right + a ⤢ expand toggle** to compare. `SAVE →` enabled.
- **Before/after inset is the right pattern** — it makes the value obvious and justifies the paywall.
- Positioning difference vs. Fits: Fits sells this per-credit; Indyx bundles it into membership. Same feature, two monetisation philosophies.

### 7.4 First item added + habit nudge — `IMG_7807`
- Grid item card: **white card, cut-out image, brand name (`Spykar`) as the label underneath** — cards *with* labels, unlike Fits' label-less grid. (Consistent with the "catalogue" mental model.)
- A coloured band at the bottom: "**Isn't that a little addicting?** Let's keep going. **Upload a top that you like to wear with this bottom.**"
- **Sequenced onboarding nudges that build a first outfit**: bottom → matching top → outfit. Each nudge is one concrete action, and by step 3 the user has an outfit. This is a much better cold-start than "add 20 items".

### 7.5 Custom Display (Insider) — `IMG_7808`
Per-view display preferences, tabs `ITEMS | OUTFITS | COLLECTIONS`:
| Setting | Options |
|---|---|
| **DISPLAYED IN A ROW** | 2 · **3** · 5 · 7 |
| **PRIMARY LABEL** | **BRAND** · NAME |
| **DEFAULT SORTING** | **CREATED: NEWEST** · CREATED: OLDEST · PURCHASED: NEWEST · PURCHASED: OLDEST · **COST/WEAR: HIGHEST** · **COST/WEAR: LOWEST** · **MOST WORN** · **LEAST WORN** · CATEGORY · CUSTOM |
| **DEFAULT SEASON** | SPRING · SUMMER · FALL · WINTER |
| **DEFAULT LOCATION** | (multi-home) |

- **Cost-per-wear and wear-count are *sort orders*, not just stats.** That is the deepest integration of the CPW concept in the category — the user can literally browse their closet worst-value-first.
- Letting the user pick 7-per-row is a power-user affordance almost no consumer app offers.

---

### 7.6 Custom Display — Outfits & Collections — `IMG_7809`, `IMG_7810`
**OUTFITS tab:**
- `DISPLAYED IN A ROW`: 2 · **3** · 5 · 7
- **`DEFAULT STYLIST`: SELF STYLED · SOCIAL STYLED · EXPERT STYLED** ← **outfits carry provenance.** Who made this outfit: me, a friend/community, or a paid expert. This is a first-class dimension of their data model and it is *the* schema difference that enables the marketplace.
- **`DEFAULT STATUS`: IN WARDROBE · RECOMMENDATION · WISHLIST** ← an outfit can be composed of items you *don't own yet*. That's how a stylist proposes purchases inside the same object model.
- `DEFAULT SORTING`: CREATED NEWEST/OLDEST · MOST WORN · LEAST WORN · CUSTOM

**COLLECTIONS tab:** `DEFAULT TYPE`: PACKING · CAPSULE · WISH · INSPIRATION; `DEFAULT SORTING`: CREATED NEWEST/OLDEST · TYPE · CUSTOM.

> **For StyleSense this is the single most important schema insight in the Indyx teardown:** add `source` (`self | ai | expert | social`) and `status` (`owned | recommendation | wishlist`) to the outfit model *now*, before the data grows. It costs two columns today and unlocks stylist marketplace, shopping recommendations and "outfits that need a purchase" later.

### 7.7 Filter sheet — `IMG_7811`, `IMG_7812`
Modal sheet, `Clear` (left) / `FILTER` / `✕`, with **`APPLY FILTER →`** pinned. Sections:
| Section | Values |
|---|---|
| **CATEGORY** | the 10 top-level types |
| **SEASON** | Spring · Summer · Fall · Winter |
| **COLOR** | 14 swatches |
| **VISIBILITY** | PRIVATE · FAVORITE · **DO NOT STYLE** · ARCHIVE · **SOLD/DONATED** |
| **SOURCE** | **PURCHASE · GIFT · SELF-MADE** |
| **SECONDHAND** | YES · NO |
| **LOCATION** | (multi-home) |
| **SORT** | CREATED ▲▼ · PURCHASED ▲▼ · **COST/WEAR HIGHEST/LOWEST** · MOST/LEAST WORN · CATEGORY · CUSTOM |

**Four fields nobody else has:**
1. **`DO NOT STYLE`** — an explicit exclusion flag. The user tells the engine "never suggest this" (a gift you hate, a uniform, a maternity piece). *This is the cheapest, highest-value styling-quality feature in this entire analysis* — it converts every bad suggestion into permanent training data with one tap, without any ML.
2. **`SOLD/DONATED`** — closes the item lifecycle (owned → archived → sold/donated) and preserves history for analytics.
3. **`SOURCE: purchase | gift | self-made`** — gifts shouldn't count in "wardrobe spend"; self-made matters to a maker audience.
4. **`SECONDHAND: yes/no`** — sustainability metric and a resale-market hook.

For India, `source` should extend to **`inherited/hand-me-down`** and **`tailored/stitched`** (a huge share of Indian wardrobes are made by a local darzi, not bought), and `SOLD/DONATED` maps onto the very common "given to help/relatives" flow.

### 7.8 Location permission screen — `IMG_7814`
Full editorial photo, then "**It helps to know where you are.**" with an honest bulleted rationale:
- Display your local weather
- **Match you with nearby stylists**
- Improve calendar accuracy while traveling
Plus a plain-language data promise: "Your location data is not sold or shared with third parties except as required to provide these features (e.g., weather data services)."
`SET PERMISSION →`.
**Best-in-class permission screen in this analysis** — three concrete uses and an explicit non-sale promise. Copy the structure verbatim for our location and camera prompts (and it maps well onto Indian users' rising privacy sensitivity).

### 7.9 "Link a Board" — the planner primitive — `IMG_7815`, `IMG_7816`
- Sheet `LINK A BOARD`, tabs **`AUG 12 BOARDS` | `ALL BOARDS`**.
- Copy: "**Link a board or create a new one to automatically update cost per wear.**"
- All Boards has a search ("Search by outfit name, brand, or category / subcategory") and an **`OUTFIT TAG`** section.
- Empty: "You do not have any boards assigned to August 12, 2026."

**"Board" = a planned outfit assigned to a date.** The killer detail is the framing: *linking a board to a day automatically updates cost-per-wear*. Planning and wear-logging are the same action, and the economic metric is the stated reward. That is a much better retention loop than "please remember to log what you wore".

---

---

## PART 8 — OUTFIT BUILDER (collage canvas)

### 8.1 Create Outfit canvas — `IMG_7817`
- Header `CREATE OUTFIT` with `⋯` overflow. `CLEAR` top-right of the canvas.
- Large white **free-form canvas** (no mannequin — Indyx is collage-only; there is **no Dressing Room equivalent**).
- **Canvas toolbar** (6 line icons): 🗑 delete · ⤢ scale up · ⤡ scale down · ▣ bring forward · ▤ send backward · 🔓 lock.
- **Three input tabs**: `Add Selfie` | `Add Items` | **`Add Inspiration`**.
- `SAVE →` pinned.
- **`Add Inspiration` is unique**: an outfit can contain a Pinterest-style reference image alongside your real garments — "this is the vibe I'm going for with these pieces". That's how a *stylist* works, and it bridges aspiration and inventory.
- **Gap vs. Fits:** no on-body rendering, no per-slot swipe-swap, no shuffle. Indyx's builder is a design tool; Fits' is a toy. **Fits wins decisively on this screen** — which is why our builder should follow Fits, while our data model follows Indyx.

### 8.2 Select Items sheet — `IMG_7818`
- `Clear` / `SELECT ITEMS` / `✕`, search "Search by brand, subcategory or tags".
- **A dimension switcher rail**: `CATEGORY · COLOR · LOCATION · SEASON · COLLECTION` — picking a dimension changes the chip row beneath it (chips are in *italic serif*, a nice touch).
- Item cards with brand labels; `ADD TO OUTFIT →`.
- **Faceted browsing by five dimensions inside the picker** is much stronger than a single category rail. `LOCATION` again — "show me only what's in this house".

### 8.3 More Create Item taxonomy — `IMG_7819`, `IMG_7820`, `IMG_7821`, `IMG_7826`
- **TOP subcategories** (16): BLOUSE · BODYSUIT · CAMISOLE · CARDIGAN · HOODIE · JERSEY · OTHER · POLO · SHIRT · STRAPLESS · SWEATER · SWEATSHIRT · T-SHIRT · TANK · TUNIC · VEST.
- Note **TUNIC** exists — the closest thing to a kurta in any Western taxonomy, and it's a poor substitute. Confirms the localisation gap.
- Colour grid confirmed at **21 swatches**, single-select ring shown on the chosen one but the label says `Color(s)` (multi-select supported).
- `UPLOAD` stays disabled until required fields (Brand, Category, Subcategory) are filled — hard validation on a *brand* field is a bold choice.

### 8.4 Receipt-based ingestion — `IMG_7823`
Loading-state copy over the item photo:
> "**Shop online? Forward us your email receipts and we'll extract the items for your review.**"

**This is the fourth ingestion path and it's the most under-appreciated one.** Forward an order confirmation → they parse brand, item name, price, purchase date, and product image → items appear pre-populated for approval. It captures **exactly the metadata that manual entry never gets** (price and purchase date — the two inputs cost-per-wear needs).
For India this maps onto Myntra / Ajio / Flipkart / Nykaa Fashion / Meesho order emails, all of which have highly regular templates. **High-value, low-difficulty, and it produces the analytics data that makes everything else work.**

### 8.5 Enhance on a hard case — `IMG_7824`
Cargo trousers shot on a patterned bedsheet → clean cut-out on white with the original as an inset. Handles a genuinely messy Indian-bedroom-floor photo well. This is the quality bar our background-removal (SS-011) must hit.

---

### 8.6 Complete Indyx taxonomy — `IMG_7827`–`IMG_7834`
(Brand field here is **"Snitch"** — another Indian D2C brand recognised by their catalogue.)

| Category | Subcategories |
|---|---|
| **TOP** (16) | Blouse · Bodysuit · Camisole · Cardigan · Hoodie · Jersey · Polo · Shirt · Strapless · Sweater · Sweatshirt · T-Shirt · Tank · Tunic · Vest · Other |
| **BOTTOM** (8) | Denim · Leggings · Pants · Shorts · Skirt · Sweatpants · Tights · Other |
| **OUTERWEAR** (5) | Blazer · Coat · Jacket · Vest · Other |
| **ONE PIECE** (3) | Dress · Jumpsuit · Romper |
| **BAG** (11) | Backpack · Belt Bag · Briefcase · Bucket · Clutch · Crossbody · Shoulder · Top Handle · Tote · Wallet · Other |
| **SHOES** (11) | Boots · Clogs · Flats · Heels · Loafers · Mules · Oxford/Derby · Sandals · Sneakers · Wedges · Other |
| **ACCESSORY** (11) | Belt · Gloves · Hair Accessories · Hat · Pocket Square · Scarf · Socks · Sunglasses · Tie · Other |
| **JEWELRY** (7) | Bracelet · Brooch · Earrings · Necklace · Ring · Watch · Other |
| **SWIM** (4) | Cover-up · One-Piece · Separates · Trunks |
| **OTHER** | — |

**≈76 leaf types, no icons** (all text pills). Fits has ~70 *with* icons.

**The India gap, stated precisely.** Neither taxonomy can represent:
- Tops: **Kurta · Kurti · Anarkali · Choli/Blouse (saree) · Sherwani · Nehru jacket · Bandhgala**
- Bottoms: **Salwar · Churidar · Palazzo · Dhoti · Patiala · Sharara · Garara · Lungi/Mundu**
- One-piece: **Saree · Lehenga · Salwar-kameez set · Kurta set**
- Drape/other: **Dupatta · Stole · Angavastram · Pagdi/Safa · Turban**
- Footwear: **Juttis · Kolhapuris · Mojaris · Chappals**
- Jewellery: **Bangles · Jhumkas · Maang tikka · Nose ring · Payal · Mangalsutra**

A saree is not a "dress"; a dupatta is not a "scarf" (it is a required component of an outfit, with drape styles); a kurta is not a "tunic". **This is not cosmetic — it breaks the outfit-composition rules**, because a saree+blouse+petticoat is one outfit made of three garments, and a kurta-salwar-dupatta set is three garments that must be suggested together. Any Western engine will either treat these as unmatched singletons or propose incoherent combinations.

---

---

## PART 9 — EDIT ITEM: THE FULL DATA MODEL (the most valuable screens in this teardown)

`EDIT ITEM` has a two-level tab structure: **`ITEM` | `OUTFITS`** (the outfits this piece appears in), and inside ITEM: **`COST PER WEAR` | `PRODUCT INFO` | `TAGS`**. A 🗑 delete sits in the nav bar. Multiple images per item via an **`+ Add Image`** strip.

### 9.1 `COST PER WEAR` tab — `IMG_7837`, `IMG_7838`
Hero stat in **italic serif**: **`$0.00`** with the sub-line "**0 times in 0 days**". Then the economic record:
| Field | Type |
|---|---|
| **TIMES WORN** | number (directly editable — you can backfill) |
| **SOURCE** | dropdown: Purchase / Gift / Self-made |
| **SECONDHAND** | dropdown yes/no |
| **DATE ACQUIRED** | date |
| **PURCHASE PRICE** | currency |
| **ORIGINAL PRICE** | currency ← lets them compute *discount captured* |
| **PURCHASE LOCATION** | text |
| **RESALE VALUE** | currency |
| **DATE SOLD / DONATED** | date |
| **SOLD PRICE** | currency |

**This is a full asset-lifecycle ledger for a garment.** `original price` + `purchase price` + `resale value` + `sold price` + `times worn` + `days held` yields: cost per wear, discount captured, depreciation, realised recovery, and holding period. No other app in this set models the *end* of an item's life.

For India this maps directly onto real behaviour — **resale (Cashify-style for clothes is nascent, but hand-me-downs and "give to didi/help" are universal)**, and `original price` matters enormously in a market where MRP-vs-sale-price is the dominant purchase frame.

### 9.2 `PRODUCT INFO` tab — `IMG_7839`, `IMG_7840`
| Field | Notes |
|---|---|
| **BRAND\*** | required (`Max`, `Westside`, `Souledstore`, `Zaydn`, `asics` all recognised = **their brand catalogue already covers Indian retail**) |
| **NAME** | placeholder "Enter **2-3 word** description" — an explicit length hint |
| **CATEGORY\*** / **SUB-CATEGORY\*** | dropdowns |
| **SIZE\*** | required here (optional at create) |
| **COLOR** | 21-swatch grid |
| **MAIN MATERIAL** | dropdown, defaults to `Undefined` |
| **PERSONAL NOTE** | textarea — "a personal note about this item" |
| **DESCRIPTION** | textarea — the objective description |
| **CONDITION** | dropdown |
| **CONDITION DETAILS** | text ("small stain on left cuff") |
| **ORIGIN** | text, placeholder "E.g China, Turkey, Italy" ← country of manufacture, a *sustainability/ethics* field |
| **SHOPPING URL** | the re-purchase / affiliate link |

Note the separation of **personal note** (subjective, private) from **description** (objective, shareable). And **CONDITION + CONDITION DETAILS** is what makes resale credible.

### 9.3 `TAGS` tab — `IMG_7841`
| Group | Values |
|---|---|
| **SEASON** | Spring · Summer · Fall · Winter (multi) |
| **VISIBILITY** | PRIVATE · FAVORITE · **DO NOT STYLE** · ARCHIVE |
| **LOCATION** | ✏️ editable (which home) |
| **CUSTOM HASH TAG** | free text — *"Enter any custom hashtag e.g. #long-sleeve, #classic, #casual. **Hashtags are searchable in your wardrobe.**"* |

**User-defined hashtags are the escape valve for taxonomy gaps.** An Indian user can tag `#diwali`, `#officeformal`, `#gymwear`, `#mummykasaree` today without waiting for us to model it — *and those tags are exactly the signal we should mine to decide what to add to the official taxonomy.* Cheap to build, and it doubles as product research.

### 9.4 Populated wardrobe grid — `IMG_7842`
- 3-column grid, **white cards with a hairline grid rule between them**, cut-out on white, **brand name label beneath each**.
- Real Indian wardrobe visible: `Souledstore` polo, `Zaydn` sneakers, `Westside` derbies, `asics` runners, `Max` cargos, `Westside` tee, Nike Air Max.
- Filter icon carries a **red badge `1`** showing an active filter count.
- Header counts update live: `ITEMS (12)`.

**The Indian brand coverage (Souledstore, Zaydn, Westside, Max, Snitch, Spykar) is important competitive intelligence: Indyx's catalogue is already usable in India.** Our "India-first" claim cannot rest on brand coverage alone — it has to rest on **garment taxonomy, occasions, and styling rules**, which is where they are genuinely absent.

### 9.5 Confirmation dialog pattern — `IMG_7836`
Rounded card with one asymmetric corner: "Are you sure you want to leave without selecting an image?" → filled `LEAVE →` / outlined `GO BACK →`. Consistent arrow affordance on every button in the app.

---

---

## PART 10 — WARDROBE ANALYTICS (the deepest analytics in the category)

Three tabs: **`COMPOSITION` | `USAGE` | `INVESTMENT`**, all Insider-gated. Every card has a **`?` info affordance** explaining the metric — a small thing that makes an analytics screen teachable instead of intimidating.
Chart language: horizontal bars, **donut charts with a legend above and the majority % inside**, vertical bar charts for time series, pastel-on-bone palette (forest / lilac / olive / butter / taupe-for-Undefined).

### 10.1 COMPOSITION — `IMG_7843`–`IMG_7849`
| Card | Chart | Detail |
|---|---|---|
| **CATEGORY** | horizontal bars with `count (percent)` | Bottom 5 (42%) · Shoes 4 (33%) · Top 3 (25%) · all others 0 (0%) — **zero rows are still shown**, which is what makes gaps visible |
| **COLOR** | grid of swatches with **% written inside each swatch** | black 23% · grey 23% · beige 23% · blue 15% · brown 8% · green 8% · rest 0% — brilliant: the chart *is* the palette |
| **SOURCE** | donut | Purchase / Gift / Self-Made |
| **NEW VS SECONDHAND** | donut | New / Secondhand / **Undefined** |
| **MATERIAL TYPE** | donut | **Natural / Synthetic / Semi-Synthetic** / Undefined ← rolled-up from the material field; a sustainability metric |
| **SEASON** | donut | Winter/Spring/Summer/Fall/Undefined |
| **LONGEVITY** | donut | **< 1 Year · 1–3 · 3–5 · > 5 Years** ← how long you've *kept* things |
| **ITEMS ADDED** | vertical bars | `+12` at **1M · 3M · 6M · 1Y** windows |
| **ITEMS SOLD / DONATED** | vertical bars | same windows |

**`Undefined` is always a first-class slice.** It quietly nags the user to complete their data, and it's honest about coverage — far better than silently excluding incomplete rows.

### 10.2 USAGE — `IMG_7850`
- Two chip rails: category (`TOP · BOTTOM · OUTERWEAR · ONE…`, italic serif) then subcategory (`BLOUSE · BODYSUIT · CAMISOLE · C…`) — analytics are **drillable to leaf type**.
- **`MOST VERSATILE ITEMS`** and **`LEAST VERSATILE ITEMS`** — horizontally scrolling item cards showing `brand` + **`N outfits`**.
- **"Versatility" = number of distinct outfits an item appears in.** This is the single best wardrobe metric in the entire competitive set:
  - It is a pure `COUNT(DISTINCT outfit_id)` — free.
  - It answers the real question ("what's actually earning its place?") better than wear count, because a piece worn 20 times in the same outfit is not versatile.
  - "Least versatile" is a natural, non-judgemental shopping/decluttering prompt.
  - **And it is a ranking signal for the styling engine**: high-versatility items are safe anchors, low-versatility items are the ones the engine should work harder to use.

---

### 10.3 USAGE continued — `IMG_7851`–`IMG_7854`
- **`MOST WORN ITEMS`** / **`LEAST WORN ITEMS`** — item cards with `brand` + `N wears`.
- **A two-metric table**, sortable by tapping the column header (active column gets a **red underline**):
  | CATEGORY | **# OF WEAR** | **CPW** |
  |---|---|---|
  | Total Wardrobe · Top · Bottom · Outerwear · One Piece · Bag · Shoes · Accessory · Jewelry · Swim · Other | | |
  Repeated for **COLOR** (rows are swatches) and presumably brand/season.
- Tapping `?` reveals a precise definition tooltip:
  - `# OF WEAR` → "**Average # of times an item has been worn, by category. Includes only items that are worn at least once.**"
  - `CPW` → "**Average cost-per-wear, by category. Includes only items where cost per wear is greater than $0.**"
- **Stating the exclusion rule inside the tooltip is exemplary.** Every derived metric we ship should carry its definition this way — it pre-empts "your numbers are wrong" and it forces us to actually decide the semantics.
- Analytics **by colour** is an under-rated axis: "you wear 60% of your black items but 10% of your yellow ones" is directly actionable at the point of purchase.

### 10.4 Outfit-photo (selfie) viewer — `IMG_7855`, `IMG_7856`
- Full-bleed **background-removed mirror selfie** on white — they cut out the *person*, not just the garment.
- Bottom action row of circular buttons: 🗑 delete · 🔖 bookmark/save · ↻ rotate · 📷 retake · **✨ enhance**.
- `SD | HD` toggle and a **`‹ 2 of 2 ›` pager**.
- Multiple images per item, with one being a **worn-on-body shot** — see 10.5.

### 10.5 Item with both packshot and worn-shot — `IMG_7857`, `IMG_7858`
- The image strip under the main photo shows `+ Add Image` then the **on-body selfie** as a second image of the *same item*.
- TAGS tab shows the item marked `SPRING`+`SUMMER` and `FAVORITE` (selected pills are solid black here, vs. forest green elsewhere — inconsistent, a minor blemish).
- **Attaching a real worn photo to a catalogue item is the cheapest possible "virtual try-on"**: the user already knows what it looks like on them, because it's a photo of them. Fits spends AI credits to synthesise this; Indyx just stores it. Worth offering both.

---

---

## PART 11 — OUTFIT CANVAS IN USE + VIRTUAL SELFIE

### 11.1 Canvas with items placed — `IMG_7859`, `IMG_7864`
- Selected element gets a **thin blue bounding box** (a desktop-design-tool convention, not an iOS one).
- Items are freely positioned; the composition reads as a flat-lay (polo top-left, jeans right, sneakers bottom-left) — **no automatic layout assistance at all**. Compare Fits, which snaps garments onto body slots. Indyx is manual work; Fits is play.
- Toolbar: 🗑 · ⤢ scale-up · ⤡ scale-down · ▣ forward · ▤ backward · 🔓 lock.

### 11.2 Select Items — faceted picker in action — `IMG_7860`–`IMG_7863`
- Selected items get a **butter-yellow ✓ badge** and a grey card background — a warm, non-aggressive selection state.
- **Active facet shows a count**: `CATEGORY (1)`, `COLOR (1)`. Choosing `BOTTOM` reveals a second row of subcategory chips (`DENIM · LEGGINGS · OTHER · PANTS`) — **two-level chip drilldown inside the picker**.
- `SEASON` facet → `SPRING · SUMMER · FALL · WINTER`; `COLOR` facet → swatch rail; both filter the grid live.
- **This picker is better than Fits'** (which only offers a category rail + a filter sheet). Facet tabs + counts + live drilldown is the right pattern for a wardrobe of 200+ items.

### 11.3 Virtual try-on prompt — `IMG_7865`
Modal after composing: "**See this outfit on you in seconds.** / Would you like to try this outfit on virtually?" → filled **`CREATE A VIRTUAL SELFIE →`** / outlined `SKIP →` / **☐ Don't ask me again**.
- Offering the generative feature *at the moment of completion*, with a permanent opt-out, is respectful and converts well. (Fits instead makes AI Try-On a mode you must choose upfront.)

### 11.4 Reference Selfie setup — `IMG_7866`
`PROFILE` with tabs `PERSONAL | OPEN CLOSET | **VIRTUAL SELFIE**`.
> **Reference Selfie** — "We need a photo of you to create virtual selfies. Upload a new photo or click on the existing photo to update."
> Ghosted full-body illustration + instructions: "**To generate your virtual selfie, we'll need a full-body photo of you. Stand back from the mirror, cover your face with your phone, and make sure your whole body is in frame.**"

- **"Cover your face with your phone"** is a brilliant privacy-preserving instruction: they get body shape and proportions without ever holding a face photo. It also sidesteps the hardest part of generative try-on (face identity preservation).
- **For India this matters a lot.** Asking women users for a full-body photo is a real trust barrier; "your face never needs to be in it" removes most of the objection. We should adopt this instruction verbatim, and go further — offer the **mannequin/avatar path (Fits-style) as the default** and generative try-on as opt-in.

---

### 11.5 Personal profile fields — `IMG_7867`
`USER NAME*` · `FIRST NAME*` · `LAST NAME*` · `EMAIL ADDRESS*` · `BIRTH YEAR` · `GENDER` (dropdown, "Man") · `ADDRESS` · `ZIP CODE` · `DISPLAY LOCATION`.
- **Email-first identity, not phone** — a US-centric choice. Our phone-OTP + `+91` path is correct for India and is a real localisation advantage (Indyx would need to rebuild auth to compete here).
- `ZIP CODE` powers weather + **nearby stylist matching**.

### 11.6 Outfit detail — Board/Selfie toggle & overflow — `IMG_7868`, `IMG_7869`
- Top-right pill toggle: **`👕 Board` | `🧍 Selfie`** — the *same outfit* has two representations: the flat-lay board and the on-body photo. Pager `‹ 1 of 2 ›`.
- Selfie tab empty state: "**Capture how you wear it or virtually try it on**" → outlined **`ADD A MIRROR SELFIE`** / filled **`CREATE A VIRTUAL SELFIE`**. Real photo is offered *first*.
- Coach copy: "A great reference photo goes a long way. We recommend a full-body selfie taken with your phone positioned in front of your face."
- **Overflow menu (right-aligned labels + icon tiles)** — the complete outfit action set:
  | Action | Note |
  |---|---|
  | **Edit Board** | re-open the canvas |
  | **Manage Selfies** | multiple on-body photos per outfit |
  | **Outfit Details** | metadata |
  | **Wear History** | *every date this outfit was worn* |
  | **Duplicate Outfit** | ← clever: iterate a look ("same but with the other jacket") |
  | **Add to Calendar** | plan it |
  | **Add to Collection** | |
  | **Delete Outfit** | |
- **`Duplicate Outfit` + `Wear History` are both missing from Fits and from us.** Duplicate is how users actually build a wardrobe of variations; wear history per outfit (not just per item) is what makes "you wore this 3 weeks ago" possible.

### 11.7 Virtual selfie generation — `IMG_7870`, `IMG_7871`
- Loading: "**Sit tight! Virtual selfies can take up to 20 seconds to generate.**" — an explicit, honest time estimate. (Fits narrates named steps instead; both beat a bare spinner.)
- Result: a genuinely good full-body render of the user wearing the composed outfit, face obscured by the phone as instructed. Quality is high — the polo, jeans and Nikes are all recognisably the user's own items.

### 11.8 Public "Open Closet" web profile — `IMG_7872`, `IMG_7873`
- `INDYX` masthead, 🔒 privacy and ⬆️ share icons, circular avatar, `@handle` + italic-serif real name, ✏️ edit.
- **Four tabs rendered as icons**: `👕 (outfits)` · `▦ (items)` · `📁 (collections)` · `💼 (?)` — with the active one showing its label + count (`OUTFITS (2)`, `ITEMS (12)`).
- Outfit cards carry a **❤️ like** (filled red when liked).
- Item cards carry a **🔔 bell** — *notify me* / *ask about this item*, the social-commerce hook on someone else's closet.
- This is the **shareable public wardrobe** — a web-accessible URL, an SEO surface, and a referral loop that a purely in-app product doesn't get.

---

## PART 12 — INDYX: SYNTHESIS

### What Indyx does better than anyone
1. **Item data model** — full asset lifecycle (acquire → wear → resell/donate) with `original price`, `resale value`, `condition`, `origin`, `source`, `secondhand`.
2. **Analytics** — three tabs, ~15 charts, drillable to leaf category, with *stated metric definitions*, including the best single metric in the category (**versatility = distinct outfits an item appears in**).
3. **Outfit provenance** — `self | social | expert` styled, and `in-wardrobe | recommendation | wishlist` status. The schema that makes a stylist marketplace possible.
4. **`DO NOT STYLE`** — one-tap permanent exclusion, the cheapest styling-quality lever in existence.
5. **Locations / multi-home inventory** — nobody else models this, and it maps perfectly onto Indian wardrobes split between city and family home.
6. **Human-stylist marketplace** with productised SKUs (3-look mini / 10-look deep dive) and a credit/gifting economy.
7. **Receipt-forwarding ingestion** — the only path that captures price and purchase date reliably.
8. **Privacy-preserving virtual try-on** ("cover your face with your phone").
9. **Public web closet** with likes and item-level bells.
10. **Editorial brand craft** — the aesthetic ceiling of the category.

### Where Indyx is weak (and Fits/we can win)
1. **No on-body dressing room, no swap/shuffle** — outfit creation is manual desktop-style collage work. Slow, unfun, and it kills daily engagement.
2. **No proactive suggestions at all** — the app never says "wear this today". Every outfit is user- or stylist-initiated. `Today` asks *you* what you're wearing.
3. **No AI stylist / no conversational or task-based AI surface.**
4. **Cold start is brutal** — required Brand field, required category/subcategory, and no seed wardrobe, no photo-library mining, no catalogue search.
5. **Everything good is Insider-gated** (analytics, enhance, custom display), with a hard 14-day countdown banner on every screen — heavy-handed.
6. **Dense, form-heavy UI** — beautiful but effortful. It rewards the obsessive user and loses the casual one.
7. **US-centric identity (email), currency default USD, Western taxonomy, Western seasons** (Spring/Summer/Fall/Winter is meaningless for most of India — we need Summer / Monsoon / Winter / Festive).

### The strategic read
**Fits monetises engagement; Indyx monetises intention.** Fits' revenue comes from AI credits consumed by people playing with the dressing room; Indyx's comes from membership + human styling bought by people who take their wardrobe seriously.
**StyleSense should take Fits' interaction model and Indyx's data model** — the playful, zero-marginal-cost outfit surface on top of a ledger rich enough to support analytics, resale, and (eventually) a stylist marketplace, all on an India-native taxonomy neither of them has.

---

<!-- BATCH LOG: INDYX COMPLETE — all 87 screenshots analysed (7785–7873). -->
