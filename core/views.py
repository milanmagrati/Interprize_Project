"""
Function-based views for the Celebra frontend.

Nothing here touches the database. Each view assembles a context dict from
`core.sample_data` in the same shape a queryset would return, so swapping in
real models later is a line-for-line replacement inside these functions.
"""

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import Http404
from django.shortcuts import render

from . import sample_data as data

PAGE_SIZE = 6


def home(request):
    context = {
        "page_id": "home",
        "meta_description": (
            "Celebra books balloon and event decoration setups in 100+ cities at "
            "fixed prices, with verified decorators and an on-time guarantee."
        ),
        "trust_badges": data.TRUST_BADGES,
        "featured_packages": data.featured_packages(limit=8),
        "how_it_works": data.HOW_IT_WORKS,
        "features": data.FEATURES,
        "testimonials": data.TESTIMONIALS,
        "pricing_rows": data.PRICING_ROWS,
        "faqs": data.FAQS[:6],
        "occasions": data.CATEGORIES,
    }
    return render(request, "core/home.html", context)


def categories(request):
    context = {
        "page_id": "categories",
        "meta_description": "Every occasion Celebra decorates, from first birthdays to reception stages.",
        "category_rows": data.category_counts(),
        "breadcrumbs": [{"label": "All categories", "url": None}],
    }
    return render(request, "core/categories.html", context)


def category_detail(request, slug):
    category = data.get_category(slug)
    if category is None:
        raise Http404("No category matches the given slug.")

    packages = data.packages_in_category(slug)

    # Filters. Real backend swaps these for queryset .filter() calls.
    def _int(name, default=None):
        raw = request.GET.get(name)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    price_floor = min((p["price"] for p in packages), default=0)
    price_ceiling = max((p["price"] for p in packages), default=50000)
    max_price = _int("max_price", price_ceiling)
    min_rating = request.GET.get("rating", "")
    sort = request.GET.get("sort", "popular")

    filtered = [p for p in packages if p["price"] <= max_price]
    if min_rating:
        try:
            filtered = [p for p in filtered if p["rating"] >= float(min_rating)]
        except ValueError:
            min_rating = ""

    sorters = {
        "price_low": lambda p: p["price"],
        "price_high": lambda p: -p["price"],
        "rating": lambda p: -p["rating"],
        "discount": lambda p: -p["discount_percent"],
        "popular": lambda p: -p["review_count"],
    }
    filtered.sort(key=sorters.get(sort, sorters["popular"]))

    paginator = Paginator(filtered, PAGE_SIZE)
    try:
        page_obj = paginator.page(request.GET.get("page", 1))
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    # Querystring without `page`, so pagination links keep the active filters.
    params = request.GET.copy()
    params.pop("page", None)
    querystring = params.urlencode()

    context = {
        "page_id": "category",
        "meta_description": f"{category['name']} decoration packages from Celebra. {category['blurb']}",
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
            {"label": category["name"], "url": None},
        ],
    }
    return render(request, "core/category_detail.html", context)


def package_detail(request, slug):
    package = data.get_package(slug)
    if package is None:
        raise Http404("No package matches the given slug.")

    category = data.get_category(package["category"])
    context = {
        "page_id": "package",
        "meta_description": package["description"][:155],
        "package": package,
        "category": category,
        "time_slots": data.TIME_SLOTS,
        "add_ons": data.ADD_ONS,
        "related": data.related_packages(package, limit=6),
        "reviews": data.reviews_for(package, limit=5),
        "faqs": data.FAQS[:4],
        "breadcrumbs": [
            {"label": "Categories", "url": "core:categories"},
            {"label": category["name"], "url": "core:category_detail", "arg": category["slug"]},
            {"label": package["title"], "url": None},
        ],
    }
    return render(request, "core/package_detail.html", context)


def how_it_works(request):
    context = {
        "page_id": "how-it-works",
        "meta_description": "How a Celebra booking works, from choosing a package to the decorator leaving.",
        "how_it_works": data.HOW_IT_WORKS,
        "features": data.FEATURES,
        "faqs": data.FAQS,
        "trust_badges": data.TRUST_BADGES,
        "breadcrumbs": [{"label": "How it works", "url": None}],
    }
    return render(request, "core/how_it_works.html", context)


def contact(request):
    context = {
        "page_id": "contact",
        "meta_description": "Talk to the Celebra team about a booking, a custom setup or a corporate event.",
        "occasions": data.CATEGORIES,
        "faqs": data.FAQS[:4],
        "breadcrumbs": [{"label": "Contact", "url": None}],
    }
    return render(request, "core/contact.html", context)


def cart(request):
    context = {
        "page_id": "cart",
        "meta_description": "Your Celebra cart.",
        "cart": data.cart_summary(),
        "suggested": data.featured_packages(limit=4),
        "breadcrumbs": [{"label": "Cart", "url": None}],
    }
    return render(request, "core/cart.html", context)


def page_not_found(request, exception=None):
    """Handler for 404s. Also routed at /preview/404/ so it can be styled with DEBUG on."""
    context = {
        "page_id": "not-found",
        "popular_categories": data.CATEGORIES[:6],
    }
    return render(request, "404.html", context, status=404)
