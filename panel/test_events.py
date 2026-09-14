"""
The Events pages, driven the way a person would: through the panel's URLs,
signed in with a real role.
"""

import re
import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Category,
    CounterSale,
    Customer,
    Event,
    EventExpense,
    EventItem,
    EventPayment,
    InventoryItem,
    StaffProfile,
    StockMovement,
    Testimonial,
)


def make_login(username, role):
    user = get_user_model().objects.create_user(username, password="x-Strong-pass-1")
    StaffProfile.objects.create(user=user, role=role)
    return user


class EventPanelTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = make_login("editor", "editor")
        cls.viewer = make_login("viewer", "viewer")
        cls.admin = make_login("boss", "admin")
        cls.customer = Customer.objects.create(name="Asha Rao", phone="+977 98450 00000")
        cls.wedding = Category.objects.create(name="Wedding", blurb="Stages and mandaps")

    def setUp(self):
        self.client.force_login(self.editor)
        self.chair = InventoryItem.objects.create(
            name="Chair", usage_type="reusable", cost_price=450, sale_price=900,
        )
        self.chair.record_movement(100, kind="opening")
        self.speaker = InventoryItem.objects.create(
            name="Speaker", usage_type="reusable", cost_price=3000, sale_price=6000,
        )
        self.speaker.record_movement(10, kind="opening")
        self.event = Event.objects.create(
            name="Rao wedding", customer=self.customer, revenue=250000, occasion=self.wedding,
            event_date=timezone.localdate() + timedelta(days=5), location="Palace Grounds",
        )

    def url(self, name, *args):
        return reverse(f"panel:{name}", args=args)

    def act(self, action, event=None):
        return self.client.post(self.url("event_action", (event or self.event).pk), {"action": action})

    def reload(self):
        self.event = Event.objects.get(pk=self.event.pk)
        return self.event


class PageTests(EventPanelTestCase):
    def test_pages_render(self):
        line = self.event.add_inventory_item(self.chair, 10)
        EventItem.objects.create(event=self.event, item_type="external", name="Flowers", quantity=1, unit_cost=5000)
        EventExpense.objects.create(event=self.event, name="Van", category="transport", amount=1500)
        EventPayment.objects.create(event=self.event, amount=20000)

        pages = [
            self.url("events"),
            self.url("events") + "?status=draft&when=upcoming&payment=partial&q=rao",
            self.url("events") + "?from=2020-01-01&to=2099-12-31&sort=-revenue",
            self.url("events") + "?from=2026-02-30&sort=bogus&page=99",
            self.url("event_create"),
            self.url("event_create") + f"?customer={self.customer.pk}",
            self.url("event_detail", self.event.pk),
            self.url("event_edit", self.event.pk),
            self.url("event_line_edit", self.event.pk, line.pk),
            self.url("resource_list", "customers"),
            self.url("resource_edit", "customers", self.customer.pk),
            self.url("resource_list", "stock-items"),
            self.url("resource_list", "stock-items") + "?usage_type=reusable&sort=free_total",
            self.url("resource_list", "stock-items") + "?q=chai&sort=-free_total",
            self.url("resource_list", "customers") + "?q=asha&sort=-billed",
            self.url("resource_edit", "stock-items", self.chair.pk),
            self.url("resource_list", "stock-ledger"),
            self.url("resource_create", "stock-ledger"),
            self.url("counter"),
            self.url("stock"),
            self.url("dashboard"),
        ]
        for page in pages:
            with self.subTest(page=page):
                response = self.client.get(page)
                self.assertEqual(response.status_code, 200)

    def test_sidebar_has_events(self):
        response = self.client.get(self.url("dashboard"))
        self.assertContains(response, f'href="{self.url("events")}"')
        self.assertContains(response, "Customers")

    def test_list_shows_money_columns(self):
        EventPayment.objects.create(event=self.event, amount=100000)
        response = self.client.get(self.url("events"))
        self.assertContains(response, self.event.number)
        self.assertContains(response, "Rs. 250,000")
        self.assertContains(response, "Part paid")
        self.assertContains(response, "Rs. 150,000 due")

    def test_search_and_status_filter(self):
        other = Event.objects.create(
            name="Office party", customer=Customer.objects.create(name="Zed Corp"),
            event_date=timezone.localdate(), status="cancelled",
        )
        response = self.client.get(self.url("events") + "?q=zed")
        self.assertContains(response, other.number)
        self.assertNotContains(response, self.event.number)
        response = self.client.get(self.url("events") + "?status=draft")
        self.assertContains(response, self.event.number)
        self.assertNotContains(response, other.number)

    def test_date_filter(self):
        far = Event.objects.create(
            name="Far away", customer=self.customer,
            event_date=timezone.localdate() + timedelta(days=400),
        )
        cutoff = (timezone.localdate() + timedelta(days=30)).isoformat()
        response = self.client.get(self.url("events") + f"?to={cutoff}")
        self.assertContains(response, self.event.number)
        self.assertNotContains(response, far.number)

    def test_quick_search_finds_events(self):
        response = self.client.get(self.url("search") + "?q=Rao")
        labels = [row["label"] for row in response.json()["results"]]
        self.assertIn(f"{self.event.number} · Rao wedding", labels)


class CreateTests(EventPanelTestCase):
    def test_create_event_with_a_new_customer(self):
        response = self.client.post(self.url("event_create"), {
            "name": "Mehta anniversary",
            "occasion": self.wedding.pk,
            "new_customer_name": "Ravi Mehta",
            "new_customer_phone": "+977 90000 11111",
            "event_date": (timezone.localdate() + timedelta(days=20)).isoformat(),
            "location": "Rooftop",
            "guests": 80,
            "revenue": 120000,
            "notes": "",
        })
        event = Event.objects.get(name="Mehta anniversary")
        self.assertRedirects(response, event.get_absolute_url() + "#items", fetch_redirect_response=False)
        self.assertEqual(event.customer.name, "Ravi Mehta")
        self.assertEqual(event.customer.phone, "+977 90000 11111")
        self.assertEqual(event.status, "draft")
        self.assertEqual(event.created_by, self.editor)
        self.assertRegex(event.number, r"^EVT-\d{5}$")

    def test_create_needs_a_customer(self):
        response = self.client.post(self.url("event_create"), {
            "name": "Nobody's event",
            "event_date": timezone.localdate().isoformat(),
            "guests": 0, "revenue": 0,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pick a customer")
        self.assertFalse(Event.objects.filter(name="Nobody's event").exists())

    def test_edit_event(self):
        response = self.client.post(self.url("event_edit", self.event.pk), {
            "name": "Rao wedding reception", "customer": self.customer.pk, "occasion": self.wedding.pk,
            "event_date": self.event.event_date.isoformat(), "location": "Palace Grounds",
            "guests": 300, "revenue": 275000, "notes": "Stage on the left",
        })
        self.assertEqual(response.status_code, 302)
        event = self.reload()
        self.assertEqual((event.name, event.guests, event.revenue), ("Rao wedding reception", 300, 275000))
        self.assertEqual(event.status, "draft")


class WorkflowTests(EventPanelTestCase):
    def test_full_event_through_the_panel(self):
        # Add from inventory and from outside.
        response = self.client.post(self.url("event_add_stock", self.event.pk), {
            "pick": [self.chair.pk], f"qty-{self.chair.pk}": "30",
        })
        self.assertEqual(response.status_code, 302)
        response = self.client.post(self.url("event_add_external", self.event.pk), {
            "name": "Flower wall", "quantity": "1", "unit_cost": "40000", "vendor": "Petal House",
        })
        self.assertEqual(response.status_code, 302)
        line = self.event.items.get(inventory_item=self.chair)
        external = self.event.items.get(item_type="external")
        self.assertEqual(external.cost, 40000)

        # Confirm, reserve, start.
        self.act("confirm")
        self.assertEqual(self.reload().status, "confirmed")
        self.act("allocate")
        chair = InventoryItem.objects.get(pk=self.chair.pk)
        self.assertEqual((chair.quantity, chair.reserved_quantity, chair.available_quantity), (100, 30, 70))
        self.act("start")
        self.assertEqual(self.reload().status, "in_progress")

        # Expense and payment.
        self.client.post(self.url("event_add_expense", self.event.pk), {
            "name": "Crew", "category": "staff", "amount": "10000",
            "spent_on": timezone.localdate().isoformat(), "notes": "",
        })
        self.client.post(self.url("event_add_payment", self.event.pk), {
            "amount": "100000", "paid_on": timezone.localdate().isoformat(),
            "method": "upi", "reference": "UTR123", "notes": "",
        })

        # Chairs back: 28 returned, 1 damaged, 1 lost.
        response = self.client.post(self.url("event_line_usage", self.event.pk, line.pk), {
            "returned": "28", "damaged": "1", "lost": "1",
        })
        self.assertEqual(response.status_code, 302)
        chair = InventoryItem.objects.get(pk=self.chair.pk)
        self.assertEqual((chair.quantity, chair.reserved_quantity, chair.available_quantity), (98, 0, 98))

        self.act("complete")
        event = self.reload()
        self.assertEqual(event.status, "completed")
        self.assertEqual(event.paid, 100000)
        self.assertEqual(event.total_cost, 40000 + 10000 + 2 * 450)
        self.assertEqual(event.profit, 250000 - 50900)
        self.assertEqual(event.remaining, 150000)

        response = self.client.get(event.get_absolute_url())
        self.assertContains(response, "1 × Chair damaged in")
        self.assertContains(response, "1 × Chair lost at")
        self.assertContains(response, "Back, with losses")

    def test_picker_marks_items_with_nothing_free(self):
        other = Event.objects.create(
            name="Takes every speaker", customer=self.customer,
            event_date=timezone.localdate(), status="confirmed",
        )
        other.add_inventory_item(self.speaker, 10)
        response = self.client.get(self.event.get_absolute_url())
        self.assertContains(response, "None free")
        self.assertContains(
            response, f'name="pick" value="{self.speaker.pk}" disabled', html=False,
        )
        self.assertNotContains(response, f'name="pick" value="{self.chair.pk}" disabled')
        # And the server still refuses it if the list is bypassed.
        response = self.client.post(self.url("event_add_stock", self.event.pk), {
            "pick": [self.speaker.pk], f"qty-{self.speaker.pk}": "1",
        })
        self.assertContains(response, "Only 0 units are available.")

    def test_over_allocation_shows_the_message(self):
        response = self.client.post(self.url("event_add_stock", self.event.pk), {
            "pick": [self.speaker.pk], f"qty-{self.speaker.pk}": "15",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Only 10 units are available.")
        self.assertFalse(self.event.items.exists())

    def test_several_items_are_added_in_one_go(self):
        self.act("confirm")
        response = self.client.post(self.url("event_add_stock", self.event.pk), {
            "pick": [self.chair.pk, self.speaker.pk],
            f"qty-{self.chair.pk}": "40", f"qty-{self.speaker.pk}": "4",
            # A quantity typed against an item that is not ticked is ignored.
            f"qty-{InventoryItem.objects.create(name='Unticked').pk}": "3",
        })
        self.assertEqual(response.status_code, 302)
        lines = {line.name: line for line in self.event.items.all()}
        self.assertEqual(set(lines), {"Chair", "Speaker"})
        self.assertEqual((lines["Chair"].quantity, lines["Chair"].reserved_qty), (40, 40))
        self.assertEqual((lines["Speaker"].quantity, lines["Speaker"].reserved_qty), (4, 4))
        page = self.client.get(response.url)
        self.assertContains(page, "Added and reserved: 40 × Chair, 4 × Speaker.")

    def test_several_items_are_all_or_nothing(self):
        response = self.client.post(self.url("event_add_stock", self.event.pk), {
            "pick": [self.chair.pk, self.speaker.pk],
            f"qty-{self.chair.pk}": "40", f"qty-{self.speaker.pk}": "11",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Only 10 units are available.")
        self.assertFalse(self.event.items.exists())
        # The ticks and quantities come back as they were typed.
        self.assertContains(response, f'value="{self.chair.pk}" checked')
        self.assertContains(response, 'value="11"')

    def test_picker_refuses_nothing_ticked_and_bad_quantities(self):
        response = self.client.post(self.url("event_add_stock", self.event.pk), {})
        self.assertContains(response, "Tick at least one item to add.")
        response = self.client.post(self.url("event_add_stock", self.event.pk), {
            "pick": [self.chair.pk, self.speaker.pk],
            f"qty-{self.chair.pk}": "2.5", f"qty-{self.speaker.pk}": "lots",
        })
        self.assertContains(response, "counted in whole units")
        self.assertContains(response, "Enter a number.")
        response = self.client.post(self.url("event_add_stock", self.event.pk), {
            "pick": ["999999"],
        })
        self.assertContains(response, "no longer on the stock list")
        self.assertFalse(self.event.items.exists())

    def test_adding_an_item_already_on_the_event_tops_it_up(self):
        self.event.add_inventory_item(self.speaker, 6)
        response = self.client.get(self.event.get_absolute_url())
        self.assertContains(response, "6 already on this event")
        # A draft holds nothing, so its own 6 count against the 10 on the shelf.
        response = self.client.post(self.url("event_add_stock", self.event.pk), {
            "pick": [self.speaker.pk], f"qty-{self.speaker.pk}": "5",
        })
        self.assertContains(response, "Only 10 units are available.")
        response = self.client.post(self.url("event_add_stock", self.event.pk), {
            "pick": [self.speaker.pk], f"qty-{self.speaker.pk}": "4",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.event.items.get().quantity, 10)

    def test_external_item_takes_a_photo(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        photo = SimpleUploadedFile(
            "flowers.gif",
            b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00"
            b"\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;",
            content_type="image/gif",
        )
        with self.settings(MEDIA_ROOT=self.media_root):
            response = self.client.post(self.url("event_add_external", self.event.pk), {
                "name": "Flower wall", "quantity": "1", "unit_cost": "40000", "image_file": photo,
            })
            self.assertEqual(response.status_code, 302)
            line = self.event.items.get(item_type="external")
            self.assertTrue(line.image_file.name.endswith(".gif"))
            page = self.client.get(self.event.get_absolute_url())
            self.assertContains(page, line.image_file.url)

        url_line = EventItem.objects.create(
            event=self.event, item_type="external", name="Stage", quantity=1,
            image_url="https://example.com/stage.jpg",
        )
        self.assertEqual(url_line.picture, "https://example.com/stage.jpg")
        # No picture at all shows an icon, never a stand-in photo.
        bare = EventItem.objects.create(event=self.event, item_type="external", name="Tent", quantity=1)
        self.assertEqual(bare.picture, "")

    def test_status_changes_from_the_list_come_straight_back_to_it(self):
        self.event.add_inventory_item(self.chair, 10)
        list_url = self.url("events") + "?status=draft"
        page = self.client.get(list_url)
        self.assertContains(page, 'name="action" value="confirm"')
        self.assertContains(page, "Next: confirm event")

        response = self.client.post(self.url("event_action", self.event.pk), {
            "action": "confirm", "next": list_url,
        })
        self.assertRedirects(response, f"{list_url}#event-{self.event.pk}", fetch_redirect_response=False)
        self.assertEqual(self.reload().status, "confirmed")

        # The list now offers the next step, and shows the new status at once.
        page = self.client.get(self.url("events"))
        self.assertContains(page, f"{self.event.number} confirmed.")
        self.assertContains(page, 'name="action" value="allocate"')
        self.client.post(self.url("event_action", self.event.pk), {"action": "allocate", "next": list_url})
        page = self.client.get(self.url("events"))
        self.assertContains(page, 'name="action" value="start"')
        self.assertContains(page, f"{self.event.number}: reserved stock on 1 line.")

    def steps_of(self, response):
        """The progress track's step classes, in order."""
        html = response.content.decode()
        track = html[html.index('<ol class="steps'):html.index("</ol>", html.index('<ol class="steps'))]
        return re.findall(r'class="steps__one ([^"]*)"', track)

    def test_progress_track_walks_through_every_status(self):
        self.event.add_inventory_item(self.chair, 10)
        page = self.client.get(self.event.get_absolute_url())
        self.assertEqual(
            self.steps_of(page), ["is-current", "is-todo has-action", "is-todo", "is-todo"],
        )
        self.assertContains(page, "When the customer says yes")

        self.act("confirm")
        page = self.client.get(self.event.get_absolute_url())
        steps = self.steps_of(page)
        self.assertEqual(steps[:2], ["is-done", "is-current is-arrived"])
        # Starting waits on the stock, and says so instead of offering a button.
        self.assertEqual(steps[2], "is-todo")
        self.assertContains(page, "Reserve the stock first")
        self.assertEqual(self.reload().confirmed_at is not None, True)
        # The celebration plays once, not on every visit.
        page = self.client.get(self.event.get_absolute_url())
        self.assertNotIn("is-arrived", " ".join(self.steps_of(page)))

        self.act("allocate")
        page = self.client.get(self.event.get_absolute_url())
        self.assertEqual(self.steps_of(page)[2], "is-todo has-action")

        self.act("start")
        self.act("complete")
        page = self.client.get(self.event.get_absolute_url())
        # The last step is finished, but stock is still out.
        self.assertEqual(self.steps_of(page), ["is-done", "is-done", "is-done", "is-warn is-arrived"])
        self.assertContains(page, "Stock still out")

        self.act("finalize")
        page = self.client.get(self.event.get_absolute_url())
        self.assertEqual(self.steps_of(page), ["is-done", "is-done", "is-done", "is-done is-arrived"])
        self.assertContains(page, "All stock settled")
        self.assertContains(page, "is-settled")
        event = self.reload()
        self.assertTrue(event.started_at and event.completed_at)
        self.assertContains(page, "by editor")

    def test_cancelled_track_shows_how_far_it_got(self):
        self.act("confirm")
        self.act("cancel")
        page = self.client.get(self.event.get_absolute_url())
        self.assertEqual(self.steps_of(page), ["is-done", "is-done", "is-cancelled is-arrived"])
        self.assertContains(page, "steps--cancelled")
        self.assertContains(page, "Stock released")
        self.assertEqual(self.reload().reached, "confirmed")

    def test_viewer_gets_no_buttons_on_the_track(self):
        self.client.force_login(self.viewer)
        page = self.client.get(self.event.get_absolute_url())
        self.assertNotIn("has-action", " ".join(self.steps_of(page)))

    def test_list_action_ignores_an_outside_next(self):
        response = self.client.post(self.url("event_action", self.event.pk), {
            "action": "confirm", "next": "https://evil.example/manage/events/",
        })
        self.assertRedirects(response, self.event.get_absolute_url(), fetch_redirect_response=False)

    def test_a_stale_button_says_what_happened(self):
        self.act("cancel")
        response = self.client.post(self.url("event_action", self.event.pk), {
            "action": "confirm", "next": self.url("events"),
        }, follow=True)
        self.assertContains(response, f"{self.event.number} is cancelled now")
        self.assertEqual(self.reload().status, "cancelled")

    def test_panel_pages_are_never_served_from_the_browser_cache(self):
        for url in (self.url("events"), self.event.get_absolute_url()):
            response = self.client.get(url)
            self.assertIn("no-store", response["Cache-Control"])

    def test_viewer_sees_no_status_buttons_on_the_list(self):
        self.client.force_login(self.viewer)
        page = self.client.get(self.url("events"))
        self.assertNotContains(page, 'name="action"')

    def test_cancelled_event_shows_no_profit_or_amount_due(self):
        self.act("cancel")
        response = self.client.get(self.event.get_absolute_url())
        self.assertContains(response, "Not earned")
        self.assertNotContains(response, "Rs. 250,000 still owed")
        self.assertNotContains(response, "100% margin")

    def test_cancel_releases_through_the_panel(self):
        self.event.add_inventory_item(self.speaker, 6)
        self.act("confirm")
        self.act("allocate")
        self.assertEqual(InventoryItem.objects.get(pk=self.speaker.pk).available_quantity, 4)
        self.act("cancel")
        self.assertEqual(self.reload().status, "cancelled")
        self.assertEqual(InventoryItem.objects.get(pk=self.speaker.pk).available_quantity, 10)

    def test_actions_outside_their_status_are_refused(self):
        self.act("start")  # a draft cannot start
        self.assertEqual(self.reload().status, "draft")
        self.act("finalize")
        self.assertEqual(self.reload().status, "draft")

    def test_start_without_reserving_is_refused_with_a_message(self):
        self.event.add_inventory_item(self.chair, 5)
        self.act("confirm")
        response = self.act("start")
        self.assertEqual(self.reload().status, "confirmed")
        response = self.client.get(response.url)
        self.assertContains(response, "Reserve the inventory before starting")

    def test_payment_cannot_exceed_what_is_owed(self):
        response = self.client.post(self.url("event_add_payment", self.event.pk), {
            "amount": "300000", "paid_on": timezone.localdate().isoformat(), "method": "cash",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "more than the Rs. 250,000 still owed")
        self.assertFalse(EventPayment.objects.exists())

    def test_remove_expense_and_payment(self):
        expense = EventExpense.objects.create(event=self.event, name="Van", category="transport", amount=1500)
        payment = EventPayment.objects.create(event=self.event, amount=5000)
        self.client.post(self.url("event_remove_expense", self.event.pk, expense.pk))
        self.client.post(self.url("event_remove_payment", self.event.pk, payment.pk))
        self.assertFalse(EventExpense.objects.exists())
        self.assertFalse(EventPayment.objects.exists())

    def test_line_edit_changes_quantity_and_holds(self):
        self.event.status = "confirmed"
        self.event.save()
        line = self.event.add_inventory_item(self.chair, 30)
        response = self.client.post(self.url("event_line_edit", self.event.pk, line.pk), {
            "quantity": "12", "notes": "Only the gold ones",
        })
        self.assertEqual(response.status_code, 302)
        line = EventItem.objects.get(pk=line.pk)
        self.assertEqual((line.quantity, line.reserved_qty, line.notes), (12, 12, "Only the gold ones"))

    def test_finalize_from_the_panel(self):
        line = self.event.add_inventory_item(self.chair, 20)
        for step in ("confirm", "allocate", "start", "complete"):
            self.act(step)
        self.assertTrue(self.reload().has_outstanding)
        self.act("finalize")
        self.assertFalse(self.reload().has_outstanding)
        self.assertEqual(EventItem.objects.get(pk=line.pk).returned_qty, 20)
        self.assertEqual(InventoryItem.objects.get(pk=self.chair.pk).available_quantity, 100)


class PermissionTests(EventPanelTestCase):
    def test_viewer_can_look_but_not_change(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(self.url("events")).status_code, 200)
        self.assertEqual(self.client.get(self.event.get_absolute_url()).status_code, 200)

        self.client.post(self.url("event_add_stock", self.event.pk), {
            "pick": [self.chair.pk], f"qty-{self.chair.pk}": "5",
        })
        self.act("confirm")
        self.client.post(self.url("event_add_payment", self.event.pk), {
            "amount": "10", "paid_on": timezone.localdate().isoformat(), "method": "cash",
        })
        response = self.client.get(self.url("event_create"))
        self.assertEqual(response.status_code, 302)

        self.assertFalse(self.event.items.exists())
        self.assertEqual(self.reload().status, "draft")
        self.assertFalse(EventPayment.objects.exists())

    def test_delete_needs_admin_and_a_safe_state(self):
        self.client.post(self.url("event_delete", self.event.pk))
        self.assertTrue(Event.objects.filter(pk=self.event.pk).exists())

        self.client.force_login(self.admin)
        confirmed = Event.objects.create(
            name="Held", customer=self.customer, event_date=timezone.localdate(), status="confirmed",
        )
        self.client.post(self.url("event_delete", confirmed.pk))
        self.assertTrue(Event.objects.filter(pk=confirmed.pk).exists())

        response = self.client.post(self.url("event_delete", self.event.pk))
        self.assertRedirects(response, self.url("events"), fetch_redirect_response=False)
        self.assertFalse(Event.objects.filter(pk=self.event.pk).exists())

    def test_anonymous_is_sent_to_login(self):
        self.client.logout()
        response = self.client.get(self.url("events"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("panel:login"), response.url)


class InventoryIntegrationTests(EventPanelTestCase):
    def test_counter_cannot_sell_reserved_stock(self):
        self.speaker.is_sellable = True
        self.speaker.save()
        self.event.status = "confirmed"
        self.event.save()
        self.event.add_inventory_item(self.speaker, 8)

        session = self.client.session
        session["counter_cart"] = {str(self.speaker.pk): {"qty": "3", "price": 6000}}
        session.save()
        response = self.client.post(self.url("counter"), {
            "action": "checkout", "payment_method": "cash",
            "discount": "0", "tax_percent": "0", "amount_tendered": "0",
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CounterSale.objects.exists())
        self.assertEqual(InventoryItem.objects.get(pk=self.speaker.pk).quantity, 10)

        session = self.client.session
        session["counter_cart"] = {str(self.speaker.pk): {"qty": "2", "price": 6000}}
        session.save()
        self.client.post(self.url("counter"), {
            "action": "checkout", "payment_method": "cash",
            "discount": "0", "tax_percent": "0", "amount_tendered": "0",
        })
        self.assertEqual(CounterSale.objects.count(), 1)
        self.assertEqual(InventoryItem.objects.get(pk=self.speaker.pk).quantity, 8)

    def test_ledger_form_does_not_offer_event_only_reasons(self):
        response = self.client.get(self.url("resource_create", "stock-ledger"))
        self.assertNotContains(response, 'value="reserve"')
        self.assertContains(response, 'value="lost"')

    def test_ledger_shows_reservations(self):
        self.event.status = "confirmed"
        self.event.save()
        self.event.add_inventory_item(self.chair, 30)
        response = self.client.get(self.url("resource_list", "stock-ledger") + f"?q={self.event.number}")
        self.assertContains(response, "Reserved for an event")
        self.assertContains(response, "30 reserved")
        self.assertEqual(StockMovement.objects.filter(event=self.event).count(), 1)

    def test_stock_item_shows_its_events(self):
        self.event.add_inventory_item(self.chair, 30)
        response = self.client.get(self.url("resource_edit", "stock-items", self.chair.pk))
        self.assertContains(response, "Booked on events")
        self.assertContains(response, self.event.number)


class DashboardAndScheduleTests(EventPanelTestCase):
    """The dashboard, schedule and staff numbers all read events now."""

    def setUp(self):
        super().setUp()
        from core.models import StaffCategory, StaffMember

        self.decorators = StaffCategory.objects.get_or_create(name="Decorator", defaults={"slug": "decorator"})[0]
        self.crew = StaffMember.objects.create(name="Studio Marigold", category=self.decorators)
        self.today = timezone.localdate()
        # One this month, one overdue and still open, one cancelled.
        self.event.event_date = self.today
        self.event.time_slot = "4 PM – 6 PM"
        self.event.save()
        self.event.crew.add(self.crew)
        self.late = Event.objects.create(
            name="Late launch", customer=self.customer, revenue=10000,
            event_date=self.today - timedelta(days=3),
        )
        self.gone = Event.objects.create(
            name="Called off", customer=self.customer, revenue=99999, event_date=self.today,
        )
        self.gone.cancel()

    def test_dashboard_counts_events(self):
        response = self.client.get(self.url("dashboard"))
        self.assertContains(response, "Events this month")
        self.assertContains(response, "Open events")
        self.assertContains(response, "1 past their date")
        self.assertContains(response, self.late.number)
        self.assertContains(response, "Rs. 250,000")            # on the upcoming list
        self.assertNotContains(response, "99,999")          # cancelled events earn nothing
        self.assertContains(response, "Studio Marigold")     # the crew on the upcoming list
        self.assertNotContains(response, "/manage/bookings/")

    def test_schedule_places_events_on_their_day(self):
        response = self.client.get(self.url("schedule"))
        self.assertContains(response, self.url("event_detail", self.event.pk))
        self.assertContains(response, "crew: Studio Marigold")
        self.assertContains(response, "New event")
        self.assertContains(response, "In progress")         # the legend is the event statuses

    def test_crew_is_picked_on_the_form_and_counts_as_open_jobs(self):
        form = self.client.get(self.url("event_edit", self.event.pk))
        self.assertContains(form, "Studio Marigold · Decorator")
        response = self.client.post(self.url("event_create"), {
            "name": "Crewed party", "customer": self.customer.pk, "occasion": self.wedding.pk,
            "event_date": (self.today + timedelta(days=4)).isoformat(),
            "guests": 10, "revenue": 5000, "crew": [self.crew.pk],
        })
        created = Event.objects.get(name="Crewed party")
        self.assertRedirects(response, self.url("event_detail", created.pk) + "#items", fetch_redirect_response=False)
        self.assertEqual(list(created.crew.all()), [self.crew])
        self.assertEqual(self.crew.open_jobs, 2)
        self.assertEqual(self.decorators.open_jobs, 2)
        self.assertContains(self.client.get(self.url("event_detail", created.pk)), "Studio Marigold")
        self.client.force_login(self.admin)
        staff_list = self.client.get(self.url("resource_list", "staffs") + "?sort=-job_total")
        self.assertEqual(staff_list.status_code, 200)

    def test_old_bookings_are_gone(self):
        self.assertEqual(self.client.get("/manage/bookings/").status_code, 404)
        search = self.client.get(self.url("search") + "?q=Rao").json()["results"]
        self.assertIn("Events", {row["group"] for row in search})
        self.assertNotIn("Bookings", {row["group"] for row in search})

class OccasionTests(EventPanelTestCase):
    """An occasion is the kind of celebration; an event is one booking of it."""

    def setUp(self):
        super().setUp()
        self.birthday = Category.objects.create(name="Birthday", blurb="Balloons and cake tables")
        self.party = Event.objects.create(
            name="Aarav turns five", customer=self.customer, occasion=self.birthday,
            event_date=timezone.localdate() + timedelta(days=9),
        )

    def test_an_event_needs_an_occasion(self):
        form = self.client.get(self.url("event_create"))
        self.assertContains(form, 'Occasion <span class="field__req" title="Required">*</span>', html=False)
        response = self.client.post(self.url("event_create"), {
            "name": "Kind unknown", "customer": self.customer.pk,
            "event_date": timezone.localdate().isoformat(), "guests": 0, "revenue": 0,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "every event is one")
        self.assertFalse(Event.objects.filter(name="Kind unknown").exists())

    def test_a_setup_alone_says_which_occasion(self):
        from core.models import Package

        cake = Package.objects.create(
            title="Cake table", category=self.birthday, price=5000, original_price=6000,
            description="Balloons over the cake.",
        )
        self.client.post(self.url("event_create"), {
            "name": "Cake only", "customer": self.customer.pk, "package": cake.pk,
            "event_date": timezone.localdate().isoformat(), "guests": 0, "revenue": 0,
        })
        self.assertEqual(Event.objects.get(name="Cake only").occasion, self.birthday)

    def test_events_filter_by_occasion(self):
        response = self.client.get(self.url("events") + "?occasion=birthday")
        self.assertContains(response, self.party.number)
        self.assertNotContains(response, self.event.number)
        self.assertContains(response, '<option value="birthday" selected>Birthday</option>', html=False)
        # The status tabs count inside the chosen occasion too.
        self.assertEqual(
            [tab["count"] for tab in response.context["tabs"] if tab["value"] == ""], [1]
        )
        # An unknown slug is ignored rather than emptying the list.
        response = self.client.get(self.url("events") + "?occasion=nope")
        self.assertContains(response, self.party.number)
        self.assertContains(response, self.event.number)

    def test_occasions_show_their_events(self):
        listing = self.client.get(self.url("resource_list", "categories") + "?sort=-event_count")
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, "every event is booked as one")
        edit = self.client.get(self.url("resource_edit", "categories", self.birthday.pk))
        self.assertContains(edit, f'{self.url("events")}?occasion=birthday')
        dashboard = self.client.get(self.url("dashboard"))
        self.assertContains(dashboard, f'{self.url("events")}?occasion=wedding')

    def test_an_occasion_with_events_is_retired_not_deleted(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url("resource_delete", "categories", self.birthday.pk))
        self.assertRedirects(
            response, self.url("resource_delete", "categories", self.birthday.pk),
            fetch_redirect_response=False,
        )
        self.assertTrue(Category.objects.filter(pk=self.birthday.pk).exists())
        self.party.refresh_from_db()
        self.assertEqual(self.party.occasion, self.birthday)

    def test_a_review_remembers_what_was_booked(self):
        from core.models import Package

        cake = Package.objects.create(
            title="Cake table", category=self.birthday, price=5000, original_price=6000,
            description="Balloons over the cake.",
        )
        response = self.client.post(self.url("resource_create", "testimonials"), {
            "name": "Maya", "city": "Lalitpur", "rating": 5, "package": cake.pk,
            "booked": "", "date": "May 2026", "text": "Lovely.", "is_published": "on",
            "position": 0,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Testimonial.objects.get(name="Maya").booked, "Cake table")
