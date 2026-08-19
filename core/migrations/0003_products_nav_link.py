"""
Put "Products" in the header menu.

The link is a NavLink row like every other menu entry, so it stays editable
(and removable) from the panel afterwards. It goes in straight after Home,
which means the links below it shift down one place.
"""

from django.db import migrations
from django.db.models import F

LABEL = "Products"
ROUTE = "core:products"
POSITION = 1


def add_link(apps, schema_editor):
    NavLink = apps.get_model("core", "NavLink")
    if NavLink.objects.filter(url_name=ROUTE).exists():
        return
    NavLink.objects.filter(position__gte=POSITION).update(position=F("position") + 1)
    NavLink.objects.create(
        label=LABEL, url_name=ROUTE, anchor="", position=POSITION, is_active=True
    )


def remove_link(apps, schema_editor):
    NavLink = apps.get_model("core", "NavLink")
    removed = NavLink.objects.filter(url_name=ROUTE)
    if not removed.exists():
        return
    removed.delete()
    NavLink.objects.filter(position__gt=POSITION).update(position=F("position") - 1)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_sitesettings_home_products_cta_label_and_more"),
    ]

    operations = [
        migrations.RunPython(add_link, remove_link),
    ]
