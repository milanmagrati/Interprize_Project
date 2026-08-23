from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve as serve_static

urlpatterns = [
    # Django's own admin stays available for the raw-data cases the panel does
    # not cover (permissions, sessions, a bad migration).
    path("admin/", admin.site.urls),
    path("manage/", include("panel.urls", namespace="panel")),
    path("", include("core.urls", namespace="core")),
]

# Uploaded media, served by Django itself. django.conf.urls.static.static()
# is a no-op once DEBUG=False, but the deploy target has no separate web
# server in front, so wire the view directly — fine at this traffic level;
# move to object storage if that changes.
urlpatterns += [
    re_path(
        r"^%s(?P<path>.*)$" % settings.MEDIA_URL.lstrip("/"),
        serve_static,
        {"document_root": settings.MEDIA_ROOT},
    ),
]

# Custom error handlers. With DEBUG = True Django shows its own debug page
# instead, so /preview/404/ exists to review the styled page during development.
handler404 = "core.views.page_not_found"
