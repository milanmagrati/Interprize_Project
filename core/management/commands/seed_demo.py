"""
Load the original sample content into the database.

    python manage.py seed_demo            # fills anything still empty
    python manage.py seed_demo --reset    # wipes the content tables first

`sample_data.py` is no longer read at request time — this command is the only
thing left that imports it. Events and enquiries are generated rather than
copied, so the panel's dashboard and schedule have something to show.
"""

import random
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core import sample_data as data
from core.models import (
    AddOn,
    Category,
    City,
    CounterSale,
    CounterSaleLine,
    Coupon,
    Customer,
    Enquiry,
    Event,
    EventExpense,
    EventItem,
    EventPayment,
    FAQ,
    Feature,
    HeroSlide,
    HowItWorksStep,
    InventoryItem,
    NavLink,
    Package,
    PricingRow,
    SiteSettings,
    StaffCategory,
    StaffMember,
    StockCategory,
    StockMovement,
    Supplier,
    Testimonial,
    TimeSlot,
    TrustBadge,
)

CONTENT_MODELS = [
    # Events first: their lines hold on to stock items, which refuse to go
    # while anything points at them.
    Event,
    Customer,
    # Then inventory: sales and ledger rows hang off the items above them.
    CounterSale,
    StockMovement,
    InventoryItem,
    StockCategory,
    Supplier,
    Enquiry,
    Coupon,
    StaffMember,
    StaffCategory,
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
    "Aarav", "Bibek", "Sujata", "Rohan", "Sabin", "Anish", "Kritika", "Sameer",
    "Saru", "Prabin", "Sunita", "Dipesh", "Anjali", "Nischal", "Sristi", "Bishal",
]
LAST_NAMES = [
    "Shrestha", "Thapa", "Gurung", "Rai", "Maharjan", "Karki", "Tamang",
    "Basnet", "Poudel", "Adhikari", "Magar", "Lama", "Khadka", "Bhattarai",
]
#: (group, tone) — how the demo store room is divided up.
STOCK_GROUPS = [
    ("Balloons", "violet", "Latex, foil, arches and everything to inflate them."),
    ("Fresh flowers", "green", "Stems and garlands, counted in bunches."),
    ("Fabric & drapes", "blue", "Backdrop cloth, runners, chair covers."),
    ("Lighting", "amber", "Fairy lights, uplighters, spare bulbs."),
    ("Tableware", "grey", "Crockery, cutlery and serving pieces on hire."),
]

SUPPLIERS = [
    ("Metro Party Supplies", "Rajesh Shrestha", 2),
    ("Green Valley Florists", "Sundari Gurung", 1),
    ("Drape House Textiles", "Imtiaz Khan", 5),
]

#: (name, group, supplier, unit, cost, sale, reorder, opening)
STOCK_ITEMS = [
    ("Latex balloon pack of 50", 0, 0, "pack", 120, 220, 10, 46),
    ("Foil number balloon", 0, 0, "piece", 90, 180, 12, 38),
    ("Balloon arch kit", 0, 0, "set", 340, 650, 4, 9),
    ("Helium canister", 0, 0, "piece", 1600, 2600, 2, 5),
    ("Rose bunch (20 stems)", 1, 1, "pack", 260, 480, 8, 22),
    ("Marigold garland", 1, 1, "piece", 70, 150, 15, 12),
    ("Orchid stem", 1, 1, "piece", 55, 120, 20, 64),
    ("Backdrop cloth, 3m", 2, 2, "metre", 180, 340, 12, 30),
    ("Chair cover", 2, 2, "piece", 45, 95, 40, 120),
    ("Table runner", 2, 2, "piece", 110, 240, 10, 26),
    ("Fairy light string, 10m", 3, 0, "roll", 210, 420, 8, 18),
    ("Warm uplighter", 3, 0, "piece", 900, 1500, 3, 7),
    ("Spare bulb pack", 3, 0, "pack", 130, 260, 6, 4),
    ("Dinner plate set of 12", 4, 2, "set", 420, 780, 4, 8),
    ("Cutlery set of 12", 4, 2, "set", 380, 700, 4, 3),
]

#: Stock that goes out to an event and comes back. Everything else is used up.
REUSABLE_STOCK = {
    "Balloon arch kit", "Helium canister", "Backdrop cloth, 3m", "Chair cover",
    "Table runner", "Fairy light string, 10m", "Warm uplighter",
    "Dinner plate set of 12", "Cutlery set of 12",
}

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
        self.seed_enquiries(categories)
        self.seed_coupons()
        self.seed_inventory(decorators)
        self.seed_events(decorators)

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
                    "booked": row["booked"],
                    "package": by_title.get(row["booked"]),
                    "date": row["date"],
                    "position": position,
                },
            )
        self.stdout.write(f"  {Testimonial.objects.count()} testimonials")

    # -- operations --------------------------------------------------------

    def seed_decorators(self, cities):
        metros = [c for c in cities if c.is_metro] or cities
        # The types themselves are created by the staff migration, so the
        # demo crews only have to pick one.
        decorator_type = StaffCategory.objects.filter(slug="decorator").first()
        for index, name in enumerate(DECORATOR_NAMES):
            StaffMember.objects.get_or_create(
                name=name,
                defaults={
                    "phone": f"+97798{random.randint(10000000, 99999999)}",
                    "city": metros[index % len(metros)],
                    "category": decorator_type,
                    "employment": random.choice(["inhouse", "freelance", "vendor"]),
                    "rating": round(random.uniform(4.3, 5.0), 1),
                    "is_verified": index % 4 != 3,
                },
            )
        decorators = list(StaffMember.objects.all())
        self.stdout.write(f"  {len(decorators)} staff members")
        return decorators

    def seed_enquiries(self, categories):
        if Enquiry.objects.exists():
            return
        occasions = [c.name for c in categories.values()]
        messages = [
            "Do you cover Baneshwor on a Sunday morning?",
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
                phone=f"+97798{random.randint(10000000, 99999999)}",
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

    def seed_inventory(self, staff):
        """
        Stock, its ledger and a month of counter sales.

        Counts are never assigned directly, exactly as in the panel: every item
        gets an opening-balance movement and the shelf total follows from it.
        """
        if InventoryItem.objects.exists():
            return

        groups = []
        for position, (name, tone, blurb) in enumerate(STOCK_GROUPS):
            group, _ = StockCategory.objects.get_or_create(
                name=name,
                defaults={"tone": tone, "description": blurb, "position": position},
            )
            groups.append(group)

        suppliers = []
        for name, contact, lead in SUPPLIERS:
            supplier, _ = Supplier.objects.get_or_create(
                name=name,
                defaults={
                    "contact_name": contact,
                    "lead_time_days": lead,
                    "phone": f"+97701{random.randint(10000000, 99999999)}",
                    "email": f"orders@{name.split()[0].lower()}.example",
                },
            )
            suppliers.append(supplier)

        items = []
        for name, group_index, supplier_index, unit, cost, price, reorder, opening in STOCK_ITEMS:
            item = InventoryItem.objects.create(
                name=name,
                category=groups[group_index],
                supplier=suppliers[supplier_index],
                unit=unit,
                cost_price=cost,
                sale_price=price,
                reorder_level=reorder,
                usage_type="reusable" if name in REUSABLE_STOCK else "consumable",
                location=f"Rack {group_index + 1}-{len(items) % 4 + 1}",
            )
            item.record_movement(
                opening, kind="opening", unit_cost=cost, note="Opening count",
            )
            items.append(item)
        self.stdout.write(f"  {len(items)} stock items")

        # A month of walk-ins, so the stock room has a shape to show.
        now = timezone.now()
        sellable = [item for item in items if item.quantity > 2]
        for day_back in range(28, 0, -1):
            for _ in range(random.randint(0, 2)):
                basket = random.sample(sellable, random.randint(1, 3))
                sale = CounterSale.objects.create(
                    customer_name=(
                        f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
                        if random.random() > 0.35 else ""
                    ),
                    phone=f"+97798{random.randint(10000000, 99999999)}",
                    sold_at=now - timedelta(days=day_back, hours=random.randint(0, 8)),
                    served_by=random.choice(staff) if staff else None,
                    payment_method=random.choice(["cash", "cash", "upi", "upi", "card"]),
                    discount=random.choice([0, 0, 0, 50, 100]),
                    tax_percent=random.choice([0, 0, 5]),
                )
                lines = []
                for item in basket:
                    item.refresh_from_db()
                    if item.quantity < 1:
                        continue
                    quantity = min(random.randint(1, 3), int(item.quantity))
                    lines.append(CounterSaleLine(
                        sale=sale, item=item, name=item.name, sku=item.sku,
                        quantity=quantity, unit_price=item.sale_price,
                        unit_cost=item.cost_price,
                    ))
                if not lines:
                    sale.delete()
                    continue
                CounterSaleLine.objects.bulk_create(lines)
                sale.recalculate()
                sale.apply_stock()

        # One refund, because a panel that has never seen one looks untested.
        refundable = CounterSale.objects.order_by("-sold_at").first()
        if refundable:
            refundable.refund(note="Customer changed their mind")

        sold = CounterSale.objects.count()
        self.stdout.write(f"  {sold} counter sales, {StockMovement.objects.count()} ledger rows")

    def seed_events(self, crews=()):
        """
        A handful of events in every state, built through the same model methods
        the panel calls, so each reservation and return lands in the ledger.
        """
        if Event.objects.exists() or not InventoryItem.objects.exists():
            return

        today = timezone.localdate()
        customers = [
            Customer.objects.create(
                name=f"{first} {last}",
                phone=f"+97798{random.randint(10000000, 99999999)}",
                email=f"{first.lower()}.{last.lower()}@example.com",
            )
            for first, last in [
                ("Ananya", "Iyer"), ("Vikram", "Malhotra"), ("Fatima", "Sheikh"),
                ("Rohan", "Nair"), ("Priya", "Kapoor"),
            ]
        ]

        #: (name, customer, days from today, guests, revenue, final status,
        #:  [(stock item, qty)], [(external, qty, unit cost)], [(expense, category, amount)],
        #:  share of revenue paid)
        plans = [
            ("Iyer wedding reception", 0, 12, 250, 185000, "confirmed",
             [("Chair cover", 40), ("Table runner", 8), ("Rose bunch (20 stems)", 6)],
             [("Mandap flower wall", 1, 42000)],
             [("Venue deposit", "venue", 25000)], 0.4),
            ("Malhotra 50th anniversary", 1, 3, 80, 64000, "in_progress",
             [("Chair cover", 30), ("Fairy light string, 10m", 3), ("Latex balloon pack of 50", 4)],
             [("Live violinist", 1, 9000)],
             [("Tempo hire", "transport", 2200), ("Crew meals", "food", 1800)], 0.5),
            ("Sheikh baby shower", 2, -6, 40, 38000, "completed",
             [("Table runner", 6), ("Backdrop cloth, 3m", 9), ("Foil number balloon", 6)],
             [("Custom welcome banner", 1, 1800)],
             [("Fuel", "fuel", 900), ("Decor helper", "staff", 1500)], 1.0),
            ("Nair corporate launch", 3, 21, 120, 96000, "draft",
             [("Backdrop cloth, 3m", 12), ("Dinner plate set of 12", 3)],
             [("Rented sound system", 1, 14000)], [], 0),
            ("Kapoor engagement", 4, 9, 150, 72000, "cancelled",
             [("Chair cover", 30)], [], [], 0),
        ]

        # Every event is one occasion, so each demo event names its own rather
        # than hoping the event's name happens to contain an occasion's.
        occasion_of = {
            "Iyer wedding reception": "wedding",
            "Malhotra 50th anniversary": "anniversary",
            "Sheikh baby shower": "baby-shower",
            "Nair corporate launch": "corporate",
            "Kapoor engagement": "romantic",
        }
        occasions = {c.slug: c for c in Category.objects.all()}
        fallback = Category.objects.order_by("position", "id").first()

        for (name, who, days, guests, revenue, status, stock_lines, externals,
             expenses, share) in plans:
            event = Event.objects.create(
                name=name, customer=customers[who], guests=guests, revenue=revenue,
                event_date=today + timedelta(days=days),
                location=random.choice([
                    "Palace Grounds, Bellary Road", "The Leela, Old Airport Road",
                    "Rooftop, Indiranagar", "Community hall, Jayanagar 4th Block",
                ]),
                occasion=occasions.get(occasion_of.get(name), fallback),
            )
            if crews:
                event.crew.set(random.sample(list(crews), min(2, len(crews))))
            for item_name, quantity in stock_lines:
                item = InventoryItem.objects.filter(name=item_name).first()
                if item is None:
                    continue
                # The demo counter sales may have run the shelf short; take
                # what is free rather than fail.
                quantity = min(quantity, int(item.available_quantity))
                if quantity > 0:
                    event.add_inventory_item(item, quantity)
            for item_name, quantity, cost in externals:
                EventItem.objects.create(
                    event=event, item_type="external", name=item_name,
                    quantity=quantity, unit_cost=cost, vendor="Local vendor",
                )
            for label, category, amount in expenses:
                EventExpense.objects.create(
                    event=event, name=label, category=category, amount=amount,
                    spent_on=min(today, event.event_date),
                )
            if share:
                EventPayment.objects.create(
                    event=event, amount=int(revenue * share), method="upi",
                    paid_on=min(today, event.event_date), reference="Advance",
                )

            if status == "draft":
                continue
            try:
                self.advance(event, status)
            except ValidationError:
                pass  # not enough free stock to go further; it stays where it got to

        self.stdout.write(f"  {Event.objects.count()} events for {Customer.objects.count()} customers")

    @staticmethod
    def advance(event, status):
        event.confirm()
        if status == "cancelled":
            event.cancel()
            return
        event.allocate()
        if status == "confirmed":
            return
        event.start()
        if status == "in_progress":
            return
        for line in event.items.filter(item_type="inventory"):
            if line.usage_type == "reusable":
                # One of everything reusable comes back broken, so the demo
                # shows a write-off.
                line.record_usage(returned=line.outstanding - 1, damaged=1)
            else:
                line.record_usage(consumed=line.outstanding)
        event.complete()

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
