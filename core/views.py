"""
Function-based views for the Celebra public site.

Every lookup goes through `core.queries`, which returns published rows only.
Nothing here knows about the admin panel; the panel writes to the same models
and these views simply read whatever is currently published.
"""

from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import Http404
from django.shortcuts import redirect, render

from . import queries as q
from .forms import EnquiryForm

PAGE_SIZE = 6


def handle_enquiry(request):
    """
    Save a contact-form submission.

    The enquiry form is included on more than one page, so this returns a
    redirect on success (post/redirect/get, no resubmission on refresh) and
    None otherwise, leaving the calling view to render its own page.
    """
    if request.method != "POST":
        return None

    form = EnquiryForm(request.POST)
    if form.is_valid():
        enquiry = form.save()
        messages.success(
            request,
            f"Thanks {enquiry.name.split()[0]} — that's with the team. "
            "Somebody replies within the hour, 9 AM to 11 PM.",
        )
        return redirect(f"{request.path}#enquiry")

    for errors in form.errors.values():
        for error in errors:
            messages.error(request, error)
    return None


def home(request):
    saved = handle_enquiry(request)
    if saved:
        return saved

    context = {
        "page_id": "home",
        "meta_description": (
            "Celebra books balloon and event decoration setups in 100+ cities at "
            "fixed prices, with verified decorators and an on-time guarantee."
        ),
        "hero_slides": q.hero_slides(),
        "trust_badges": q.trust_badges(),
        "featured_packages": q.featured_packages(limit=8),
        "how_it_works": q.how_it_works(),
        "features": q.features(),
        "testimonials": q.testimonials(),
        "pricing_rows": q.pricing_rows(),
        "faqs": q.faqs(limit=6),
        "occasions": q.categories(),
    }
    return render(request, "core/home.html", context)


def categories(request):
    context = {
        "page_id": "categories",
        "meta_description": "Every occasion Celebra decorates, from first birthdays to reception stages.",
        "category_rows": q.category_rows(),
        "breadcrumbs": [{"label": "All categories", "url": None}],
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
        "meta_description": f"{category.name} decoration packages from Celebra. {category.blurb}",
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
            {"label": "Categories", "url": "core:categories"},
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
        "breadcrumbs": [
            {"label": "Categories", "url": "core:categories"},
            {"label": category.name, "url": "core:category_detail", "arg": category.slug},
            {"label": package.title, "url": None},
        ],
    }
    return render(request, "core/package_detail.html", context)


def how_it_works(request):
    context = {
        "page_id": "how-it-works",
        "meta_description": "How a Celebra booking works, from choosing a package to the decorator leaving.",
        "how_it_works": q.how_it_works(),
        "features": q.features(),
        "faqs": q.faqs(),
        "trust_badges": q.trust_badges(),
        "breadcrumbs": [{"label": "How it works", "url": None}],
    }
    return render(request, "core/how_it_works.html", context)


def contact(request):
    saved = handle_enquiry(request)
    if saved:
        return saved

    context = {
        "page_id": "contact",
        "meta_description": "Talk to the Celebra team about a booking, a custom setup or a corporate event.",
        "occasions": q.categories(),
        "faqs": q.faqs(limit=4),
        "breadcrumbs": [{"label": "Contact", "url": None}],
    }
    return render(request, "core/contact.html", context)


def cart(request):
    context = {
        "page_id": "cart",
        "meta_description": "Your Celebra cart.",
        "cart": q.cart_summary(),
        "suggested": q.featured_packages(limit=4),
        "breadcrumbs": [{"label": "Cart", "url": None}],
    }
    return render(request, "core/cart.html", context)


def page_not_found(request, exception=None):
    """Handler for 404s. Also routed at /preview/404/ so it can be styled with DEBUG on."""
    context = {
        "page_id": "not-found",
        "popular_categories": q.categories()[:6],
    }
    return render(request, "404.html", context, status=404)
