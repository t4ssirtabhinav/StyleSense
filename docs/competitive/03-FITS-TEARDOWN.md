# Fits — Screen-by-Screen Teardown

> Primary UI/UX inspiration source. 135 screenshots analysed in serial order.
> Design language summary is at the bottom (`## Design System Extraction`) — grows as batches are analysed.

---

## PART 1 — ONBOARDING (the "profile-building funnel")

Fits' onboarding is **not** a 4-step wizard. It is a ~15+ screen, single-question-per-screen funnel with a thin
progress bar pinned at the top. Every screen is: `progress bar` → `big bold H1 question` → `one-line grey rationale
("We ask this to…")` → `answer surface` → `full-width black pill CTA`. This is the single highest-leverage pattern
to copy: it feels fast because each screen has one decision, and it harvests an enormous profile.

### 1.1 Gender — `IMG_7874`
- H1: "What's your gender?" · Sub: "We ask this to personalize the styling experience for you."
- Options as full-width grey (`#F2F2F2`) rounded-16 rows, emoji + label, ~72pt tall, 12pt gap.
- Values: 🙋‍♀️ Woman · 🙋‍♂️ Man · 🙋 Non-binary · 🙅 Prefer not to say.
- **No CTA button** — tapping a row auto-advances. (Single-select screens auto-advance; multi-select screens get a Next button.)
- Progress bar ~4% filled → tells the user the funnel is long but sets expectation early.

### 1.2 Motivation / JTBD — `IMG_7875`
- H1: "What do you want the most from Fits?" — **multi-select**, all pre-checked by default except the last.
- Options (this is their explicit JTBD taxonomy — worth copying verbatim as our value-prop framing):
  - 💸 Shop smarter and save money
  - 🪞 Track what I'm wearing
  - 👕 Create and discover outfits
  - 🗂️ Organize my clothes
  - 📊 Wardrobe stats and insights
  - ⏳ Save time choosing an outfit daily
  - 👀 Just looking around  *(escape hatch, unchecked, and unchecking others)*
- Selected state = white fill + 2px black border + black filled ✓ circle on right. Unselected = flat grey, no check.
- **Pre-checking everything is a deliberate dark-ish pattern**: it maximises declared intent and makes the user feel the app does a lot.
- Downstream use: this is almost certainly what drives which home-screen modules are shown/ordered.

### 1.3 Selfie for AI try-on + facial analysis — `IMG_7876`, `IMG_7878`
- H1: "Add a selfie to try on outfits with AI" · Sub: "We also customize outfit suggestions based on your facial features."
- Illustration: headshot card → chevron → 3 full-body model renders in different outfits. Sells the output before asking for the input.
- CTAs stacked: **Take a selfie** (black pill) / **Choose from library** (grey pill) / **Skip** (bare text).
- Note the double ask: the selfie powers *both* virtual try-on *and* colour/facial-feature-based recommendation. One input, two features — that framing is what makes users hand over a face photo.

### 1.4 Photo-library scan permission — `IMG_7879`
- H1: "Train your AI stylist from your outfit photos" · Sub: "We scan your photo library for outfit photos **on-device**."
- **Pre-permission priming screen**: renders a *mock* of the iOS permission dialog behind a blur, with a big → arrow pointing at "Allow Full Access", and helper copy "Tap 'Allow Full Access' so we can find your outfit photos." Then a black "Continue" CTA triggers the real dialog.
- "on-device" is doing heavy lifting for consent. This is a **major acquisition mechanic**: instead of making the user photograph 60 garments, Fits mines their camera roll for existing OOTD mirror selfies. Cold-start problem solved.

### 1.5 Location permission — `IMG_7880`
- Same pre-permission priming pattern. H1: "Dress according to the weather near you". Mock dialog + arrow at "Allow While Using App" + rationale "…to get updated weather info when travelling."

### 1.6 Social proof / community — `IMG_7881`
- H1: "Discover outfits and wardrobes" · Sub: "Connect with your friends and the Fits community to get inspired."
- Illustration: 3 overlapping phone cards — a creator profile w/ Follow button + flat-lay wardrobe grid, a mirror-selfie OOTD, and a flat-lay outfit collage with heart reactions.
- Establishes the social layer *before* the user has any content — sets the expectation that wardrobes are shareable objects.

### 1.7 Date of birth — `IMG_7882`, `IMG_7883`
- H1: "Add your date of birth" · Sub: "This won't be part of your profile, but we need to ensure you are at least 13 years old."
- Bordered input showing formatted date + calendar glyph; native 3-wheel picker docked at the bottom, **below** the Next button (button stays reachable).
- Compliance framing ("won't be part of your profile") reduces drop-off. Age is also a strong styling signal they quietly get for free.

### 1.8 Shopping frequency — `IMG_7884`
- H1: "How often do you buy clothes?" · Sub: "This helps us tailor styling tips to your shopping habits."
- Weekly / Monthly / Seasonally / Rarely. Plain grey rows, auto-advance.
- Feeds the "shop smarter" narrative + likely gates how aggressively they push shopping/affiliate content.

### 1.9 Value-prop interstitial: cost-per-wear — `IMG_7885`
- Not a question — a **belief-installation screen** mid-funnel. H1: "Fits helps you make better purchases".
- Two cards side by side: "Most worn" (striped tee, **$0.12** cost per wear, neutral/white) vs "Rarely worn" (leather jacket, **$17.50**, pink/red alarm header).
- Then a 3-item ✓ list: Reduce impulse buys · Find meaningful pieces · Sell or donate what you're not wearing.
- **Teaches the metric before the user has data.** By the time they see their own CPW, they already know it's a scoreboard. Cheap, no AI, high retention value.

### 1.10 Style aesthetic picker — `IMG_7886`, `IMG_7887`, `IMG_7888`, `IMG_7889`
- H1: "Which styles speak to you?" · Sub: "You can select multiple."
- **2-column grid of full-body editorial photos**, label under each. Photos are gender-matched to §1.1 (male model set shown here).
- Full taxonomy observed (12+): Classic · Minimal · Streetwear · Tailored · Sporty · Old Money · Smart Casual · Y2K · Rugged · Relaxed · Creative · Edgy · Techwear · Alternative.
- Selected state = mint/aqua wash overlay on the tile (visible on "Alternative"). Next stays disabled-grey until ≥1 selection.
- **Photo-based, not chip-based.** Users cannot reliably self-describe "Old Money" but they can point at it. Our current onboarding uses text chips — this is a direct, high-impact upgrade.

### 1.11 Recommendation-breadth slider — `IMG_7890`
- H1: "How close to your style should we recommend looks?"
- Visual: black "Your style" circle inside a lilac dashed "Recommendations" halo — **the halo grows/shrinks live with the slider**. Best single piece of information design in the whole funnel.
- Slider with 3 labelled stops: Focused / **Balanced** / Broad, 9 dot ticks (so it stores a finer 0–8 value than the 3 labels suggest).
- Live explanatory caption in a grey card: "Stick to my style, but I'm open to occasional recommendations to new styles that could suit me."
- **This is an explicit exploration/exploitation dial handed to the user.** Directly maps onto our MMR diversity λ in SS-038. Enormous: it turns an engine hyperparameter into a user-legible setting, and pre-empts "your suggestions are boring" / "these aren't me" complaints in one control.

### 1.11b Slider end-states — `IMG_7891` (Focused), `IMG_7892` (Balanced), `IMG_7893` (Broad)
- **Focused**: halo is a thin ring hugging the black circle. Caption: "I know my style. Recommend only looks that match my personal taste."
- **Balanced**: halo ~1.4× the circle. Caption: "Stick to my style, but I'm open to occasional recommendations to new styles that could suit me."
- **Broad**: halo ~2.2× the circle, near-full width. Caption: "I want style guidance. Help me find my style by recommending diverse looks that suit me."
- The circle stays the same size; only the halo scales → "you don't change, your options widen." Perfect metaphor.

### 1.12 Seed-wardrobe picker ("Add suggested pieces") — `IMG_7894`
- H1: "Add suggested pieces" · Sub: "Fits is more fun when you've added a few clothes. Add some of these to start."
- 2-col grid of **catalogue stock images** (Nike Air Force 1, Basic Jeans, Adidas Campus, Basic T-Shirt, black jeans, Adidas Samba), each a card with a checkbox disc top-right; selected = white card + black border + filled ✓, unselected = grey card + hollow ring.
- **Solves cold start #2.** A brand-new user leaves onboarding with 6–10 items already in the wardrobe, which means the engine can produce outfits on day 0 without the user photographing anything. This is the single cheapest fix for "empty wardrobe = dead app".
- Note the pieces are deliberately *universal staples* + iconic sneakers, and are pre-selected by default.
- India adaptation: white kurta, dark jeans, black formal trousers, white sneakers, ethnic dupatta, plain white shirt, chappals — a "starter Indian wardrobe" set, with women's/men's variants.

### 1.13 Funnel completion — `IMG_7895`
- Progress bar 100%, animated black ✓ with sparkle particles, kicker "All done!", H1 "Time to train your personal stylist", Next.

### 1.14 Facial-feature analysis progress — `IMG_7896`
- User's actual selfie in a rounded card with a **glitchy pink/mint scan overlay** animating over it. H1 "Analyzing your facial features…", determinate progress bar + "41%".
- The pink/mint chromatic-aberration motif recurs throughout the app as the "AI is working" signature. Cheap to build (two translucent rects + blend mode), and it makes latency feel like craft.

### 1.15 Stylist training progress — `IMG_7897`
- App icon (hanger) on a lilac blob, H1 "Training your AI stylist…", progress bar 77%.
- Two separate progress screens back to back. They are **deliberately spending 20–30 s of user time** to make the personalisation feel expensive. Perceived-value theatre — and it also gives real backend jobs time to finish.

### 1.16 Style-profile reveal — `IMG_7898`
- ✓ disc + "Congratulations! Your custom profile is ready".
- **Radar/spider chart "Your style profile"** with 8 axes: Tailored · Minimal · Classic · Creative · Edgy · Sporty · Streetwear · Relaxed, lilac filled polygon.
  - This is the payoff for the whole funnel — the user *sees* a personalised artefact. Highly screenshot-able/shareable.
  - Technically: it's just the normalised weights from the style picker + inferred adjacency. Zero AI cost.
- Below: "Your AI stylist" with a human-looking avatar photo.

### 1.17 Named AI stylist persona + wardrobe recap — `IMG_7899`
- Avatar photo, name **"Ezra"** with a pencil (rename), and beneath: "Bohemian · Natural" — the stylist has its *own* style descriptors.
- "Your wardrobe so far" — masonry grid of the seed items on white, no chrome, no labels.
- **Personified stylist is a retention moat**: users form a relationship with "Ezra", not with "the app's AI". Renaming makes it theirs. Cost: zero.

### 1.18 Photo-library mining result + paywall hook — `IMG_7900`
- Continues the recap scroll, then a fanned deck of the user's *own* camera-roll photos (with the pink/mint AI wash) and the headline:
  > "We found **65 outfit photos** that can add **~195 more pieces** to your wardrobe."
  > "Import all in one tap with **Fits Pro**."
- **This is the best monetisation moment in the entire category.** They quantify the user's own latent value, then put it behind the paywall. The number is computed on-device (cheap classifier), not by an LLM.

### 1.19 Trial paywall — `IMG_7901`, `IMG_7902`
- H1 "We want you to try Fits Pro for free". Device mock showing the item-confirm screen with "**944 AI credits ⊕**" visible — seeding the credits mental model before purchase.
- "✓ No Payment Due Now" · black **Next** · "Your first week is on us." · footer links Restore purchase / Terms / Privacy.
- **Credit-based metering, not feature-gating.** Note for us: Fits sells *AI credits*, so heavy users self-fund their inference cost — exactly the model SS-029's cost ledger enables.

### 1.20 Trial-reminder screen — `IMG_7905`
- H1 "We'll send you a reminder before your free trial ends", bell + red badge "1". "✓ No Payment Due Now" → Next → "After the free trial, you can choose a monthly or yearly plan."
- Standard high-converting trial pattern (Apple's own guidance): promise the reminder, defer plan choice.

---

## PART 2 — HOME SCREEN

### 2.1 Home layout — `IMG_7907`, `IMG_7908`
Top-to-bottom structure (all sections have a `Title ›` header that opens a full page):

1. **App bar**: `⟂Fits` wordmark (left) · `Upgrade` pill · 🔔 bell · 🔍 search. Bell/search sit in a single white floating capsule with shadow.
2. **Daily suggestion carousel** (scrolled off-top here): full-bleed horizontally-paged cards with captions like *"…smart-casual for a warm Thursday"*, *"…style with black accents"*, *"…monochrome city stroll"*. Weather + day-of-week are baked into the caption text.
3. **`AI Stylist ›`** — horizontally scrolling row of large image tiles, each an *action*, not content:
   - **Rate my outfit** (two models, 👍/👎 discs overlaid)
   - **Find my colors** (model + colour wheel)
   - **Create packing list** (suitcase in a Paris hotel room)
   - **Find gaps in wardrobe** (empty rail in a closet)
   - Tiles are ~16:10 photos, radius 16, label in 17pt medium *below* the tile.
   - **This is the whole "AI stylist" surfaced as 4 concrete jobs instead of a chat box.** Users don't know what to ask an AI stylist; these tell them.
4. **`Recent outfits ›`** — empty state is a grey card with a fanned 3-card illustration (a model shot, a flat-lay, a mirror selfie — teaching all three outfit formats), copy "Your outfits will appear here.", and a black **Create outfit** pill.
5. **`Recently added items ›`** — horizontal strip of cut-out garments on white.
6. **Floating bottom tab bar**: white pill, shadow, only **Home** · `➕` (black disc, elevated) · **Profile**. Just 3 slots — everything else is reached from Home sections. Very deliberate simplicity.

**Key structural lesson:** Home is a *launcher of jobs* + *recent state*, not a feed. Each section is a horizontally scrolling row with a `›` to a full page — so Home stays short and every row is cheap to render.

### 2.2 AI Stylist chat — `IMG_7909`
- Header: `‹` back · stylist avatar + **"Ezra ⌄"** (dropdown → switch stylist persona) + "AI Stylist" subtitle · 🕘 history icon (right).
- Empty state: centred "How can I help you, **Abhinav**?" — personalised by first name.
- Above the composer: horizontally scrolling **suggestion chips**: `Make an outfit` · `Create a packing list` · `Rate my o…` (cut off).
- Composer: rounded grey field "Ask anything", `+` (attach) bottom-left, black ↑ send disc bottom-right.
- So the same 4 jobs exist both as home tiles and as chat prompts — the tiles are just pre-filled prompts into this chat. **One backend, two entry points.**

---

## PART 3 — ADDING CLOTHES (ingestion)

### 3.1 "Recently added items" full page — `IMG_7910`
- White circular `‹` back button floating top-left (consistent across the app), centred title.
- **3-column masonry of cut-out garments on pure white, no cards, no borders, no labels, no shadows.** Items are simply PNGs with transparent backgrounds laid on a white page.
- This is *the* reason Fits looks premium and our grid looks basic: **they render the garment, not a card containing a garment.** No chrome at all. Item heights vary naturally (a jacket is taller than a watch), producing a soft magazine rhythm.

### 3.2 Add clothes hub — `IMG_7911`
- Title "Add clothes". Horizontally scrolling **source chips** (grey rounded squares w/ icon + label, ~112pt):
  - **Library** (photo icon) · **Camera** · **Extract** (garment-scan icon) · **Rece…**(= *Receipt*/*Recent* — see 3.6) and more off-screen.
- Below: pill search field "Search for clothes" (they have a **product catalogue**, so users can add items without any photo at all).
- "Popular searches" bulleted list: Nike air force 1 white · Adidas Samba black · Blue jeans · Ralph Lauren polo shirt · Uggs · The North Face puffer jacket · White t-shirt · Converse Chuck Taylor · Levis 501 jeans.
- **Four ingestion paths (photo / camera / extract-from-outfit-photo / catalogue search) is the biggest single UX gap vs. StyleSense**, which currently only has camera+library. Catalogue search means adding 20 items in 3 minutes with perfect packshots and brand metadata for free.

### 3.3 Photo-quality coaching sheet — `IMG_7912`
- Bottom sheet "How to get best results": "…pick online shop images for best results or snap your clothes on a flat surface."
- Three labelled examples with emoji verdict badges: 😍 (green) **Shop screenshot** · 🙂 (yellow) **Flat surface** · 🙁 (red) **Hanging with creases**.
- Black **"Got it 👌"** CTA.
- Cheap, and it materially raises segmentation quality — fewer bad cut-outs means fewer support complaints and lower re-processing cost.

### 3.4 Background-removal progress toast — `IMG_7913`
- Dark charcoal floating toast pinned above the tab bar: thumbnail + "**Removing background…**" / "Do not close the app" / "**0/1 completed**" + ✕ dismiss.
- **Non-blocking, batch-aware, dismissible.** The user keeps browsing/adding while processing runs. Our current flow has a blocking `ProcessingStep`.

### 3.5 Item detail / post-ingest editor — `IMG_7914`
- Large image at top with a `›` arrow on the right edge (paged: original vs. processed vs. enhanced).
- **"Make this a packshot?" → purple gradient pill "✨ Enhance image" / "No thanks"** (purple = paid AI action throughout the app).
  - *Enhance image* = generative re-render of a messy user photo into a clean e-commerce packshot. This is the "enhancing clothes image" feature you flagged, and it's an **AI-credit sink** — a monetised, opt-in, per-item action.
- Action row: ♡ (favourite) · 💬 (comment/note) · **Edit** (grey pill with image icon).
- Editable name with pencil: "E.T.A. shirt ✏️" — brand+type auto-parsed from the image/label.
- Attribute rows below (each a tappable row with a `›`): category **Shirt** (with garment-type icon) · colour · **Add tags** · … (continues in later screenshots).

### 3.6 Category picker — `IMG_7917`, `IMG_7918`, `IMG_7919`
Bottom sheet, searchable ("Search category"), **line-icon per garment type**, grouped by section header. Full taxonomy observed:
- **Tops**: Jacket · Coat · Blazer · Suit · Vest (+ more above the scroll: T-shirt, Shirt, Sweater, Hoodie, etc.)
- **Bottoms**: Jeans · Pants · Leggings · Sweatpants · Shorts · Skirt · Mini skirt · Maxi skirt
- **Full Body**: Mini Dress · Dress · Maxi Dress · Jumpsuit
- **Underwear & More**: Swimwear · Bra · Underwear · Socks · Tights · Nightwear
- **Shoes**: Sneaker · Boot · Ankle Boot · Heels · Sandal · Loafer · Pumps · Lace-up shoe · Flat shoe · Outdoor shoe · Sport shoe · Slippers
- **Accessories**: (below the fold)

**Observations that matter for us:**
1. ~50+ leaf garment types in 6 groups — far more granular than a 20-value enum. We already built `garment_types` registry (SS-034) — this validates that direction and gives us the target granularity.
2. **Every leaf type has a hand-drawn line icon.** That icon set is doing enormous work: it makes an otherwise boring list feel designed, and it doubles as the placeholder when an item has no image.
3. Shoes are first-class leaf types inside the same picker, not a separate module (contrast our SS-024 footwear module).
4. India gap: no Kurta / Kurti / Saree / Salwar / Lehenga / Sherwani / Dupatta / Dhoti / Palazzo / Anarkali / Blouse / Nehru jacket / Churidar. **This is our taxonomy moat** — see `05-GAP-ANALYSIS.md`.

### 3.7 Accessories taxonomy — `IMG_7920`, `IMG_7921`
- **Accessories**: Bag · Backpack · Sunglasses · Eyeglasses · Hat · Cap · Beanie · Hair accessory · Beret · **Headscarf** · Watch · Necklace · Earring · Ring · Bracelet · Other Jewelry · Belt · Scarf · Gloves · Tie · Bowtie · Miscellaneous.
- Note **Headscarf** is included with a hijab-style icon — deliberate inclusivity, and directly relevant to our market.
- Every leaf has an icon. Total taxonomy ≈ **70 leaf types**.

### 3.8 Colour picker — `IMG_7922`
- Bottom sheet, 6-column grid of **circular swatches**, ~30 colours: black, brown, tan/beige, grey, light grey, white, cream, light blue, blue, navy, teal, aqua, mint, green, olive, yellow, orange, red, maroon, pink, lilac, magenta, silver(gradient), gold/khaki.
- **Last row is patterns, not colours**: leopard, tiger, zebra, camo (green), camo (b/w) — rendered as texture-filled circles — plus a **rainbow-wheel swatch = custom colour picker**.
- Selected swatch gets a ring. Footer: white "Clear selection" pill (left) + black "Done" pill (right).
- Mixing colour + pattern into one control is smart: users think "what colour is it?" and "leopard" is a valid answer.

### 3.9 Material/fabric picker — `IMG_7923`, `IMG_7924`, `IMG_7925`, `IMG_7926`
- Searchable list, **each material has a real photographic texture swatch** (rounded square) — enormously more legible than text.
- Full list (~35): Cotton · Polyester · Nylon · Denim · Wool · Silk · Linen · Spandex · Acrylic · Fur · Rayon · Cashmere · Leather · Velvet · Chiffon · Tweed · Corduroy · Flannel · Fleece · Satin · Lace · Organza · Tulle · Sequin · Shearling · Down Feather · Mohair · Angora · Alpaca · Lyocell · Cupro · Metal · Other.
- Single-select (radio), black ✓ disc when chosen. Footer Clear selection / Done.
- **We already have SS-036 pattern & fabric registries** — this is the UI target for it. The texture swatches are the differentiator; a plain list of fabric names is forgettable.

### 3.10 Item attribute model (from the detail screen behind the sheets) — `IMG_7927`
The item detail rows, in order, form Fits' full per-item data model:
| Row | Icon | Example value |
|---|---|---|
| Category | garment line icon | `Shirt` |
| Brand | ⓘ badge | `INTL d.e.t.a.i.l.s` |
| Tags | 🏷 | `Add tags` |
| Colour | 💧 droplet | swatch chip |
| Material | 🧵 spool | `Cotton` + texture chip |
| **Season** | ☀/❄ | `🌱 Spring · ☀️ Summer` (multi-select sheet: Spring/Summer/Fall/Winter with emoji) |
| **Links** | 🔗 | `Add links` (product URL / where to rebuy) |
| …below | | price, size, notes, purchase date (seen in later screens) |

- The **Season** multi-select with emoji is a 4-row sheet — trivial to build, and it's a first-class filter + a styling-engine input.
- **Links** is a quietly powerful field: it turns the wardrobe into a re-purchase/affiliate surface.

### 3.11 Enhance-image paywall modal — `IMG_7928`
- Full-screen white, ✕ top-right, the raw photo large, then purple pill **"✨ Enhance image"**, caption "**Costs 1 AI credit**", balance readout "**1 AI credits ⊕**" (tap ⊕ = buy more), and a bordered pill **"✏️ Add custom instructions"**.
- **Per-action credit pricing shown at the point of use** — no surprise. `Add custom instructions` lets power users direct the generation (e.g. "on a white background, front view").
- Copy this pattern wholesale for any generative feature we add: *action → credit cost → balance → optional prompt*.

---

## PART 4 — PROFILE / WARDROBE (the "closet")

### 4.1 Profile header — `IMG_7929`
- Handle `abhiabhinav98` as the page title (bold, 28pt). Right: floating white capsule holding **📅 calendar** · **◔ insights/pie** · **☰ menu**.
- Avatar (circle, with a `+` badge to add a story/photo) · display name · **0 Followers · 0 Following** (social from day 1).
- Two grey pills: **Edit profile** · **Share profile**.
- Segmented tabs: **Clothes** | **Outfits** | **Collections** (underline indicator).
- **Profile = wardrobe.** There is no separate "wardrobe tab" — your closet *is* your public profile. That single decision is what makes the social layer feel natural rather than bolted on.

### 4.2 Clothes tab — category chip rail — `IMG_7929`–`IMG_7933`
- Horizontally scrolling chip rail: `All` · **Tops** · Bottoms · Shoes · Outerwear · **Full Body** · **Accessories** · Other. Active chip = black pill w/ white text; inactive = plain text, no chrome.
- Right of the rail, pinned: **filter icon** (grey disc) and **⋯ overflow** (grey disc).
- Grid: 3-column, cut-out garments on white, **no cards** (as in 3.1).
- Empty state per category (`IMG_7932`): a beautifully composed *illustration of real garments* (bag, trench, blazer, loafer) + "No clothes in this category" / "Add more clothes to see them here." / black **Add clothes** pill. Even the empty state is merchandised.

### 4.3 Filters sheet — `IMG_7934`, `IMG_7935` (THE most copyable screen for us)
Bottom sheet titled **Filters**, with `Clear filters` (grey pill) / `Done` (black pill) pinned at the bottom. Sections:

| Section | Control |
|---|---|
| **Colors** | horizontal rail of circular swatches (multi-select) |
| **Categories** | `Select categories` pill → opens the category sheet |
| **Season** | 4 bordered pills with emoji: 🌱 Spring · ☀️ Summer · 🍂 Fall · ❄️ Winter |
| **Brands** | `Select brands` pill |
| **Materials** | `Select materials` pill |
| **Name** | `Search for name` free-text |
| **Usage** | 3 pills: **All** · **Not used in outfits** · **Used in outfits** |
| **Sort items by** | pills: Custom · **Date added** · Categories · Colors · Most… (worn) |
| **Group items by** | pills: **None** · Tags · Categories · Season · Colors |

**Why this matters:** *Usage* + *Sort by most worn* + *Group by* turn a static grid into an analysis tool. "Not used in outfits" is exactly the "pairs you have never tried / not yet worn" surface — implemented as a **filter**, not a separate AI feature. Zero marginal cost, high perceived intelligence.

---

## PART 5 — OUTFIT CREATION (Collage / Dressing Room / AI Try-On)

### 5.1 Outfits tab empty state — `IMG_7937`
- Fanned 3-card illustration again (model shot / flat-lay collage / mirror selfie).
- "Start adding outfits" · "Your outfits will appear here. **Create collages or add outfit selfies.**" · black **Create outfit**.
- Copy explicitly teaches the two content types.

### 5.2 Outfit builder — item picking step — `IMG_7938`
Header row: `‹` back · **`🌦 25 / 23 °C`** (live weather, high/low, condition emoji) · **`📅 Today`** pill (the outfit is being created *for a date* — this is how the planner/calendar is fed).

Two big grey action cards side by side:
- **`👤 Selfie`** — attach a mirror-selfie as the outfit image
- **`✨ Suggestions`** — let the engine propose combinations from the current selection

Then the standard category chip rail (`All`/Tops/Bottoms/Shoes/Outerwear/Full…) + filter disc, and a 3-col grid of cut-outs each with a **hollow selection ring top-right** (filled black ✓ when selected).

Pinned bottom sheet:
- "**3 selected**" + a horizontal strip of chosen item thumbnails, each in a white card with an **✕ badge** to remove
- Left: **`Collage ⌃⌄`** — a *mode selector* pill
- Right: black **`Next →`**

**Everything about this screen is worth copying**: weather in the header, date binding, live selection tray with remove-badges, and mode selection surfaced as a pill rather than a hidden setting.

### 5.3 Mode selector — `IMG_7939`
Sheet: "**Select how to create outfits**", 3 photo tiles:
| Mode | What it is | Cost |
|---|---|---|
| **Collage** (selected, black border + ✓) | Free-canvas flat-lay: cut-outs arranged on white, drag/scale/rotate. Illustration shows jeans + shirt + bag + sunglasses + sneakers. | free |
| **Dressing Room** | Cut-outs **layered onto a mannequin/avatar body**, tap-and-swipe to swap each slot. Illustration shows a headless avatar with a finger swiping. | free |
| **AI Try-On** | Generative render of the outfit **on a photorealistic model matched to the user's selfie**. | AI credits |

**This 3-tier ladder is the single most important product insight in this teardown.**
Free deterministic composition (Collage) → free semi-structured composition on a body (Dressing Room) → paid generative (AI Try-On). The first two carry ~all of the daily engagement at **zero marginal cost**; the third is the monetised delight moment. Most of the "wow" users attribute to "AI" is actually 5.4–5.6, which is pure client-side compositing.

### 5.4 Dressing Room — "How it works" coach marks — `IMG_7940`, `IMG_7941`, `IMG_7942`
A 3-page sheet over the live canvas, dot pager, Next / Next / **Let's go**:

1. **"Tap and swipe to switch clothes"** — "Select a clothing item and swipe through your closet to experiment with outfits."
   - Canvas shows a headless avatar with hair, wearing a black sweater + white jeans + Vans. `↔` icon.
   - Under the canvas, a **horizontally scrolling type rail**: `…Shirt · Polo · Top · Shirt · Blouse` + a settings disc — i.e. swiping horizontally on a *slot* cycles through every wardrobe item of that garment type.
2. **"Adjust size"** — "Press the reposition button to fit clothes on the body. **Positions are saved for the future.**" `✥` icon.
   - Selecting a garment reveals a vertical floating control stack next to it: **✓ (confirm)** · **✥ (reposition/scale)** · **🗑 (delete)**.
   - *Positions are saved per item* — so the fiddly manual alignment is a one-time cost per garment, and every future outfit reuses it. That's the trick that makes a cut-out mannequin look good without any AI.
3. **"Arrange layers"** — "You can reorder layers, for example to **tuck in a top by moving the pants up**." 👕 icon.
   - Right-edge vertical toolbar: **👤 (avatar/body settings)** · **👕 (layers)** · **🔀 (shuffle/randomise outfit)**.

### 5.5 Dressing Room — live canvas — `IMG_7943`
- Headless light-grey **mannequin with a hairstyle** (hair is a separate selectable asset — this is the "hairstyles" feature you noted).
- Garments composited in place: grey sweatshirt, light-wash jeans, Nike Dunks. Proportions look right because of per-item saved transforms (5.4.2).
- Right toolbar: 👤 body · 👕 layers · 🔀 shuffle.
- Bottom: grey **"Switch to…"** pill (jump to Collage/AI Try-On) + black **Next**.

**Technical read (important for our costing):**
The Dressing Room is a **z-ordered stack of transparent PNGs on a mannequin sprite**, with per-item `{x, y, scale, rotation, z}` persisted. No ML at render time. The 🔀 shuffle button = randomly re-pick one item per slot from the filtered wardrobe = a *free* outfit generator that feels like AI. This is the answer to "how do they suggest outfits without leveraging AI upfront" — see `08-CHEAP-SUGGESTION-ENGINE.md`.

### 5.6 Slot swap interaction — `IMG_7944`
- Tapping the bottoms slot opens a **bottom drawer scoped to that slot's garment family**: chip rail `All · **Jeans** · Pants · Leggings · Sweatpants · S…` + filter disc, and a grid of only that family's items.
- The mannequin above **live-previews** the candidate as you scrub (dark jeans shown mid-swap, next candidate peeking at the right edge).
- A floating black **✓** disc confirms.
- Swiping horizontally *on the mannequin's garment itself* cycles candidates without opening the drawer.

### 5.7 Hairstyle picker — `IMG_7946`
- Sheet with a 3-column grid of ~15+ **hairstyle PNGs** (long wavy, bob, straight long, curly long, short pixie, side-part, afro, tight curls, half-up, ponytail, bun, …) — and a **hair-colour rail** at the bottom: black, near-black, dark brown, brown, medium brown, light brown, dark blonde, blonde, platinum, ginger, … (~12 swatches).
- Cheap avatar personalisation with a big identity payoff. Two asset sets (style × colour) and it covers most users.
- **India adaptation:** add long braid, oiled centre-part, bun with gajra, turban/pagdi, hijab, and darker-hair-first ordering.

### 5.8 Body type / avatar picker — `IMG_7947`, `IMG_7948`
- Sheet with sections **Female** / **Male** (scrollable), each a 3-column grid of grey body silhouettes.
- Grid axes: **size** (S / M / L / XL …) × **proportion** (default / **Short legs** / **Long legs**).
- Labels are literally `S`, `S Short legs`, `S Long legs`, `M`, `M Short legs`, `M Long legs`, … — a 2-D matrix, ~12–18 bodies per gender.
- Selected = **yellow/amber 2px rounded border** (the only place amber is used).
- **This is the "inclusive body type analysis" feature.** Note what it is *not*: no measurements, no photo analysis, no ML. It's a **finite sprite library indexed by (gender, size, leg proportion)**. The garment transforms from 5.4.2 are stored per body so the same shirt sits correctly on every body.
- It also silently gives them a body-shape signal for the styling engine at zero inference cost.

### 5.9 Layers panel — `IMG_7949`, `IMG_7950`, `IMG_7951`
Bottom sheet titled **Clothes** / "Select or reorder layers", `+` disc top-right (add another garment).
- One row per garment: thumbnail · name (`Sneaker`, `Sweater`, `T-Shirt`, `Jeans`) · 🗑 delete.
- The **selected row expands to show 4 small line-icon buttons** = **layer-depth presets**: `outerwear-most-outer` · `mid` · `base` · `innermost` (the icons are blazer / long-sleeve / tee / sleeve). Tapping one moves that garment in the z-stack.
- The canvas gives **live feedback**: the mannequin renders the sweater and the tee half-and-half (left half sweater, right half tee) so you can see exactly which is on top.
- Rows are drag-reorderable (that's the primary z-order control); the icon buttons are the shortcut.
- **The half-and-half live preview is a genuinely clever affordance** — it makes an abstract z-index concept physically visible.

### 5.10 Per-item transform toolbar — `IMG_7952`
Selecting an item on the canvas reveals a right-edge vertical stack of circular buttons:
| Icon | Action |
|---|---|
| **✓** (black, active) | confirm/deselect |
| **✥** | move / scale / rotate handle mode |
| **🔓** | lock/unlock position (prevents accidental drags) |
| **🔀** | shuffle *this slot only* — swap for a random alternative of the same type |
| **🗑** | remove from outfit |
And at the bottom, the slot-scoped drawer (`All · Sneakers · Boots · Ankle Boots · Heels · S…`).
- Accessories are placed freely (the Apple Watch is floating at the wrist).
- **Per-slot shuffle** is the micro-version of the whole-outfit shuffle — "give me a different shoe" without leaving the canvas. Extremely cheap, extremely engaging.

### 5.11 Save-outfit sheet — `IMG_7953`, `IMG_7954`
Title "New outfit". Rendered outfit card at top (white card, radius 16, shadow), then:
| Field | Control | Value |
|---|---|---|
| Caption | free text | "Add a caption…" |
| **Date** | row → date picker | `Today ›` |
| **Add to OOTD story** | purple toggle (ON by default) | "Show this outfit to your followers for **24h** as your fit of the day." |
| **Occasion** | row → sheet | `👔 Work ›` |
| **Visibility** | row → sheet | `Everyone ›` |
| **Save to** | row → sheet | `Main wardrobe ›` |
Black **Save outfit** CTA.

- **The 24h OOTD story is the retention loop**: the same artefact that logs a wear also becomes ephemeral social content. One action, three jobs (wear log + planner entry + social post).
- Purple is used for the toggle → purple = "premium/AI/social boost" throughout.

### 5.12 Occasion taxonomy — `IMG_7955`
Sheet, emoji + label, single-select: 👔 **Work** · 🧢 Casual · 🏠 Home · 🎒 School · 🥰 Date · 🥂 Party · 🎽 Sports · 🎩 Formal event · 💍 Wedding · (more below).
- ~10 occasions, generic-Western. **Our occasion registry (SS-025/SS-007) is already richer and India-aware — a genuine advantage.** Their list has no Festival / Puja / Mehendi / Sangeet / Diwali / Office-casual-India / Temple.

### 5.13 Visibility model — `IMG_7956`
Three options with icons + explanatory sub-copy:
- **👥 Everyone** — "Visible in your profile and can be discovered by others."
- **🔒 Only you** — "Visible in your profile but only to you. Cannot be discovered by others."
- **🚫👁 Hidden** — "Only visible in the planner and only to you. Not visible in your profile. **Still counts towards your wear stats.**"
- That third state is thoughtful: it separates *analytics participation* from *display*. Users log everything (good data for the engine) without curating publicly.

### 5.14 Save-to / Collections — `IMG_7957`, `IMG_7959`, `IMG_7960`
- Sheet: **Main wardrobe** (default, ✓) + **Collections** list (`My Wishlist ♡ Wishlist`).
- Collections tab (`IMG_7959`): chip rail `All · Wishlists · Packing · Custom`; grid of collection cards (rounded grey tile with a `👕+` glyph, name, and a type sub-label). Black **Create new collection** CTA pinned near the bottom.
- Collection detail (`IMG_7960`): title + "0 items", tabs **Clothes | Outfits**, merchandised empty state, black **+ Add items**.
- **Three collection types** — `Wishlist` (items you don't own yet → shopping), `Packing` (trip lists), `Custom`. One data model, three product surfaces. The **packing list AI feature just writes into a Packing collection** — the AI output lands in an existing, browsable container rather than a dead chat message.

### 5.15 Saving state — `IMG_7958`
- Simple centred spinner + "Saving…" under the outfit card. Rendering + upload of the composed image happens here.

### 5.16 Collection item-adding flow — `IMG_7961`–`IMG_7968`
- `+ Add items` → sheet: **👕 Add clothes ›** / **👔 Add outfits ›** (white cards on grey).
- Then a second sheet: **👕 Add from wardrobe ›** / **➕ Add new ›**, plus a radio pair:
  - ⦿ **To my wardrobe and this collection**
  - ○ **Only to this collection**
  - This is how a **Wishlist** works — items you don't own go *only* to the collection and never pollute wardrobe stats. Elegant single-model solution to "wishlist vs. owned".
- Multi-select picker: full-screen, `Cancel` / `Done` text buttons in the nav bar, 3-col grid with ring/✓ badges (`IMG_7963`, `IMG_7967`).
- Populated collection (`IMG_7964`, `IMG_7968`): "Tesss · 3 items", Clothes|Outfits tabs, chip rails — Clothes rail is by category, **Outfits rail is by occasion** (`All · Work · Casual · Home · School · Date · P…`).
- **Outfits are filterable by occasion everywhere** — the occasion tag set at save time pays off in browse, planner, and suggestions.

### 5.17 Collection overflow — `IMG_7969`
Sheet: ✓ **Select items** · ✏️ **Rename collection** · 🗑 **Delete collection**. (Grey icon discs + label rows — the app's standard action sheet.)

---

## PART 6 — SETTINGS & INSIGHTS

### 6.1 Settings — `IMG_7970`, `IMG_7971`
Two grey cards at top: ⭐ **Rate the app** · ⬆️ **Share the app**. Then grouped rows:

**Your wardrobe**
- ◔ **Insights ›**
- 🏷 **Manage tags ›**
- ⊕ **Custom brands ›**  ← users can define brands not in the catalogue
- 🗄 **Archive ›**
- $ **Currency** — `INR ›`  ← **Fits already supports INR. They are live-ready for India today.**
- ☁️↓ **Re-sync wardrobe ›**

**Community**
- 👥 **Styled together ›**  ← social/collab feature
- 💡 **Feature requests ›**  ← public roadmap board; cheap community moat
- 🚫 **Blocked users ›**

**Fits**
- ⭐ **Upgrade to Pro ›** · 👤 Account · 🌐 **Language ›** · 💬 Contact us · 🪙 **AI credits — `1 ›`** · 📱 **App starts in — `Home ›`** · 🌙 **Display — `Light ›`**

**Follow us**: TikTok · Instagram · X · Pinterest.

Notable: *App starts in* (user chooses the launch tab), *Language*, *Currency*, and a *public feature-request board* — all cheap trust/retention signals.

### 6.2 Insights — Composition — `IMG_7972`
- Title "Insights". **Dimension chip rail**: `Categories` (free, black active) · `Colors 🌟` · `Brands 🌟` · `Season 🌟` · `Tags 🌟` — the star badge marks Pro-gated dimensions.
- **Donut chart** with a centred stat: "**16 clothes** in 8 categories". Pastel palette (yellow, lilac, mint, blush, periwinkle, aqua, pink, steel).
- Below: category chip rail (All/Tops/Bottoms/…) to scope the chart.
- **Two-column legend** with colour dot · label · **count** · **percentage**: `T-Shirts 3 19%` · `Shirts 3 19%` · `Jeans 3 19%` · `Sweaters 2 13%` · `Sneakers 2 13%` · `Long Sleeves 1 6%` · `Jackets 1 6%` · `Watches 1 6%`.

### 6.3 Insights — Money & usage — `IMG_7973`, `IMG_7974`, `IMG_7975`
Vertical stack of metric blocks, each with a title and a `🌟 Pro` badge if gated:
| Block | Free/Pro | Rendering |
|---|---|---|
| **Wardrobe value** / **Average item price** | free | two-up stat tile, **₹0.00** (INR formatting confirmed) |
| **Highest price** | Pro | locked card: "Upgrade to Pro 🔒 / Unlock all insights with Fits Pro / [Upgrade]" (purple pill) |
| **Cost per wear** | Pro | locked card |
| **Wardrobe usage** | **free** | headline "**31%**", full-width progress bar, category chip rail, caption "You're using 31% of your wardrobe" |
| **Worn last month** | Pro | locked |
| **Worn overall** | Pro | locked |
| **Never worn** | Pro | locked |
| **Recently added** | free | horizontal strip of item cards |

**Monetisation lesson:** the *free* insight is the one that creates anxiety (**"you're using 31% of your wardrobe"**), and every insight that *resolves* that anxiety (which items? never worn? cost per wear?) is paid. That is a textbook tension-then-relief paywall, and it's built entirely on `wear_count` data the app already has. Zero AI.

### 6.4 Archive — `IMG_7977`
- Tabs **Clothes | Outfits**, emoji empty state 🗄, "No archived items" / "You can archive items to keep them for later. **They will be hidden from your main wardrobe view.**"
- Archive ≠ delete. Seasonal storage, items lent out, things you're about to sell. Keeps stats honest without destroying history.

### 6.5 Display mode — `IMG_7978`
Sheet: ☀️/🌙 **System (automatic)** "Use the color mode from your device settings" · ☀️ **Light** "Always use light mode" · 🌙 **Dark** "Always use dark mode". Radio list with sub-copy per option.

---

## PART 7 — HOME SCREEN (dark mode) — THE SUGGESTION SURFACES

The rest of the Home feed, captured in dark mode. **This is the most commercially important part of the teardown** — these are the modules that make the app feel like it has a stylist, and none of them require a per-request LLM call.

### 7.1 `Pairs you've never tried ›` — `IMG_7979`, `IMG_7980`, `IMG_7981`
- Horizontal carousel of **Dressing-Room-rendered outfits on the user's mannequin** against a mid-grey card, each with a **one-line caption in the app's editorial voice**:
  - *"Cozy evening casual with a clean finish"*
  - *"Edgy urban layer for cooler summer nights"*
  - *"Refined boh… for a relaxed…"*
  - *"Minimalist evening look for cool summer nights"*
- Full page (`IMG_7980`): 2-column grid where uncomputed tiles show a **blurred placeholder + "Creating outfit…"** — they generate lazily and progressively, so the page is instantly interactive.
- Free tier shows **1 outfit**, then a white pill: **"🔒 Upgrade for 29 more outfits"** (`IMG_7981`).
- **Mechanism (inferred, high confidence): combinatorial generation over the wardrobe, filtered by rules, ranked, then narrated.** The item-pair novelty check (`has this (top,bottom) pair ever appeared in a saved outfit?`) is a SQL query. The caption is the only place an LLM could be involved, and even that is cheaply cached per outfit — note the app pre-computes 30 and paywalls 29, i.e. **generation happens in one batch, not per view**.
- The name is the product: *"Pairs you've never tried"* frames combinatorics as discovery.

### 7.2 `Not yet worn ›` — `IMG_7979`, `IMG_7982`
- Horizontal strip → full page: plain 3-col grid of items with `wear_count = 0`. No chrome, no explanation needed.
- **A single `WHERE wear_count = 0` query, shipped as a headline feature.**

### 7.3 `AI Try On backgrounds ›` — `IMG_7979`
- "Create outfit photos at various locations." Horizontal cards of location photos (a bar interior, a European street, a **NYC subway car**), each stamped with a small **`AI`** badge.
- Generative try-on *with scene control* — the monetised tier. Location presets remove prompt-writing from the user.

### 7.4 `Outfit frames ›` — `IMG_7983`, `IMG_7984`, `IMG_7985`
- "Create beautiful images for social platforms." Carousel of **template cards**:
  1. **"OUTFIT of the DAY"** — serif editorial header, flat-lay of items on white, footer `@handle on Fits`.
  2. **Credits template** — outfit on a cream mat, caption listing every piece: *"Basic Jeans / Basic T-Shirt / Basic Sweater / Nike Dunk Low (Nike) / Apple Watch (Apple)"*, footer `@handle on Fits`.
  3. **Product-list template** — a right-hand column of item cards each with product name + brand (`Uniqlo`, `Arket`, `New Balance`, `Kapten & Son`, `47 Brand`), profile chip + Follow button.
- Frame detail view (`IMG_7984`, `IMG_7985`): full-bleed frame preview, **`🔄 Replace outfit`** pill, then a native-style share row: **Save image · Instagram · Messages · WhatsApp · More**.
- **This is the growth engine.** Every exported frame carries `@handle on Fits` — free, attributed, aesthetically desirable distribution. WhatsApp being a first-class share target matters enormously for India.
- Templates are static layouts + the already-composed outfit PNG. Cost: zero.

### 7.5 Editorial rails — `IMG_7983`
- `Easy Summer Tailoring ›` — a *curated theme* rail of mannequin-rendered outfits **built from the user's own wardrobe**, each captioned (*"Relaxed summer day in textured neutrals"*, *"Clean casual city look with simple lines"*, *"Polished monochrom… summer eve…"*).
- Below it: `Ideas for your newest pieces ›`.
- **Editorial themes are just parameterised queries over the rules engine** (season=summer + formality=smart-casual + palette=neutral). The magazine framing is what makes it feel human.

### 7.6 Outfit frame templates in detail — `IMG_7986`, `IMG_7987`
- **Template C (product grid)**: left column of item cards (image + `Basic Jeans` / `Basic T-Shirt` / `Basic Sweater` / `Nike Dunk Low` *Nike* / `Apple Watch` *Apple*), right column the outfit render, footer block with the user's **avatar, `@handle`, display name, Fits app icon and "Follow me on Fits"**.
- **Template D (film-strip)**: black-bordered frame, outfit inside, black footer bar with the app icon + "**Outfit of the day** / @handle on Fits".
- Every template is an acquisition asset. The item list doubles as free brand marketing (which is how affiliate revenue eventually plugs in).

### 7.7 Theme rail full pages — `IMG_7989` (`Easy Summer Tailoring`), `IMG_7990` (`Ideas for your newest pieces`)
- 2-col grid of captioned mannequin outfits. **Free users get 3; the 4th tile is blurred with a 🔒 lock disc.** Blur-tease rather than absence — the user sees the shape of what they're missing.
- Captions from `Ideas for your newest pieces`: *"Bohemian summer ease with textured neutrals"*, *"Relaxed evening look for cool summer nights"*, *"Rela… earthy textures"*.
- Note *Ideas for your newest pieces* = "outfits containing an item added in the last N days" — again a query, framed as a feature. **This directly answers "what do I do with the thing I just bought?", one of the highest-intent moments in the category.**

### 7.8 AI Try-On backgrounds detail — `IMG_7991`, `IMG_7992`
- Carousel of generated photos with an `AI` chip top-right: a studio shot, a **festive restaurant interior**, a street scene.
- Caption: "Select clothes and create an **AI photo shoot at real locations**." White **Generate image** CTA.
- Positioned as a *photo shoot*, not a "try-on" — the aspiration is content, not fit accuracy. Smart: it removes the accuracy expectation that kills most virtual try-on features.

### 7.9 `Rate my outfit` entry — `IMG_7993`
Sheet "**Select outfit to rate**": 📷 **Camera** · 🖼 **Library** · 👔 **Outfits** (pick a saved one).
- Three input paths, including rating an outfit you built in-app. The wardrobe becomes the input to the AI feature, not a separate upload.

### 7.10 `Find my colors` / Colour analysis — `IMG_7994`
Title **"Find your color palette"**. Top: a row of 5 result swatches (camel, terracotta, cream, slate blue, taupe). Hero: a model with **floating colour circles beside her face** (the visual language of seasonal colour analysis). Headline "**Discover your ideal colors**".
Inputs, as rows:
| Row | Value |
|---|---|
| **Selfie photo** (thumbnail) | "Should show your face. Can be different from your public profile picture." |
| **Body type** (silhouette icon) | `›` |
| **Season** | `All year ›` |
| **Color temperature** | `Automatic ›` |
White **Generate color palette** CTA.

- This is the "**body and facial analysis + colour theory**" feature. Note the structure: it's a **form with 4 inputs producing a palette artefact**, not a chat. The palette then presumably feeds the styling engine as a colour preference vector.
- `Color temperature: Automatic` (vs. manual warm/cool) is the escape hatch for when the auto-detection is wrong on darker skin tones — worth copying, since seasonal colour analysis is notoriously calibrated on light skin. **For India this must be explicitly tuned; it's a credibility make-or-break.**

### 7.11 Colour-temperature override — `IMG_7995`
Sheet: 🤍 **Automatic (what's best for me)** ✓ · 💙 **Cool** · 🧡 **Warm**. Emoji-as-icon again.

### 7.12 Colour analysis progress — `IMG_7996`, `IMG_7997`
- Card with the user's circular selfie and a **3-step checklist that ticks sequentially**:
  1. Analyzing facial features
  2. Detect matching colors
  3. Fine-tune for your body type
- Spinner on the active step → white ✓ discs when done. **Named steps make the wait feel like work being done** and simultaneously teach the user what the feature considers. Far better than a bare progress bar.

### 7.13 Colour palette result — `IMG_7998`, `IMG_7999`, `IMG_8001`
A scrollable result page — this is a **template for how any AI output should be presented**:

1. **Palette card** (cream, radius 20): kicker `COLOR PALETTE`, **named palette "Urban Classic"**, 3×3 grid of colour swatches (charcoal, slate, steel blue, pale grey, terracotta, taupe, green, amber, cobalt), footer with the **Fits mark + `@handle`**, and ⬇️ / ⬆️ (download / share) circular buttons in the corner. → **shareable artefact**, branded.
2. **"See how this palette looks on you"** — 3 generated portraits of the user in palette colours, purple **`✨ Generate image`** CTA, "**Costs 1 AI credit**", balance `1 AI credits ⊕`. → the paid upsell sits *inside* the free result.
3. **"Items that match this palette"** — `🌟 Pro` locked card.
4. **"Wardrobe color matching — 75%"** — purple progress bar, category chip rail, caption "**75% of your wardrobe matches this palette**". → free, and immediately actionable/anxiety-inducing.
5. **"Color theory"** — a ~120-word prose explanation, e.g.:
   > *"This 'Urban Classic' palette combines neutral darks and grays with warm and cool accent colors that complement your **medium skin tone and dark hair**. The deep charcoal and steel blues enhance your mature and confident appearance, while the warm terracotta and earthy browns bring warmth and approachability… suits your average male body type and all-year wearability."*
   - Notice it explicitly references **medium skin tone and dark hair** — the model is genuinely reading the selfie, and the copy is inclusive by construction.
   - **One LLM call, cached forever.** The palette is generated once per user and reused across every surface.

**Pattern to copy verbatim: `named artefact → shareable branded card → free % metric about YOUR wardrobe → paid visualisation → prose rationale`.**

### 7.14 Home (dark) with recent outfits — `IMG_8002`
- Same layout; now `Recent outfits ›` has content and gains a **`⇅` sort control** in the section header.
- The daily suggestion carousel captions confirm weather+day binding: *"Crisp bohemian smart-casual for a **warm Thursday**"*, *"Relaxed earthy street style with black accents"*, *"Sophistic… monochro… city stroll"*.

### 7.15 `Make an outfit` — the occasion intake form — `IMG_8003`
Opened from the AI Stylist. A **card-shaped form**, not a chat turn:
- H1 "**What are you getting dressed for?**"
- Free-text field "Describe the occasion…"
- **`Suggested`** list of occasion rows (👔 Work · 🧢 Casual · 🏠 Home · 🎒 School · 🥰 Date · …)
- Row **`When` — `Now`**
- Row **`More info` — `Add details`**
- White CTA **`✨ Make outfits`**

**This is the single most important interaction-design lesson for our SS-023 flow:** even inside a chat-branded feature, the actual request is collected with a **structured form** (occasion + time + optional free text). That guarantees the backend gets clean parameters, keeps prompts short and cheap, and removes the blank-page problem. The "AI stylist" chrome is presentation; the payload is a form.

### 7.16 `Make outfits` — the full request schema — `IMG_8004`–`IMG_8011`
After picking an occasion, the form collapses to two summary rows plus an optional-details card:

`Occasion — Casual` · `When — Now` · card **"Want to give me more info?"** / *All optional*:

| Field | Icon | Control | Observed values |
|---|---|---|---|
| **Style specific items** | 👕 | `+` → wardrobe multi-picker | opens a sheet with a **wardrobe/collection switcher** (`Main wardrobe ⌄` → `Tesss (Custom)`, `My Wishlist (Wishlist)`), category chip rail, filter, a dashed **`+` "add new item"** tile, ring/✓ selection, "0 selected" + **Done** (`IMG_8006`, `IMG_8007`). **`Select multiple`** pill for cross-collection picking. |
| **Vibe** | 〰️ | `+` → multi-select sheet | 💪 Confident · 🧸 Cozy · ⚪ Minimalist · 🖤 Edgy · 🌹 Romantic · 🎈 Playful · ✨ Polished · 🌿 Relaxed (`IMG_8008`) |
| **Who you'll be with** | 👥 | `+` → single-select sheet | A date · Friends · Family · Coworkers · My partner · Alone (`IMG_8009`) |
| **Custom instructions** | 📝 | `+` → textarea | "Anything else your stylist should know…" + `Clear` / `Done` (`IMG_8010`) |

White CTA **`✨ Make outfits`**.

**This is the complete suggestion request schema, and it is worth adopting almost verbatim:**
```
{ occasion, when, seed_items[], vibe[], company, free_text }
```
- **`Style specific items`** = "build around this piece" — the single most requested styling job ("I want to wear this new kurta, what goes with it?") and it costs nothing but a pre-filter.
- **`Vibe`** is a *mood* axis orthogonal to *occasion*, which is how humans actually think ("work, but confident").
- **`Who you'll be with`** is a social-context axis nobody else models. It's a strong (and cheap) formality/impression prior.
- Everything is optional, every field has a default, and the free-text box is last — so the LLM prompt is mostly enum values, i.e. short, cheap, and cacheable.

---

## PART 8 — PLANNER, AI TRY-ON, GLOBAL FAB

### 8.1 Planner / Calendar — `IMG_8012`
- Title **Planner**, `Today` pill top-right, tabs **Day | Month**.
- **Week strip**: Mon–Sun columns, date numbers, today = filled white disc with a small dot beneath (dot = has an outfit).
- Below: "**Today**" label + a **horizontally paged full-height outfit card** (peeking cards left and right = previous/next day). `⋯` overflow top-right of the card, and **"Add a note…"** at the bottom-left of the card.
- Month tab presumably a grid of thumbnails.
- **Design note:** the planner is *outfit-first*, not calendar-first. Most competitors show a month grid of tiny squares; Fits shows one big beautiful outfit and makes the week strip secondary. That's why it feels like a wardrobe app and not a calendar app.
- Per-day **note** field is a small but sticky affordance ("wore this to Rhea's mehendi").

### 8.2 Mode switch from the canvas — `IMG_8013`
`Switch to…` opens a sheet with the *other two* modes (**Collage**, **AI Try On**) — you can move a work-in-progress outfit between renderers without rebuilding it. The composition is stored as data, the renderer is a view.

### 8.3 Dressing room with a real user photo — `IMG_8014`
Shows the failure mode honestly: a badly-cut, wrinkled user photo of a shirt sits awkwardly on the mannequin. The transform toolbar (✓ ✥ 🔓 🔀 🗑) is how the user fixes it. **The Enhance-image upsell exists precisely because of this screen** — bad cut-outs are the funnel into the paid feature.

### 8.4 AI Try-On flow — `IMG_8015`, `IMG_8016`, `IMG_8017`
1. **"Select clothes to try on"** — wardrobe/collection switcher, chip rail, ring/✓ selection, bottom tray with thumbnails + ✕, "3 selected", white **Next →**. User avatar shown top-right (it will render *them*).
2. **AI try on** — a heavily blurred preview of the result behind a purple **`✨ Generate image`** CTA + "**Costs 1 AI credit**" + `1 AI credits ⊕`. Below, three input tiles: **Background** (a model photo) · **Clothes** (the selected items) · **Custom prompt** (✏️).
3. Custom prompt sheet with a *teaching placeholder*: "**Example: Barrel pants, wide fit**" + Clear / Done.

- The blurred-result-behind-the-button is the paywall equivalent of a scratch card. Strong conversion pattern, mildly manipulative — worth using but only where the result genuinely varies.
- **`Background` / `Clothes` / `Custom prompt` as three tiles** is a clean way to present a generative request without a prompt box.

### 8.5 Global FAB — `IMG_8018`
The `➕` in the tab bar opens a sheet of three big rows:
- 👕 **Add clothes ›**
- 👔 **Create outfit ›**
- 🧔 **Chat with AI stylist ›** (with the stylist's avatar)

Also visible behind it: another home rail — **"Basics you may have"** with brand-chip cards (`Ⓑ basics`) — i.e. **shopping suggestions for wardrobe gaps**, the commerce hook.

**Only three creation verbs in the whole app.** Compare with our current nav, which spreads the same actions across tabs.

---

## Design System Extraction (final)

| Token | Light | Dark |
|---|---|---|
| Page bg | `#FFFFFF` | `#000000` (true black) |
| Surface / row | `#F2F2F2`–`#F5F5F5` | `#1C1C1E`–`#2C2C2E` |
| Elevated sheet | `#EFEFEF`, radius 28, grab handle | `#1C1C1E`, radius 28 |
| Primary CTA | black pill, white 17pt semibold, ~64pt tall | **white pill, black label** (inverts) |
| Secondary CTA | `#EDEDED` pill, black label | `#3A3A3C` pill, white label |
| Selected chip | black pill / white text | white pill / black text |
| Selection badge | black disc + white ✓ | white disc + black ✓ |
| Unselected badge | 2px `#C7C7CC` hollow ring | 2px `#48484A` hollow ring |
| **Purple (paid AI)** | `#8B6FE8` fill, white label | same |
| **Mint/aqua (AI motion)** | `#B8F5E4` translucent | same |
| **Pink (AI motion)** | `#FFD3E2` translucent | same |
| Amber (body select) | `#F5A623` 2px border | same |
| Alarm | `#FDE7E7` bg / `#C6362F` text | — |
| Pro badge | black pill + `⭐ Pro` | white pill + `⭐ Pro` |
| H1 | 34pt / 800 | same |
| Section header | 24pt / 700 + `›` chevron | same |
| Body | 17pt / 400, `#6B6B6B` secondary | `#8E8E93` secondary |
| Radius | 16 (cards/tiles) · 20 (big cards) · 28 (sheets) · full (pills) | same |
| Grid | 3-col items, 2-col outfits, 12–16pt gutters, 20pt page margin | same |

### The 12 rules that make Fits look expensive
1. **Render the garment, not a card.** Cut-out PNGs directly on the page background — no borders, no shadows, no labels in grids.
2. **One black pill CTA per screen**, pinned to the bottom, full width.
3. **Every list row that opens something ends in `›`.** Every section header that has a full page ends in `›`.
4. **Sheets, not screens**, for any pick-one-thing task. Always with `Clear …` (left) / `Done` (right).
5. **Emoji as icons** for taxonomies (season, occasion, vibe) — warm, zero asset cost, instantly legible.
6. **Line icons for garment types** — one consistent hand-drawn set, ~70 glyphs, used in pickers *and* as image fallbacks.
7. **Photographic swatches for materials, circular swatches for colours, texture circles for patterns.**
8. **Colour is meaning:** black = action, purple = paid AI, mint/pink = AI processing, amber = body, red = waste/alarm. Nothing is decorative.
9. **Progress is narrated** — named steps that tick, not spinners.
10. **Empty states are merchandised** — real garment photography, a headline, a subtitle, and one black CTA.
11. **Every AI output is an artefact** — named, branded, downloadable, shareable, with `@handle on Fits`.
12. **Free features create the anxiety; paid features resolve it.**

---

<!-- BATCH LOG: FITS COMPLETE — all 135 screenshots analysed (7874–8018). -->


| Token | Observed value |
|---|---|
| Page bg | Pure white `#FFFFFF` |
| Surface / unselected row | `#F2F2F2`–`#F5F5F5`, radius ~16 |
| Selected row | White fill + 2px `#000` border + black ✓ disc |
| Selected tile (photo) | Mint/aqua wash overlay `#C9F5EC`-ish |
| Primary CTA | Full-width black pill, radius = height/2, white 17pt semibold, ~64pt tall, 24pt side margins |
| Secondary CTA | Same pill, `#EDEDED` fill, black label |
| Tertiary CTA | Bare centred text, no chrome ("Skip") |
| Disabled CTA | Same pill, `#9E9E9E` fill |
| H1 | ~34pt, weight 800, `#111`, 2-line wrap, tight leading |
| Sub | ~17pt, `#6B6B6B`, max 2 lines |
| Progress | 4pt full-width track `#E5E5E5`, black fill, fully rounded, pinned top |
| Accent (rare) | Lilac/purple `#8B6FE8` for the recommendation-breadth control only |
| Alarm | Soft pink `#FDE7E7` bg + `#C6362F` text (used for "Rarely worn") |

**Structural rules observed so far**
1. One question per screen. Single-select auto-advances; multi-select shows Next.
2. Every ask carries a one-line "why" — no unexplained data collection.
3. Permissions are always preceded by a priming screen that mocks the OS dialog and points at the right button.
4. Value-prop interstitials are interleaved between questions so the funnel never feels like a form.
5. Photos > words wherever the concept is aesthetic (style picker).
6. Engine parameters are exposed as human controls with live visual feedback (breadth slider).

---

<!-- BATCH LOG: analysed 7874–7890 (16 files incl. dupes 7877/7878 pair). NEXT: 7891 -->
