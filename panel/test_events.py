"""
The Events pages, driven the way a person would: through the panel's URLs,
signed in with a real role.
"""

import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    CounterSale,
    Customer,
    Event,
    EventExpense,
    EventItem,
    EventPayment,
    InventoryItem,
    StaffProfile,
    StockMovement,
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
        cls.customer = Customer.objects.create(name="Asha Rao", phone="+91 98450 00000")

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
            name="Rao wedding", customer=self.customer, revenue=250000,
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
        self.assertContains(response, "₹250,000")
        self.assertContains(response, "Part paid")
        self.assertContains(response, "₹150,000 due")

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
            "new_customer_name": "Ravi Mehta",
            "new_customer_phone": "+91 90000 11111",
            "event_date": (timezone.localdate() + timedelta(days=20)).isoformat(),
            "location": "Rooftop",
            "guests": 80,
            "revenue": 120000,
            "notes": "",
        })
        event = Event.objects.get(name="Mehta anniversary")
        self.assertRedirects(response, event.get_absolute_url() + "#items", fetch_redirect_response=False)
        self.assertEqual(event.customer.name, "Ravi Mehta")
        self.assertEqual(event.customer.phone, "+91 90000 11111")
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
            "name": "Rao wedding reception", "customer": self.customer.pk,
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

    def test_cancelled_event_shows_no_profit_or_amount_due(self):
        self.act("cancel")
        response = self.client.get(self.event.get_absolute_url())
        self.assertContains(response, "Not earned")
        self.assertNotContains(response, "₹250,000 still owed")
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
        self.assertContains(response, "more than the ₹250,000 still owed")
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
