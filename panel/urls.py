"""
Control panel routes.

Everything sits under /manage/. The resource routes are generic — `slug` is a
key in `resources.BY_SLUG`, so adding a model to the registry adds its five
URLs at the same time.

The catch-all resource patterns come last so the named pages above them
(schedule, counter, stock, settings, staff…) are never shadowed by a resource
with the same slug — which is why the inventory tables are `stock-items` and
`stock-ledger` rather than plain `stock`.
"""

from django.urls import path

from . import event_views, views

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
    # Kept because the section used to live here and links are still around.
    path("decorators/", views.decorators_redirect, name="decorators_redirect"),
    path("staff/<int:pk>/", views.staff_edit, name="staff_edit"),
    path("staff/invite/<int:pk>/revoke/", views.invite_delete, name="invite_delete"),
    path("activity/", views.activity, name="activity"),
    path("media/", views.media_library, name="media"),

    # -- inventory --------------------------------------------------------
    path("counter/", views.counter, name="counter"),
    path("counter/<int:pk>/", views.counter_sale, name="counter_sale"),
    path("counter/<int:pk>/refund/", views.counter_refund, name="counter_refund"),
    path("stock/", views.stock_room, name="stock"),

    # -- events -----------------------------------------------------------
    path("events/", event_views.event_list, name="events"),
    path("events/new/", event_views.event_create, name="event_create"),
    path("events/<int:pk>/", event_views.event_detail, name="event_detail"),
    path("events/<int:pk>/edit/", event_views.event_edit, name="event_edit"),
    path("events/<int:pk>/delete/", event_views.event_delete, name="event_delete"),
    path("events/<int:pk>/action/", event_views.event_action, name="event_action"),
    path("events/<int:pk>/items/stock/", event_views.event_add_stock, name="event_add_stock"),
    path("events/<int:pk>/items/external/", event_views.event_add_external, name="event_add_external"),
    path("events/<int:pk>/items/<int:line_pk>/", event_views.event_line_edit, name="event_line_edit"),
    path("events/<int:pk>/items/<int:line_pk>/remove/", event_views.event_line_remove, name="event_line_remove"),
    path("events/<int:pk>/items/<int:line_pk>/usage/", event_views.event_line_usage, name="event_line_usage"),
    path("events/<int:pk>/expenses/", event_views.event_add_expense, name="event_add_expense"),
    path("events/<int:pk>/expenses/<int:expense_pk>/remove/", event_views.event_remove_expense, name="event_remove_expense"),
    path("events/<int:pk>/payments/", event_views.event_add_payment, name="event_add_payment"),
    path("events/<int:pk>/payments/<int:payment_pk>/remove/", event_views.event_remove_payment, name="event_remove_payment"),

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
