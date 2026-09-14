"""
Stock items from the panel: starting stock on a new item, and the receive /
correct dialogs on an existing one landing back on the item.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import InventoryItem, StaffProfile, StockMovement, Supplier


class StockItemPanelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("editor", password="x-Strong-pass-1")
        StaffProfile.objects.create(user=cls.user, role="editor")
        cls.supplier = Supplier.objects.create(name="Milan champs")

    def setUp(self):
        self.client.force_login(self.user)

    def item_data(self, **extra):
        data = {
            "name": "Balloon", "sku": "", "unit": "piece", "usage_type": "consumable",
            "reorder_level": "0", "cost_price": "50", "sale_price": "70",
            "supplier": self.supplier.pk, "is_active": "on", "save": "",
        }
        data.update(extra)
        return data

    def test_new_item_page_offers_starting_stock(self):
        response = self.client.get(reverse("panel:resource_create", args=["stock-items"]))
        self.assertContains(response, 'name="opening_quantity"')
        self.assertContains(response, "starting stock")

    def test_edit_page_has_no_starting_stock_but_has_dialogs(self):
        item = InventoryItem.objects.create(name="Chair", cost_price=10, sale_price=20)
        response = self.client.get(reverse("panel:resource_edit", args=["stock-items", item.pk]))
        self.assertNotContains(response, 'name="opening_quantity"')
        self.assertContains(response, 'data-modal="modal-receive"')
        self.assertContains(response, 'data-modal="modal-adjust"')

    def test_create_with_starting_stock_writes_the_ledger(self):
        response = self.client.post(
            reverse("panel:resource_create", args=["stock-items"]),
            self.item_data(opening_quantity="25", opening_kind="purchase", opening_reference="INV-9"),
        )
        item = InventoryItem.objects.get(name="Balloon")
        self.assertEqual(item.quantity, 25)
        move = StockMovement.objects.get(item=item)
        self.assertEqual((move.kind, move.change, move.unit_cost), ("purchase", 25, 50))
        self.assertEqual((move.supplier, move.reference, move.created_by), (self.supplier, "INV-9", self.user))
        self.assertRedirects(response, reverse("panel:resource_list", args=["stock-items"]))

    def test_create_without_starting_stock_starts_empty(self):
        self.client.post(reverse("panel:resource_create", args=["stock-items"]), self.item_data())
        item = InventoryItem.objects.get(name="Balloon")
        self.assertEqual(item.quantity, 0)
        self.assertFalse(StockMovement.objects.filter(item=item).exists())

    def test_reusable_starting_stock_must_be_whole(self):
        response = self.client.post(
            reverse("panel:resource_create", args=["stock-items"]),
            self.item_data(usage_type="reusable", opening_quantity="2.5"),
        )
        self.assertContains(response, "whole units")
        self.assertFalse(InventoryItem.objects.filter(name="Balloon").exists())

    def test_receive_and_correct_land_back_on_the_item(self):
        item = InventoryItem.objects.create(name="Chair", cost_price=10, sale_price=20)
        ledger = reverse("panel:resource_create", args=["stock-ledger"])
        back = reverse("panel:resource_edit", args=["stock-items", item.pk])

        response = self.client.post(ledger, {"item": item.pk, "kind": "purchase", "change": "10", "unit_cost": "10"})
        self.assertRedirects(response, back)
        response = self.client.post(ledger, {"item": item.pk, "kind": "adjustment", "change": "-3", "unit_cost": "0"})
        self.assertRedirects(response, back)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 7)

    def test_correction_below_zero_is_refused(self):
        item = InventoryItem.objects.create(name="Chair", cost_price=10, sale_price=20)
        response = self.client.post(
            reverse("panel:resource_create", args=["stock-ledger"]),
            {"item": item.pk, "kind": "adjustment", "change": "-3", "unit_cost": "0"},
        )
        self.assertContains(response, "on the shelf")
        item.refresh_from_db()
        self.assertEqual(item.quantity, 0)
