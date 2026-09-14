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

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.urls import reverse

from core import models as m
from . import forms as f


@dataclass
class Column:
    """One cell in the list table."""

    name: str                     # attribute, property or callable on the row
    label: str
    kind: str = "text"            # text image money toggle badge tag access
                                  # date datetime rating chip excerpt
                                  # stock delta
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


class StockFilter(Filter):
    """
    "Running low" is not a column, it is a comparison between two of them, so
    this filter reaches for the queryset methods that know how to express it.
    """

    def apply(self, queryset, value):
        if value == "low":
            return queryset.low_stock()
        if value == "out":
            return queryset.out_of_stock()
        if value == "attention":
            return queryset.needs_attention()
        if value == "in":
            return queryset.in_stock()
        return queryset


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
    can_edit: bool = True          # False makes existing rows open read-only
    can_delete: bool = True
    no_create_hint: str = ""       # why this table has no New button
    preview_url: str = ""          # "get_absolute_url" if rows have a page of their own
    preview_label: str = "View on the site"

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
        queryset = queryset.filter(query)
        if any("__" in name for name in self.search_fields):
            # A search that reaches through a relation joins, and a join can
            # hand the same row back once per match.
            queryset = queryset.distinct()
        return queryset

    @property
    def create_label(self):
        return self.add_label or f"New {self.label.lower()}"

    @property
    def url(self):
        return reverse("panel:resource_list", args=[self.slug])

    @property
    def nav_key(self):
        return self.slug


@dataclass
class PageLink:
    """
    A bespoke page that belongs in a sidebar group beside the resources — the
    counter and the stock room are screens, not tables, but a person looking
    for them looks under Inventory.
    """

    url_name: str
    plural: str
    icon: str
    permission: str = "viewer"

    @property
    def url(self):
        return reverse(f"panel:{self.url_name}")

    @property
    def nav_key(self):
        return self.url_name

    @property
    def slug(self):
        return ""


#: Pages pinned to the top of a group, before its resources.
GROUP_PAGES = {
    "Events": [
        PageLink("events", "Events", "sparkles"),
    ],
    "Inventory": [
        PageLink("counter", "Counter", "cart", permission="editor"),
        PageLink("stock", "Stock room", "trending-up"),
    ],
}


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
MOVEMENT_TONES = {
    "Opening balance": "grey",
    "Purchase in": "green",
    "Counter sale": "blue",
    "Customer return": "violet",
    "Returned to supplier": "amber",
    "Used on an event": "violet",
    "Damaged": "red",
    "Lost": "red",
    "Stock count adjustment": "grey",
    "Reserved for an event": "blue",
    "Back from an event": "green",
    "Reservation released": "grey",
}
USAGE_TONES = {"Reusable": "blue", "Consumable": "violet"}
SALE_TONES = {"Completed": "green", "Refunded": "red"}
STOCK_STATES = [
    ("attention", "Needs ordering"),
    ("low", "Running low"),
    ("out", "Out of stock"),
    ("in", "In stock"),
]
GROUP_TONES = {
    "Field crew — on site at the event": "green",
    "Office — coordination and support": "blue",
    "Partner — vendor or agency": "amber",
}
EMPLOYMENT_TONES = {
    "In-house": "green",
    "Freelance": "violet",
    "Vendor / agency": "amber",
    "Intern": "grey",
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
        blurb=(
            "Everything on /packages/ and in the homepage grid. Drag to set the "
            "order the site shows them in; Site settings decides how many of "
            "them reach the homepage."
        ),
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
        blurb=(
            "The kinds of celebration you decorate — Birthday, Wedding. Packages are "
            "grouped under one, and every event is booked as one. Order here is the "
            "order on the site; switch Live off to retire one — past events keep it."
        ),
        columns=[
            Column("image", "", "image"),
            Column("name", "Occasion", sortable="name", hint="blurb"),
            Column("price_from", "From", "money", sortable="price_from"),
            Column("live_count", "Packages", "chip", sortable="package_total"),
            Column("event_total", "Events", "chip", sortable="event_count"),
            Column("is_active", "Live", "toggle", sortable="is_active"),
        ],
        search_fields=["name", "blurb", "slug"],
        filters=[PUBLISHED_FILTER],
        # An aggregate adds a GROUP BY, which drops the model's Meta ordering,
        # so it is restated here — the paginator needs a stable sort. Two
        # counts over two joins multiply, hence distinct.
        annotate=lambda qs: qs.annotate(
            package_total=Count("packages", distinct=True),
            event_count=Count("events", distinct=True),
        ),
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
            Column("booked", "Booked", hint="date"),
            Column("text", "Quote", "excerpt"),
            Column("is_published", "Live", "toggle", sortable="is_published"),
        ],
        search_fields=["name", "text", "booked", "city"],
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
        slug="enquiries",
        model=m.Enquiry,
        form_class=f.EnquiryForm,
        label="Enquiry",
        plural="Enquiries",
        icon="message",
        group="Events",
        blurb=(
            "Questions from the website — about an occasion, a package, or anything. "
            "Open one to turn it into an event when the customer is ready."
        ),
        can_create=False,
        select_related=["package", "event"],
        columns=[
            Column("name", "From", sortable="name", hint="phone"),
            Column("occasion", "About", hint="about_label"),
            Column("message", "Message", "excerpt"),
            Column("created_at", "Received", "datetime", sortable="created_at"),
            Column("status", "Status", "badge", sortable="status", badges=STATUS_TONES),
        ],
        search_fields=["name", "email", "phone", "message", "occasion", "package__title"],
        filters=[
            Filter("status", "Status", m.Enquiry.STATUS_CHOICES),
            # The lookup is "has no event", so the yes/no values read inverted.
            Filter("event", "Became an event", [("__false__", "Yes"), ("__true__", "Not yet")], lookup="event__isnull"),
        ],
    ),
    Resource(
        slug="staffs",
        model=m.StaffMember,
        form_class=f.StaffMemberForm,
        label="Staff member",
        plural="Staffs",
        icon="users",
        group="Operations",
        blurb=(
            "Everyone who works an event — decorators, florists, drivers, "
            "coordinators. Give somebody a type, then put them on an event's crew."
        ),
        permission="admin",
        add_label="New staff member",
        columns=[
            Column("name", "Person", sortable="name", hint="contact_line"),
            Column("category", "Type", "tag", sortable="category__name", hint="city"),
            Column("get_employment_display", "Engagement", "badge",
                   sortable="employment", badges=EMPLOYMENT_TONES),
            Column("rating", "Rating", "rating", sortable="rating"),
            Column("open_jobs", "Open jobs", "chip", sortable="job_total"),
            Column("account_role", "Panel access", "access"),
            Column("is_verified", "Verified", "toggle", sortable="is_verified"),
            Column("is_active", "Active", "toggle", sortable="is_active"),
        ],
        search_fields=[
            "name", "phone", "email", "skills",
            "city__name", "category__name", "account__username",
        ],
        filters=[
            Filter("type", "Type", [], lookup="category__slug"),
            Filter("group", "Group", m.StaffCategory.KIND_CHOICES, lookup="category__kind"),
            Filter("employment", "Engagement", m.StaffMember.EMPLOYMENT_CHOICES),
            Filter("city", "City", [], lookup="city__slug"),
            Filter("is_verified", "Verified", YES_NO),
            Filter("is_active", "Active", YES_NO),
        ],
        select_related=["city", "category", "account"],
        annotate=lambda qs: qs.annotate(
            job_total=Count("events", filter=Q(events__status__in=m.Event.OPEN_STATUSES))
        ),
        ordering="name",
    ),
    Resource(
        slug="staff-types",
        model=m.StaffCategory,
        form_class=f.StaffCategoryForm,
        label="Staff type",
        plural="Staff types",
        icon="layers",
        group="Operations",
        blurb=(
            "The kinds of work you hire for. Every staff member gets one, and "
            "the Staffs list filters on it."
        ),
        permission="admin",
        add_label="New staff type",
        columns=[
            Column("name", "Type", "tag", sortable="name", hint="description"),
            Column("get_kind_display", "Group", "badge", sortable="kind", badges=GROUP_TONES),
            Column("member_total", "People", "chip", sortable="member_count"),
            Column("open_jobs", "Open jobs", "chip"),
            Column("is_active", "Selectable", "toggle", sortable="is_active"),
        ],
        search_fields=["name", "slug", "description"],
        filters=[
            Filter("kind", "Group", m.StaffCategory.KIND_CHOICES),
            Filter("is_active", "Selectable", YES_NO),
        ],
        annotate=lambda qs: qs.annotate(member_count=Count("members")),
        ordering="position,id",
        orderable=True,
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
    # ------------------------------------------------------------- inventory
    Resource(
        slug="stock-items",
        model=m.InventoryItem,
        form_class=f.InventoryItemForm,
        label="Stock item",
        plural="Stock items",
        icon="package",
        group="Inventory",
        blurb=(
            "Everything on the shelves — what it is, what it cost, what it "
            "sells for and how much is left. The count itself is written by "
            "the stock ledger, never typed in."
        ),
        add_label="New stock item",
        columns=[
            Column("image", "", "image"),
            Column("name", "Item", sortable="name", hint="sku"),
            Column("category", "Group", "tag", sortable="category__name", hint="shelf_label"),
            Column("usage_label", "Kind", "badge", sortable="usage_type", badges=USAGE_TONES),
            Column("quantity_label", "On hand", "stock", sortable="quantity", hint="reorder_label"),
            Column("available_label", "Free to use", sortable="free_total", hint="reserved_label"),
            Column("cost_price", "Cost", "money", sortable="cost_price"),
            Column("sale_price", "Sells for", "money", sortable="sale_price", hint="margin_label"),
            Column("stock_value", "Stock value", "money", sortable="value_total", align="end"),
            Column("is_sellable", "At counter", "toggle", sortable="is_sellable"),
            Column("is_active", "Active", "toggle", sortable="is_active"),
        ],
        search_fields=[
            "name", "sku", "barcode", "location", "description",
            "category__name", "supplier__name",
        ],
        filters=[
            Filter("group", "Group", [], lookup="category__slug"),
            Filter("supplier", "Supplier", [], lookup="supplier_id"),
            StockFilter("stock", "Stock", STOCK_STATES),
            Filter("usage_type", "Kind", [
                ("reusable", "Reusable"), ("consumable", "Consumable"),
            ]),
            Filter("unit", "Counted in", m.InventoryItem.UNIT_CHOICES),
            Filter("is_sellable", "At the counter", YES_NO),
            Filter("is_active", "Active", YES_NO),
        ],
        select_related=["category", "supplier"],
        annotate=lambda qs: qs.with_reserved().annotate(
            value_total=ExpressionWrapper(
                F("quantity") * F("cost_price"),
                output_field=DecimalField(max_digits=16, decimal_places=2),
            ),
            free_total=ExpressionWrapper(
                F("quantity") - F("reserved_total"),
                output_field=DecimalField(max_digits=16, decimal_places=2),
            ),
        ),
        ordering="name",
    ),
    Resource(
        slug="stock-groups",
        model=m.StockCategory,
        form_class=f.StockCategoryForm,
        label="Stock group",
        plural="Stock groups",
        icon="layers",
        group="Inventory",
        blurb=(
            "How the store room is divided up. Every stock item gets one, and "
            "the stock list filters on it."
        ),
        permission="admin",
        add_label="New stock group",
        columns=[
            Column("name", "Group", "tag", sortable="name", hint="description"),
            Column("item_total", "Items", "chip", sortable="item_count"),
            Column("low_total", "Need ordering", "chip"),
            Column("stock_value", "Stock value", "money", align="end"),
            Column("is_active", "Selectable", "toggle", sortable="is_active"),
        ],
        search_fields=["name", "slug", "description"],
        filters=[Filter("is_active", "Selectable", YES_NO)],
        annotate=lambda qs: qs.annotate(item_count=Count("items")),
        prefetch_related=["items"],
        ordering="position,id",
        orderable=True,
    ),
    Resource(
        slug="suppliers",
        model=m.Supplier,
        form_class=f.SupplierForm,
        label="Supplier",
        plural="Suppliers",
        icon="truck",
        group="Inventory",
        blurb="Who the stock is bought from, and how long they take to deliver.",
        permission="admin",
        columns=[
            Column("name", "Supplier", sortable="name", hint="contact_line"),
            Column("gst_number", "GSTIN"),
            Column("item_total", "Items", "chip", sortable="item_count"),
            Column("lead_time_days", "Lead days", sortable="lead_time_days", align="end"),
            Column("stock_value", "Stock value", "money", align="end"),
            Column("is_active", "Selectable", "toggle", sortable="is_active"),
        ],
        search_fields=["name", "contact_name", "phone", "email", "gst_number"],
        filters=[Filter("is_active", "Selectable", YES_NO)],
        annotate=lambda qs: qs.annotate(item_count=Count("items")),
        prefetch_related=["items"],
        ordering="name",
    ),
    Resource(
        slug="stock-ledger",
        model=m.StockMovement,
        form_class=f.StockMovementForm,
        label="Stock movement",
        plural="Stock ledger",
        icon="clipboard",
        group="Inventory",
        blurb=(
            "Every unit that came in or went out, and why. Receive stock, write "
            "off breakages or correct a count here — rows are never edited "
            "afterwards, they are corrected with another movement."
        ),
        add_label="Record a movement",
        can_edit=False,
        can_delete=False,
        columns=[
            Column("created_at", "When", "datetime", sortable="created_at", hint="by_label"),
            Column("item", "Item", sortable="item__name", hint="source_label"),
            Column("get_kind_display", "Reason", "badge", sortable="kind", badges=MOVEMENT_TONES),
            Column("signed_label", "Change", "delta", sortable="change", hint="balance_label"),
            Column("value", "Value", "money", align="end"),
            Column("note", "Note", "excerpt"),
        ],
        search_fields=[
            "item__name", "item__sku", "reference", "note", "supplier__name",
            "event__number",
        ],
        filters=[
            Filter("kind", "Reason", m.StockMovement.KIND_CHOICES),
            Filter("group", "Group", [], lookup="item__category__slug"),
            Filter("supplier", "Supplier", [], lookup="supplier_id"),
        ],
        select_related=["item", "supplier", "sale", "event", "created_by"],
        ordering="-created_at,-id",
    ),
    Resource(
        slug="counter-sales",
        model=m.CounterSale,
        form_class=f.CounterSaleForm,
        label="Counter sale",
        plural="Counter sales",
        icon="receipt",
        group="Inventory",
        blurb=(
            "What went over the counter. Sales are rung up on the Counter "
            "screen; this is the record of them, and where refunds are issued."
        ),
        can_create=False,
        can_delete=False,
        no_create_hint=(
            "Sales are rung up on the Counter screen, not typed in here."
        ),
        preview_url="get_absolute_url",
        preview_label="Open the receipt",
        columns=[
            Column("reference", "Receipt", sortable="reference", hint="sold_label"),
            Column("customer_label", "Customer", sortable="customer_name", hint="phone"),
            Column("items_label", "Basket"),
            Column("served_label", "Sold by"),
            Column("total", "Total", "money", sortable="total", hint="get_payment_method_display"),
            Column("profit", "Margin", "money", align="end"),
            Column("get_status_display", "State", "badge", sortable="status", badges=SALE_TONES),
        ],
        search_fields=["reference", "customer_name", "phone", "notes", "lines__name"],
        filters=[
            Filter("status", "State", m.CounterSale.STATUS_CHOICES),
            Filter("payment_method", "Paid by", m.CounterSale.PAYMENT_CHOICES),
        ],
        select_related=["served_by", "cashier"],
        prefetch_related=["lines"],
        ordering="-sold_at,-id",
    ),
    # ----------------------------------------------------------------- events
    Resource(
        slug="customers",
        model=m.Customer,
        form_class=f.CustomerForm,
        label="Customer",
        plural="Customers",
        icon="user",
        group="Events",
        blurb=(
            "Who you run events for. Every event points at one, so a repeat "
            "customer's history and spend live in one place."
        ),
        add_label="New customer",
        columns=[
            Column("name", "Customer", sortable="name", hint="contact_line"),
            Column("email", "Email"),
            Column("event_total", "Events", "chip", sortable="event_count"),
            Column("revenue_total", "Event revenue", "money", sortable="billed", align="end"),
            Column("created_at", "Added", "date", sortable="created_at"),
        ],
        search_fields=["name", "phone", "email", "address", "notes"],
        annotate=lambda qs: qs.annotate(
            event_count=Count("events", distinct=True),
            billed=Sum("events__revenue", filter=~Q(events__status="cancelled")),
        ),
        ordering="name",
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
GROUP_ORDER = ["Events", "Operations", "Inventory", "Catalogue", "Homepage", "Site"]
GROUP_ICONS = {
    "Operations": "activity",
    "Events": "sparkles",
    "Inventory": "package",
    "Catalogue": "box",
    "Homepage": "home",
    "Site": "settings",
}


def get(slug):
    return BY_SLUG.get(slug)


def grouped(profile=None):
    """Sidebar structure: [(group, icon, [entries])], filtered by role."""
    groups = {}
    for name, pages in GROUP_PAGES.items():
        visible = [
            page for page in pages
            if profile is None or profile.at_least(page.permission)
        ]
        if visible:
            groups[name] = list(visible)
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
    staff_types = [(c.slug, c.name) for c in m.StaffCategory.objects.all()]
    stock_groups = [(c.slug, c.name) for c in m.StockCategory.objects.all()]
    suppliers = [(str(s.pk), s.name) for s in m.Supplier.objects.filter(is_active=True)]
    return {
        "category": categories,
        "city": cities,
        "type": staff_types,
        "group": stock_groups,
        "supplier": suppliers,
    }
