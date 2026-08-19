from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("products/", views.products, name="products"),
    path("categories/", views.categories, name="categories"),
    path("category/<slug:slug>/", views.category_detail, name="category_detail"),
    path("package/<slug:slug>/", views.package_detail, name="package_detail"),
    path("how-it-works/", views.how_it_works, name="how_it_works"),
    path("contact/", views.contact, name="contact"),
    path("cart/", views.cart, name="cart"),
    # Lets you look at the styled 404 while DEBUG = True.
    path("preview/404/", views.page_not_found, name="preview_404"),
]
