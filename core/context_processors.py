"""Context available to every template: brand chrome, nav, city list."""

from . import sample_data


def site_chrome(request):
    return {
        "brand": sample_data.BRAND,
        "nav_links": sample_data.NAV_LINKS,
        "cities": sample_data.CITIES,
        "popular_cities": sample_data.POPULAR_CITIES,
        "categories": sample_data.CATEGORIES,
        # Cart badge count. Real implementation reads the session/cart model.
        "cart_count": len(sample_data.CART_ITEMS),
        "active_city": request.GET.get("city") or sample_data.DEFAULT_CITY,
    }
