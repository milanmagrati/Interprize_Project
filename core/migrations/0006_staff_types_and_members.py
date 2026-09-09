"""
Decorators become staff.

The old `Decorator` table held one kind of worker. It is renamed rather than
replaced so every existing row — and every booking pointing at one — survives,
and a `StaffCategory` is added on top so the same table can hold florists,
photographers and drivers too. Existing rows are moved into a "Decorator" type
by the data step at the end, which is exactly what they were.
"""

from django.conf import settings
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


DEFAULT_TYPES = [
    ("Decorator", "field", "green", "Builds and dresses the setup on site."),
    ("Florist", "field", "violet", "Fresh flowers, bouquets and floral walls."),
    ("Photographer", "field", "blue", "Photo and video coverage of the event."),
    ("Driver", "field", "amber", "Moves the kit between the warehouse and the venue."),
    ("Helper", "field", "grey", "Extra hands for setup and clean-up."),
    ("Coordinator", "office", "blue", "Runs the schedule and talks to the customer."),
]


def seed_types(apps, schema_editor):
    StaffCategory = apps.get_model("core", "StaffCategory")
    StaffMember = apps.get_model("core", "StaffMember")

    created = {}
    for position, (name, kind, tone, description) in enumerate(DEFAULT_TYPES):
        row, _ = StaffCategory.objects.get_or_create(
            slug=name.lower(),
            defaults={
                "name": name,
                "kind": kind,
                "tone": tone,
                "description": description,
                "position": position,
            },
        )
        created[name] = row

    # Everyone who existed before this migration was, by definition, a decorator.
    StaffMember.objects.filter(category__isnull=True).update(category=created["Decorator"])


def drop_types(apps, schema_editor):
    apps.get_model("core", "StaffCategory").objects.filter(
        slug__in=[name.lower() for name, *_ in DEFAULT_TYPES]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0005_add_logo_height_and_show_name"),
    ]

    operations = [
        migrations.RenameModel(old_name="Decorator", new_name="StaffMember"),
        migrations.RenameField(model_name="booking", old_name="decorator", new_name="staff"),
        migrations.CreateModel(
            name="StaffCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, help_text="Lower numbers appear first. Drag rows in the list to reorder.")),
                ("name", models.CharField(max_length=60, unique=True)),
                ("slug", models.SlugField(blank=True, max_length=70, unique=True)),
                ("kind", models.CharField(choices=[("field", "Field crew — on site at the event"), ("office", "Office — coordination and support"), ("partner", "Partner — vendor or agency")], default="field", help_text="The broad bucket this type belongs to. Used to filter the staff list.", max_length=10, verbose_name="Group")),
                ("tone", models.CharField(choices=[("green", "Green"), ("blue", "Blue"), ("violet", "Violet"), ("amber", "Amber"), ("red", "Red"), ("grey", "Grey")], default="grey", help_text="The colour this type wears wherever it is shown.", max_length=10, verbose_name="Badge colour")),
                ("description", models.CharField(blank=True, help_text="What this type is responsible for.", max_length=200)),
                ("is_active", models.BooleanField(default=True, help_text="Turn off to retire a type. Existing staff keep it; new ones cannot pick it.", verbose_name="Selectable")),
            ],
            options={
                "verbose_name": "Staff type",
                "verbose_name_plural": "Staff types",
                "ordering": ["position", "id"],
                "abstract": False,
            },
        ),
        migrations.AlterModelOptions(
            name="staffmember",
            options={"ordering": ["name"], "verbose_name": "Staff member", "verbose_name_plural": "Staffs"},
        ),
        migrations.AlterModelOptions(
            name="staffprofile",
            options={"ordering": ["user__username"], "verbose_name": "Panel account", "verbose_name_plural": "Panel accounts"},
        ),
        migrations.AddField(
            model_name="staffmember",
            name="category",
            field=models.ForeignKey(blank=True, help_text="What they do. The list is managed under Staff types.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="members", to="core.staffcategory", verbose_name="Staff type"),
        ),
        migrations.AddField(
            model_name="staffmember",
            name="employment",
            field=models.CharField(choices=[("inhouse", "In-house"), ("freelance", "Freelance"), ("vendor", "Vendor / agency"), ("intern", "Intern")], default="inhouse", help_text="How this person is engaged.", max_length=12, verbose_name="Engagement"),
        ),
        migrations.AddField(
            model_name="staffmember",
            name="skills",
            field=models.CharField(blank=True, help_text="Comma separated — balloons, mandap, drone. Shown when you assign a booking.", max_length=160),
        ),
        migrations.AddField(
            model_name="staffmember",
            name="account",
            field=models.OneToOneField(blank=True, help_text="The control-panel account this person signs in with, if they have one.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="staff_member", to=settings.AUTH_USER_MODEL, verbose_name="Panel login"),
        ),
        migrations.AlterField(
            model_name="staffmember",
            name="city",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="staff_members", to="core.city"),
        ),
        migrations.AlterField(
            model_name="staffmember",
            name="rating",
            field=models.DecimalField(decimal_places=1, default=5, max_digits=2, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(5)]),
        ),
        migrations.AlterField(
            model_name="booking",
            name="staff",
            field=models.ForeignKey(blank=True, help_text="Who is doing this job. Filter the list by staff type when you pick.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="bookings", to="core.staffmember", verbose_name="Assigned to"),
        ),
        migrations.AlterField(
            model_name="booking",
            name="status",
            field=models.CharField(choices=[("new", "New"), ("confirmed", "Confirmed"), ("assigned", "Staff assigned"), ("completed", "Completed"), ("cancelled", "Cancelled")], db_index=True, default="new", max_length=20),
        ),
        migrations.AddField(
            model_name="invitecode",
            name="staff_member",
            field=models.ForeignKey(blank=True, help_text="Optional. Whoever signs up with this code is linked to that staff record.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="invites", to="core.staffmember", verbose_name="For which staff member"),
        ),
        migrations.RunPython(seed_types, drop_types),
    ]
