"""
Read helpers for the public site.

These are the functions the views used to import from `sample_data`; the
signatures are unchanged, only the bodies now hit the database. Keeping them in
one place means a caching layer or a switch to a different store is a change to
this file alone.

Everything filters on the published flags, so the panel's publish/unpublish
toggles are the single control over what the public sees.
"""

from datetime import timedelta

from django.db.utils import DatabaseError
from django.utils import timezone

from .models import (
    AddOn,
    Category,
    City,
    FAQ,
    Feature,
    HeroSlide,
    HowItWorksStep,
    NavLink,
    Package,
    PricingRow,
    SiteSettings,
    Testimonial,
    TimeSlot,
    TrustBadge,
)

# Shown when the database has not been migrated yet, so a fresh clone renders
# a page instead of a 500 while you are still typing `manage.py migrate`.
FALLBACK_BRAND = {
    "name": "Celebra",
    "tagline": "Celebrations, Beautifully Delivered",
    "phone": "+91 98765 43210",
    "phone_href": "+919876543210",
    "email": "hello@celebra.in",
    "address": "",
    "hours": "",
    "founded_year": 2019,
    "announcement": "",
}


def site_settings():
    try:
        return SiteSettings.objects.current()
    except DatabaseError:
        return None


def brand():
    return site_settings() or FALLBACK_BRAND


def _safe(queryset, default=()):
    """Evaluate a queryset, tolerating an un-migrated database."""
    try:
        return list(queryset)
    except DatabaseError:
        return list(default)


# ---------------------------------------------------------------------------
# Chrome
# ---------------------------------------------------------------------------


def nav_links():
    # The navbar reverses `url_name` itself and appends `anchor`, so the panel
    # form offers a fixed choice of routes rather than a free-text field.
    return _safe(NavLink.objects.filter(is_active=True))


def trust_badges():
    return _safe(TrustBadge.objects.filter(is_active=True))


def cities():
    return _safe(City.objects.filter(is_active=True))


def popular_cities():
    return _safe(City.objects.filter(is_active=True, is_metro=True))


# ---------------------------------------------------------------------------
# Hero
# ---------------------------------------------------------------------------


def hero_slides():
    """
    Live slides in display order.

    `is_first` is stamped on each instance rather than stored: it depends on
    which slides are live right now, which scheduling can change between one
    request and the next.
    """
    now = timezone.now()
    rows = _safe(
        HeroSlide.objects.filter(is_active=True)
        .exclude(starts_at__gt=now)
        .exclude(ends_at__lt=now)
    )
    for index, slide in enumerate(rows):
        slide.is_first = index == 0
    return rows


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------


def categories():
    return _safe(Category.objects.filter(is_active=True))


def category_rows():
    """Categories for the index page, each with its live package count."""
    return _safe(Category.objects.filter(is_active=True))


def get_category(slug):
    return Category.objects.filter(slug=slug, is_active=True).first()


def get_package(slug):
    return (
        Package.objects.live()
        .select_related("category")
        .prefetch_related("images")
        .filter(slug=slug)
        .first()
    )


def packages_in_category(slug):
    return list(
        Package.objects.live().select_related("category").filter(category__slug=slug)
    )


def featured_packages(limit=8):
    """Featured first, then anything else, so the grid is never short."""
    live = Package.objects.live().select_related("category")
    rows = list(live.filter(is_featured=True)[:limit])
    if len(rows) < limit:
        rows += list(live.exclude(is_featured=True)[: limit - len(rows)])
    return rows


def related_packages(package, limit=6):
    same = list(
        Package.objects.live()
        .select_related("category")
        .filter(category_id=package.category_id)
        .exclude(pk=package.pk)[:limit]
    )
    if len(same) < limit:
        same += list(
            Package.objects.live()
            .select_related("category")
            .exclude(category_id=package.category_id)[: limit - len(same)]
        )
    return same


# ---------------------------------------------------------------------------
# Copy blocks
# ---------------------------------------------------------------------------


def testimonials(limit=None):
    rows = Testimonial.objects.filter(is_published=True)
    return _safe(rows[:limit] if limit else rows)


def reviews_for(package, limit=5):
    """Reviews attached to this package first, then general ones as filler."""
    attached = list(
        Testimonial.objects.filter(is_published=True, package=package)[:limit]
    )
    if len(attached) < limit:
        attached += list(
            Testimonial.objects.filter(is_published=True)
            .exclude(package=package)[: limit - len(attached)]
        )
    return attached


def faqs(limit=None):
    rows = FAQ.objects.filter(is_active=True)
    return _safe(rows[:limit] if limit else rows)


def features():
    return _safe(Feature.objects.filter(is_active=True))


def how_it_works():
    return _safe(HowItWorksStep.objects.filter(is_active=True))


def pricing_rows():
    return _safe(PricingRow.objects.filter(is_active=True).select_related("category"))


def time_slots():
    return _safe(TimeSlot.objects.all())


def add_ons():
    return _safe(AddOn.objects.filter(is_active=True))


# ---------------------------------------------------------------------------
# Cart (still a front-end demonstration, now built from real packages)
# ---------------------------------------------------------------------------


def demo_cart_items():
    """
    Two lines assembled from whatever is in the catalogue. The cart has no
    persistence yet — this exists so the cart page has something to lay out.
    """
    packages = list(Package.objects.live().select_related("category")[:2])
    if not packages:
        return []
    extras = list(AddOn.objects.filter(is_active=True)[:1])
    settings_row = site_settings()
    city = getattr(settings_row, "default_city", "Bengaluru")
    date = timezone.localdate() + timedelta(days=5)
    slots = ["4 PM – 6 PM", "8 PM – 10 PM"]
    items = []
    for index, package in enumerate(packages):
        items.append(
            {
                "id": package.pk,
                "package": package,
                "quantity": index + 1,
                "city": city,
                "date": date.strftime("%d %B %Y"),
                "slot": slots[index % len(slots)],
                "add_ons": extras if index == 0 else [],
            }
        )
    return items


def cart_summary(items=None):
    items = demo_cart_items() if items is None else items
    config = site_settings()
    threshold = getattr(config, "free_delivery_threshold", 3000)
    fee = getattr(config, "delivery_fee", 249)
    tax_rate = float(getattr(config, "tax_percent", 18)) / 100

    lines = []
    subtotal = 0
    savings = 0
    for item in items:
        add_on_total = sum(a.price for a in item["add_ons"])
        line_total = (item["package"].price + add_on_total) * item["quantity"]
        savings += item["package"].saving * item["quantity"]
        subtotal += line_total
        line = dict(item)
        line["add_on_total"] = add_on_total
        line["line_total"] = line_total
        lines.append(line)

    delivery = 0 if subtotal >= threshold else fee
    tax = round(subtotal * tax_rate)
    return {
        "lines": lines,
        "subtotal": subtotal,
        "savings": savings,
        "delivery": delivery,
        "tax": tax,
        "total": subtotal + delivery + tax,
        "free_delivery_threshold": threshold,
    }


def cart_count():
    try:
        return len(demo_cart_items())
    except DatabaseError:
        return 0
