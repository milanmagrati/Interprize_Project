"""
Template helpers for the panel.

`cell` is the important one: the list table renders every column through it, so
a new column kind is a branch in one template rather than a change to nineteen
list pages.
"""

import os

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def static_v(path):
    """
    `{% static %}`, but with the file's mtime appended as a cache-buster so an
    edited CSS/JS file is never served stale from the browser cache — this
    project has no ManifestStaticFilesStorage to do that automatically.
    """
    url = static(path)
    found = finders.find(path)
    if not found:
        return url
    return f"{url}?v={int(os.path.getmtime(found))}"


@register.filter
def lookup(obj, name):
    """Attribute, property or zero-argument method — templates cannot call methods with args."""
    value = getattr(obj, name, "")
    return value() if callable(value) else value


@register.filter
def money(value):
    try:
        return f"₹{int(value):,}"
    except (TypeError, ValueError):
        return value


@register.filter
def excerpt(value, length=90):
    text = str(value or "").strip()
    return text if len(text) <= length else text[: length - 1].rstrip() + "…"


@register.filter
def tone_for(column, value):
    """Badge colour for a value, from the column's `badges` map."""
    if not column.badges:
        return "grey"
    return column.badges.get(str(value), "grey")


@register.simple_tag(takes_context=True)
def querystring(context, **kwargs):
    """
    Current query string with some parameters replaced. `None` drops a key.

        {% querystring sort='-price' page=None %}
    """
    request = context["request"]
    params = request.GET.copy()
    for key, value in kwargs.items():
        if value is None or value == "":
            params.pop(key, None)
        else:
            params[key] = value
    if "page" not in kwargs:
        # Changing a filter should send you back to page one.
        params.pop("page", None)
    encoded = params.urlencode()
    return mark_safe(f"?{encoded}" if encoded else "")


@register.simple_tag(takes_context=True)
def sort_link(context, field):
    """Toggles between ascending and descending on the column you click."""
    request = context["request"]
    current = request.GET.get("sort", "")
    new = f"-{field}" if current == field else field
    params = request.GET.copy()
    params["sort"] = new
    params.pop("page", None)
    return mark_safe(f"?{params.urlencode()}")


@register.simple_tag(takes_context=True)
def sort_state(context, field):
    current = context["request"].GET.get("sort", "")
    if current == field:
        return "asc"
    if current == f"-{field}":
        return "desc"
    return ""


@register.inclusion_tag("panel/partials/_cell.html", takes_context=True)
def cell(context, row, column, resource):
    value = lookup(row, column.name)
    hint = lookup(row, column.hint) if column.hint else ""
    return {
        "row": row,
        "column": column,
        "resource": resource,
        "value": value,
        "hint": hint,
        "tone": tone_for(column, value),
        "can_write": context.get("can_write", False),
        "csrf_token": context.get("csrf_token", ""),
    }


@register.inclusion_tag("panel/partials/_field.html")
def field(bound_field, wide=False):
    return {"field": bound_field, "wide": wide}


@register.filter
def rating_width(value):
    """Percentage width for the star overlay."""
    try:
        return round(float(value) * 20)
    except (TypeError, ValueError):
        return 0


@register.filter
def status_tone(value):
    """Colour for a status string, using the same map the list tables use."""
    from panel.resources import STATUS_TONES

    return STATUS_TONES.get(str(value), "grey")


@register.filter
def role_tone(role):
    return {"owner": "violet", "admin": "blue", "editor": "green", "viewer": "grey"}.get(role, "grey")


@register.filter
def action_tone(action):
    return {
        "create": "green",
        "update": "blue",
        "delete": "red",
        "bulk": "violet",
        "auth": "grey",
    }.get(action, "grey")
