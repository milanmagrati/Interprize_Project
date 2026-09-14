from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("products/", views.products, name="products"),
    # Occasions keep their old route names, so links saved in the panel still work.
    path("occasions/", views.categories, name="categories"),
    path("occasions/<slug:slug>/", views.category_detail, name="category_detail"),
    path("categories/", RedirectView.as_view(pattern_name="core:categories", permanent=True, query_string=True)),
    path("category/<slug:slug>/", RedirectView.as_view(pattern_name="core:category_detail", permanent=True, query_string=True)),
    path("package/<slug:slug>/", views.package_detail, name="package_detail"),

    # -- booking an event ---------------------------------------------------
    path("book/", views.book, name="book"),
    path("bookings/", views.track, name="track"),
    path("bookings/<str:number>/", views.booking_status, name="booking_status"),
    path("bookings/<str:number>/cancel/", views.booking_cancel, name="booking_cancel"),
    path("enquire/", views.enquire, name="enquire"),

    path("how-it-works/", views.how_it_works, name="how_it_works"),
    path("contact/", views.contact, name="contact"),
    # The old basket page; booking happens in one go now.
    path("cart/", views.cart, name="cart"),
    # Lets you look at the styled 404 while DEBUG = True.
    path("preview/404/", views.page_not_found, name="preview_404"),
]
