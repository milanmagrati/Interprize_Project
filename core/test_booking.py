"""
Booking an event from the website, and everything that follows from it: the
customer's own booking page, finding it again, cancelling a request, asking a
question, and what the panel sees of all of it.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    ActivityLog,
    AddOn,
    Category,
    City,
    Customer,
    Enquiry,
    Event,
    NavLink,
    Package,
    StaffProfile,
    TimeSlot,
)


class BookingTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.birthday = Category.objects.create(name="Birthday", blurb="Balloons and cake tables", icon="gift")
        cls.wedding = Category.objects.create(name="Wedding", blurb="Stages and mandaps", icon="sparkles")
        cls.hidden = Category.objects.create(name="Retired", blurb="Gone", is_active=False)
        cls.wall = Package.objects.create(
            title="Golden Balloon Wall", category=cls.birthday, price=4999, original_price=6999,
            description="A wall of balloons.",
        )
        cls.stage = Package.objects.create(
            title="Mandap Stage", category=cls.wedding, price=45000, original_price=50000,
            description="A stage.",
        )
        cls.offline = Package.objects.create(
            title="Old Setup", category=cls.birthday, price=100, original_price=100,
            description="Unpublished.", is_active=False,
        )
        cls.photographer = AddOn.objects.create(name="Photographer", price=1999)
        cls.takedown = AddOn.objects.create(name="Take-down", price=499)
        cls.evening = TimeSlot.objects.create(label="4 PM – 6 PM", value="16-18")
        cls.full = TimeSlot.objects.create(label="8 PM – 10 PM", value="20-22", available=False)
        cls.city = City.objects.create(name="Kathmandu", state="Bagmati")

    def booking(self, **overrides):
        data = {
            "occasion": "birthday",
            "package": self.wall.slug,
            "event_date": (timezone.localdate() + timedelta(days=10)).isoformat(),
            "time_slot": "16-18",
            "city": self.city.slug,
            "address": "12 Lazimpat Road",
            "guests": "30",
            "add_ons": [str(self.photographer.pk)],
            "name": "Milan Magrati",
            "phone": "98660 41254",
            "email": "milan@example.com",
            "notes": "Pastel colours, please.",
            "website": "",
        }
        data.update(overrides)
        return {key: value for key, value in data.items() if value is not None}

    def book(self, **overrides):
        return self.client.post(reverse("core:book"), self.booking(**overrides))


class BookPageTests(BookingTestCase):
    def test_page_renders_with_choices_prefilled_from_the_link(self):
        response = self.client.get(reverse("core:book"), {"package": self.wall.slug, "date": "2030-01-02", "slot": "16-18"})
        self.assertEqual(response.status_code, 200)
        page = response.content.decode()
        self.assertRegex(page, r'name="occasion" value="birthday"[^>]*\schecked')
        self.assertRegex(page, rf'name="package" value="{self.wall.slug}"[^>]*\schecked')
        self.assertNotRegex(page, r'name="occasion" value="wedding"[^>]*\schecked')
        self.assertIn('value="2030-01-02"', page)
        self.assertNotIn("Old Setup", page)       # unpublished packages are not offered
        self.assertNotIn("Retired", page)
        self.assertIn("8 PM – 10 PM <em>full</em>", page)

    def test_a_booking_becomes_a_new_draft_event_with_its_customer(self):
        response = self.book()
        event = Event.objects.get()
        self.assertRedirects(response, reverse("core:booking_status", args=[event.number]) + "?new=1")

        self.assertEqual(event.status, "draft")
        self.assertEqual(event.source, "website")
        self.assertTrue(event.is_new)
        self.assertEqual(event.occasion, self.birthday)
        self.assertEqual(event.package, self.wall)
        self.assertEqual(event.time_slot, "4 PM – 6 PM")
        self.assertEqual(event.location, "12 Lazimpat Road, Kathmandu")
        self.assertEqual(event.guests, 30)
        self.assertEqual(event.revenue, 4999 + 1999)
        self.assertEqual(event.booked_extras, [{"name": "Photographer", "price": 1999}])
        self.assertEqual(event.name, "Golden Balloon Wall — Milan")
        self.assertIsNone(event.created_by)

        customer = event.customer
        self.assertEqual((customer.name, customer.phone, customer.email), ("Milan Magrati", "98660 41254", "milan@example.com"))
        self.assertTrue(ActivityLog.objects.filter(detail="booked on the website").exists())

    def test_a_returning_phone_number_is_the_same_customer(self):
        known = Customer.objects.create(name="Milan M.", phone="+977-9866041254")
        self.book(email="new@example.com")
        event = Event.objects.get()
        self.assertEqual(event.customer, known)
        known.refresh_from_db()
        self.assertEqual(known.name, "Milan M.")            # never renamed from the website
        self.assertEqual(known.email, "new@example.com")    # but gaps are filled
        self.assertIn("Booked as Milan Magrati.", event.notes)
        self.assertEqual(Customer.objects.count(), 1)

    def test_no_setup_means_planned_together_and_quoted_later(self):
        self.book(package="", add_ons=[], occasion="wedding")
        event = Event.objects.get()
        self.assertIsNone(event.package)
        self.assertEqual(event.revenue, 0)
        self.assertEqual(event.name, "Wedding celebration — Milan")

    def test_a_setup_alone_says_which_occasion(self):
        self.book(occasion="")
        self.assertEqual(Event.objects.get().occasion, self.birthday)

    def test_bad_requests_book_nothing_and_say_why(self):
        cases = {
            "event_date": ((timezone.localdate() - timedelta(days=1)).isoformat(), "That date has already gone"),
            "time_slot": ("20-22", "is full"),
            "phone": ("12345", "10-digit phone number"),
            "package": (self.offline.slug, "no longer available"),
            "occasion": ("retired", "not one we book"),
            "address": ("", "Tell us where the event is"),
        }
        for field, (value, message) in cases.items():
            with self.subTest(field=field):
                response = self.book(**{field: value})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, message)
        # A wedding package for a birthday.
        response = self.book(package=self.stage.slug)
        self.assertContains(response, "is a Wedding package")
        # No occasion and no package.
        response = self.book(occasion="", package="")
        self.assertContains(response, "Pick what you are celebrating.")
        self.assertEqual(Event.objects.count(), 0)

    def test_what_was_typed_survives_an_error(self):
        response = self.book(phone="1")
        self.assertContains(response, 'value="12 Lazimpat Road"')
        self.assertContains(response, "Pastel colours, please.")

    def test_bots_filling_the_hidden_field_book_nothing(self):
        self.book(website="http://spam.example")
        self.assertEqual(Event.objects.count(), 0)


class BookingPageTests(BookingTestCase):
    def setUp(self):
        self.book()
        self.event = Event.objects.get()
        self.page = reverse("core:booking_status", args=[self.event.number])

    def test_the_browser_that_booked_sees_its_booking(self):
        response = self.client.get(self.page + "?new=1")
        self.assertContains(response, "Request received")
        self.assertContains(response, "Golden Balloon Wall")
        self.assertContains(response, "Photographer")
        self.assertContains(response, "Cancel this request")
        self.assertEqual(response["Cache-Control"].count("no-store"), 1)

    def test_anyone_else_is_sent_to_prove_it_with_the_phone(self):
        other = self.client_class()
        response = other.get(self.page)
        self.assertRedirects(response, reverse("core:track") + f"?number={self.event.number}")

        wrong = other.post(reverse("core:track"), {"number": self.event.number, "phone": "9999999999"})
        self.assertContains(wrong, "No booking matches that number and phone")

        right = other.post(reverse("core:track"), {"number": self.event.pk, "phone": "+977 9866041254"})
        self.assertRedirects(right, self.page)
        self.assertContains(other.get(self.page), "Golden Balloon Wall")

    def test_the_page_follows_the_panel(self):
        self.event.confirm()
        response = self.client.get(self.page)
        self.assertContains(response, "Confirmed")
        self.assertNotContains(response, "Cancel this request")
        self.assertContains(response, "call us")

    def test_a_request_can_be_withdrawn_until_it_is_confirmed(self):
        Event.objects.filter(pk=self.event.pk).update(is_new=False)
        response = self.client.post(reverse("core:booking_cancel", args=[self.event.number]))
        self.assertRedirects(response, self.page)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, "cancelled")
        self.assertTrue(self.event.is_new)          # the panel hears about it
        self.assertContains(self.client.get(self.page), "Cancelled")

    def test_a_confirmed_booking_cannot_be_cancelled_online(self):
        self.event.confirm()
        self.client.post(reverse("core:booking_cancel", args=[self.event.number]))
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, "confirmed")

    def test_a_stranger_cannot_cancel(self):
        self.client_class().post(reverse("core:booking_cancel", args=[self.event.number]))
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, "draft")

    def test_the_header_counts_bookings_still_to_come(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Your bookings, 1 coming up")
        self.assertContains(self.client.get(reverse("core:track")), self.event.number)


class EnquiryTests(BookingTestCase):
    def test_an_enquiry_about_a_setup_returns_to_the_page_it_came_from(self):
        back = reverse("core:package_detail", args=[self.wall.slug])
        response = self.client.post(reverse("core:enquire"), {
            "name": "Sita", "phone": "9800000000", "message": "Pastel?", "package": self.wall.slug,
            "guests": "25", "next": back,
        })
        self.assertRedirects(response, back + "#enquiry", fetch_redirect_response=False)
        enquiry = Enquiry.objects.get()
        self.assertEqual((enquiry.package, enquiry.occasion, enquiry.guests), (self.wall, "Birthday", 25))

    def test_a_bad_enquiry_is_shown_again_with_its_text(self):
        response = self.client.post(reverse("core:enquire"), {"name": "", "phone": "", "message": "Keep me"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tell us your name.")
        self.assertContains(response, "Keep me")
        self.assertEqual(Enquiry.objects.count(), 0)

    def test_an_unsafe_next_is_ignored(self):
        response = self.client.post(reverse("core:enquire"), {
            "name": "Sita", "phone": "9800000000", "next": "https://evil.example/",
        })
        self.assertRedirects(response, reverse("core:enquire") + "#enquiry", fetch_redirect_response=False)

    def test_pages_carrying_the_form_render(self):
        for url in (
            reverse("core:home"), reverse("core:contact"), reverse("core:enquire"),
            reverse("core:enquire") + f"?package={self.wall.slug}",
            reverse("core:package_detail", args=[self.wall.slug]),
            reverse("core:category_detail", args=["birthday"]),
            reverse("core:categories"), reverse("core:track"),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


class NamingTests(BookingTestCase):
    def test_occasions_have_one_name_and_old_links_still_work(self):
        self.assertEqual(reverse("core:categories"), "/occasions/")
        self.assertRedirects(self.client.get("/categories/"), "/occasions/", status_code=301)
        self.assertRedirects(
            self.client.get("/category/birthday/?sort=rating"), "/occasions/birthday/?sort=rating", status_code=301,
        )
        self.assertRedirects(self.client.get("/cart/"), reverse("core:book"), status_code=301)

    def test_the_setup_page_hands_its_choices_to_the_booking_page(self):
        response = self.client.get(reverse("core:package_detail", args=[self.wall.slug]))
        self.assertContains(response, f'action="{reverse("core:book")}"')
        self.assertContains(response, f'name="add_ons" value="{self.photographer.pk}"')
        self.assertNotContains(response, "Add to cart")


class PanelSideTests(BookingTestCase):
    def setUp(self):
        user = get_user_model().objects.create_user("desk", password="x-Strong-pass-1")
        StaffProfile.objects.create(user=user, role="editor")
        self.panel = self.client_class()
        self.panel.force_login(user)

    def test_a_website_booking_is_flagged_until_someone_opens_it(self):
        self.book()
        event = Event.objects.get()

        listing = self.panel.get(reverse("panel:events"))
        self.assertContains(listing, "1 new from the website")
        self.assertContains(listing, '<span class="newtag">New</span>', html=False)
        self.assertContains(self.panel.get(reverse("panel:events") + "?source=website"), event.number)
        self.assertNotContains(self.panel.get(reverse("panel:events") + "?source=panel"), event.number)

        detail = self.panel.get(reverse("panel:event_detail", args=[event.pk]))
        self.assertContains(detail, "Booked on the website")
        self.assertContains(detail, "Photographer")
        self.assertContains(detail, "the customer, online")
        event.refresh_from_db()
        self.assertFalse(event.is_new)
        self.assertNotContains(self.panel.get(reverse("panel:events")), "new from the website")

    def test_an_enquiry_becomes_an_event_through_the_form(self):
        enquiry = Enquiry.objects.create(
            name="Sita Sharma", phone="9800000000", occasion="Wedding", package=self.stage,
            guests=200, message="A winter wedding.",
        )
        form = self.panel.get(reverse("panel:event_create") + f"?enquiry={enquiry.pk}")
        self.assertContains(form, "Filled in from")
        self.assertContains(form, 'value="Mandap Stage — Sita"')

        response = self.panel.post(reverse("panel:event_create"), {
            "enquiry": enquiry.pk,
            "name": "Mandap Stage — Sita",
            "package": self.stage.pk,
            "event_date": (timezone.localdate() + timedelta(days=60)).isoformat(),
            "new_customer_name": "Sita Sharma",
            "new_customer_phone": "9800000000",
            "guests": 200, "revenue": 45000, "time_slot": "4 PM – 6 PM",
        })
        event = Event.objects.get()
        self.assertRedirects(response, reverse("panel:event_detail", args=[event.pk]) + "#items", fetch_redirect_response=False)
        self.assertEqual((event.source, event.occasion, event.time_slot), ("enquiry", self.wedding, "4 PM – 6 PM"))
        enquiry.refresh_from_db()
        self.assertEqual((enquiry.event, enquiry.status), (event, "read"))

        # Opening the same enquiry again goes to the event instead of a second one.
        again = self.panel.get(reverse("panel:event_create") + f"?enquiry={enquiry.pk}")
        self.assertRedirects(again, reverse("panel:event_detail", args=[event.pk]), fetch_redirect_response=False)
        edit = self.panel.get(reverse("panel:resource_edit", args=["enquiries", enquiry.pk]))
        self.assertContains(edit, f"Open {event.number}")

    def test_the_menu_calls_them_occasions(self):
        NavLink.objects.create(label="Occasions", url_name="core:categories")
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, ">Occasions</a>")

    def test_the_listing_calls_them_packages(self):
        self.assertEqual(reverse("core:products"), "/packages/")
        old = self.client.get("/products/?occasion=birthday")
        self.assertRedirects(old, "/packages/?occasion=birthday", status_code=301, fetch_redirect_response=False)
        page = self.client.get(reverse("core:products"))
        self.assertContains(page, "Search packages")
        self.assertContains(page, self.wall.title)
        self.assertNotContains(page, "Search products")
