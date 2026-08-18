"""
The resource registry.

Every managed model is declared once here — its columns, its searchable fields,
its filters, which role may edit it — and the generic views in `views.py` build
the list page, the form page and the delete confirmation from that declaration.

Adding a new model to the panel is one entry in `RESOURCES`, not a new view, a
new URL and two new templates.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from django.db.models import Count, Q

from core import models as m
from . import forms as f


@dataclass
class Column:
    """One cell in the list table."""

    name: str                     # attribute, property or callable on the row
    label: str
    kind: str = "text"            # text image money bool toggle badge date datetime rating chip
    sortable: str = ""            # ORM field to order by; blank means not sortable
    hint: str = ""                # a second, quieter line under the value
    align: str = ""               # "" | "end"
    badges: Optional[dict] = None  # value -> tone, for kind="badge"


@dataclass
class Filter:
    param: str
    label: str
    choices: list                 # [(value, label), ...]
    lookup: str = ""              # ORM lookup; defaults to `param`

    def apply(self, queryset, value):
        lookup = self.lookup or self.param
        if value in ("", None):
            return queryset
        if value == "__true__":
            return queryset.filter(**{lookup: True})
        if value == "__false__":
            return queryset.filter(**{lookup: False})
        return queryset.filter(**{lookup: value})


@dataclass
class Resource:
    slug: str
    model: Any
    form_class: Any
    label: str                     # singular, sentence case
    plural: str
    icon: str
    group: str
    columns: list
    search_fields: list = field(default_factory=list)
    filters: list = field(default_factory=list)
    ordering: str = ""             # default ORM ordering; blank uses Meta
    orderable: bool = False        # drag handles write `position`
    permission: str = "editor"     # minimum role that may write
    blurb: str = ""
    add_label: str = ""
    select_related: list = field(default_factory=list)
    prefetch_related: list = field(default_factory=list)
    annotate: Optional[Callable] = None
    can_create: bool = True
    can_delete: bool = True
    preview_url: str = ""          # "get_absolute_url" if rows have a public page

    def queryset(self):
        qs = self.model.objects.all()
        if self.select_related:
            qs = qs.select_related(*self.select_related)
        if self.prefetch_related:
            qs = qs.prefetch_related(*self.prefetch_related)
        if self.annotate:
            qs = self.annotate(qs)
        if self.ordering:
            qs = qs.order_by(*self.ordering.split(","))
        return qs

    def search(self, queryset, term):
        if not term or not self.search_fields:
            return queryset
        query = Q()
        for name in self.search_fields:
            query |= Q(**{f"{name}__icontains": term})
        return queryset.filter(query)

    @property
    def create_label(self):
        return self.add_label or f"New {self.label.lower()}"


YES_NO = [("__true__", "Yes"), ("__false__", "No")]

PUBLISHED_FILTER = Filter("is_active", "Published", YES_NO)
STATUS_TONES = {
    "new": "amber",
    "confirmed": "blue",
    "assigned": "violet",
    "completed": "green",
    "cancelled": "red",
    "read": "blue",
    "replied": "green",
    "archived": "grey",
    "live": "green",
    "scheduled": "blue",
    "expired": "grey",
    "hidden": "grey",
    "used": "grey",
    "unpaid": "red",
    "advance": "amber",
    "paid": "green",
    "refunded": "grey",
}


RESOURCES = [
    # ---------------------------------------------------------------- catalogue
    Resource(
        slug="packages",
        model=m.Package,
        form_class=f.PackageForm,
        label="Package",
        plural="Packages",
        icon="box",
        group="Catalogue",
        blurb="The products customers book. Price, photos, what's included.",
        columns=[
            Column("image", "", "image"),
            Column("title", "Package", sortable="title", hint="category_name"),
            Column("price", "Price", "money", sortable="price", hint="discount_label"),
            Column("rating", "Rating", "rating", sortable="rating", hint="review_count_label"),
            Column("is_featured", "Featured", "toggle", sortable="is_featured"),
            Column("is_active", "Live", "toggle", sortable="is_active"),
        ],
        search_fields=["title", "slug", "description", "badge", "category__name"],
        filters=[
            Filter("category", "Occasion", [], lookup="category__slug"),
            Filter("is_featured", "Featured", YES_NO),
            PUBLISHED_FILTER,
        ],
        select_related=["category"],
        orderable=True,
        preview_url="get_absolute_url",
    ),
    Resource(
        slug="categories",
        model=m.Category,
        form_class=f.CategoryForm,
        label="Occasion",
        plural="Occasions",
        icon="layers",
        group="Catalogue",
        blurb="The occasion each package belongs to. Order here is the order on the site.",
        columns=[
            Column("image", "", "image"),
            Column("name", "Occasion", sortable="name", hint="blurb"),
            Column("price_from", "From", "money", sortable="price_from"),
            Column("live_count", "Packages", "chip", sortable="package_total"),
            Column("is_active", "Live", "toggle", sortable="is_active"),
        ],
        search_fields=["name", "blurb", "slug"],
        filters=[PUBLISHED_FILTER],
        # An aggregate adds a GROUP BY, which drops the model's Meta ordering,
        # so it is restated here — the paginator needs a stable sort.
        annotate=lambda qs: qs.annotate(package_total=Count("packages")),
        ordering="position,id",
        orderable=True,
        preview_url="get_absolute_url",
    ),
    Resource(
        slug="gallery",
        model=m.PackageImage,
        form_class=f.PackageImageForm,
        label="Gallery photo",
        plural="Gallery photos",
        icon="image",
        group="Catalogue",
        blurb="Extra photos on a package's detail page. Without any, placeholders stand in.",
        columns=[
            Column("image", "", "image"),
            Column("package", "Package", sortable="package__title", hint="alt"),
            Column("position", "Order", sortable="position", align="end"),
        ],
        search_fields=["alt", "package__title"],
        select_related=["package"],
        orderable=True,
    ),
    Resource(
        slug="add-ons",
        model=m.AddOn,
        form_class=f.AddOnForm,
        label="Add-on",
        plural="Add-ons",
        icon="plus-circle",
        group="Catalogue",
        blurb="Extras offered at checkout.",
        columns=[
            Column("name", "Add-on", sortable="name"),
            Column("price", "Price", "money", sortable="price"),
            Column("is_active", "Live", "toggle", sortable="is_active"),
        ],
        search_fields=["name"],
        orderable=True,
    ),
    Resource(
        slug="pricing",
        model=m.PricingRow,
        form_class=f.PricingRowForm,
        label="Pricing row",
        plural="Pricing table",
        icon="tag",
        group="Catalogue",
        blurb="The homepage price-guide table.",
        columns=[
            Column("category", "Occasion", sortable="category__name"),
            Column("range", "Range"),
            Column("popular", "Most booked"),
            Column("setup_time", "Setup time"),
            Column("is_active", "Live", "toggle", sortable="is_active"),
        ],
        search_fields=["category__name", "range", "popular"],
        select_related=["category"],
        orderable=True,
    ),
    # ---------------------------------------------------------------- homepage
    Resource(
        slug="hero-slides",
        model=m.HeroSlide,
        form_class=f.HeroSlideForm,
        label="Hero slide",
        plural="Hero slider",
        icon="slides",
        group="Homepage",
        blurb="The deck at the top of the homepage. Drag to reorder; the first live slide is the one that paints first.",
        add_label="New slide",
        columns=[
            Column("image", "", "image"),
            Column("eyebrow", "Slide", sortable="eyebrow", hint="heading_line"),
            Column("media_type", "Media", "badge", sortable="media_type",
                   badges={"image": "grey", "video": "violet"}),
            Column("duration_label", "On screen"),
            Column("schedule_state", "State", "badge", badges=STATUS_TONES),
            Column("is_active", "Live", "toggle", sortable="is_active"),
        ],
        search_fields=["eyebrow", "heading", "heading_accent", "description"],
        filters=[
            Filter("media_type", "Media", m.HeroSlide.MEDIA_CHOICES),
            PUBLISHED_FILTER,
        ],
        orderable=True,
    ),
    Resource(
        slug="testimonials",
        model=m.Testimonial,
        form_class=f.TestimonialForm,
        label="Review",
        plural="Reviews",
        icon="quote",
        group="Homepage",
        blurb="Customer quotes. Attach one to a package and it also shows on that page.",
        columns=[
            Column("name", "Customer", sortable="name", hint="city"),
            Column("rating", "Rating", "rating", sortable="rating"),
            Column("occasion", "Booked", hint="date"),
            Column("text", "Quote", "excerpt"),
            Column("is_published", "Live", "toggle", sortable="is_published"),
        ],
        search_fields=["name", "text", "occasion", "city"],
        filters=[
            Filter("rating", "Stars", [(str(n), f"{n} star" + ("s" if n > 1 else "")) for n in range(5, 0, -1)]),
            Filter("is_published", "Published", YES_NO),
        ],
        select_related=["package"],
        orderable=True,
    ),
    Resource(
        slug="features",
        model=m.Feature,
        form_class=f.FeatureForm,
        label="Promise",
        plural="Promises",
        icon="shield",
        group="Homepage",
        blurb="The six reason-to-believe cards.",
        columns=[
            Column("title", "Promise", sortable="title", hint="icon"),
            Column("text", "Copy", "excerpt"),
            Column("is_active", "Live", "toggle", sortable="is_active"),
        ],
        search_fields=["title", "text"],
        orderable=True,
    ),
    Resource(
        slug="steps",
        model=m.HowItWorksStep,
        form_class=f.HowItWorksStepForm,
        label="Step",
        plural="How it works",
        icon="route",
        group="Homepage",
        blurb="The four-step explainer, used on the homepage and its own page.",
        columns=[
            Column("step", "#", sortable="step"),
            Column("title", "Step", sortable="title", hint="icon"),
            Column("text", "Copy", "excerpt"),
            Column("is_active", "Live", "toggle", sortable="is_active"),
        ],
        search_fields=["title", "text"],
        orderable=True,
    ),
    Resource(
        slug="faqs",
        model=m.FAQ,
        form_class=f.FAQForm,
        label="FAQ",
        plural="FAQs",
        icon="help",
        group="Homepage",
        blurb="Answers shown on the homepage, the package pages and How it works.",
        columns=[
            Column("question", "Question", sortable="question"),
            Column("answer", "Answer", "excerpt"),
            Column("is_active", "Live", "toggle", sortable="is_active"),
        ],
        search_fields=["question", "answer"],
        orderable=True,
    ),
    Resource(
        slug="trust-badges",
        model=m.TrustBadge,
        form_class=f.TrustBadgeForm,
        label="Trust badge",
        plural="Trust badges",
        icon="award",
        group="Homepage",
        blurb="The four numbers under the hero.",
        columns=[
            Column("value", "Number", sortable="value"),
            Column("label", "Label", sortable="label"),
            Column("is_active", "Live", "toggle", sortable="is_active"),
        ],
        search_fields=["value", "label"],
        orderable=True,
    ),
    # -------------------------------------------------------------- operations
    Resource(
        slug="bookings",
        model=m.Booking,
        form_class=f.BookingForm,
        label="Booking",
        plural="Bookings",
        icon="calendar",
        group="Operations",
        blurb="Every event the company is committed to delivering.",
        columns=[
            Column("reference", "Ref", sortable="reference", hint="created_label"),
            Column("customer_name", "Customer", sortable="customer_name", hint="phone"),
            Column("package", "Package", sortable="package__title", hint="city"),
            Column("event_date", "Event", "date", sortable="event_date", hint="time_slot"),
            Column("amount", "Value", "money", sortable="amount", hint="get_payment_status_display"),
            Column("status", "Status", "badge", sortable="status", badges=STATUS_TONES),
        ],
        search_fields=["reference", "customer_name", "phone", "email", "package__title", "city__name"],
        filters=[
            Filter("status", "Status", m.Booking.STATUS_CHOICES),
            Filter("payment_status", "Payment", m.Booking.PAYMENT_CHOICES),
            Filter("city", "City", [], lookup="city__slug"),
        ],
        select_related=["package", "city", "decorator"],
        prefetch_related=["add_ons"],
    ),
    Resource(
        slug="enquiries",
        model=m.Enquiry,
        form_class=f.EnquiryForm,
        label="Enquiry",
        plural="Enquiries",
        icon="message",
        group="Operations",
        blurb="Messages from the contact form.",
        can_create=False,
        columns=[
            Column("name", "From", sortable="name", hint="phone"),
            Column("occasion", "About", hint="city"),
            Column("message", "Message", "excerpt"),
            Column("created_at", "Received", "datetime", sortable="created_at"),
            Column("status", "Status", "badge", sortable="status", badges=STATUS_TONES),
        ],
        search_fields=["name", "email", "phone", "message", "occasion"],
        filters=[Filter("status", "Status", m.Enquiry.STATUS_CHOICES)],
    ),
    Resource(
        slug="decorators",
        model=m.Decorator,
        form_class=f.DecoratorForm,
        label="Decorator",
        plural="Decorators",
        icon="users",
        group="Operations",
        blurb="The crews doing the work. Assign one to a booking.",
        permission="admin",
        columns=[
            Column("name", "Crew", sortable="name", hint="phone"),
            Column("city", "Based in", sortable="city__name"),
            Column("rating", "Rating", "rating", sortable="rating"),
            Column("open_jobs", "Open jobs", "chip", sortable="job_total"),
            Column("is_verified", "Verified", "toggle", sortable="is_verified"),
            Column("is_active", "Active", "toggle", sortable="is_active"),
        ],
        search_fields=["name", "phone", "email", "city__name"],
        filters=[Filter("is_verified", "Verified", YES_NO), PUBLISHED_FILTER],
        select_related=["city"],
        annotate=lambda qs: qs.annotate(job_total=Count("bookings")),
        ordering="name",
    ),
    Resource(
        slug="coupons",
        model=m.Coupon,
        form_class=f.CouponForm,
        label="Coupon",
        plural="Coupons",
        icon="ticket",
        group="Operations",
        blurb="Discount codes, with windows and usage caps.",
        permission="admin",
        columns=[
            Column("code", "Code", sortable="code", hint="kind_label"),
            Column("display_value", "Off"),
            Column("min_order", "Min order", "money", sortable="min_order"),
            Column("usage_label", "Used"),
            Column("state_label", "State", "badge", badges=STATUS_TONES),
            Column("is_active", "Enabled", "toggle", sortable="is_active"),
        ],
        search_fields=["code"],
        filters=[PUBLISHED_FILTER],
    ),
    # ------------------------------------------------------------------- site
    Resource(
        slug="cities",
        model=m.City,
        form_class=f.CityForm,
        label="City",
        plural="Cities",
        icon="map-pin",
        group="Site",
        blurb="Where you deliver. Metros appear in the header's popular list.",
        permission="admin",
        columns=[
            Column("name", "City", sortable="name", hint="state"),
            Column("is_metro", "Metro", "toggle", sortable="is_metro"),
            Column("is_active", "Live", "toggle", sortable="is_active"),
        ],
        search_fields=["name", "state"],
        filters=[Filter("is_metro", "Metro", YES_NO), PUBLISHED_FILTER],
    ),
    Resource(
        slug="time-slots",
        model=m.TimeSlot,
        form_class=f.TimeSlotForm,
        label="Time slot",
        plural="Time slots",
        icon="clock",
        group="Site",
        blurb="Arrival windows offered on the booking form.",
        permission="admin",
        columns=[
            Column("label", "Window", sortable="label"),
            Column("value", "Form value", sortable="value"),
            Column("available", "Bookable", "toggle", sortable="available"),
        ],
        search_fields=["label", "value"],
        orderable=True,
    ),
    Resource(
        slug="nav-links",
        model=m.NavLink,
        form_class=f.NavLinkForm,
        label="Menu link",
        plural="Menu links",
        icon="menu",
        group="Site",
        blurb="The header and drawer menu.",
        permission="admin",
        columns=[
            Column("label", "Label", sortable="label", hint="url_name"),
            Column("anchor", "Anchor"),
            Column("is_active", "Live", "toggle", sortable="is_active"),
        ],
        search_fields=["label", "url_name"],
        orderable=True,
    ),
]

BY_SLUG = {resource.slug: resource for resource in RESOURCES}

# Sidebar order. Groups not listed here fall to the end.
GROUP_ORDER = ["Operations", "Catalogue", "Homepage", "Site"]
GROUP_ICONS = {
    "Operations": "activity",
    "Catalogue": "box",
    "Homepage": "home",
    "Site": "settings",
}


def get(slug):
    return BY_SLUG.get(slug)


def grouped(profile=None):
    """Sidebar structure: [(group, icon, [resources])], filtered by role."""
    groups = {}
    for resource in RESOURCES:
        if profile is not None and not profile.at_least("viewer"):
            continue
        groups.setdefault(resource.group, []).append(resource)
    ordered = []
    for name in GROUP_ORDER + [g for g in groups if g not in GROUP_ORDER]:
        if name in groups:
            ordered.append((name, GROUP_ICONS.get(name, "dot"), groups[name]))
    return ordered


def dynamic_filter_choices():
    """
    Filters whose options are rows in another table, resolved per request so a
    new occasion shows up in the package filter without a code change.
    """
    categories = [(c.slug, c.name) for c in m.Category.objects.all()]
    cities = [(c.slug, c.name) for c in m.City.objects.filter(is_active=True)]
    return {"category": categories, "city": cities}
