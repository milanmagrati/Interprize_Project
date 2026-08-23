"""
Template helpers for the public site.

`static_v` is the one that matters: this project has no
ManifestStaticFilesStorage, so a plain `{% static %}` URL never changes when the
file behind it does and browsers happily serve an edited CSS file from cache for
days. Appending the file's mtime makes every edit a new URL.

`panel/templatetags/panel_tags.py` re-registers this same function so both
sides of the site share one implementation.
"""

import os

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def static_v(path):
    """`{% static %}` with the file's mtime appended as a cache-buster."""
    url = static(path)
    found = finders.find(path)
    if not found:
        return url
    return f"{url}?v={int(os.path.getmtime(found))}"
