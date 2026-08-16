# Celebra

**Celebrations, Beautifully Delivered.**

Frontend for a balloon and event decoration booking platform, built with Django
templates, hand-written CSS and vanilla JavaScript. Every page renders from
sample data shaped like model instances, so the backend can be dropped in
without touching the templates.

---

## Run it locally

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python manage.py migrate          # optional: only for the admin/session tables
python manage.py runserver
```

Open <http://127.0.0.1:8000/>.

There are no models yet, so `migrate` is only needed if you want the Django
admin. The site renders fine without it.

## Pages

| URL | View | Template |
| --- | --- | --- |
| `/` | `core.views.home` | `core/home.html` |
| `/categories/` | `core.views.categories` | `core/categories.html` |
| `/category/<slug>/` | `core.views.category_detail` | `core/category_detail.html` |
| `/package/<slug>/` | `core.views.package_detail` | `core/package_detail.html` |
| `/how-it-works/` | `core.views.how_it_works` | `core/how_it_works.html` |
| `/contact/` | `core.views.contact` | `core/contact.html` |
| `/cart/` | `core.views.cart` | `core/cart.html` |
| `/preview/404/` | `core.views.page_not_found` | `404.html` |

`/preview/404/` exists because Django shows its own debug page for real 404s
while `DEBUG = True`. Set `DEBUG = False` (and `ALLOWED_HOSTS`) to see the
styled 404 on a genuine miss.

Sample slugs to try: `/category/birthday/`, `/category/kids-theme/`,
`/package/golden-hour-birthday-balloon-wall/`,
`/package/rooftop-proposal-setup/`.

## Project layout

```
celebra/                        project package
  settings.py  urls.py  wsgi.py  asgi.py
core/                           the single app
  sample_data.py                all dummy content lives here
  views.py                      function-based views, one per page
  urls.py                       app_name = "core", named patterns
  context_processors.py         brand, nav, cities, cart count on every page
  templates/
    base.html                   blocks: title, meta_description, content,
                                extra_css, extra_js
    404.html
    core/
      home.html  categories.html  category_detail.html
      package_detail.html  how_it_works.html  contact.html  cart.html
      partials/
        _icons.html             inline SVG sprite (all icons)
        _navbar.html  _footer.html
        _package_card.html      the one card used on every grid
        _category_chip.html  _testimonial_card.html  _faq_item.html
        _section_head.html      heading + the garland rule
        _stars.html  _breadcrumbs.html  _pagination.html  _inquiry_form.html
  static/core/
    css/theme.css               design tokens, reset, base type
    css/style.css               components and layout (mobile-first)
    css/responsive.css          min-width media queries
    js/main.js                  nav, accordion, carousel, gallery, cart, reveal
```

## Design system

Colours are CSS custom properties in `static/core/css/theme.css`. Change them
in `:root` and the whole site follows.

| Token | Value | Used for |
| --- | --- | --- |
| `--color-primary` | `#0F6B66` | Deep teal — primary buttons, links, headings |
| `--color-accent` | `#FF7A59` | Warm coral — primary CTA fills, eyebrows |
| `--color-gold` | `#F5B942` | Sunflower — discount badges, footer headings |
| `--color-charcoal` | `#1E2328` | Body text, footer background |
| `--color-ivory` | `#FBF8F3` | Page background |
| `--color-amber` | `#F5A623` | Rating stars |

Type: **Fraunces** for display, **Plus Jakarta Sans** for body and UI, both
from Google Fonts.

The recurring mark is the **garland rule** — an arc with three balloons that
sits above every section heading (`_section_head.html`) and forms the logo.
It is the one decorative device on the site; everything else stays quiet.

## Swapping in a real backend

Everything the templates read comes from dicts in `core/sample_data.py`, keyed
exactly the way model fields would be. To go live:

1. **Define the models** in `core/models.py` with matching field names:
   - `Category(name, slug, icon, blurb, price_from)`
   - `Package(title, slug, image, price, original_price, rating, review_count,
     duration, badge, description, is_featured, category → FK)`
   - `PackageImage(package → FK, image, alt)` for the gallery
   - `Testimonial(name, city, rating, text, occasion, date)`
   - `City(name, slug, state, is_metro)`, `FAQ(question, answer)`
2. **Add the derived fields** the templates use — `discount_percent` and
   `saving` — as model properties, or annotate them on the queryset. The
   sample data computes them in `sample_data._decorate()`.
3. **Replace the lookups in `core/views.py`.** They are already isolated:

   ```python
   # now                                  # later
   data.featured_packages(limit=8)        Package.objects.filter(is_featured=True)[:8]
   data.get_package(slug)                 get_object_or_404(Package, slug=slug)
   data.packages_in_category(slug)        Package.objects.filter(category__slug=slug)
   data.cart_summary()                    request.cart.summary()
   ```

   The filter/sort/paginate block in `category_detail` already uses Django's
   `Paginator`, so only the list comprehensions become `.filter()` calls.
4. **Wire the forms.** `_inquiry_form.html` and the booking form on the package
   page already carry `{% csrf_token %}` and POST to their own URL — add a
   Django `Form`, handle `request.method == "POST"` in the view, and render
   field errors. (The two GET forms — hero search and listing filters —
   deliberately have no token, since it would end up in the query string.)
5. **Swap the images.** Every `src` is a `picsum.photos` placeholder coming
   from the sample data, never hardcoded in a template. Point `image` at an
   `ImageField` URL and the templates keep working.

Nothing in `templates/` or `static/` needs to change for any of this.

## What the JavaScript does

`static/core/js/main.js`, no dependencies, each block bails out if its markup
is absent:

- sticky-header shade on scroll
- mobile drawer with scrim and body scroll lock
- city picker dropdown plus live city filtering (header list and coverage grid)
- FAQ accordion — animated height, one answer open per group
- testimonial carousel — autoplay, arrows, dots, swipe, off-slide links pulled
  out of the tab order
- horizontal scroller arrows for the related-packages rail
- scroll reveal via `IntersectionObserver`
- package gallery with thumbnails and a keyboard-navigable lightbox
- sticky mobile booking bar on the package page
- listing filter drawer, budget slider readout, auto-submitting sort
- cart quantity steppers and line removal, with the summary recalculating

`prefers-reduced-motion` disables autoplay, smooth scrolling and the reveal
animation throughout.

## Notes

- Breakpoints: 480, 640, 768, 1024, 1280, 1440. Base styles are the phone
  layout; `responsive.css` only scales up.
- Semantic landmarks, skip link, visible focus rings, 44px minimum tap
  targets, `loading="lazy"` on everything below the fold.
- `SECRET_KEY` and `DEBUG` in `celebra/settings.py` are development values.
  Move them to environment variables before deploying.
