"""
Function-based views for the Celebra public site.

Every lookup goes through `core.queries`, which returns published rows only.
Nothing here knows about the admin panel; the panel writes to the same models
and these views simply read whatever is currently published.
"""

from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from . import queries as q
from .forms import BOOKING_HORIZON_DAYS, BookingRequestForm, EnquiryForm, TrackBookingForm
from .models import ActivityLog, Event

PAGE_SIZE = 6

#: Session key holding the events this browser booked or looked up.
MY_BOOKINGS = "my_bookings"


def _remember_booking(request, event):
    """Let this browser open the booking again without typing anything."""
    kept = [pk for pk in request.session.get(MY_BOOKINGS, []) if pk != event.pk]
    request.session[MY_BOOKINGS] = [event.pk] + kept[:19]


def _safe_next(request, fallback):
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return fallback


def home(request):
    context = {
        "page_id": "home",
        "meta_description": (
            "Barahi Florist & Events books floral and event decoration setups at "
            "fixed prices, with verified decorators and an on-time guarantee."
        ),
        "hero_slides": q.hero_slides(),
        "trust_badges": q.trust_badges(),
        # A slice of the catalogue, sized and ordered from the panel. The rest
        # lives on the products page behind the button under the grid.
        "home_products": q.home_products(),
        "product_total": q.product_count(),
        "how_it_works": q.how_it_works(),
        "features": q.features(),
        "testimonials": q.testimonials(),
        "pricing_rows": q.pricing_rows(),
        "faqs": q.faqs(limit=6),
        "occasions": q.categories(),
    }
    return render(request, "core/home.html", context)


RATING_OPTIONS = [
    {"value": "4.8", "label": "4.8 and above"},
    {"value": "4.5", "label": "4.5 and above"},
    {"value": "4.0", "label": "4.0 and above"},
]


def _listing_url(request, *drop_params, drop_value=None):
    """
    The current URL with some filters taken out — what a filter chip's × links to.

    `drop_value` removes a single value from a repeated parameter (one occasion
    out of three chosen); without it the named parameters go entirely.
    """
    params = request.GET.copy()
    params.pop("page", None)
    params.pop("partial", None)
    for name in drop_params:
        if drop_value is None:
            params.pop(name, None)
            continue
        kept = [v for v in params.getlist(name) if v != drop_value]
        if kept:
            params.setlist(name, kept)
        else:
            params.pop(name, None)
    encoded = params.urlencode()
    return f"{request.path}?{encoded}" if encoded else request.path


def products(request):
    """
    The full catalogue: search, occasion, budget, rating and offer filters,
    seven sort orders and pagination.

    Everything narrows one queryset, so the count, the page and the ordering can
    never disagree. With `?partial=1` only the results block is rendered — that
    is what the page fetches when a filter changes, so the browser keeps its
    scroll position and the cards can animate in.
    """
    config = q.site_settings()
    price_floor, price_ceiling = q.product_price_bounds()
    occasions, badges = q.product_facets()
    valid_occasions = {row["slug"] for row in occasions}

    def _int(name, default):
        try:
            return int(request.GET.get(name, ""))
        except (TypeError, ValueError):
            return default

    # -- read the request, discarding anything that is not a real option ----
    term = request.GET.get("q", "").strip()[:80]
    chosen_occasions = [s for s in request.GET.getlist("occasion") if s in valid_occasions]
    chosen_badges = [b for b in request.GET.getlist("badge") if b in badges]
    min_price = max(_int("min_price", price_floor), price_floor)
    max_price = min(_int("max_price", price_ceiling), price_ceiling)
    if min_price > max_price:
        min_price, max_price = price_floor, price_ceiling
    min_rating = request.GET.get("rating", "")
    if min_rating not in [o["value"] for o in RATING_OPTIONS]:
        min_rating = ""
    deals_only = request.GET.get("deal") == "1"
    featured_only = request.GET.get("featured") == "1"
    view_mode = "list" if request.GET.get("view") == "list" else "grid"

    # -- narrow ------------------------------------------------------------
    queryset = q.product_queryset()
    total_count = queryset.count()

    if term:
        queryset = queryset.filter(
            Q(title__icontains=term)
            | Q(description__icontains=term)
            | Q(badge__icontains=term)
            | Q(includes_text__icontains=term)
            | Q(category__name__icontains=term)
        )
    if chosen_occasions:
        queryset = queryset.filter(category__slug__in=chosen_occasions)
    if chosen_badges:
        queryset = queryset.filter(badge__in=chosen_badges)
    if price_ceiling:
        queryset = queryset.filter(price__gte=min_price, price__lte=max_price)
    if min_rating:
        queryset = queryset.filter(rating__gte=min_rating)
    if deals_only:
        queryset = queryset.filter(discount_pc__gt=0)
    if featured_only:
        queryset = queryset.filter(is_featured=True)

    queryset, sort = q.sort_products(queryset, request.GET.get("sort", ""))

    per_page = getattr(config, "products_per_page", 9) or 9
    paginator = Paginator(queryset, per_page)
    try:
        page_obj = paginator.page(request.GET.get("page", 1))
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    # -- what the toolbar shows as removable chips -------------------------
    chips = []
    if term:
        chips.append({"label": f'"{term}"', "url": _listing_url(request, "q")})
    names = {row["slug"]: row["name"] for row in occasions}
    for slug in chosen_occasions:
        chips.append({
            "label": names[slug],
            "url": _listing_url(request, "occasion", drop_value=slug),
        })
    for badge in chosen_badges:
        chips.append({
            "label": badge,
            "url": _listing_url(request, "badge", drop_value=badge),
        })
    if price_ceiling and (min_price > price_floor or max_price < price_ceiling):
        chips.append({
            "label": f"₹{min_price:,} – ₹{max_price:,}",
            "url": _listing_url(request, "min_price", "max_price"),
        })
    if min_rating:
        chips.append({"label": f"{min_rating}★ and up", "url": _listing_url(request, "rating")})
    if deals_only:
        chips.append({"label": "On offer", "url": _listing_url(request, "deal")})
    if featured_only:
        chips.append({"label": "Featured", "url": _listing_url(request, "featured")})

    params = request.GET.copy()
    params.pop("page", None)
    params.pop("partial", None)

    def _view_url(mode):
        """The same results, laid out the other way."""
        switched = params.copy()
        if mode == "grid":
            switched.pop("view", None)
        else:
            switched["view"] = mode
        encoded = switched.urlencode()
        return f"{request.path}?{encoded}" if encoded else request.path

    context = {
        "page_id": "products",
        "grid_url": _view_url("grid"),
        "list_url": _view_url("list"),
        "meta_description": (
            getattr(config, "products_page_lead", "")
            or "Every floral and event decoration setup Barahi Florist & Events builds, at a fixed price."
        )[:155],
        "products": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "querystring": params.urlencode(),
        "result_count": paginator.count,
        "total_count": total_count,
        "occasion_facets": occasions,
        "badge_facets": badges,
        "chosen_occasions": chosen_occasions,
        "chosen_badges": chosen_badges,
        "price_floor": price_floor,
        "price_ceiling": price_ceiling,
        "min_price": min_price,
        "max_price": max_price,
        "min_rating": min_rating,
        "deals_only": deals_only,
        "featured_only": featured_only,
        "term": term,
        "sort": sort,
        "view_mode": view_mode,
        "chips": chips,
        "sort_options": q.sort_options(),
        "rating_options": RATING_OPTIONS,
        "clear_url": request.path,
        "breadcrumbs": [{"label": "Products", "url": None}],
    }

    if request.GET.get("partial") == "1":
        # Only the results block: the page swaps this in without a reload.
        return render(request, "core/partials/_product_results.html", context)
    return render(request, "core/products.html", context)


def categories(request):
    context = {
        "page_id": "categories",
        "meta_description": "Every occasion Barahi Florist & Events decorates, from first birthdays to reception stages.",
        "category_rows": q.category_rows(),
        "breadcrumbs": [{"label": "Occasions", "url": None}],
    }
    return render(request, "core/categories.html", context)


def category_detail(request, slug):
    category = q.get_category(slug)
    if category is None:
        raise Http404("No category matches the given slug.")

    packages = q.packages_in_category(slug)

    def _int(name, default=None):
        raw = request.GET.get(name)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    price_floor = min((p.price for p in packages), default=0)
    price_ceiling = max((p.price for p in packages), default=50000)
    max_price = _int("max_price", price_ceiling)
    min_rating = request.GET.get("rating", "")
    sort = request.GET.get("sort", "popular")

    # Filtering in Python rather than SQL: the working set is one category's
    # worth of rows, and `discount_percent` is a derived property.
    filtered = [p for p in packages if p.price <= max_price]
    if min_rating:
        try:
            floor = float(min_rating)
            filtered = [p for p in filtered if float(p.rating) >= floor]
        except ValueError:
            min_rating = ""

    sorters = {
        "price_low": lambda p: p.price,
        "price_high": lambda p: -p.price,
        "rating": lambda p: -float(p.rating),
        "discount": lambda p: -p.discount_percent,
        "popular": lambda p: -p.review_count,
    }
    filtered.sort(key=sorters.get(sort, sorters["popular"]))

    paginator = Paginator(filtered, PAGE_SIZE)
    try:
        page_obj = paginator.page(request.GET.get("page", 1))
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    params = request.GET.copy()
    params.pop("page", None)
    querystring = params.urlencode()

    context = {
        "page_id": "category",
        "meta_description": f"{category.name} decoration packages from Barahi Florist & Events. {category.blurb}",
        "category": category,
        "packages": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "querystring": querystring,
        "result_count": len(filtered),
        "total_count": len(packages),
        "price_floor": price_floor,
        "price_ceiling": price_ceiling,
        "max_price": max_price,
        "min_rating": min_rating,
        "sort": sort,
        "sort_options": [
            {"value": "popular", "label": "Most booked"},
            {"value": "rating", "label": "Highest rated"},
            {"value": "price_low", "label": "Price: low to high"},
            {"value": "price_high", "label": "Price: high to low"},
            {"value": "discount", "label": "Biggest discount"},
        ],
        "rating_options": [
            {"value": "4.8", "label": "4.8 and above"},
            {"value": "4.5", "label": "4.5 and above"},
            {"value": "4.0", "label": "4.0 and above"},
        ],
        "breadcrumbs": [
            {"label": "Occasions", "url": "core:categories"},
            {"label": category.name, "url": None},
        ],
    }
    return render(request, "core/category_detail.html", context)


def package_detail(request, slug):
    package = q.get_package(slug)
    if package is None:
        raise Http404("No package matches the given slug.")

    category = package.category
    context = {
        "page_id": "package",
        "meta_description": package.description[:155],
        "package": package,
        "category": category,
        "time_slots": q.time_slots(),
        "add_ons": q.add_ons(),
        "related": q.related_packages(package, limit=6),
        "reviews": q.reviews_for(package, limit=5),
        "faqs": q.faqs(limit=4),
        "min_date": timezone.localdate().isoformat(),
        "max_date": (timezone.localdate() + timedelta(days=BOOKING_HORIZON_DAYS)).isoformat(),
        "breadcrumbs": [
            {"label": "Occasions", "url": "core:categories"},
            {"label": category.name, "url": "core:category_detail", "arg": category.slug},
            {"label": package.title, "url": None},
        ],
    }
    return render(request, "core/package_detail.html", context)


def how_it_works(request):
    context = {
        "page_id": "how-it-works",
        "meta_description": "How a Barahi Florist & Events booking works, from choosing a package to the decorator leaving.",
        "how_it_works": q.how_it_works(),
        "features": q.features(),
        "faqs": q.faqs(),
        "trust_badges": q.trust_badges(),
        "breadcrumbs": [{"label": "How it works", "url": None}],
    }
    return render(request, "core/how_it_works.html", context)


def contact(request):
    context = {
        "page_id": "contact",
        "meta_description": "Talk to the Barahi Florist & Events team about a booking, a custom setup or a corporate event.",
        "occasions": q.categories(),
        "faqs": q.faqs(limit=4),
        "breadcrumbs": [{"label": "Contact", "url": None}],
    }
    return render(request, "core/contact.html", context)


# ---------------------------------------------------------------------------
# Booking an event
#
# A booking from the site is a draft Event in the panel, flagged as new, with
# the customer found by phone number or added. Nothing is charged here: the
# team calls, confirms it in the panel, and the customer's page follows along.
# ---------------------------------------------------------------------------

BOOKING_FIELDS = [
    "occasion", "package", "event_date", "time_slot", "city", "address", "guests",
    "name", "phone", "email", "notes",
]


@never_cache
def book(request):
    source = request.POST if request.method == "POST" else request.GET
    form = BookingRequestForm(request.POST or None)

    if request.method == "POST":
        if form.is_valid():
            event = form.save()
            _remember_booking(request, event)
            ActivityLog.record(
                None, "create", obj=event, model_label="Event", detail="booked on the website",
            )
            messages.success(
                request,
                f"Thank you, {event.customer.name.split()[0]} — your request is in. "
                "We call you within the hour to confirm.",
                extra_tags="booked",
            )
            return redirect(f"{reverse('core:booking_status', args=[event.number])}?new=1")
        messages.error(request, "A few details need another look — they are marked below.")

    values = {name: source.get(name, "") for name in BOOKING_FIELDS}
    # The home page search and the setup page post a date as `date` and a slot
    # as `slot`; the booking form calls them something longer.
    values["event_date"] = values["event_date"] or source.get("date", "")
    values["time_slot"] = values["time_slot"] or source.get("slot", "")
    picked_extras = set(source.getlist("add_ons"))

    packages = form.packages
    chosen_package = next((p for p in packages if p.slug == values["package"]), None)
    if chosen_package and not values["occasion"]:
        values["occasion"] = chosen_package.category.slug
    if not values["city"]:
        values["city"] = request.GET.get("city", "") or getattr(q.site_settings(), "default_city", "")

    today = timezone.localdate()
    context = {
        "page_id": "book",
        "meta_description": "Book an event with Barahi Florist & Events: pick the occasion, a setup and a date, and we call to confirm.",
        "form": form,
        "errors": form.errors if request.method == "POST" else {},
        "values": values,
        "picked_extras": picked_extras,
        "occasions": form.occasions,
        "packages": packages,
        "slots": form.slots,
        "extras": form.extras,
        "chosen_package": chosen_package,
        "min_date": today.isoformat(),
        "max_date": (today + timedelta(days=BOOKING_HORIZON_DAYS)).isoformat(),
        "breadcrumbs": [{"label": "Book an event", "url": None}],
    }
    return render(request, "core/book.html", context)


def _my_booking(request, number):
    event = get_object_or_404(
        Event.objects.select_related("customer", "occasion", "package", "package__category"),
        number=number,
    )
    if event.pk not in request.session.get(MY_BOOKINGS, []):
        return None
    return event


@never_cache
def booking_status(request, number):
    event = _my_booking(request, number.upper())
    if event is None:
        # The number alone is not enough to see someone's booking.
        return redirect(f"{reverse('core:track')}?number={number}")

    return render(request, "core/booking_status.html", {
        "page_id": "booking",
        "meta_description": "Your booking with Barahi Florist & Events.",
        "event": event,
        "is_new": request.GET.get("new") == "1",
        "extras": event.booked_extras or [],
        "base_price": event.package.price if event.package_id else 0,
        "breadcrumbs": [
            {"label": "Your bookings", "url": "core:track"},
            {"label": event.number, "url": None},
        ],
    })


@require_POST
def booking_cancel(request, number):
    event = _my_booking(request, number.upper())
    if event is None:
        return redirect(f"{reverse('core:track')}?number={number}")
    if not event.can_customer_cancel:
        messages.error(
            request,
            "This booking is already confirmed, so it cannot be cancelled online — "
            "call us and we will sort it out.",
        )
        return redirect("core:booking_status", number=event.number)
    try:
        event.cancel()
    except ValidationError as error:
        for message in error.messages:
            messages.error(request, message)
        return redirect("core:booking_status", number=event.number)
    ActivityLog.record(None, "update", obj=event, model_label="Event", detail="cancelled")
    Event.objects.filter(pk=event.pk).update(is_new=True)
    messages.info(
        request,
        f"{event.number} is cancelled. We hope to celebrate with you another time.",
        extra_tags="cancelled",
    )
    return redirect("core:booking_status", number=event.number)


@never_cache
def track(request):
    form = TrackBookingForm(request.POST or None, initial={"number": request.GET.get("number", "")})
    if request.method == "POST" and form.is_valid():
        event = form.cleaned_data["event"]
        _remember_booking(request, event)
        return redirect("core:booking_status", number=event.number)

    remembered = request.session.get(MY_BOOKINGS, [])
    mine = {e.pk: e for e in Event.objects.filter(pk__in=remembered).select_related("occasion")}
    return render(request, "core/track.html", {
        "page_id": "track",
        "meta_description": "Check on a booking with Barahi Florist & Events.",
        "form": form,
        "bookings": [mine[pk] for pk in remembered if pk in mine],
        "breadcrumbs": [{"label": "Your bookings", "url": None}],
    })


def cart(request):
    """There is no basket any more: an event is booked in one go."""
    return redirect("core:book", permanent=True)


# ---------------------------------------------------------------------------
# Enquiries
# ---------------------------------------------------------------------------


@never_cache
def enquire(request):
    """
    Where every enquiry form posts. A good one goes back to the page it came
    from with a thank-you; a bad one is shown again here with what was typed.
    """
    form = EnquiryForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            enquiry = form.save()
            messages.success(
                request,
                f"Thanks {enquiry.name.split()[0]} — that's with the team. "
                "Somebody replies within the hour, 9 AM to 11 PM.",
                extra_tags="enquired",
            )
            back = _safe_next(request, reverse("core:enquire"))
            return redirect(f"{back.split('#')[0]}#enquiry")
        messages.error(request, "A few details need another look — they are marked below.")

    source = request.POST if request.method == "POST" else request.GET
    package = q.get_package(source.get("package", "")) if source.get("package") else None
    values = {
        name: source.get(name, "")
        for name in ("name", "phone", "email", "city", "occasion", "event_date", "guests", "message")
    }
    if package and not values["occasion"]:
        values["occasion"] = package.category.slug

    return render(request, "core/enquire.html", {
        "page_id": "enquire",
        "meta_description": "Ask Barahi Florist & Events about an occasion, a setup or a custom event.",
        "form": form,
        "errors": form.errors if request.method == "POST" else {},
        "values": values,
        "package": package,
        "occasions": q.categories(),
        "next": _safe_next(request, ""),
        "faqs": q.faqs(limit=4),
        "breadcrumbs": [{"label": "Ask a question", "url": None}],
    })


def page_not_found(request, exception=None):
    """Handler for 404s. Also routed at /preview/404/ so it can be styled with DEBUG on."""
    context = {
        "page_id": "not-found",
        "popular_categories": q.categories()[:6],
    }
    return render(request, "404.html", context, status=404)
