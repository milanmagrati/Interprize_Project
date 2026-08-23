from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Django's own admin stays available for the raw-data cases the panel does
    # not cover (permissions, sessions, a bad migration).
    path("admin/", admin.site.urls),
    path("manage/", include("panel.urls", namespace="panel")),
    path("", include("core.urls", namespace="core")),
]

# Uploaded media, served by Django only while DEBUG is on. In production the
# web server should serve MEDIA_ROOT directly.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Custom error handlers. With DEBUG = True Django shows its own debug page
# instead, so /preview/404/ exists to review the styled page during development.
handler404 = "core.views.page_not_found"
