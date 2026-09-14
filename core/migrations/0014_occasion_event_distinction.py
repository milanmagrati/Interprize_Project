"""
An occasion is the kind of celebration; an event is one booking of it.

- A review's `occasion` always held the setup that was booked, so it is renamed
  to `booked` (the column is renamed, the text kept).
- An occasion with events can no longer be deleted out from under them.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_alter_countersale_discount_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="testimonial",
            old_name="occasion",
            new_name="booked",
        ),
        migrations.AlterField(
            model_name="testimonial",
            name="booked",
            field=models.CharField(
                blank=True,
                help_text="The setup they had, shown as “Booked …”. Filled from the product when one is linked.",
                max_length=140,
                verbose_name="What they booked",
            ),
        ),
        migrations.AlterField(
            model_name="event",
            name="name",
            field=models.CharField(
                help_text="This event's own name, e.g. Aarav's 5th birthday. The occasion says what kind it is.",
                max_length=160,
                verbose_name="Event name",
            ),
        ),
        migrations.AlterField(
            model_name="event",
            name="occasion",
            field=models.ForeignKey(
                blank=True,
                help_text="The kind of celebration — Birthday, Wedding… Every event is one occasion.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="events",
                to="core.category",
            ),
        ),
    ]
