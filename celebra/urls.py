from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls", namespace="core")),
]

# Custom error handlers. With DEBUG = True Django shows its own debug page
# instead, so /preview/404/ exists to review the styled page during development.
handler404 = "core.views.page_not_found"
