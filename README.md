# Celebra

**Celebrations, Beautifully Delivered.**

A balloon and event decoration booking platform: a public site built with Django
templates, hand-written CSS and vanilla JavaScript, and a staff control panel at
`/manage/` that edits every word, price and picture the public site shows.

No JavaScript frameworks, no CSS frameworks, no build step. The only dependency
is Django.

---

## Run it locally

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
content tables first, and `--bookings N` to change how much demo history it
generates.

## Pages

| URL | View | Template |
| --- | --- | --- |
| `/` | `core.views.home` | `core/home.html` |
| `/products/` | `core.views.products` | `core/products.html` |
| `/categories/` | `core.views.categories` | `core/categories.html` |
| `/category/<slug>/` | `core.views.category_detail` | `core/category_detail.html` |
| `/package/<slug>/` | `core.views.package_detail` | `core/package_detail.html` |
| `/how-it-works/` | `core.views.how_it_works` | `core/how_it_works.html` |
| `/contact/` | `core.views.contact` | `core/contact.html` |
| `/cart/` | `core.views.cart` | `core/cart.html` |
| `/manage/…` | `panel.views` | `panel/…` |
| `/admin/` | Django's own admin | — |
| `/preview/404/` | `core.views.page_not_found` | `404.html` |

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

### What it manages

| Group | Sections |
| --- | --- |
| Operations | Bookings, Enquiries, Decorators, Coupons |
| Catalogue | Products, Occasions, Gallery photos, Add-ons, Pricing table |
| Homepage | Hero slider, Reviews, Promises, How it works, FAQs, Trust badges |
| Site | Cities, Time slots, Menu links |
| System | Media, Activity, Staff & access, Site settings |

Plus a **Dashboard** (revenue and booking trends, status mix, top-earning
packages, overdue jobs, content alerts) and a **Schedule** — six weeks of
calendar with every booking placed on its date.

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
- **Ctrl-K** anywhere opens a command palette that searches packages, bookings,
  hero slides, enquiries and the sections themselves
- Light and dark appearance, stored per account

### Roles

Four, ranked. Set under *Staff & access*; each one includes everything below it.

| Role | Can |
| --- | --- |
| `viewer` | Read every section. Open records. Change nothing. |
| `editor` | Content and bookings. |
| `admin` | The above plus cities, coupons, decorators, time slots, site settings. |
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
| `Category` | The occasions. `live_count` counts published packages |
| `Package` | `includes_text` is one bullet per line; `discount_percent`, `saving`, `gallery` are derived |
| `PackageImage` | Detail-page gallery, ordered |
| `HeroSlide` | The homepage deck, with scheduling |
| `Testimonial` | Attach one to a package and it also shows on that package's page |
| `FAQ` `Feature` `HowItWorksStep` `PricingRow` `TrustBadge` `NavLink` | Homepage copy blocks |
| `City` `TimeSlot` `AddOn` | Booking options |
| `Booking` | The operational record. `is_overdue` is what the dashboard shouts about |
| `Enquiry` | Contact-form messages |
| `Decorator` `Coupon` | Crews and discount codes |
| `StaffProfile` `InviteCode` `ActivityLog` | Panel accounts and audit trail |

Two abstract bases do most of the repetitive work: `Positioned` (a `position`
field plus ordering, which the drag handles write) and `PictureMixin` (the
upload-or-URL pair and the `image` property).

### Still to wire up

- **The cart** has no persistence. `queries.demo_cart_items()` builds two lines
  from real packages so the page has something to lay out; a real cart needs a
  session or a `Cart` model.
- **The booking form** on the package page posts nowhere. Point it at a view
  that creates a `Booking` and the panel picks it up with no other changes.
- **Payments** are described in the copy but not implemented.
- **Hero video URLs** seeded by `seed_demo` are Google's public sample files.
  Replace them with your own encodes — 1920×1080 H.264, no audio track, a few MB.
- **Photographs** are `picsum.photos` placeholders until something is uploaded.

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
- sticky mobile booking bar, listing filter drawer, budget slider, cart steppers
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
- `SECRET_KEY` and `DEBUG` in `celebra/settings.py` are development values. Move
  them to environment variables before deploying, and serve `MEDIA_ROOT` from
  the web server rather than Django.
