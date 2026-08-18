"""
Load the original sample content into the database.

    python manage.py seed_demo            # fills anything still empty
    python manage.py seed_demo --reset    # wipes the content tables first

`sample_data.py` is no longer read at request time — this command is the only
thing left that imports it. Bookings and enquiries are generated rather than
copied, so the panel's dashboard has a plausible few months of history to show.
"""

import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core import sample_data as data
from core.models import (
    AddOn,
    Booking,
    Category,
    City,
    Coupon,
    Decorator,
    Enquiry,
    FAQ,
    Feature,
    HeroSlide,
    HowItWorksStep,
    NavLink,
    Package,
    PricingRow,
    SiteSettings,
    Testimonial,
    TimeSlot,
    TrustBadge,
)

CONTENT_MODELS = [
    Booking,
    Enquiry,
    Coupon,
    Decorator,
    Testimonial,
    PricingRow,
    Package,
    Category,
    HeroSlide,
    FAQ,
    Feature,
    HowItWorksStep,
    TimeSlot,
    AddOn,
    TrustBadge,
    NavLink,
    City,
]

FIRST_NAMES = [
    "Ananya", "Vikram", "Meera", "Rohan", "Priya", "Arjun", "Fatima", "Sanjay",
    "Neha", "Imran", "Kavya", "Dev", "Ishita", "Nikhil", "Aisha", "Rahul",
]
LAST_NAMES = [
    "Raghavan", "Sethi", "Joshi", "Nair", "Deshmukh", "Malhotra", "Sheikh",
    "Krishnan", "Bansal", "Qureshi", "Iyer", "Kapoor", "Menon", "Verma",
]
DECORATOR_NAMES = [
    "Lakshmi Crew", "Studio Marigold", "The Balloon Room", "Anand Events",
    "Petal & Post", "Northside Decor", "Bright Hall Team",
]


class Command(BaseCommand):
    help = "Populate the database with the original sample content."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing content rows before seeding. Staff accounts are untouched.",
        )
        parser.add_argument(
            "--bookings",
            type=int,
            default=60,
            help="How many demo bookings to generate (default 60).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(20260817)  # stable output, so re-running looks the same

        if options["reset"]:
            for model in CONTENT_MODELS:
                deleted, _ = model.objects.all().delete()
                if deleted:
                    self.stdout.write(f"  cleared {model._meta.verbose_name_plural}")

        self.seed_settings()
        cities = self.seed_cities()
        categories = self.seed_categories()
        packages = self.seed_packages(categories)
        self.seed_hero()
        self.seed_copy(categories)
        self.seed_testimonials(packages)
        decorators = self.seed_decorators(cities)
        self.seed_bookings(packages, cities, decorators, options["bookings"])
        self.seed_enquiries(categories)
        self.seed_coupons()

        self.stdout.write(self.style.SUCCESS("\nSeeded. Sign in at /manage/ to edit any of it."))

    # -- chrome ------------------------------------------------------------

    def seed_settings(self):
        row = SiteSettings.objects.current()
        brand = data.BRAND
        for field in ("name", "tagline", "phone", "email", "address", "hours",
                      "founded_year", "instagram", "facebook", "youtube", "twitter"):
            setattr(row, field, brand[field])
        row.whatsapp = brand["whatsapp"]
        row.default_city = data.DEFAULT_CITY
        row.save()

        for position, link in enumerate(data.NAV_LINKS):
            NavLink.objects.get_or_create(
                label=link["label"],
                defaults={
                    "url_name": link["url_name"],
                    "anchor": link["anchor"],
                    "position": position,
                },
            )
        for position, badge in enumerate(data.TRUST_BADGES):
            TrustBadge.objects.get_or_create(
                label=badge["label"],
                defaults={"value": badge["value"], "position": position},
            )
        self.stdout.write("  settings, nav and trust badges")

    def seed_cities(self):
        for row in data.CITIES:
            City.objects.get_or_create(
                name=row["name"],
                defaults={"slug": row["slug"], "state": row["state"], "is_metro": row["is_metro"]},
            )
        cities = list(City.objects.all())
        self.stdout.write(f"  {len(cities)} cities")
        return cities

    # -- catalogue ---------------------------------------------------------

    def seed_categories(self):
        for position, row in enumerate(data.CATEGORIES):
            Category.objects.get_or_create(
                slug=row["slug"],
                defaults={
                    "name": row["name"],
                    "icon": row["icon"],
                    "blurb": row["blurb"],
                    "price_from": row["price_from"],
                    "package_count": row["package_count"],
                    "position": position,
                },
            )
        categories = {c.slug: c for c in Category.objects.all()}
        self.stdout.write(f"  {len(categories)} categories")
        return categories

    def seed_packages(self, categories):
        for position, row in enumerate(data.PACKAGES):
            Package.objects.get_or_create(
                slug=row["slug"],
                defaults={
                    "title": row["title"],
                    "category": categories[row["category"]],
                    "price": row["price"],
                    "original_price": row["original_price"],
                    "rating": row["rating"],
                    "review_count": row["review_count"],
                    "duration": row["duration"],
                    "badge": row["badge"],
                    "description": row["description"],
                    "includes_text": "\n".join(row["includes"]),
                    "is_featured": row["is_featured"],
                    "position": position,
                },
            )
        packages = list(Package.objects.all())
        self.stdout.write(f"  {len(packages)} packages")
        return packages

    def seed_hero(self):
        for position, row in enumerate(data.HERO_SLIDES):
            HeroSlide.objects.get_or_create(
                key=row["id"],
                defaults={
                    "media_type": row["media_type"],
                    "eyebrow": row["eyebrow"],
                    "heading": row["heading"],
                    "heading_accent": row["heading_accent"],
                    "description": row["description"],
                    "meta": row["meta"],
                    "alt": row["alt"],
                    "image_seed": row["image_seed"],
                    "video_mp4": row["video_mp4"] or "",
                    "video_webm": row["video_webm"] or "",
                    "duration": row["duration"],
                    "tint": row["tint"],
                    "focal": row["focal"],
                    "cta_label": row["cta_label"],
                    "cta_url_name": row["cta_url_name"],
                    "cta_url_arg": row["cta_url_arg"] or "",
                    "cta_anchor": row.get("cta_anchor", ""),
                    "cta2_label": row["cta2_label"] or "",
                    "cta2_url_name": row["cta2_url_name"] or "",
                    "cta2_url_arg": row["cta2_url_arg"] or "",
                    "cta2_anchor": row.get("cta2_anchor", ""),
                    "position": position,
                },
            )
        self.stdout.write(f"  {HeroSlide.objects.count()} hero slides")

    def seed_copy(self, categories):
        for position, row in enumerate(data.HOW_IT_WORKS):
            HowItWorksStep.objects.get_or_create(
                title=row["title"],
                defaults={
                    "step": row["step"],
                    "icon": row["icon"],
                    "text": row["text"],
                    "position": position,
                },
            )
        for position, row in enumerate(data.FEATURES):
            Feature.objects.get_or_create(
                title=row["title"],
                defaults={"icon": row["icon"], "text": row["text"], "position": position},
            )
        for position, row in enumerate(data.FAQS):
            FAQ.objects.get_or_create(
                question=row["question"],
                defaults={"answer": row["answer"], "position": position},
            )
        for position, row in enumerate(data.PRICING_ROWS):
            category = categories.get(row["slug"])
            if category:
                PricingRow.objects.get_or_create(
                    category=category,
                    defaults={
                        "range": row["range"],
                        "popular": row["popular"],
                        "setup_time": row["setup_time"],
                        "position": position,
                    },
                )
        for position, row in enumerate(data.TIME_SLOTS):
            TimeSlot.objects.get_or_create(
                value=row["value"],
                defaults={"label": row["label"], "available": row["available"], "position": position},
            )
        for position, row in enumerate(data.ADD_ONS):
            AddOn.objects.get_or_create(
                name=row["name"], defaults={"price": row["price"], "position": position}
            )
        self.stdout.write("  steps, features, FAQs, pricing, slots and add-ons")

    def seed_testimonials(self, packages):
        by_title = {p.title: p for p in packages}
        for position, row in enumerate(data.TESTIMONIALS):
            Testimonial.objects.get_or_create(
                name=row["name"],
                text=row["text"],
                defaults={
                    "city": row["city"],
                    "rating": row["rating"],
                    "occasion": row["occasion"],
                    "package": by_title.get(row["occasion"]),
                    "date": row["date"],
                    "position": position,
                },
            )
        self.stdout.write(f"  {Testimonial.objects.count()} testimonials")

    # -- operations --------------------------------------------------------

    def seed_decorators(self, cities):
        metros = [c for c in cities if c.is_metro] or cities
        for index, name in enumerate(DECORATOR_NAMES):
            Decorator.objects.get_or_create(
                name=name,
                defaults={
                    "phone": f"+9198{random.randint(10000000, 99999999)}",
                    "city": metros[index % len(metros)],
                    "rating": round(random.uniform(4.3, 5.0), 1),
                    "is_verified": index % 4 != 3,
                },
            )
        decorators = list(Decorator.objects.all())
        self.stdout.write(f"  {len(decorators)} decorators")
        return decorators

    def seed_bookings(self, packages, cities, decorators, count):
        if Booking.objects.exists() or not packages:
            return
        today = timezone.localdate()
        slots = [s.label for s in TimeSlot.objects.all()] or ["4 PM – 6 PM"]
        add_ons = list(AddOn.objects.all())
        metros = [c for c in cities if c.is_metro] or cities

        # Weighted towards the past so the dashboard has revenue history, with a
        # tail of upcoming jobs for the schedule board.
        for index in range(count):
            offset = random.randint(-120, 30)
            event_date = today + timedelta(days=offset)
            package = random.choice(packages)
            quantity = 1 if random.random() < 0.85 else 2

            if offset < -1:
                status = "cancelled" if random.random() < 0.08 else "completed"
            elif offset < 3:
                status = random.choice(["assigned", "confirmed"])
            else:
                status = random.choice(["new", "new", "confirmed", "assigned"])

            payment = {
                "completed": "paid",
                "cancelled": "refunded",
                "assigned": "advance",
                "confirmed": "advance",
                "new": "unpaid",
            }[status]

            booking = Booking.objects.create(
                customer_name=f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
                email=f"guest{index}@example.com",
                phone=f"+9198{random.randint(10000000, 99999999)}",
                package=package,
                quantity=quantity,
                city=random.choice(metros),
                address=f"Flat {random.randint(101, 908)}, {random.choice(['Lake View', 'Green Acres', 'Sunrise Residency', 'Palm Court'])}",
                event_date=event_date,
                time_slot=random.choice(slots),
                amount=package.price * quantity,
                status=status,
                payment_status=payment,
                decorator=random.choice(decorators) if status in ("assigned", "completed") else None,
                notes=random.choice(
                    ["", "", "Surprise — do not call, message on arrival.", "No adhesive on walls.",
                     "Lift access only until 8 PM.", "Park in visitor bay B."]
                ),
            )
            if add_ons and random.random() < 0.4:
                booking.add_ons.add(random.choice(add_ons))
            # created_at is auto_now_add; push it back so charts have a spread.
            Booking.objects.filter(pk=booking.pk).update(
                created_at=timezone.now() - timedelta(days=max(0, -offset) + random.randint(2, 9))
            )
        self.stdout.write(f"  {Booking.objects.count()} bookings")

    def seed_enquiries(self, categories):
        if Enquiry.objects.exists():
            return
        occasions = [c.name for c in categories.values()]
        messages = [
            "Do you cover Whitefield on a Sunday morning?",
            "Looking for a corporate launch setup for about 80 guests.",
            "Can the balloon wall be done in navy and silver instead?",
            "Is same-day booking possible for tomorrow evening?",
            "We need a quote for a three-day wedding function.",
            "Do you provide a photographer with the romantic setups?",
        ]
        for index, message in enumerate(messages):
            row = Enquiry.objects.create(
                name=f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
                email=f"enquiry{index}@example.com",
                phone=f"+9198{random.randint(10000000, 99999999)}",
                city=random.choice(list(data.CITIES))["name"],
                occasion=random.choice(occasions),
                event_date=timezone.localdate() + timedelta(days=random.randint(3, 40)),
                message=message,
                status=random.choice(["new", "new", "read", "replied"]),
            )
            Enquiry.objects.filter(pk=row.pk).update(
                created_at=timezone.now() - timedelta(days=index, hours=random.randint(0, 20))
            )
        self.stdout.write(f"  {Enquiry.objects.count()} enquiries")

    def seed_coupons(self):
        rows = [
            ("WELCOME10", "percent", 10, 2000, 0),
            ("DIWALI500", "flat", 500, 4000, 200),
            ("FIRSTBABY", "percent", 15, 3000, 50),
        ]
        for code, kind, value, min_order, max_uses in rows:
            Coupon.objects.get_or_create(
                code=code,
                defaults={
                    "kind": kind,
                    "value": value,
                    "min_order": min_order,
                    "max_uses": max_uses,
                    "valid_to": timezone.localdate() + timedelta(days=90),
                },
            )
        self.stdout.write(f"  {Coupon.objects.count()} coupons")
