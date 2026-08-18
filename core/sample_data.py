"""
Seed content for Celebra.

Nothing at request time reads this file any more — the site is driven by the
models in `core/models.py` and the read helpers in `core/queries.py`. What is
left here is the original hand-written catalogue, kept as the payload for:

    python manage.py seed_demo

Every structure mirrors the shape of the model it fills, which is also why the
templates never had to change when the database arrived:

    Category  -> name, slug, icon, blurb, image, package_count
    Package   -> id, title, slug, image, gallery, price, original_price,
                 discount_percent, rating, review_count, category,
                 category_name, includes, description, duration, badge
    Testimonial -> name, city, rating, text, occasion, avatar, date
    City      -> name, slug, state, is_metro
    FAQ       -> question, answer

Helper functions at the bottom stand in for the manager methods you'll
replace them with (`Package.objects.filter(...)`, `get_object_or_404`, ...).
"""

from django.urls import reverse

# ---------------------------------------------------------------------------
# Brand
# ---------------------------------------------------------------------------

BRAND = {
    "name": "Celebra",
    "tagline": "Celebrations, Beautifully Delivered",
    "phone": "+91 98765 43210",
    "phone_href": "+919876543210",
    "whatsapp": "+91 98765 43210",
    "email": "hello@celebra.in",
    "address": "4th Floor, Lumen House, 12 Residency Road, Bengaluru 560025",
    "hours": "Bookings 9 AM – 11 PM, all seven days",
    "founded_year": 2019,
    "instagram": "https://instagram.com/",
    "facebook": "https://facebook.com/",
    "youtube": "https://youtube.com/",
    "twitter": "https://x.com/",
}

NAV_LINKS = [
    {"label": "Home", "url_name": "core:home", "anchor": ""},
    {"label": "Categories", "url_name": "core:categories", "anchor": ""},
    {"label": "How It Works", "url_name": "core:how_it_works", "anchor": ""},
    {"label": "Reviews", "url_name": "core:home", "anchor": "#reviews"},
    {"label": "Contact", "url_name": "core:contact", "anchor": ""},
]

TRUST_BADGES = [
    {"value": "5+", "label": "Years decorating"},
    {"value": "100+", "label": "Cities covered"},
    {"value": "5,000+", "label": "Setups every month"},
    {"value": "4.8", "label": "Average rating"},
]

# ---------------------------------------------------------------------------
# Homepage hero slider
#
# HeroSlide -> id, media_type, eyebrow, heading, heading_accent, description,
#              meta, alt, image_seed, video_mp4, video_webm, duration,
#              cta_label/url_name/url_arg, cta2_*, tint, align, focal
#
# `media_type` is "image" or "video". Video slides still carry an image_seed:
# it becomes the poster frame, so the slide paints instantly and the video file
# is only fetched once that slide is about to become active.
#
# The picsum.photos and commondatastorage URLs are placeholders. Point
# `image_seed` at your CDN and `video_mp4` / `video_webm` at your own encodes
# (1920x1080 H.264 + VP9, no audio track, ~2-4 MB each) and nothing else here
# has to change.
# ---------------------------------------------------------------------------

HERO_SLIDES = [
    {
        "id": "birthday",
        "media_type": "image",
        "eyebrow": "Birthdays",
        "heading": "Someone else can",
        "heading_accent": "hang the balloons.",
        "description": (
            "Pick a setup, pick a slot, and a Celebra decorator arrives with everything "
            "in the van — builds it, photographs it, and takes the packaging away."
        ),
        "meta": "148 birthday setups · from ₹1,499",
        "alt": "A pastel balloon arch built around a cake table in a living room",
        "image_seed": "celebra-hero-birthday",
        "video_mp4": None,
        "video_webm": None,
        "duration": 6500,
        "cta_label": "Browse birthday setups",
        "cta_url_name": "core:category_detail",
        "cta_url_arg": "birthday",
        "cta2_label": "See how it works",
        "cta2_url_name": "core:how_it_works",
        "cta2_url_arg": None,
        "tint": "night",
        "align": "left",
        "focal": "50% 42%",
    },
    {
        "id": "wedding",
        "media_type": "video",
        "eyebrow": "Weddings",
        "heading": "A mandap that earns",
        "heading_accent": "every photograph.",
        "description": (
            "Haldi, mehendi, sangeet and reception stages, built by a crew that has done "
            "it four hundred times. One planner from the first call to the clean-up."
        ),
        "meta": "58 wedding setups · from ₹7,999",
        "alt": "Decorators assembling a floral wedding stage in a banquet hall",
        "image_seed": "celebra-hero-wedding",
        "video_mp4": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerJoyrides.mp4",
        "video_webm": None,
        "duration": 9000,
        "cta_label": "Explore wedding decor",
        "cta_url_name": "core:category_detail",
        "cta_url_arg": "wedding",
        "cta2_label": "Talk to a planner",
        "cta2_url_name": "core:contact",
        "cta2_url_arg": None,
        "tint": "plum",
        "align": "left",
        "focal": "50% 50%",
    },
    {
        "id": "romantic",
        "media_type": "image",
        "eyebrow": "Romantic",
        "heading": "Candlelight, terrace,",
        "heading_accent": "and nothing to carry.",
        "description": (
            "Proposals, anniversaries and quiet dinners for two. We set up while you are "
            "still at work and come back the next morning to take it all down."
        ),
        "meta": "87 romantic setups · from ₹2,199",
        "alt": "A candlelit table for two set up on a terrace at dusk",
        "image_seed": "celebra-hero-romantic",
        "video_mp4": None,
        "video_webm": None,
        "duration": 6500,
        "cta_label": "Plan a romantic evening",
        "cta_url_name": "core:category_detail",
        "cta_url_arg": "romantic",
        "cta2_label": "See all occasions",
        "cta2_url_name": "core:categories",
        "cta2_url_arg": None,
        "tint": "teal",
        "align": "left",
        "focal": "50% 50%",
    },
    {
        "id": "kids-theme",
        "media_type": "video",
        "eyebrow": "Kids themes",
        "heading": "Dinosaurs by four,",
        "heading_accent": "cake by five.",
        "description": (
            "Jungle, space, unicorn or under-the-sea — themed head to toe, props included, "
            "and photographed before we leave so you have the room at its best."
        ),
        "meta": "112 themed setups · from ₹2,999",
        "alt": "A jungle-themed birthday corner with balloon animals and a photo backdrop",
        "image_seed": "celebra-hero-kids",
        "video_mp4": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerFun.mp4",
        "video_webm": None,
        "duration": 9000,
        "cta_label": "Browse kids themes",
        "cta_url_name": "core:category_detail",
        "cta_url_arg": "kids-theme",
        "cta2_label": "Read reviews",
        "cta2_url_name": "core:home",
        "cta2_url_arg": None,
        "cta2_anchor": "#reviews",
        "tint": "night",
        "align": "left",
        "focal": "50% 45%",
    },
    {
        "id": "baby-shower",
        "media_type": "image",
        "eyebrow": "Baby showers",
        "heading": "Pastel arches, seating,",
        "heading_accent": "and a photo corner.",
        "description": (
            "Everything the afternoon needs, priced as one number — materials, labour, "
            "travel inside city limits and clean-up all included."
        ),
        "meta": "64 baby shower setups · from ₹2,499",
        "alt": "A pastel balloon arch and photo corner set for a baby shower",
        "image_seed": "celebra-hero-baby",
        "video_mp4": None,
        "video_webm": None,
        "duration": 6500,
        "cta_label": "Browse baby showers",
        "cta_url_name": "core:category_detail",
        "cta_url_arg": "baby-shower",
        "cta2_label": "Get a custom quote",
        "cta2_url_name": "core:contact",
        "cta2_url_arg": None,
        "tint": "teal",
        "align": "left",
        "focal": "50% 50%",
    },
]

# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

CATEGORIES = [
    {
        "name": "Birthday",
        "slug": "birthday",
        "icon": "gift",
        "blurb": "Balloon walls, number foils and cake tables for every age.",
        "price_from": 1499,
        "package_count": 148,
    },
    {
        "name": "Anniversary",
        "slug": "anniversary",
        "icon": "heart",
        "blurb": "Warm, grown-up setups built around the two of you.",
        "price_from": 1999,
        "package_count": 96,
    },
    {
        "name": "Baby Shower",
        "slug": "baby-shower",
        "icon": "cloud",
        "blurb": "Pastel arches, photo corners and mum-to-be seating.",
        "price_from": 2499,
        "package_count": 64,
    },
    {
        "name": "Kids Theme",
        "slug": "kids-theme",
        "icon": "star",
        "blurb": "Dinosaurs, space, jungle, unicorns — themed head to toe.",
        "price_from": 2999,
        "package_count": 112,
    },
    {
        "name": "Wedding",
        "slug": "wedding",
        "icon": "sparkles",
        "blurb": "Haldi, mehendi, sangeet and reception stage decor.",
        "price_from": 7999,
        "package_count": 58,
    },
    {
        "name": "Romantic",
        "slug": "romantic",
        "icon": "flame",
        "blurb": "Candlelight dinners, proposals and private terraces.",
        "price_from": 2199,
        "package_count": 87,
    },
    {
        "name": "Newborn Welcome",
        "slug": "newborn-welcome",
        "icon": "home",
        "blurb": "Bring the baby home to a doorway worth photographing.",
        "price_from": 1799,
        "package_count": 41,
    },
    {
        "name": "Corporate",
        "slug": "corporate",
        "icon": "briefcase",
        "blurb": "Launches, milestones and office celebrations, on brand.",
        "price_from": 5999,
        "package_count": 37,
    },
    {
        "name": "Festival",
        "slug": "festival",
        "icon": "sun",
        "blurb": "Diwali, Christmas, Eid and Onam decor for home or office.",
        "price_from": 2499,
        "package_count": 52,
    },
]

# ---------------------------------------------------------------------------
# Packages
# ---------------------------------------------------------------------------

_PACKAGES = [
    {
        "id": 1,
        "title": "Golden Hour Birthday Balloon Wall",
        "slug": "golden-hour-birthday-balloon-wall",
        "category": "birthday",
        "price": 2799,
        "original_price": 3999,
        "rating": 4.9,
        "review_count": 428,
        "duration": "3–4 hours on site",
        "badge": "Most booked",
        "is_featured": True,
        "description": (
            "A floor-to-ceiling balloon wall in ivory, gold and deep teal with a "
            "personalised name banner at the centre. Our decorator handles the wall, "
            "the cake table styling and the fairy-light backdrop, then clears every "
            "scrap of packaging before leaving."
        ),
        "includes": [
            "120 metallic and pastel balloons in a organic garland",
            "Personalised name banner (up to 12 characters)",
            "Fairy-light curtain backdrop, 2m x 2m",
            "Styled cake table with runner and two risers",
            "Two number foil balloons of your choice",
            "On-site decorator plus full clean-up",
        ],
    },
    {
        "id": 2,
        "title": "Candlelit Terrace Anniversary Dinner",
        "slug": "candlelit-terrace-anniversary-dinner",
        "category": "anniversary",
        "price": 4499,
        "original_price": 6499,
        "rating": 4.8,
        "review_count": 312,
        "duration": "4 hours on site",
        "badge": "Editor's pick",
        "is_featured": True,
        "description": (
            "A private table for two under a canopy of warm bulbs, framed by a low "
            "balloon arch and a hand-lettered anniversary sign. Works on a terrace, "
            "a lawn or a cleared living room."
        ),
        "includes": [
            "Table for two with linen, runner and charger plates",
            "36 tea lights in glass holders",
            "Warm-white bulb canopy, 4m span",
            "Low balloon arch in teal and ivory",
            "Hand-lettered 'Happy Anniversary' sign",
            "Fresh rose petal pathway",
        ],
    },
    {
        "id": 3,
        "title": "Cloud Nine Baby Shower Arch",
        "slug": "cloud-nine-baby-shower-arch",
        "category": "baby-shower",
        "price": 5299,
        "original_price": 7499,
        "rating": 4.9,
        "review_count": 186,
        "duration": "4–5 hours on site",
        "badge": "New",
        "is_featured": True,
        "description": (
            "A pastel cloud-and-balloon arch built around a cushioned seat for the "
            "mum-to-be, with a photo corner guests actually queue for."
        ),
        "includes": [
            "Organic balloon arch, 3m wide, in blush and sage",
            "Hanging cloud and raindrop props",
            "Cushioned mum-to-be chair with drape",
            "Dessert table styling with two tiers",
            "'Oh Baby' marquee letters",
            "Polaroid photo corner with props",
        ],
    },
    {
        "id": 4,
        "title": "Little Explorer Dinosaur Party",
        "slug": "little-explorer-dinosaur-party",
        "category": "kids-theme",
        "price": 4899,
        "original_price": 6999,
        "rating": 4.7,
        "review_count": 254,
        "duration": "4 hours on site",
        "badge": "Kids favourite",
        "is_featured": True,
        "description": (
            "A jungle-green balloon canopy, life-size dinosaur cutouts and a fossil "
            "dig corner that keeps eight children busy for an hour. Tested on real "
            "six-year-olds."
        ),
        "includes": [
            "Green and sand balloon garland, 4m",
            "Three life-size dinosaur standees",
            "Fossil dig sand tray with brushes",
            "Themed cake table and backdrop",
            "Ten party hats and eight loot bags",
            "Dino footprint floor decals",
        ],
    },
    {
        "id": 5,
        "title": "Marigold Haldi Courtyard",
        "slug": "marigold-haldi-courtyard",
        "category": "wedding",
        "price": 14999,
        "original_price": 19999,
        "rating": 4.8,
        "review_count": 97,
        "duration": "Full day, team of four",
        "badge": "Premium",
        "is_featured": True,
        "description": (
            "Fresh marigold curtains, low seating and brass detailing for the haldi "
            "ceremony. Priced for up to 60 guests; larger courtyards quoted on site."
        ),
        "includes": [
            "15kg fresh marigold garlands and curtains",
            "Low seating for the couple with bolsters",
            "Brass urli and floating flower arrangement",
            "Fabric drape ceiling, up to 6m x 6m",
            "Photo signage in regional script",
            "Team of four decorators, full day",
        ],
    },
    {
        "id": 6,
        "title": "Rooftop Proposal Setup",
        "slug": "rooftop-proposal-setup",
        "category": "romantic",
        "price": 6999,
        "original_price": 9499,
        "rating": 5.0,
        "review_count": 143,
        "duration": "3 hours, discreet arrival",
        "badge": "She said yes",
        "is_featured": True,
        "description": (
            "A heart of candles, a ring-box pedestal and a lit 'MARRY ME' sign, set "
            "up while you keep them busy elsewhere. Decorator arrives unmarked and "
            "leaves before you do."
        ),
        "includes": [
            "60 LED pillar candles in a 3m heart",
            "Lit 'MARRY ME' marquee letters",
            "Ring-box pedestal with spotlight",
            "Rose petal pathway and scatter",
            "Balloon cluster with photo pegs",
            "Discreet unmarked arrival and setup",
        ],
    },
    {
        "id": 7,
        "title": "Welcome Home Little One",
        "slug": "welcome-home-little-one",
        "category": "newborn-welcome",
        "price": 3299,
        "original_price": 4499,
        "rating": 4.9,
        "review_count": 121,
        "duration": "2–3 hours on site",
        "badge": "Same-day",
        "is_featured": True,
        "description": (
            "A doorway arch and hallway trail that turns the drive home from the "
            "hospital into the first photo in the album. Bookable same day until 2 PM."
        ),
        "includes": [
            "Doorway balloon arch in soft pastels",
            "'Welcome Home' banner with baby's name",
            "Hallway balloon trail to the nursery",
            "Cot or bassinet drape with bow",
            "Footprint floor decals",
            "Quiet setup, no adhesive on walls",
        ],
    },
    {
        "id": 8,
        "title": "Milestone Launch Backdrop",
        "slug": "milestone-launch-backdrop",
        "category": "corporate",
        "price": 18999,
        "original_price": 24999,
        "rating": 4.7,
        "review_count": 64,
        "duration": "Full day, team of three",
        "badge": "GST invoice",
        "is_featured": True,
        "description": (
            "A branded step-and-repeat wall, balloon columns in your brand colours "
            "and a ribbon-cutting station. Comes with a GST invoice and a named "
            "account manager."
        ),
        "includes": [
            "3m x 2.5m branded step-and-repeat wall",
            "Two balloon columns in brand colours",
            "Ribbon-cutting station with brass scissors",
            "Reception table styling and signage",
            "Setup completed before 8 AM",
            "GST invoice and account manager",
        ],
    },
    {
        "id": 9,
        "title": "Diwali Doorway Rangoli & Diyas",
        "slug": "diwali-doorway-rangoli-and-diyas",
        "category": "festival",
        "price": 3999,
        "original_price": 5499,
        "rating": 4.8,
        "review_count": 208,
        "duration": "3 hours on site",
        "badge": "Seasonal",
        "is_featured": False,
        "description": (
            "A hand-drawn rangoli, marigold torans and forty lit diyas across your "
            "entrance and balcony. Booked in October, arrives before sundown."
        ),
        "includes": [
            "Hand-drawn rangoli, up to 5ft diameter",
            "Fresh marigold and mango-leaf torans",
            "40 clay diyas, lit and placed",
            "Balcony fairy-light run, up to 10m",
            "Brass urli with floating flowers",
            "Next-morning clean-up option",
        ],
    },
    {
        "id": 10,
        "title": "First Birthday Pastel Picnic",
        "slug": "first-birthday-pastel-picnic",
        "category": "birthday",
        "price": 5499,
        "original_price": 7299,
        "rating": 4.9,
        "review_count": 176,
        "duration": "4 hours on site",
        "badge": "",
        "is_featured": False,
        "description": (
            "A low picnic table, pastel canopy and a smash-cake corner, sized for a "
            "one-year-old and the twelve adults photographing them."
        ),
        "includes": [
            "Low picnic table with cushions for eight",
            "Pastel fabric canopy, 3m x 3m",
            "Smash-cake corner with backdrop",
            "Monthly photo clothesline, 12 pegs",
            "Balloon garland in blush and mint",
            "Crown and sash for the birthday baby",
        ],
    },
    {
        "id": 11,
        "title": "Neon Teen Birthday Room",
        "slug": "neon-teen-birthday-room",
        "category": "birthday",
        "price": 3899,
        "original_price": 5299,
        "rating": 4.6,
        "review_count": 139,
        "duration": "3 hours on site",
        "badge": "",
        "is_featured": False,
        "description": (
            "UV lights, a neon quote sign and a black-and-chrome balloon ceiling. "
            "Loud, photogenic, and gone by morning."
        ),
        "includes": [
            "Chrome and black balloon ceiling",
            "Custom neon-style LED quote sign",
            "Two UV blacklight bars",
            "Glow-stick and prop box for ten",
            "Photo wall with streamer curtain",
            "Bluetooth speaker on request",
        ],
    },
    {
        "id": 12,
        "title": "Silver Jubilee Stage Decor",
        "slug": "silver-jubilee-stage-decor",
        "category": "anniversary",
        "price": 11999,
        "original_price": 15999,
        "rating": 4.8,
        "review_count": 88,
        "duration": "Full day, team of three",
        "badge": "",
        "is_featured": False,
        "description": (
            "A stage for the couple with fresh florals, a photo timeline and seating "
            "for the family. Built for banquet halls and community centres."
        ),
        "includes": [
            "Stage backdrop, up to 5m wide",
            "Fresh flower arrangements, four stands",
            "Photo timeline display, 25 frames",
            "Couple's seating with drape",
            "Entrance arch and welcome signage",
            "Team of three, full-day setup",
        ],
    },
    {
        "id": 13,
        "title": "Sage & Cream Gender Reveal",
        "slug": "sage-and-cream-gender-reveal",
        "category": "baby-shower",
        "price": 4699,
        "original_price": 6299,
        "rating": 4.7,
        "review_count": 132,
        "duration": "3–4 hours on site",
        "badge": "",
        "is_featured": False,
        "description": (
            "A neutral sage-and-cream setup with the reveal balloon prepared on site "
            "and kept sealed until your moment."
        ),
        "includes": [
            "Sage and cream balloon garland, 3m",
            "Sealed reveal balloon with confetti",
            "'Boy or Girl' vote board with pegs",
            "Dessert table styling",
            "Guest sign-in frame",
            "Confetti cannons, pair",
        ],
    },
    {
        "id": 14,
        "title": "Galaxy Voyager Kids Setup",
        "slug": "galaxy-voyager-kids-setup",
        "category": "kids-theme",
        "price": 5799,
        "original_price": 7999,
        "rating": 4.8,
        "review_count": 167,
        "duration": "4 hours on site",
        "badge": "",
        "is_featured": False,
        "description": (
            "A deep navy balloon galaxy with hanging planets, a rocket cutout and a "
            "star projector left running through the party."
        ),
        "includes": [
            "Navy and silver balloon galaxy ceiling",
            "Six hanging planet props",
            "Life-size rocket standee",
            "Star projector, running through event",
            "Astronaut photo cutout",
            "Themed cake table and backdrop",
        ],
    },
    {
        "id": 15,
        "title": "Unicorn Dream Balloon Arch",
        "slug": "unicorn-dream-balloon-arch",
        "category": "kids-theme",
        "price": 4299,
        "original_price": 5899,
        "rating": 4.7,
        "review_count": 203,
        "duration": "3–4 hours on site",
        "badge": "",
        "is_featured": False,
        "description": (
            "A pastel rainbow arch with a unicorn horn centrepiece, cloud props and "
            "a glitter photo corner."
        ),
        "includes": [
            "Pastel rainbow balloon arch, 3.5m",
            "Unicorn horn and ear centrepiece",
            "Cloud and star hanging props",
            "Glitter backdrop photo corner",
            "Themed table runner and cups",
            "Eight party crowns",
        ],
    },
    {
        "id": 16,
        "title": "Mehendi Night Fabric Canopy",
        "slug": "mehendi-night-fabric-canopy",
        "category": "wedding",
        "price": 16999,
        "original_price": 22999,
        "rating": 4.9,
        "review_count": 74,
        "duration": "Full day, team of four",
        "badge": "",
        "is_featured": False,
        "description": (
            "Layered fabric canopies, low seating and lantern clusters for the "
            "mehendi evening, lit for photography after dark."
        ),
        "includes": [
            "Layered fabric canopy, up to 8m x 8m",
            "Low seating for 20 with bolsters",
            "24 hanging lanterns, lit",
            "Mehendi artist station with lighting",
            "Entrance drape and floral pillars",
            "Team of four decorators",
        ],
    },
    {
        "id": 17,
        "title": "Reception Stage Floral Wall",
        "slug": "reception-stage-floral-wall",
        "category": "wedding",
        "price": 29999,
        "original_price": 38999,
        "rating": 4.8,
        "review_count": 51,
        "duration": "Full day, team of six",
        "badge": "Premium",
        "is_featured": False,
        "description": (
            "A full fresh-flower stage wall with couple seating, aisle styling and "
            "an entrance arch. Site visit included before booking."
        ),
        "includes": [
            "Fresh flower stage wall, up to 6m",
            "Couple's seating with upholstery",
            "Aisle styling and entrance arch",
            "Uplighting, eight fixtures",
            "Free site visit before the event",
            "Team of six, full-day setup",
        ],
    },
    {
        "id": 18,
        "title": "Private Cabana Candlelight Dinner",
        "slug": "private-cabana-candlelight-dinner",
        "category": "romantic",
        "price": 5499,
        "original_price": 7499,
        "rating": 4.9,
        "review_count": 219,
        "duration": "4 hours on site",
        "badge": "",
        "is_featured": False,
        "description": (
            "A draped cabana with a candlelit table for two, a floral centrepiece "
            "and a projector for your own slideshow."
        ),
        "includes": [
            "Draped cabana, 3m x 3m",
            "Candlelit table for two",
            "Fresh floral centrepiece",
            "Projector and screen for slideshow",
            "Rose petal pathway",
            "Bluetooth speaker with your playlist",
        ],
    },
    {
        "id": 19,
        "title": "Car Boot Surprise Setup",
        "slug": "car-boot-surprise-setup",
        "category": "romantic",
        "price": 2199,
        "original_price": 2999,
        "rating": 4.6,
        "review_count": 158,
        "duration": "90 minutes on site",
        "badge": "Under ₹2,500",
        "is_featured": False,
        "description": (
            "Balloons, a lit sign and a cake stand fitted into your car boot in the "
            "parking lot, ready in ninety minutes."
        ),
        "includes": [
            "Boot-fitted balloon cluster",
            "Battery-lit name or message sign",
            "Cake stand with fairy lights",
            "Rose petals and photo props",
            "Setup in your parking spot",
            "No adhesive, no residue",
        ],
    },
    {
        "id": 20,
        "title": "Naming Ceremony Home Decor",
        "slug": "naming-ceremony-home-decor",
        "category": "newborn-welcome",
        "price": 6499,
        "original_price": 8499,
        "rating": 4.8,
        "review_count": 79,
        "duration": "5 hours on site",
        "badge": "",
        "is_featured": False,
        "description": (
            "A cradle drape, floral entrance and family seating arrangement for the "
            "naming ceremony, set up quietly around a sleeping baby."
        ),
        "includes": [
            "Decorated cradle with drape and florals",
            "Floral entrance arch",
            "Family seating arrangement for 20",
            "Name reveal board, hand-lettered",
            "Pooja table styling",
            "Quiet, low-noise setup",
        ],
    },
    {
        "id": 21,
        "title": "Office Anniversary Balloon Columns",
        "slug": "office-anniversary-balloon-columns",
        "category": "corporate",
        "price": 8999,
        "original_price": 11999,
        "rating": 4.6,
        "review_count": 43,
        "duration": "Before-hours setup",
        "badge": "",
        "is_featured": False,
        "description": (
            "Reception columns, a lift-lobby arch and desk-level styling in your "
            "brand colours, finished before the first employee badges in."
        ),
        "includes": [
            "Four balloon columns in brand colours",
            "Lift-lobby entrance arch",
            "Reception desk styling and signage",
            "Milestone number foils",
            "Setup completed before 8 AM",
            "GST invoice",
        ],
    },
    {
        "id": 22,
        "title": "Christmas Living Room Makeover",
        "slug": "christmas-living-room-makeover",
        "category": "festival",
        "price": 7499,
        "original_price": 9999,
        "rating": 4.7,
        "review_count": 114,
        "duration": "5 hours on site",
        "badge": "Seasonal",
        "is_featured": False,
        "description": (
            "A dressed tree, mantel garland and window lights, installed and then "
            "taken down in January if you'd rather not climb the ladder twice."
        ),
        "includes": [
            "6ft tree, dressed and lit",
            "Mantel or shelf garland",
            "Window and balcony light run",
            "Wreath for the front door",
            "Gift-stack props under the tree",
            "January take-down included",
        ],
    },
    {
        "id": 23,
        "title": "Onam Pookalam & Pandal",
        "slug": "onam-pookalam-and-pandal",
        "category": "festival",
        "price": 5999,
        "original_price": 7999,
        "rating": 4.8,
        "review_count": 67,
        "duration": "Morning setup",
        "badge": "",
        "is_featured": False,
        "description": (
            "A fresh-flower pookalam laid at dawn with a banana-leaf entrance and "
            "traditional lamp arrangement."
        ),
        "includes": [
            "Fresh flower pookalam, up to 6ft",
            "Banana-leaf and tender-coconut entrance",
            "Nilavilakku lamp arrangement",
            "Sadhya table styling",
            "Traditional umbrella props",
            "Dawn setup, complete by 9 AM",
        ],
    },
    {
        "id": 24,
        "title": "Half-Saree Ceremony Stage",
        "slug": "half-saree-ceremony-stage",
        "category": "wedding",
        "price": 13999,
        "original_price": 17999,
        "rating": 4.7,
        "review_count": 39,
        "duration": "Full day, team of three",
        "badge": "",
        "is_featured": False,
        "description": (
            "A traditional stage with fresh florals, a decorated seat and a "
            "photo-ready entrance for the ceremony."
        ),
        "includes": [
            "Stage backdrop with fresh florals",
            "Decorated ceremonial seat",
            "Entrance arch with garlands",
            "Family seating styling",
            "Traditional lamp and kalash setup",
            "Team of three decorators",
        ],
    },
    {
        "id": 25,
        "title": "Surprise Room Balloon Drop",
        "slug": "surprise-room-balloon-drop",
        "category": "birthday",
        "price": 1899,
        "original_price": 2599,
        "rating": 4.5,
        "review_count": 291,
        "duration": "2 hours on site",
        "badge": "Under ₹2,000",
        "is_featured": False,
        "description": (
            "The entry-level setup: a ceiling balloon drop net, a message wall and "
            "a photo corner. Our most-booked last-minute option."
        ),
        "includes": [
            "Ceiling balloon drop net, 60 balloons",
            "Message wall with letter balloons",
            "Photo corner with streamers",
            "LED string lights, 10m",
            "Confetti poppers, pair",
            "Same-day slots until 4 PM",
        ],
    },
    {
        "id": 26,
        "title": "Jungle Safari Toddler Party",
        "slug": "jungle-safari-toddler-party",
        "category": "kids-theme",
        "price": 5199,
        "original_price": 6999,
        "rating": 4.8,
        "review_count": 148,
        "duration": "4 hours on site",
        "badge": "",
        "is_featured": False,
        "description": (
            "Leafy garlands, animal standees and a low activity table, arranged so "
            "toddlers can reach everything safely."
        ),
        "includes": [
            "Leaf and balloon garland, 4m",
            "Four animal standees",
            "Low activity table with cushions",
            "Themed cake table backdrop",
            "Safari hats for eight",
            "Rounded, toddler-safe props only",
        ],
    },
    {
        "id": 27,
        "title": "Terrace Birthday Under Fairy Lights",
        "slug": "terrace-birthday-under-fairy-lights",
        "category": "birthday",
        "price": 6299,
        "original_price": 8499,
        "rating": 4.8,
        "review_count": 164,
        "duration": "4 hours on site",
        "badge": "",
        "is_featured": False,
        "description": (
            "A canopy of warm bulbs over a terrace, low seating, and a lit name sign "
            "sized to be readable in photographs from across the roof."
        ),
        "includes": [
            "Warm bulb canopy, up to 8m span",
            "Low seating with cushions for 12",
            "Lit name sign, up to 10 characters",
            "Balloon garland along the parapet",
            "Cake table with runner and risers",
            "Weighted bases, no drilling",
        ],
    },
    {
        "id": 28,
        "title": "Retro Nineties Birthday Corner",
        "slug": "retro-nineties-birthday-corner",
        "category": "birthday",
        "price": 4199,
        "original_price": 5799,
        "rating": 4.6,
        "review_count": 112,
        "duration": "3 hours on site",
        "badge": "",
        "is_featured": False,
        "description": (
            "Cassette-tape props, a disc-wall backdrop and neon-lettered signage for "
            "a birthday that leans hard into the decade."
        ),
        "includes": [
            "Disc-wall backdrop, 2m x 2m",
            "Cassette and boombox props",
            "Neon-style lettering, custom text",
            "Streamer curtain photo corner",
            "Balloon cluster in primary colours",
            "Prop box with sunglasses for ten",
        ],
    },
    {
        "id": 29,
        "title": "Pastel Half-Birthday Setup",
        "slug": "pastel-half-birthday-setup",
        "category": "birthday",
        "price": 3499,
        "original_price": 4799,
        "rating": 4.7,
        "review_count": 98,
        "duration": "3 hours on site",
        "badge": "",
        "is_featured": False,
        "description": (
            "For the six-month mark: a small pastel arch, a half-cake stand and a "
            "photo corner scaled for a baby who cannot sit unaided yet."
        ),
        "includes": [
            "Pastel balloon arch, 2m",
            "Half-cake stand with backdrop",
            "Floor-level photo corner with mat",
            "'Half Way to One' banner",
            "Milestone card set, 12 cards",
            "Soft props only, no hard edges",
        ],
    },
    {
        "id": 30,
        "title": "Sixtieth Birthday Garden Lunch",
        "slug": "sixtieth-birthday-garden-lunch",
        "category": "birthday",
        "price": 9499,
        "original_price": 12499,
        "rating": 4.8,
        "review_count": 71,
        "duration": "Full day, team of two",
        "badge": "",
        "is_featured": False,
        "description": (
            "Daytime garden styling with fresh florals, a shaded seating area and a "
            "photo timeline, built for a lunch rather than an evening party."
        ),
        "includes": [
            "Fresh floral table arrangements, six",
            "Shaded seating area for 25",
            "Photo timeline display, 30 frames",
            "Entrance welcome board",
            "Buffet table styling",
            "Team of two, full-day setup",
        ],
    },
    {
        "id": 31,
        "title": "Balcony Midnight Surprise",
        "slug": "balcony-midnight-surprise",
        "category": "birthday",
        "price": 2499,
        "original_price": 3399,
        "rating": 4.6,
        "review_count": 187,
        "duration": "2 hours, late slot",
        "badge": "Late slot",
        "is_featured": False,
        "description": (
            "A compact balcony setup delivered in the 10 PM slot, so the surprise is "
            "waiting when the clock turns over."
        ),
        "includes": [
            "Balcony balloon cluster and drape",
            "Battery fairy lights, 10m",
            "Lit number candles and cake stand",
            "Message board with chalk pen",
            "Rose petal scatter",
            "Late 10 PM arrival window",
        ],
    },
    {
        "id": 32,
        "title": "Bollywood Theme Birthday Stage",
        "slug": "bollywood-theme-birthday-stage",
        "category": "birthday",
        "price": 7999,
        "original_price": 10499,
        "rating": 4.7,
        "review_count": 84,
        "duration": "5 hours on site",
        "badge": "",
        "is_featured": False,
        "description": (
            "A film-poster backdrop, marquee bulbs and a red-carpet entrance for a "
            "birthday that ends in a dance floor."
        ),
        "includes": [
            "Custom film-poster backdrop, 3m",
            "Marquee bulb frame",
            "Red carpet entrance, 4m",
            "Director's clapboard props",
            "Uplighting, four fixtures",
            "Dance-floor perimeter styling",
        ],
    },
    {
        "id": 33,
        "title": "Underwater Mermaid Party",
        "slug": "underwater-mermaid-party",
        "category": "kids-theme",
        "price": 5399,
        "original_price": 7299,
        "rating": 4.8,
        "review_count": 129,
        "duration": "4 hours on site",
        "badge": "",
        "is_featured": False,
        "description": (
            "Teal and shell-pink balloon waves, hanging jellyfish and a treasure-hunt "
            "corner with a chest that actually opens."
        ),
        "includes": [
            "Wave-form balloon garland, 4m",
            "Six hanging jellyfish props",
            "Treasure chest with hunt clues",
            "Shell and coral table styling",
            "Mermaid tail photo cutout",
            "Bubble machine for the entrance",
        ],
    },
    {
        "id": 34,
        "title": "Construction Site Play Party",
        "slug": "construction-site-play-party",
        "category": "kids-theme",
        "price": 4799,
        "original_price": 6499,
        "rating": 4.6,
        "review_count": 96,
        "duration": "4 hours on site",
        "badge": "",
        "is_featured": False,
        "description": (
            "Caution-tape styling, a foam-brick building zone and eight hard hats. "
            "Chaotic by design, cleared away by us."
        ),
        "includes": [
            "Caution-tape and cone entrance",
            "Foam brick building zone",
            "Eight hard hats and vests",
            "Digger and truck props",
            "Yellow and black balloon garland",
            "Full clean-up of the play zone",
        ],
    },
    {
        "id": 35,
        "title": "Fairy Garden Toddler Setup",
        "slug": "fairy-garden-toddler-setup",
        "category": "kids-theme",
        "price": 4599,
        "original_price": 6199,
        "rating": 4.7,
        "review_count": 141,
        "duration": "3–4 hours on site",
        "badge": "",
        "is_featured": False,
        "description": (
            "Moss, toadstools and a lit archway, with a low tea-party table set for "
            "six small guests."
        ),
        "includes": [
            "Lit fairy archway, 2.5m",
            "Moss and toadstool floor props",
            "Low tea-party table for six",
            "Butterfly and lantern hangings",
            "Pastel balloon cloud",
            "Fairy wings for six children",
        ],
    },
    {
        "id": 36,
        "title": "First Anniversary Room Surprise",
        "slug": "first-anniversary-room-surprise",
        "category": "anniversary",
        "price": 2999,
        "original_price": 3999,
        "rating": 4.7,
        "review_count": 226,
        "duration": "2 hours on site",
        "badge": "",
        "is_featured": False,
        "description": (
            "A bedroom or hotel-room setup with a photo clothesline, candle path and "
            "balloon ceiling, arranged while you are out for dinner."
        ),
        "includes": [
            "Balloon ceiling with ribbon drop",
            "Photo clothesline, 20 pegs",
            "LED candle path",
            "Rose petal bed styling",
            "Lit '1 Year' sign",
            "Hotel-safe, no adhesive",
        ],
    },
    {
        "id": 37,
        "title": "Jungle Safari Baby Shower",
        "slug": "jungle-safari-baby-shower",
        "category": "baby-shower",
        "price": 5899,
        "original_price": 7899,
        "rating": 4.7,
        "review_count": 88,
        "duration": "4 hours on site",
        "badge": "",
        "is_featured": False,
        "description": (
            "Leafy garlands, wooden crates and animal-print accents, with a raised "
            "seat for the mum-to-be and a nappy-raffle station."
        ),
        "includes": [
            "Leaf and balloon garland, 4m",
            "Wooden crate dessert display",
            "Raised mum-to-be seat with drape",
            "Animal standees, three",
            "Nappy raffle station",
            "Guest advice card wall",
        ],
    },
    {
        "id": 38,
        "title": "Beachside Sunset Dinner",
        "slug": "beachside-sunset-dinner",
        "category": "romantic",
        "price": 8999,
        "original_price": 11999,
        "rating": 4.9,
        "review_count": 106,
        "duration": "4 hours, evening",
        "badge": "Goa only",
        "is_featured": False,
        "description": (
            "A cabana, a low table and a lantern path on the sand, timed so the "
            "setup finishes twenty minutes before sunset."
        ),
        "includes": [
            "Beach cabana with drapes",
            "Low table for two on the sand",
            "Lantern path, 20 lanterns",
            "Floral arch facing the water",
            "Timed to finish before sunset",
            "Permits handled for public beaches",
        ],
    },
]


def _decorate(package):
    """Fill the derived fields a model would compute (or a manager annotate)."""
    slug = package["slug"]
    package.setdefault("image", f"https://picsum.photos/seed/{slug}/800/600")
    package.setdefault(
        "gallery",
        [
            {
                "url": f"https://picsum.photos/seed/{slug}-{i}/1200/900",
                "thumb": f"https://picsum.photos/seed/{slug}-{i}/240/180",
                "alt": f"{package['title']} — setup photo {i}",
            }
            for i in range(1, 6)
        ],
    )
    saving = package["original_price"] - package["price"]
    package["discount_percent"] = round(saving * 100 / package["original_price"])
    package["saving"] = saving
    package["category_name"] = CATEGORY_BY_SLUG[package["category"]]["name"]
    package["alt"] = f"{package['title']} decoration setup by Celebra"
    return package


CATEGORY_BY_SLUG = {c["slug"]: c for c in CATEGORIES}
PACKAGES = [_decorate(p) for p in _PACKAGES]
PACKAGE_BY_SLUG = {p["slug"]: p for p in PACKAGES}

# ---------------------------------------------------------------------------
# Testimonials
# ---------------------------------------------------------------------------

TESTIMONIALS = [
    {
        "name": "Ananya Raghavan",
        "city": "Bengaluru",
        "rating": 5,
        "occasion": "Golden Hour Birthday Balloon Wall",
        "date": "March 2026",
        "text": (
            "The decorator reached at 4 PM for a 7 PM party and was done with an "
            "hour to spare. The balloon wall held up through forty guests and a "
            "ceiling fan on full speed. Photos came out exactly like the listing."
        ),
    },
    {
        "name": "Vikram Sethi",
        "city": "Pune",
        "rating": 5,
        "occasion": "Rooftop Proposal Setup",
        "date": "February 2026",
        "text": (
            "I was terrified they'd ring the doorbell and ruin the surprise. They "
            "messaged instead, set up in silence, and left through the service "
            "lift. She had no idea. Worth every rupee."
        ),
    },
    {
        "name": "Meera Joshi",
        "city": "Mumbai",
        "rating": 4,
        "occasion": "Cloud Nine Baby Shower Arch",
        "date": "January 2026",
        "text": (
            "Beautiful setup and the mum-to-be chair was genuinely comfortable. "
            "One prop arrived slightly damaged and they swapped it within the hour "
            "without me having to argue about it."
        ),
    },
    {
        "name": "Rohan Nair",
        "city": "Kochi",
        "rating": 5,
        "occasion": "Onam Pookalam & Pandal",
        "date": "September 2025",
        "text": (
            "They started at 5:30 AM so the pookalam was finished before the family "
            "woke up. My mother, who has laid one every year for thirty years, "
            "approved. That is the highest rating available in this house."
        ),
    },
    {
        "name": "Priya Deshmukh",
        "city": "Hyderabad",
        "rating": 5,
        "occasion": "Little Explorer Dinosaur Party",
        "date": "March 2026",
        "text": (
            "The fossil dig kept nine children occupied for over an hour, which "
            "meant the adults actually got to eat. I'd book it again for that "
            "alone."
        ),
    },
    {
        "name": "Arjun Malhotra",
        "city": "Delhi",
        "rating": 4,
        "occasion": "Milestone Launch Backdrop",
        "date": "December 2025",
        "text": (
            "Branded wall matched our colour codes exactly and the GST invoice came "
            "the same day, which finance appreciated more than the balloons. Setup "
            "ran fifteen minutes past the promised time."
        ),
    },
    {
        "name": "Fatima Sheikh",
        "city": "Ahmedabad",
        "rating": 5,
        "occasion": "Welcome Home Little One",
        "date": "February 2026",
        "text": (
            "Booked at 11 AM on the day we were discharged. The doorway was done by "
            "the time we reached home at 4 PM. No adhesive on the walls, exactly as "
            "promised — our landlord thanks you."
        ),
    },
    {
        "name": "Sanjay Krishnan",
        "city": "Chennai",
        "rating": 5,
        "occasion": "Silver Jubilee Stage Decor",
        "date": "November 2025",
        "text": (
            "Twenty-five years of photographs on a timeline wall, and my parents "
            "stood in front of it for most of the evening. The team handled the "
            "hall's awkward pillars without being asked."
        ),
    },
    {
        "name": "Neha Bansal",
        "city": "Jaipur",
        "rating": 5,
        "occasion": "Private Cabana Candlelight Dinner",
        "date": "January 2026",
        "text": (
            "The projector slideshow was the detail that got me. They loaded my "
            "photos beforehand and tested it, so nothing needed fixing while we "
            "were sitting there."
        ),
    },
    {
        "name": "Imran Qureshi",
        "city": "Lucknow",
        "rating": 4,
        "occasion": "Diwali Doorway Rangoli & Diyas",
        "date": "October 2025",
        "text": (
            "Rangoli was hand-drawn, not a sticker, which is what I was worried "
            "about. Forty diyas lit before sundown. Next-morning clean-up saved my "
            "Sunday."
        ),
    },
]

# ---------------------------------------------------------------------------
# Cities
# ---------------------------------------------------------------------------

_CITY_ROWS = [
    ("Bengaluru", "Karnataka", True),
    ("Mumbai", "Maharashtra", True),
    ("Delhi", "Delhi NCR", True),
    ("Gurugram", "Delhi NCR", True),
    ("Noida", "Delhi NCR", True),
    ("Hyderabad", "Telangana", True),
    ("Chennai", "Tamil Nadu", True),
    ("Pune", "Maharashtra", True),
    ("Kolkata", "West Bengal", True),
    ("Ahmedabad", "Gujarat", True),
    ("Jaipur", "Rajasthan", False),
    ("Kochi", "Kerala", False),
    ("Thiruvananthapuram", "Kerala", False),
    ("Kozhikode", "Kerala", False),
    ("Coimbatore", "Tamil Nadu", False),
    ("Madurai", "Tamil Nadu", False),
    ("Tiruchirappalli", "Tamil Nadu", False),
    ("Mysuru", "Karnataka", False),
    ("Mangaluru", "Karnataka", False),
    ("Hubballi", "Karnataka", False),
    ("Vijayawada", "Andhra Pradesh", False),
    ("Visakhapatnam", "Andhra Pradesh", False),
    ("Guntur", "Andhra Pradesh", False),
    ("Warangal", "Telangana", False),
    ("Nagpur", "Maharashtra", False),
    ("Nashik", "Maharashtra", False),
    ("Aurangabad", "Maharashtra", False),
    ("Thane", "Maharashtra", False),
    ("Surat", "Gujarat", False),
    ("Vadodara", "Gujarat", False),
    ("Rajkot", "Gujarat", False),
    ("Indore", "Madhya Pradesh", False),
    ("Bhopal", "Madhya Pradesh", False),
    ("Lucknow", "Uttar Pradesh", False),
    ("Kanpur", "Uttar Pradesh", False),
    ("Varanasi", "Uttar Pradesh", False),
    ("Agra", "Uttar Pradesh", False),
    ("Ghaziabad", "Delhi NCR", False),
    ("Faridabad", "Delhi NCR", False),
    ("Chandigarh", "Punjab", False),
    ("Ludhiana", "Punjab", False),
    ("Amritsar", "Punjab", False),
    ("Dehradun", "Uttarakhand", False),
    ("Patna", "Bihar", False),
    ("Ranchi", "Jharkhand", False),
    ("Bhubaneswar", "Odisha", False),
    ("Raipur", "Chhattisgarh", False),
    ("Guwahati", "Assam", False),
    ("Goa", "Goa", False),
    ("Udaipur", "Rajasthan", False),
    ("Jodhpur", "Rajasthan", False),
    ("Siliguri", "West Bengal", False),
]

CITIES = [
    {
        "name": name,
        "slug": name.lower().replace(" ", "-"),
        "state": state,
        "is_metro": metro,
    }
    for name, state, metro in _CITY_ROWS
]

POPULAR_CITIES = [c for c in CITIES if c["is_metro"]]
DEFAULT_CITY = "Bengaluru"

# ---------------------------------------------------------------------------
# How it works / features / pricing / FAQs
# ---------------------------------------------------------------------------

HOW_IT_WORKS = [
    {
        "step": 1,
        "title": "Choose your package",
        "icon": "gift",
        "text": (
            "Browse by occasion and pick a setup at a price that's already final. "
            "Every listing shows exactly what arrives with the decorator."
        ),
    },
    {
        "step": 2,
        "title": "Pick city and slot",
        "icon": "calendar",
        "text": (
            "Tell us where and when. We hold a two-hour arrival window and confirm "
            "the decorator assigned to you by name."
        ),
    },
    {
        "step": 3,
        "title": "Confirm and pay",
        "icon": "credit-card",
        "text": (
            "Pay 30% to lock the slot and the rest after setup. Free cancellation "
            "up to 24 hours before your arrival window."
        ),
    },
    {
        "step": 4,
        "title": "Decorator arrives",
        "icon": "truck",
        "text": (
            "They bring everything, set it up, photograph it for you and take the "
            "packaging away. You walk in to a finished room."
        ),
    },
]

FEATURES = [
    {
        "title": "Fixed pricing",
        "icon": "tag",
        "text": "The price on the card is the price on the invoice. No travel surcharge, no 'material adjustment' at the door.",
    },
    {
        "title": "Verified decorators",
        "icon": "shield",
        "text": "Every decorator is background-checked, trained on our setups and rated by customers after each booking.",
    },
    {
        "title": "On-time guarantee",
        "icon": "clock",
        "text": "If the setup isn't finished by the end of your arrival window, that booking is 25% off, applied automatically.",
    },
    {
        "title": "Real setup photos",
        "icon": "camera",
        "text": "Listing photos come from bookings we actually delivered, not stock libraries or renders.",
    },
    {
        "title": "100+ cities",
        "icon": "globe",
        "text": "Metro coverage with same-week slots, and a decorator network reaching fifty-two tier-two cities.",
    },
    {
        "title": "Same-day booking",
        "icon": "zap",
        "text": "Book before 2 PM for an evening setup in any metro. Selected packages go out in ninety minutes.",
    },
]

PRICING_ROWS = [
    {"category": "Birthday", "slug": "birthday", "range": "₹1,899 – ₹8,999", "popular": "₹3,499", "setup_time": "2–4 hrs"},
    {"category": "Anniversary", "slug": "anniversary", "range": "₹2,199 – ₹15,999", "popular": "₹4,999", "setup_time": "3–5 hrs"},
    {"category": "Baby Shower", "slug": "baby-shower", "range": "₹2,499 – ₹9,999", "popular": "₹5,299", "setup_time": "3–5 hrs"},
    {"category": "Kids Theme", "slug": "kids-theme", "range": "₹2,999 – ₹11,999", "popular": "₹5,199", "setup_time": "3–4 hrs"},
    {"category": "Wedding", "slug": "wedding", "range": "₹7,999 – ₹45,000", "popular": "₹16,999", "setup_time": "Full day"},
    {"category": "Romantic", "slug": "romantic", "range": "₹2,199 – ₹12,999", "popular": "₹5,499", "setup_time": "2–4 hrs"},
    {"category": "Newborn Welcome", "slug": "newborn-welcome", "range": "₹1,799 – ₹7,999", "popular": "₹3,299", "setup_time": "2–3 hrs"},
    {"category": "Corporate", "slug": "corporate", "range": "₹5,999 – ₹60,000", "popular": "₹18,999", "setup_time": "Before hours"},
    {"category": "Festival", "slug": "festival", "range": "₹2,499 – ₹14,999", "popular": "₹5,999", "setup_time": "3–5 hrs"},
]

FAQS = [
    {
        "question": "How far in advance should I book?",
        "answer": (
            "Three days is comfortable and gets you the widest choice of slots. "
            "Same-day booking is available in every metro if you order before 2 PM, "
            "and a handful of compact setups go out in ninety minutes."
        ),
    },
    {
        "question": "Is the price on the listing the final price?",
        "answer": (
            "Yes. The card price covers materials, labour, travel within city limits "
            "and clean-up. The only things that change it are add-ons you choose "
            "yourself at checkout, and they're priced before you pay."
        ),
    },
    {
        "question": "What if my venue has rules about walls and adhesive?",
        "answer": (
            "Tell us in the booking notes and the decorator switches to freestanding "
            "frames, weighted bases and removable clips. Most of our setups already "
            "work this way — we decorate a lot of rented flats and hotel rooms."
        ),
    },
    {
        "question": "Can I cancel or reschedule?",
        "answer": (
            "Reschedule free of charge up to 24 hours before your arrival window, "
            "once per booking. Cancel in the same window for a full refund of the "
            "advance. Inside 24 hours the advance covers materials already bought."
        ),
    },
    {
        "question": "Who takes down the decoration afterwards?",
        "answer": (
            "You can keep it up as long as you like — balloons hold three to five "
            "days indoors. Add next-morning take-down at checkout for ₹499 and a "
            "decorator returns to clear everything."
        ),
    },
    {
        "question": "Do you deliver to venues, not just homes?",
        "answer": (
            "Yes: banquet halls, restaurants, offices, hotel rooms, farmhouses and "
            "terraces. Share the venue's access rules when you book so the decorator "
            "arrives with the right permissions and the right ladder."
        ),
    },
    {
        "question": "Will the setup look like the photos?",
        "answer": (
            "Listing photos are from bookings we delivered. Fresh flowers and foil "
            "colours vary a little by city and season; if a substitution is needed "
            "we message you before the decorator leaves the warehouse."
        ),
    },
    {
        "question": "How do payments work?",
        "answer": (
            "Thirty percent confirms the slot. The rest is due after the setup is "
            "finished and you've seen it, by UPI, card or net banking. Corporate "
            "bookings can be invoiced with GST on request."
        ),
    },
]

# ---------------------------------------------------------------------------
# Time slots and cart (UI placeholders)
# ---------------------------------------------------------------------------

TIME_SLOTS = [
    {"label": "8 AM – 10 AM", "value": "08-10", "available": True},
    {"label": "10 AM – 12 PM", "value": "10-12", "available": True},
    {"label": "12 PM – 2 PM", "value": "12-14", "available": False},
    {"label": "2 PM – 4 PM", "value": "14-16", "available": True},
    {"label": "4 PM – 6 PM", "value": "16-18", "available": True},
    {"label": "6 PM – 8 PM", "value": "18-20", "available": True},
    {"label": "8 PM – 10 PM", "value": "20-22", "available": False},
]

ADD_ONS = [
    {"name": "Next-morning take-down", "price": 499},
    {"name": "Photographer, 60 minutes", "price": 1999},
    {"name": "Fresh flower upgrade", "price": 899},
    {"name": "Custom name signage", "price": 649},
]

CART_ITEMS = [
    {
        "id": 1,
        "package": PACKAGE_BY_SLUG["golden-hour-birthday-balloon-wall"],
        "quantity": 1,
        "city": "Bengaluru",
        "date": "22 August 2026",
        "slot": "4 PM – 6 PM",
        "add_ons": [{"name": "Custom name signage", "price": 649}],
    },
    {
        "id": 2,
        "package": PACKAGE_BY_SLUG["car-boot-surprise-setup"],
        "quantity": 2,
        "city": "Bengaluru",
        "date": "22 August 2026",
        "slot": "8 PM – 10 PM",
        "add_ons": [],
    },
]

# ---------------------------------------------------------------------------
# Helpers — replace these with querysets when models land
# ---------------------------------------------------------------------------


def _picsum(seed, width, height):
    return f"https://picsum.photos/seed/{seed}/{width}/{height}"


def _srcset(seed, sizes):
    """`sizes` is a list of (width, height) pairs, all the same aspect ratio."""
    return ", ".join(f"{_picsum(seed, w, h)} {w}w" for w, h in sizes)


def _hero_url(url_name, arg=None, anchor=""):
    if not url_name:
        return None
    path = reverse(url_name, args=[arg]) if arg else reverse(url_name)
    return f"{path}{anchor}"


# Landscape crops for tablet/desktop, a taller crop for phones. Two aspect
# ratios means <picture> art direction rather than one srcset, so a phone never
# downloads a 16:9 frame it would have to crop away.
HERO_WIDE = [(1280, 720), (1920, 1080), (2560, 1440)]
HERO_TALL = [(720, 900), (1080, 1350)]


def hero_slides():
    """
    Homepage hero slides, with URLs reversed and media URLs expanded.

    Stand-in for HeroSlide.objects.filter(is_active=True).order_by("position").
    URLs are reversed here rather than in the template because a slide can point
    at a detail route that needs an argument.
    """
    slides = []
    for position, slide in enumerate(HERO_SLIDES):
        row = dict(slide)
        seed = row["image_seed"]
        row["position"] = position
        row["is_first"] = position == 0
        row["image"] = _picsum(seed, 1920, 1080)
        row["image_srcset"] = _srcset(seed, HERO_WIDE)
        row["image_tall"] = _picsum(seed, 1080, 1350)
        row["image_tall_srcset"] = _srcset(seed, HERO_TALL)
        row["is_video"] = row["media_type"] == "video"
        row["cta_url"] = _hero_url(
            row.get("cta_url_name"), row.get("cta_url_arg"), row.get("cta_anchor", "")
        )
        row["cta2_url"] = _hero_url(
            row.get("cta2_url_name"), row.get("cta2_url_arg"), row.get("cta2_anchor", "")
        )
        slides.append(row)
    return slides


def get_category(slug):
    """Stand-in for get_object_or_404(Category, slug=slug)."""
    return CATEGORY_BY_SLUG.get(slug)


def get_package(slug):
    """Stand-in for get_object_or_404(Package, slug=slug)."""
    return PACKAGE_BY_SLUG.get(slug)


def packages_in_category(slug):
    """Stand-in for Package.objects.filter(category__slug=slug)."""
    return [p for p in PACKAGES if p["category"] == slug]


def featured_packages(limit=8):
    """Stand-in for Package.objects.filter(is_featured=True)[:limit]."""
    featured = [p for p in PACKAGES if p["is_featured"]]
    if len(featured) < limit:
        featured += [p for p in PACKAGES if not p["is_featured"]]
    return featured[:limit]


def related_packages(package, limit=6):
    """Same category first, then anything else, excluding the package itself."""
    same = [p for p in PACKAGES if p["category"] == package["category"] and p["slug"] != package["slug"]]
    others = [p for p in PACKAGES if p["category"] != package["category"]]
    return (same + others)[:limit]


def reviews_for(package, limit=5):
    """Reviews attached to a package. Stand-in for package.reviews.all()."""
    matching = [t for t in TESTIMONIALS if t["occasion"] == package["title"]]
    filler = [t for t in TESTIMONIALS if t["occasion"] != package["title"]]
    return (matching + filler)[:limit]


def category_counts():
    """Attach a live package count to each category, as annotate(Count(...)) would."""
    rows = []
    for category in CATEGORIES:
        row = dict(category)
        row["sample_count"] = len(packages_in_category(category["slug"]))
        row["image"] = f"https://picsum.photos/seed/cat-{category['slug']}/600/450"
        rows.append(row)
    return rows


def cart_summary(items=None):
    """Totals for the cart page. Replace with a Cart model method later."""
    items = CART_ITEMS if items is None else items
    lines = []
    subtotal = 0
    savings = 0
    for item in items:
        add_on_total = sum(a["price"] for a in item["add_ons"])
        line_total = (item["package"]["price"] + add_on_total) * item["quantity"]
        savings += item["package"]["saving"] * item["quantity"]
        subtotal += line_total
        line = dict(item)
        line["add_on_total"] = add_on_total
        line["line_total"] = line_total
        lines.append(line)
    delivery = 0 if subtotal >= 3000 else 249
    tax = round(subtotal * 0.18)
    return {
        "lines": lines,
        "subtotal": subtotal,
        "savings": savings,
        "delivery": delivery,
        "tax": tax,
        "total": subtotal + delivery + tax,
        "free_delivery_threshold": 3000,
    }
