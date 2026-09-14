"""
Events against stock: reservations, returns, write-offs, and the money.

Every scenario here is one a business actually meets — 100 chairs, 30 of them
out at a wedding, 28 back, one broken, one gone.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from core.models import (
    Customer,
    Event,
    EventExpense,
    EventItem,
    EventPayment,
    InventoryItem,
    StockMovement,
)


class EventStockTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("crew", password="x-Strong-pass-1")
        cls.customer = Customer.objects.create(name="Asha Rao", phone="+977 98450 00000")

    def setUp(self):
        self.chair = self.stock("Chair", 100, usage="reusable", cost=450)
        self.water = self.stock("Water bottle", 50, usage="consumable", cost=20, unit="piece")

    # -- helpers -----------------------------------------------------------

    def stock(self, name, count, usage="reusable", cost=0, unit="piece"):
        item = InventoryItem.objects.create(
            name=name, usage_type=usage, cost_price=cost, sale_price=cost * 2, unit=unit,
        )
        if count:
            item.record_movement(count, kind="opening", unit_cost=cost)
        return item

    def event(self, status="draft", revenue=0, **extra):
        event = Event.objects.create(
            name=extra.pop("name", "Rao wedding"),
            customer=self.customer,
            event_date=timezone.localdate() + timedelta(days=10),
            revenue=revenue,
            **extra,
        )
        if status != "draft":
            Event.objects.filter(pk=event.pk).update(status=status)
            event.refresh_from_db()
        return event

    def fresh(self, item):
        return InventoryItem.objects.get(pk=item.pk)

    def line(self, line):
        return EventItem.objects.get(pk=line.pk)


class AddSeveralItemsTests(EventStockTestCase):
    def test_adds_and_reserves_every_item(self):
        event = self.event(status="confirmed")
        lines = event.add_inventory_items([(self.chair, 30), (self.water, 12)], user=self.user)

        self.assertEqual([line.name for line in lines], ["Chair", "Water bottle"])
        self.assertEqual(self.fresh(self.chair).available_quantity, 70)
        self.assertEqual(self.fresh(self.water).available_quantity, 38)
        self.assertEqual(StockMovement.objects.filter(event=event, kind="reserve").count(), 2)

    def test_one_shortfall_adds_nothing_and_names_it(self):
        event = self.event(status="confirmed")
        with self.assertRaises(ValidationError) as caught:
            event.add_inventory_items([(self.chair, 30), (self.water, 51)], user=self.user)

        self.assertEqual(
            caught.exception.messages,
            ["Only 50 units of Water bottle are available (this needs 51)."],
        )
        self.assertFalse(event.items.exists())
        self.assertFalse(StockMovement.objects.filter(event=event).exists())
        self.assertEqual(self.fresh(self.chair).available_quantity, 100)

    def test_counts_other_events_and_the_line_already_there(self):
        other = self.event(status="confirmed", name="Other")
        other.add_inventory_item(self.chair, 60)
        event = self.event()
        event.add_inventory_item(self.chair, 30)

        with self.assertRaises(ValidationError):
            # 60 held elsewhere, 30 planned here: only 10 more fit.
            event.add_inventory_items([(self.chair, 11)])
        event.add_inventory_items([(self.chair, 6), (self.chair, 4)])
        self.assertEqual(event.items.get().quantity, 40)

    def test_reusable_stock_is_whole_units_and_empty_is_refused(self):
        event = self.event()
        with self.assertRaises(ValidationError):
            event.add_inventory_items([(self.chair, Decimal("1.5"))])
        with self.assertRaises(ValidationError):
            event.add_inventory_items([])
        with self.assertRaises(ValidationError):
            self.event(status="completed").add_inventory_items([(self.chair, 1)])


class EventBasicsTests(EventStockTestCase):
    def test_create_event_gets_a_number(self):
        event = self.event()
        self.assertEqual(event.number, f"EVT-{event.pk:05d}")
        self.assertRegex(Event.objects.get(pk=event.pk).number, r"^EVT-\d{5}$")
        self.assertEqual(event.status, "draft")
        self.assertIsNotNone(event.created_at)

    def test_add_inventory_item_to_a_draft_plans_without_reserving(self):
        event = self.event()
        line = event.add_inventory_item(self.chair, 30, user=self.user)

        self.assertEqual(line.item_type, "inventory")
        self.assertEqual(line.name, "Chair")
        self.assertEqual(line.usage_type, "reusable")
        self.assertEqual(line.unit_cost, 450)
        self.assertEqual(line.reserved_qty, 0)
        chair = self.fresh(self.chair)
        self.assertEqual(chair.quantity, 100)
        self.assertEqual(chair.available_quantity, 100)
        # No new stock product appears.
        self.assertEqual(InventoryItem.objects.count(), 2)

    def test_adding_the_same_item_twice_tops_up_one_line(self):
        event = self.event()
        event.add_inventory_item(self.chair, 20)
        event.add_inventory_item(self.chair, 10)
        lines = event.items.filter(inventory_item=self.chair)
        self.assertEqual(lines.count(), 1)
        self.assertEqual(lines.get().quantity, 30)

    def test_add_external_item_never_enters_inventory(self):
        event = self.event(status="confirmed")
        movements = StockMovement.objects.count()
        line = EventItem.objects.create(
            event=event, item_type="external", name="Flower wall",
            quantity=2, unit_cost=12500, vendor="Petal House",
        )
        self.assertTrue(line.is_external)
        self.assertIsNone(line.inventory_item)
        self.assertEqual(line.cost, 25000)
        self.assertEqual(InventoryItem.objects.count(), 2)
        self.assertEqual(StockMovement.objects.count(), movements)
        self.assertFalse(InventoryItem.objects.filter(name="Flower wall").exists())

    def test_reusable_stock_is_counted_in_whole_units(self):
        event = self.event()
        with self.assertRaisesMessage(ValidationError, "whole units"):
            event.add_inventory_item(self.chair, Decimal("2.5"))

    def test_quantity_must_be_positive(self):
        event = self.event()
        with self.assertRaises(ValidationError):
            event.add_inventory_item(self.chair, 0)


class ReservationTests(EventStockTestCase):
    def test_reserve_inventory_holds_without_moving_the_shelf(self):
        event = self.event()
        event.add_inventory_item(self.chair, 30)
        event.confirm(user=self.user)
        reserved = event.allocate(user=self.user)

        self.assertEqual(reserved, 1)
        chair = self.fresh(self.chair)
        self.assertEqual(chair.quantity, 100)
        self.assertEqual(chair.reserved_quantity, 30)
        self.assertEqual(chair.available_quantity, 70)

        move = StockMovement.objects.filter(event=event).get()
        self.assertEqual(move.kind, "reserve")
        self.assertEqual(move.change, 0)
        self.assertEqual(move.held_change, 30)
        self.assertEqual(move.note, f"30 × Chair reserved for {event.number}")
        self.assertEqual(move.created_by, self.user)

    def test_annotated_and_computed_reservations_agree(self):
        event = self.event()
        event.add_inventory_item(self.chair, 30)
        event.confirm()
        event.allocate()
        annotated = InventoryItem.objects.with_reserved().get(pk=self.chair.pk)
        self.assertEqual(annotated.reserved_total, 30)
        self.assertEqual(annotated.available_quantity, 70)

    def test_adding_to_a_confirmed_event_reserves_immediately(self):
        event = self.event(status="confirmed")
        line = event.add_inventory_item(self.chair, 12)
        self.assertEqual(self.line(line).reserved_qty, 12)
        self.assertEqual(self.fresh(self.chair).available_quantity, 88)

    def test_reservations_from_other_events_count(self):
        a = self.event(status="confirmed", name="Event A")
        b = self.event(status="confirmed", name="Event B")
        a.add_inventory_item(self.chair, 30)
        b.add_inventory_item(self.chair, 20)
        chair = self.fresh(self.chair)
        self.assertEqual(chair.quantity, 100)
        self.assertEqual(chair.reserved_quantity, 50)
        self.assertEqual(chair.available_quantity, 50)

    def test_prevent_over_allocation_on_add(self):
        speaker = self.stock("Speaker", 10, cost=3000)
        event = self.event()
        with self.assertRaisesMessage(ValidationError, "Only 10 units are available."):
            event.add_inventory_item(speaker, 15)
        self.assertFalse(event.items.exists())

    def test_prevent_over_allocation_counts_other_events(self):
        speaker = self.stock("Speaker", 10, cost=3000)
        self.event(status="confirmed", name="Other").add_inventory_item(speaker, 6)
        event = self.event(status="confirmed")
        with self.assertRaisesMessage(ValidationError, "Only 4 units are available."):
            event.add_inventory_item(speaker, 5)
        self.assertEqual(self.fresh(speaker).available_quantity, 4)

    def test_allocation_is_all_or_nothing(self):
        speaker = self.stock("Speaker", 10, cost=3000)
        event = self.event()
        event.add_inventory_item(self.chair, 30)
        event.add_inventory_item(speaker, 8)
        event.confirm()
        # Someone else takes most of the speakers before this event allocates.
        self.event(status="confirmed", name="Rival").add_inventory_item(speaker, 5)

        with self.assertRaisesMessage(ValidationError, "Only 5 units of Speaker are available"):
            event.allocate()
        # The chairs were fine, but nothing was half-reserved.
        self.assertEqual(self.fresh(self.chair).reserved_quantity, 0)
        self.assertFalse(event.items.filter(reserved_qty__gt=0).exists())
        self.assertFalse(StockMovement.objects.filter(event=event).exists())

    def test_allocating_twice_does_not_double_reserve(self):
        event = self.event()
        event.add_inventory_item(self.chair, 30)
        event.confirm()
        event.allocate()
        self.assertEqual(event.allocate(), 0)
        self.assertEqual(self.fresh(self.chair).reserved_quantity, 30)

    def test_stock_is_never_negative_from_a_hold(self):
        event = self.event(status="confirmed")
        event.add_inventory_item(self.chair, 100)
        self.assertEqual(self.fresh(self.chair).available_quantity, 0)
        with self.assertRaises(ValidationError):
            self.event(status="confirmed", name="Late").add_inventory_item(self.chair, 1)

    def test_start_requires_everything_reserved(self):
        event = self.event()
        event.add_inventory_item(self.chair, 30)
        event.confirm()
        with self.assertRaisesMessage(ValidationError, "Reserve the inventory before starting"):
            event.start()
        event.allocate()
        event.start()
        self.assertEqual(Event.objects.get(pk=event.pk).status, "in_progress")

    def test_lowering_a_quantity_releases_the_surplus(self):
        event = self.event(status="confirmed")
        line = event.add_inventory_item(self.chair, 30)
        line.set_quantity(20, user=self.user)
        self.assertEqual(self.line(line).reserved_qty, 20)
        self.assertEqual(self.fresh(self.chair).available_quantity, 80)
        self.assertTrue(StockMovement.objects.filter(event=event, kind="release", held_change=-10).exists())

    def test_raising_a_quantity_reserves_the_extra_if_free(self):
        event = self.event(status="confirmed")
        line = event.add_inventory_item(self.chair, 30)
        line.set_quantity(40)
        self.assertEqual(self.line(line).reserved_qty, 40)
        with self.assertRaises(ValidationError):
            line.set_quantity(101)
        self.assertEqual(self.line(line).reserved_qty, 40)

    def test_removing_a_line_releases_its_hold(self):
        event = self.event(status="confirmed")
        line = event.add_inventory_item(self.chair, 30)
        line.remove(user=self.user)
        self.assertFalse(EventItem.objects.filter(pk=line.pk).exists())
        self.assertEqual(self.fresh(self.chair).available_quantity, 100)


class CancellationTests(EventStockTestCase):
    def test_cancel_event_releases_reservation(self):
        event = self.event()
        event.add_inventory_item(self.chair, 30)
        event.add_inventory_item(self.water, 20)
        event.confirm()
        event.allocate()
        self.assertEqual(self.fresh(self.chair).available_quantity, 70)

        released = event.cancel(user=self.user)

        self.assertEqual(released, 2)
        self.assertEqual(Event.objects.get(pk=event.pk).status, "cancelled")
        chair = self.fresh(self.chair)
        self.assertEqual((chair.quantity, chair.reserved_quantity, chair.available_quantity), (100, 0, 100))
        self.assertEqual(self.fresh(self.water).available_quantity, 50)
        self.assertEqual(
            StockMovement.objects.filter(event=event, kind="release").count(), 2
        )

    def test_cancel_in_progress_keeps_what_was_used(self):
        event = self.event()
        line = event.add_inventory_item(self.water, 20)
        event.confirm()
        event.allocate()
        event.start()
        line.record_usage(consumed=5)
        event.cancel()
        water = self.fresh(self.water)
        self.assertEqual(water.quantity, 45)
        self.assertEqual(water.reserved_quantity, 0)
        # Only what was actually used counts as cost on a cancelled event.
        self.assertEqual(self.line(line).cost, 5 * 20)

    def test_cannot_cancel_twice(self):
        event = self.event()
        event.cancel()
        with self.assertRaises(ValidationError):
            event.cancel()


class ReturnAndUsageTests(EventStockTestCase):
    def running(self, item, quantity):
        event = self.event()
        line = event.add_inventory_item(item, quantity)
        event.confirm()
        event.allocate()
        event.start()
        return event, self.line(line)

    def test_return_reusable_inventory(self):
        event, line = self.running(self.chair, 30)
        line.record_usage(returned=30, user=self.user)
        chair = self.fresh(self.chair)
        self.assertEqual((chair.quantity, chair.reserved_quantity, chair.available_quantity), (100, 0, 100))
        move = StockMovement.objects.filter(event=event, kind="event_return").get()
        self.assertEqual(move.change, 0)
        self.assertEqual(move.note, f"30 × Chair returned from {event.number}")

    def test_record_damaged_and_lost_items(self):
        event, line = self.running(self.chair, 30)
        line.record_usage(returned=28, damaged=1, lost=1, user=self.user)

        line = self.line(line)
        self.assertEqual(
            (line.returned_qty, line.damaged_qty, line.lost_qty, line.outstanding),
            (28, 1, 1, 0),
        )
        chair = self.fresh(self.chair)
        self.assertEqual(chair.quantity, 98)
        self.assertEqual(chair.reserved_quantity, 0)
        self.assertEqual(chair.available_quantity, 98)

        damage = StockMovement.objects.get(event=event, kind="damage")
        lost = StockMovement.objects.get(event=event, kind="lost")
        self.assertEqual((damage.change, lost.change), (-1, -1))
        self.assertEqual(damage.note, f"1 × Chair damaged in {event.number}")
        self.assertEqual(lost.note, f"1 × Chair lost at {event.number}")
        # Two lost chairs' worth of cost, at the price snapshotted on the line.
        self.assertEqual(line.cost, 2 * 450)

    def test_partial_returns_add_up(self):
        _event, line = self.running(self.chair, 30)
        line.record_usage(returned=10)
        line.record_usage(returned=18, damaged=2)
        line = self.line(line)
        self.assertEqual(line.outstanding, 0)
        self.assertEqual(self.fresh(self.chair).quantity, 98)

    def test_consume_consumable_inventory(self):
        event, line = self.running(self.water, 20)
        line.record_usage(consumed=15, returned=5, user=self.user)
        water = self.fresh(self.water)
        self.assertEqual(water.quantity, 35)
        self.assertEqual(water.reserved_quantity, 0)
        self.assertEqual(water.available_quantity, 35)
        move = StockMovement.objects.get(event=event, kind="event")
        self.assertEqual(move.change, -15)
        self.assertEqual(move.balance_after, 35)
        # Planned 20, 5 came back unused: 15 cost.
        self.assertEqual(self.line(line).cost, 15 * 20)

    def test_cannot_settle_more_than_is_out(self):
        _event, line = self.running(self.chair, 30)
        with self.assertRaisesMessage(ValidationError, "Only 30 pc of Chair are still out"):
            line.record_usage(returned=29, lost=2)
        self.assertEqual(self.line(line).settled_qty, 0)
        self.assertEqual(self.fresh(self.chair).quantity, 100)

    def test_reusable_stock_cannot_be_consumed(self):
        _event, line = self.running(self.chair, 30)
        with self.assertRaises(ValidationError):
            line.record_usage(consumed=1)

    def test_consumable_stock_is_not_damaged_or_lost(self):
        _event, line = self.running(self.water, 10)
        with self.assertRaises(ValidationError):
            line.record_usage(damaged=1)

    def test_invalid_quantities_are_refused(self):
        _event, line = self.running(self.chair, 30)
        with self.assertRaises(ValidationError):
            line.record_usage(returned=-1)
        with self.assertRaises(ValidationError):
            line.record_usage()

    def test_usage_waits_until_the_event_starts(self):
        event = self.event(status="confirmed")
        line = event.add_inventory_item(self.chair, 5)
        with self.assertRaisesMessage(ValidationError, "once the event has started"):
            self.line(line).record_usage(returned=5)

    def test_a_line_with_usage_cannot_be_removed(self):
        _event, line = self.running(self.chair, 30)
        line.record_usage(returned=3)
        with self.assertRaises(ValidationError):
            self.line(line).remove()

    def test_finalize_inventory_after_completion(self):
        event = self.event()
        chairs = event.add_inventory_item(self.chair, 30)
        water = event.add_inventory_item(self.water, 20)
        event.confirm()
        event.allocate()
        event.start()
        self.line(chairs).record_usage(damaged=1)
        with self.assertRaises(ValidationError):
            event.finalize_inventory()  # not completed yet
        event.complete()

        settled = event.finalize_inventory(user=self.user)

        self.assertEqual(settled, 2)
        self.assertFalse(Event.objects.get(pk=event.pk).has_outstanding)
        chair = self.fresh(self.chair)
        self.assertEqual((chair.quantity, chair.reserved_quantity), (99, 0))
        self.assertEqual(self.line(chairs).returned_qty, 29)
        water_item = self.fresh(self.water)
        self.assertEqual((water_item.quantity, water_item.reserved_quantity), (30, 0))
        self.assertEqual(self.line(water).consumed_qty, 20)


class MoneyTests(EventStockTestCase):
    def test_add_expense(self):
        event = self.event(revenue=10000)
        EventExpense.objects.create(event=event, name="Tempo hire", category="transport", amount=1800)
        EventExpense.objects.create(event=event, name="Diesel", category="fuel", amount=700)
        event = Event.objects.get(pk=event.pk)
        self.assertEqual(event.expenses_total, 2500)
        self.assertEqual(event.total_cost, 2500)

    def test_add_payments(self):
        event = self.event(revenue=250000)
        EventPayment.objects.create(event=event, amount=60000, method="upi")
        EventPayment.objects.create(event=event, amount=40000, method="cash")
        event = Event.objects.get(pk=event.pk)
        self.assertEqual(event.paid, 100000)
        self.assertEqual(event.payment_state, "partial")
        annotated = Event.objects.with_paid().get(pk=event.pk)
        self.assertEqual(annotated.paid, 100000)

    def test_revenue_cost_profit_and_remaining(self):
        event = self.event(revenue=250000)
        EventItem.objects.create(
            event=event, item_type="external", name="Outside catering",
            quantity=1, unit_cost=70000,
        )
        EventExpense.objects.create(event=event, name="Venue", category="venue", amount=80000)
        EventPayment.objects.create(event=event, amount=100000)

        event = Event.objects.prefetch_related("items", "expenses", "payments").get(pk=event.pk)
        self.assertEqual(event.revenue, 250000)
        self.assertEqual(event.total_cost, 150000)
        self.assertEqual(event.paid, 100000)
        self.assertEqual(event.profit, 100000)
        self.assertEqual(event.remaining, 150000)
        self.assertEqual(event.margin_percent, 40)

    def test_cost_includes_consumables_but_not_returned_reusables(self):
        event = self.event(revenue=50000)
        chairs = event.add_inventory_item(self.chair, 30)     # 450 each, reusable
        water = event.add_inventory_item(self.water, 100 - 60)  # 20 each, consumable
        EventItem.objects.create(event=event, item_type="external", name="Banner", quantity=2, unit_cost=1500)
        EventExpense.objects.create(event=event, name="Crew", category="staff", amount=4000)

        event = Event.objects.get(pk=event.pk)
        # Before the event: consumables at their planned quantity, chairs free.
        self.assertEqual(self.line(chairs).cost, 0)
        self.assertEqual(self.line(water).cost, 40 * 20)
        self.assertEqual(event.total_cost, 800 + 3000 + 4000)

        event.confirm()
        event.allocate()
        event.start()
        self.line(chairs).record_usage(returned=29, lost=1)
        self.line(water).record_usage(consumed=30, returned=10)
        event = Event.objects.get(pk=event.pk)
        self.assertEqual(event.inventory_cost, 450 + 30 * 20)
        self.assertEqual(event.external_cost, 3000)
        self.assertEqual(event.total_cost, 450 + 600 + 3000 + 4000)
        self.assertEqual(event.profit, 50000 - 8050)

    def test_payment_states(self):
        event = self.event(revenue=1000)
        self.assertEqual(Event.objects.get(pk=event.pk).payment_state, "unpaid")
        EventPayment.objects.create(event=event, amount=1000)
        event = Event.objects.get(pk=event.pk)
        self.assertEqual(event.payment_state, "paid")
        self.assertEqual(event.remaining, 0)
        self.assertEqual(event.paid_percent, 100)

    def test_a_loss_is_a_negative_profit(self):
        event = self.event(revenue=1000)
        EventExpense.objects.create(event=event, name="Venue", category="venue", amount=4000)
        self.assertEqual(Event.objects.get(pk=event.pk).profit, -3000)
