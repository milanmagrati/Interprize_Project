# Celebra

**Celebrations, Beautifully Delivered.**

A balloon and event decoration booking platform: a public site built with Django
templates, hand-written CSS and vanilla JavaScript, and a staff control panel at
`/manage/` that edits every word, price and picture the public site shows.

No JavaScript frameworks, no CSS frameworks, no build step. The only dependency
is Django.

---

## Run it locally

Settings are read from a `.env` file at the project root (via `python-decouple`) —
copy `.env.example` to `.env` and fill in real values, especially `DB_PASSWORD`.
The project runs on MySQL, so create an empty database first (name must match
`DB_NAME` in `.env`):

```sql
CREATE DATABASE celebra_db CHARACTER SET utf8mb4;
```

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo          # fills the database with the sample catalogue
python manage.py runserver
```

Open <http://127.0.0.1:8000/> for the site and
<http://127.0.0.1:8000/manage/signup/> to create the first staff account.

**The first account you create becomes the owner.** After that the signup page
demands an invite code, which owners generate under *Staff & access* — so the
signup URL can stay public without the panel being public.

`seed_demo` is optional but recommended; without it the site renders with empty
sections until you add content through the panel. It takes `--reset` to wipe the
content tables first.

## Pages

| URL | View | Template |
| --- | --- | --- |
| `/` | `core.views.home` | `core/home.html` |
| `/products/` | `core.views.products` | `core/products.html` |
| `/occasions/` | `core.views.categories` | `core/categories.html` |
| `/occasions/<slug>/` | `core.views.category_detail` | `core/category_detail.html` |
| `/package/<slug>/` | `core.views.package_detail` | `core/package_detail.html` |
| `/book/` | `core.views.book` | `core/book.html` |
| `/bookings/` | `core.views.track` | `core/track.html` |
| `/bookings/<number>/` | `core.views.booking_status` | `core/booking_status.html` |
| `/enquire/` | `core.views.enquire` | `core/enquire.html` |
| `/how-it-works/` | `core.views.how_it_works` | `core/how_it_works.html` |
| `/contact/` | `core.views.contact` | `core/contact.html` |
| `/manage/…` | `panel.views` | `panel/…` |
| `/admin/` | Django's own admin | — |
| `/preview/404/` | `core.views.page_not_found` | `404.html` |

The old `/categories/`, `/category/<slug>/` and `/cart/` addresses redirect to
`/occasions/…` and `/book/`.

`/preview/404/` exists because Django shows its own debug page for real 404s
while `DEBUG = True`. Set `DEBUG = False` (and `ALLOWED_HOSTS`) to see the styled
404 on a genuine miss.

### The products page

`/products/` is the whole catalogue in one place, reached from **Products** in
the header (a `NavLink` row, so it can be renamed or removed from the panel).
The homepage keeps a slice of the same catalogue and a button through to here.

It filters on search text, occasion, budget, rating, discount, featured and
label, sorts seven ways and pages — all of it in one queryset, so the count, the
ordering and the page can never disagree. `discount_pc` is annotated in
`core.queries.product_queryset()` rather than derived in Python, which is what
lets "biggest saving" sort in the database.

The same view answers `?partial=1` with only the results block. That is what
`main.js` fetches when a filter moves: results swap in, the URL is rewritten
with `pushState`, and the cards stagger back. Every control is also a plain GET
form or a real link, so the page works identically with JavaScript off.

What the panel controls, under **Site settings**:

| Section | Sets |
| --- | --- |
| Products on the homepage | eyebrow, heading, sub-heading, which products, how many, button label |
| The products page | eyebrow, heading, sub-heading, products per page |

The products themselves are **Catalogue → Products**; drag them there to set the
order the "Featured first" and "hand-ordered" modes use.

## Project layout

```
celebra/                        project package
  settings.py  urls.py  wsgi.py  asgi.py
core/                           the public site and all the models
  models.py                     every content model, with the properties the
                                templates read (discount_percent, gallery, …)
  queries.py                    published-only read helpers used by the views
  views.py                      function-based views, one per page
  forms.py                      the public enquiry form
  admin.py                      Django admin registrations
  urls.py                       app_name = "core", named patterns
  context_processors.py         brand, nav, cities, cart count on every page
  sample_data.py                the original dummy content; now only read by
                                the seed_demo command
  management/commands/
    seed_demo.py                loads sample_data into the database
  templates/
    base.html                   blocks: title, meta_description, content,
                                extra_css, extra_js
    404.html
    core/
      home.html  categories.html  category_detail.html
      package_detail.html  how_it_works.html  contact.html  cart.html
      partials/
        _icons.html             inline SVG sprite (all icons)
        _hero_slider.html       homepage hero deck (images + video)
        _navbar.html  _footer.html
        _package_card.html      the one card used on every grid
        _category_chip.html  _testimonial_card.html  _faq_item.html
        _section_head.html      heading + the garland rule
        _stars.html  _breadcrumbs.html  _pagination.html  _inquiry_form.html
  static/core/
    css/theme.css               design tokens, reset, base type
    css/style.css               components and layout (mobile-first)
    css/responsive.css          min-width media queries
    js/main.js                  hero slider, nav, accordion, carousel,
                                gallery, cart, reveal
panel/                          the staff control panel
  resources.py                  the registry: one entry per managed model
  views.py                      account flow, generic CRUD, bespoke pages
  forms.py                      model forms and the signup/login forms
  permissions.py                the four roles and the access decorators
  urls.py                       everything under /manage/
  templatetags/panel_tags.py    cell rendering, sorting links, querystrings
  templates/panel/              base.html, auth/, resources/, pages/, partials/
  static/panel/                 panel.css, panel.js
```

## The control panel

`/manage/`. Sign in with a staff account; everything below is behind that.

### Occasions, products and events

Three words, three different things. Keep them apart:

| | Occasion | Product | Event |
| --- | --- | --- | --- |
| What it is | A *kind* of celebration — Birthday, Wedding, Tihar | A ready-made decoration design for one occasion, at a fixed price | *One real job* for one customer, on one date, at one venue |
| Model | `Category` | `Package` | `Event` |
| In the panel | Catalogue → Occasions | Catalogue → Products | Events |
| On the site | browsed: `/occasions/`, menus, filters | browsed and picked: `/products/`, `/package/<slug>/` | booked at `/book/`, followed at `/bookings/EVT-…` |
| Lifetime | Permanent. Retired by switching *Live* off | Published or unpublished | Draft → Confirmed → In progress → Completed / Cancelled |

An occasion has many products and many events. **Every event is of exactly one
occasion** and may use one product of that occasion — pick a product and its occasion
is filled in. An occasion that has events cannot be deleted (their history would
lose what they were); switch it off instead. The Events list filters by occasion,
each occasion's page in the panel links to its events, and the dashboard ranks
occasions by what their events earned.

The code and URLs call a product a `Package` (`/package/<slug>/`); everything a
person reads says **product**. The word *setup* is kept only for the act of
setting up — "delivery, setup and clean-up", "Setup time". What arrives on site
is the *decoration*, and what sits on a shelf is a *stock item*.

### What it manages

| Group | Sections |
| --- | --- |
| Events | Events, Enquiries, Customers |
| Operations | Staffs, Staff types, Coupons |
| Inventory | Counter, Stock room, Stock items, Stock groups, Suppliers, Stock ledger, Counter sales |
| Catalogue | Products, Occasions, Gallery photos, Add-ons, Pricing table |
| Homepage | Hero slider, Reviews, Promises, How it works, FAQs, Trust badges |
| Site | Cities, Time slots, Menu links |
| System | Media, Activity, Staff & access, Site settings |

Plus a **Dashboard** (revenue and event trends, status mix, the occasions
earning most, events past their date, content alerts) and a **Schedule** — six
weeks of calendar with every event placed on its date. Both read events: there
is one record of the work, whether it was booked on the site, from an enquiry or
in the panel.

### Inventory and the counter

Two screens and five tables, all under `/manage/`:

- **Counter** (`/manage/counter/`) is the till. Search, filter or scan a SKU or
  barcode to drop an item into the basket, set quantities, take a discount, add
  tax, record what was tendered, and close the sale. The basket lives in the
  session, so a reload or a lookup on another screen does not lose it. Closing a
  sale writes the receipt, snapshots each line's name, price and cost, and takes
  the stock off the shelf in one transaction. It refuses to sell more than there
  is. Editor role and above.
- **Stock room** (`/manage/stock/`) is the inventory dashboard: what the shelves
  are worth at cost and at retail, what is at or under its reorder level and who
  supplies it, fourteen days of counter takings, best sellers, value by group,
  the payment mix and the latest ledger rows.
- **Stock items** carry a SKU (generated if you leave it blank), a group, a
  supplier, a unit, a shelf, a reorder level, cost and sale prices, and a photo.
  The list shows the count with its own verdict — in stock, running low, out —
  and filters on exactly that.
- **Stock ledger** is append-only: every unit in or out with a reason, who did
  it, and the balance it left behind. Receiving stock, writing off breakages and
  correcting a count all happen here. The reason decides the direction, so you
  type a plain number; only a stock-count adjustment takes a minus sign.
- **Counter sales** are the receipts. They cannot be created or edited into
  something else — a receipt that could be rewritten is not a record — but the
  customer, payment method and notes stay editable, and each has a printable
  page with a **Refund** that puts every line back on the shelf.

The count on an item is never typed. `InventoryItem.quantity` is written only by
`StockMovement.save()`, under `select_for_update` on the item, so two people
receiving stock at once cannot lose a count and the ledger always reconciles
with the shelf.

At the till: `/` jumps to the scanner, the basket has `−`/`+` steppers and an
editable unit price, and the tally recalculates as the discount, tax and cash
taken are typed. All of that is an enhancement over plain forms — every control
is a real POST that works with JavaScript off, and the basket lives in the
session rather than in the page. On a narrow screen the basket moves below the
shelves and a bar pinned to the bottom carries the running total back to it.

### Events

`/manage/events/` runs the events the company delivers, under the **Events**
sidebar group next to **Customers**.

- **Events** have a number (`EVT-00001`), a customer, occasion, date, arrival
  window, location, guests, a crew of staff members, revenue and notes, and move Draft → Confirmed → In progress → Completed (or
  Cancelled) through buttons on the event page — never by editing a field.
- **Items** are either *inventory* (an existing stock item, never copied) or
  *external* (rented, bought in or outsourced; it never enters stock).
  "Add from inventory" is a picture grid: tick any number of items, set a
  quantity on each, and they are added together — all of them or none, with
  every shortfall named. External items can carry their own photo; stock lines
  show the stock item's.
- **Stock is held, not taken.** Reserving 30 of 100 chairs leaves the count at
  100 and makes 70 free. Reusable stock comes back (returned, damaged or lost —
  only damage and loss lower the count); consumable stock is consumed or
  returned unused. Available = on hand − held by every event. The counter
  respects holds too. Every reserve, return, use, damage and loss is a row in
  the stock ledger, e.g. “30 × Chair reserved for EVT-00001”.
- Holds change under `select_for_update` locks on the stock items, so two
  people cannot reserve the last units at once, and a shortfall is refused
  (“Only 10 units are available.”) instead of going negative. Cancelling
  releases everything; *Finalise inventory* settles what is still out after
  completion.
- **Expenses** and **payments** are recorded per event. Total cost = external
  items + consumables used + reusable stock damaged or lost + expenses;
  profit = revenue − total cost; remaining = revenue − paid.
- Viewers can read, editors can run events, admins can delete a draft or
  cancelled event. Logic lives on the models in `core/models.py`; the views are
  in `panel/event_views.py`; tests in `core/test_events.py` and
  `panel/test_events.py`.

#### Booked from the website

An **occasion** (Birthday, Wedding…) is the kind of event; an **event** is one
booking of it (see *Occasions, products and events* above). Visitors book at
`/book/` — occasion, an optional product, date, arrival window, venue, extras and their details — and that becomes
a **draft event** marked *New* on the Events page (and counted in the sidebar),
with the customer matched by phone number or added. Nothing is charged online:
the team calls, presses *Confirm event*, and the customer's page at
`/bookings/EVT-00012/` follows every step. The browser that booked can open it
directly; anyone else needs the number and the phone. A request can be
withdrawn online until it is confirmed.

Visitors not ready to book use **Ask a question** (`/enquire/`, and the form on
the home, contact, occasion and product pages). Enquiries land under
Operations → Enquiries, where *Create event* opens a new event already filled
in from the enquiry and links the two. Tests: `core/test_booking.py`.

### How it is built

Every managed model is declared once in `panel/resources.py`:

```python
Resource(
    slug="packages",
    model=m.Package,
    form_class=f.PackageForm,
    label="Package", plural="Packages",
    icon="box", group="Catalogue",
    columns=[
        Column("image", "", "image"),
        Column("title", "Package", sortable="title", hint="category_name"),
        Column("price", "Price", "money", sortable="price", hint="discount_label"),
        Column("is_active", "Live", "toggle", sortable="is_active"),
    ],
    search_fields=["title", "slug", "description", "category__name"],
    filters=[Filter("category", "Occasion", [], lookup="category__slug")],
    orderable=True,
    preview_url="get_absolute_url",
)
```

From that one declaration the panel generates the list page, the create and edit
forms, the delete confirmation, five URLs, CSV export, and the sidebar entry.
Adding a model to the panel is an entry in `RESOURCES` and a `ModelForm` — not a
new view, new URLs and two new templates.

That is why every section behaves the same way:

- **Search** across the declared fields, **filters** as dropdown chips,
  **sorting** by clicking a column heading
- **Inline switches** for booleans — publish, feature, verify — saved over fetch
  without leaving the page
- **Drag to reorder** on lists that have a position (hero slides, occasions,
  FAQs, promises, menu links)
- **Bulk actions**: select rows (shift-click for a range) and turn a flag on or
  off across all of them, or delete them
- **CSV export** of exactly what is on screen, filters and sort included
- **Ctrl-K** anywhere opens a command palette that searches events, customers,
  packages, hero slides, enquiries and the sections themselves
- Light and dark appearance, stored per account

### Roles

Four, ranked. Set under *Staff & access*; each one includes everything below it.

| Role | Can |
| --- | --- |
| `viewer` | Read every section. Open records. Change nothing. |
| `editor` | Content and events. |
| `admin` | The above plus staff records and types, cities, coupons, time slots, site settings. |
| `owner` | The above plus staff accounts and invite codes. |

Roles are enforced in the view, not just hidden in the template — a `viewer`
POSTing to an edit URL is refused, and the inline-toggle endpoint answers 403.
Django's own `is_staff` / `is_superuser` are kept in step, so `/admin/` never
disagrees with what the panel shows.

Every create, edit, delete and bulk action is written to the **activity log**
with who did it.

### Uploads

Images and videos are attached to the record that needs them. Each picture field
is a pair — upload a file, *or* paste a URL — and the model's `image` property
resolves whichever is set, falling back to a deterministic placeholder so a
half-filled record still renders a picture instead of a broken `<img>`.

Uploads land in `MEDIA_ROOT` (`media/`, gitignored) and Django serves them while
`DEBUG` is on. In production, point the web server at that directory.

Files are stored as `FileField`, not `ImageField`, so **Pillow is not required**
— the trade-off is that uploads are served at their original size rather than in
a generated width ladder.

## The homepage hero slider

`_hero_slider.html` + section 4 of `style.css` + section 15 of `main.js`.
Content comes from the `HeroSlide` model, edited under *Homepage → Hero slider*:

| Field | Meaning |
| --- | --- |
| `media_type` | `image` or `video` |
| `image_file` / `image_url` | Background. On a video slide this is the poster frame |
| `video_file` / `video_mp4` / `video_webm` | Video sources |
| `eyebrow` `heading` `heading_accent` `description` `meta` `alt` | Copy |
| `cta_label` / `cta_url_name` / `cta_url_arg` / `cta_anchor` | Primary button |
| `cta2_*` | Optional secondary button |
| `duration` | Milliseconds on screen before advancing |
| `tint` | Scrim hue: `night`, `teal` or `plum` |
| `focal` | `object-position` for the crop |
| `is_active` / `starts_at` / `ends_at` | Publishing and scheduling |

Add, reorder or remove slides and everything follows — dots, counter, the
progress bar and the announcement text are all generated from the list length.
Slides can be scheduled: a Diwali slide set to expire on 3 November drops out of
the deck on its own.

The button target is a dropdown of named routes rather than free text, because
`{% url %}` raises on a bad name and would take down every page that renders it.

Behaviour: autoplay with a per-slide duration, crossfade plus a slow push-in on
the media, staggered copy, arrows, progress dots, a slide counter, swipe, arrow
keys, and a pause/play button. Videos autoplay muted, loop, and play inline.

Loading: only slide 1 ships a real `srcset` (with a `<link rel=preload>` in the
page head); the rest carry `data-srcset` and are hydrated one slide ahead of
where the reader is. Video files are `preload="none"` and fetched when their
slide is about to come up, over a poster that stays put if autoplay is refused.
Placeholder images are served art-directed — a 4:5 crop to phones, 16:9 to
everything else; uploaded files have no derivatives so the `<source>` elements
are skipped and the `<img>` serves every viewport.

Autoplay stops when the deck scrolls out of view, when the tab is hidden, while
a keyboard focus ring is inside it, and whenever the reader presses pause. Under
`prefers-reduced-motion` it opens paused — the play button still works. With
JavaScript off, slide 1 renders as a plain static hero and the controls hide.

## The data model

`core/models.py`. Everything the public templates read is either a field or a
property with the same name, which is why the templates did not change when the
database arrived.

| Model | Notes |
| --- | --- |
| `SiteSettings` | Singleton. Brand, contact, socials, checkout numbers, announcement, maintenance mode |
| `Category` | The occasions. `live_count` counts published packages, `event_total` the events booked as it |
| `Package` | `includes_text` is one bullet per line; `discount_percent`, `saving`, `gallery` are derived |
| `PackageImage` | Detail-page gallery, ordered |
| `HeroSlide` | The homepage deck, with scheduling |
| `Testimonial` | Attach one to a package and it also shows on that package's page. `booked` is the product shown as "Booked …", filled from the package |
| `FAQ` `Feature` `HowItWorksStep` `PricingRow` `TrustBadge` `NavLink` | Homepage copy blocks |
| `City` `TimeSlot` `AddOn` | Booking options |
| `Customer` `Event` | The operational record: who, what, when, the crew, and the money. See *Events* above |
| `Enquiry` | Questions from the site; can become an event |
| `StaffMember` `StaffCategory` | The people on an event's crew, and the type of work each does |
| `Coupon` | Discount codes |
| `Supplier` `StockCategory` | Who stock is bought from, and how the store room is divided |
| `InventoryItem` | One SKU on a shelf. `quantity` is read-only — the ledger writes it |
| `StockMovement` | The append-only stock ledger. `save()` applies the change and records `balance_after` |
| `CounterSale` `CounterSaleLine` | Walk-in sales. Totals and line prices are stored, not derived, so an old receipt still reads true |
| `StaffProfile` `InviteCode` `ActivityLog` | Panel accounts and audit trail. A `StaffMember` links to one through `account` when that person also signs in |

Two abstract bases do most of the repetitive work: `Positioned` (a `position`
field plus ordering, which the drag handles write) and `PictureMixin` (the
upload-or-URL pair and the `image` property).

### Still to wire up

- **Payments** are described in the copy but not implemented.
- **Hero video URLs** seeded by `seed_demo` are Google's public sample files.
  Replace them with your own encodes — 1920×1080 H.264, no audio track, a few MB.
- **Photographs** are `picsum.photos` placeholders until something is uploaded.

### On a phone

The panel's list tables are wide by nature, so below 720px each row folds into a
card with its column names beside the values (`table--stack`), rather than a
680px-wide table behind a horizontal scrollbar. Bespoke tables that are already
narrow — the receipt, the reorder list — keep their shape at every width.

## Design system

Public-site colours are CSS custom properties in `static/core/css/theme.css`.
Change them in `:root` and the whole site follows. The panel carries its own
tokens at the top of `static/panel/css/panel.css`, including the dark palette.

| Token | Value | Used for |
| --- | --- | --- |
| `--color-primary` | `#0F6B66` | Deep teal — primary buttons, links, headings |
| `--color-accent` | `#FF7A59` | Warm coral — primary CTA fills, eyebrows |
| `--color-gold` | `#F5B942` | Sunflower — discount badges, footer headings |
| `--color-charcoal` | `#1E2328` | Body text, footer background |
| `--color-ivory` | `#FBF8F3` | Page background |
| `--color-amber` | `#F5A623` | Rating stars |

Type: **Fraunces** for display, **Plus Jakarta Sans** for body and UI, both from
Google Fonts. The panel uses Plus Jakarta Sans throughout.

The recurring mark is the **garland rule** — an arc with three balloons that sits
above every section heading (`_section_head.html`) and forms the logo. It is the
one decorative device on the site; everything else stays quiet.

## What the JavaScript does

**`static/core/js/main.js`** — the public site. No dependencies, each block bails
out if its markup is absent:

- hero slider — autoplay, crossfade, arrows, progress dots, swipe, arrow keys,
  pause/play, lazy media hydration, muted looping inline video
- sticky-header shade on scroll
- mobile drawer with scrim and body scroll lock
- city picker dropdown plus live city filtering
- FAQ accordion — animated height, one answer open per group
- testimonial carousel — autoplay, arrows, dots, swipe
- horizontal scroller arrows for the related-packages rail
- scroll reveal via `IntersectionObserver`
- package gallery with thumbnails and a keyboard-navigable lightbox
- sticky mobile booking bar, listing filter drawer, budget slider
- the booking form — live summary and estimate, products filtered to the occasion
- the header's Products drop-down — hover intent, keyboard focus, Escape to close
- the products listing — live search, instant facets, a two-thumb budget slider,
  grid/list layout, and paging that swaps results in over `fetch` with history
  entries to match

**`static/panel/js/panel.js`** — the control panel, same style:

- sidebar drawer, user menu, dismissible toasts
- the Ctrl-K command palette, with keyboard navigation
- inline switches over fetch, with a reload as the honest fallback on failure
- bulk selection, including shift-click ranges
- drag-to-reorder, saving the new order in one request
- auto-submitting filter dropdowns, confirmation prompts, unsaved-changes guard
- slug generated from the title until you type your own
- upload previews, click-to-copy invite codes, instant theme swap

`prefers-reduced-motion` disables autoplay, smooth scrolling and the reveal
animation throughout.

## Notes

- Breakpoints: 480, 640, 768, 1024, 1280, 1440. Base styles are the phone
  layout; `responsive.css` only scales up.
- Semantic landmarks, skip link, visible focus rings, 44px minimum tap targets,
  `loading="lazy"` on everything below the fold.
- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` and the database credentials all come
  from `.env` (see `.env.example`) — nothing is hardcoded in
  `celebra/settings.py`. Serve `MEDIA_ROOT` from the web server rather than
  Django once `DEBUG=False`.
