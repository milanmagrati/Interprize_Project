"""Context available to every template: brand chrome, nav, city list."""

from django.utils.functional import SimpleLazyObject

from . import queries


def site_chrome(request):
    settings_row = queries.brand()
    cities = queries.cities()
    default_city = getattr(settings_row, "default_city", "Kathmandu")
    return {
        "brand": settings_row,
        "nav_links": queries.nav_links(),
        "cities": cities,
        "popular_cities": queries.popular_cities(),
        "categories": queries.categories(),
        # Bookings made or looked up in this browser, still to come.
        # No query at all for a browser that has not booked anything.
        "booking_count": queries.open_booking_count(request.session.get("my_bookings", [])),
        "active_city": request.GET.get("city") or default_city,
        # Read by the header's Products drop-down. Lazy, so a menu without a
        # Products link never runs the query.
        "nav_products": SimpleLazyObject(queries.nav_products),
    }
