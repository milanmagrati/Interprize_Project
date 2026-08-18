"""
Control panel routes.

Everything sits under /manage/. The resource routes are generic — `slug` is a
key in `resources.BY_SLUG`, so adding a model to the registry adds its five
URLs at the same time.

The catch-all resource patterns come last so the named pages above them
(schedule, settings, staff…) are never shadowed by a resource with the same slug.
"""

from django.urls import path

from . import views

app_name = "panel"

urlpatterns = [
    # -- account ----------------------------------------------------------
    path("signup/", views.panel_signup, name="signup"),
    path("login/", views.panel_login, name="login"),
    path("logout/", views.panel_logout, name="logout"),
    path("account/", views.account, name="account"),
    path("account/theme/", views.set_theme, name="set_theme"),

    # -- pages ------------------------------------------------------------
    path("", views.dashboard, name="dashboard"),
    path("schedule/", views.schedule, name="schedule"),
    path("settings/", views.site_settings, name="settings"),
    path("staff/", views.staff_list, name="staff"),
    path("staff/<int:pk>/", views.staff_edit, name="staff_edit"),
    path("staff/invite/<int:pk>/revoke/", views.invite_delete, name="invite_delete"),
    path("activity/", views.activity, name="activity"),
    path("media/", views.media_library, name="media"),

    # -- json -------------------------------------------------------------
    path("search/", views.quick_search, name="search"),
    path("stats/", views.stats_json, name="stats"),

    # -- generic resources ------------------------------------------------
    path("<slug:slug>/", views.resource_list, name="resource_list"),
    path("<slug:slug>/new/", views.resource_form, name="resource_create"),
    path("<slug:slug>/export/", views.resource_export, name="resource_export"),
    path("<slug:slug>/reorder/", views.resource_reorder, name="resource_reorder"),
    path("<slug:slug>/<int:pk>/", views.resource_form, name="resource_edit"),
    path("<slug:slug>/<int:pk>/delete/", views.resource_delete, name="resource_delete"),
    path("<slug:slug>/<int:pk>/toggle/<str:field_name>/", views.resource_toggle, name="resource_toggle"),
]
