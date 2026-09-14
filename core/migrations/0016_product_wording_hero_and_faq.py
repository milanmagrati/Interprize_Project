"""
The rest of the seeded copy that still called a product a "setup": the hero
slides and one FAQ. As in 0015, only rows still holding the exact original text
are rewritten.
"""

from django.db import migrations

# (model, field): [(old, new), ...]
SEEDED_COPY = {
    ("HeroSlide", "description"): [
        ("Pick a setup, pick a slot, and a Celebra decorator arrives with everything in the van "
         "— builds it, photographs it, and takes the packaging away.",
         "Pick a product, pick a slot, and a Celebra decorator arrives with everything in the van "
         "— builds it, photographs it, and takes the packaging away."),
    ],
    ("HeroSlide", "meta"): [
        ("148 birthday setups \xb7 from Rs. 1,499", "148 birthday products \xb7 from Rs. 1,499"),
        ("58 wedding setups \xb7 from Rs. 7,999", "58 wedding products \xb7 from Rs. 7,999"),
        ("87 romantic setups \xb7 from Rs. 2,199", "87 romantic products \xb7 from Rs. 2,199"),
        ("112 themed setups \xb7 from Rs. 2,999", "112 themed products \xb7 from Rs. 2,999"),
        ("64 baby shower setups \xb7 from Rs. 2,499", "64 baby shower products \xb7 from Rs. 2,499"),
    ],
    ("FAQ", "answer"): [
        ("Tell us in the booking notes and the decorator switches to freestanding frames, weighted "
         "bases and removable clips. Most of our setups already work this way — we decorate a "
         "lot of rented flats and hotel rooms.",
         "Tell us in the booking notes and the decorator switches to freestanding frames, weighted "
         "bases and removable clips. Most of our products already work this way — we decorate a "
         "lot of rented flats and hotel rooms."),
    ],
}


def _rewrite(apps, forwards):
    for (model_name, field), pairs in SEEDED_COPY.items():
        model = apps.get_model("core", model_name)
        for old, new in pairs:
            before, after = (old, new) if forwards else (new, old)
            model.objects.filter(**{field: before}).update(**{field: after})


def forwards(apps, schema_editor):
    _rewrite(apps, forwards=True)


def backwards(apps, schema_editor):
    _rewrite(apps, forwards=False)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_product_wording"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
