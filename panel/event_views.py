"""
Event pages: the list, one event, and every button on it.

Like the counter, each button is a plain POST that redirects back, so the page
works without JavaScript and a reload never repeats an action. The stock rules
live on the models (the Events section of `core/models.py`); these views decide
who may press what, and turn a refusal into a message rather than a 500.

Viewers can open everything. Changing anything needs the editor role, and
deleting an event needs admin — the same ladder the rest of the panel uses.
"""

from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Count, F, Prefetch, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.models import (
    ActivityLog,
    Category,
    Customer,
    Enquiry,
    Event,
    EventExpense,
    EventItem,
    EventPayment,
    InventoryItem,
    StaffMember,
    normalise_quantity,
)

from . import forms as f
from .permissions import panel_login_required
from .views import PAGE_SIZE, log, panel_context

WHEN_CHOICES = [
    ("upcoming", "Upcoming"),
    ("week", "Next 7 days"),
    ("month", "This month"),
    ("past", "Past"),
]
PAYMENT_CHOICES = [
    ("unpaid", "Unpaid"),
    ("partial", "Part paid"),
    ("paid", "Paid in full"),
]
SORTABLE = {"number", "name", "event_date", "revenue", "status", "customer__name"}

#: Which buttons each status offers, in the order they are shown.
STATUS_ACTIONS = {
    "draft": ["confirm", "cancel"],
    "confirmed": ["allocate", "start", "cancel"],
    "in_progress": ["allocate", "complete", "cancel"],
    "completed": ["finalize"],
    "cancelled": ["release"],
}
ACTIONS = {
    "confirm": {
        "label": "Confirm event", "icon": "check", "style": "primary",
        "done": "confirmed", "method": "confirm",
    },
    "allocate": {
        "label": "Reserve inventory", "icon": "package", "style": "primary",
        "done": "reserved inventory", "method": "allocate",
    },
    "start": {
        "label": "Start event", "icon": "sparkles", "style": "primary",
        "done": "started", "method": "start",
    },
    "complete": {
        "label": "Mark completed", "icon": "check", "style": "primary",
        "done": "completed", "method": "complete",
        "confirm": "Mark this event completed? Record returns and damage next.",
    },
    "finalize": {
        "label": "Finalise inventory", "icon": "clipboard", "style": "primary",
        "done": "finalised inventory", "method": "finalize_inventory",
        "confirm": (
            "Settle everything still out? Reusable stock is marked returned and "
            "consumable stock consumed. Record damage and losses first."
        ),
    },
    "cancel": {
        "label": "Cancel event", "icon": "x", "style": "danger",
        "done": "cancelled", "method": "cancel",
        "confirm": "Cancel this event and release every reserved item back to stock?",
    },
    "release": {
        "label": "Release reserved inventory", "icon": "undo", "style": "ghost",
        "done": "released its reservations", "method": "release_reservations",
    },
}
#: Short names for the one-click buttons on the list.
SHORT_LABELS = {
    "confirm": "Confirm", "allocate": "Reserve", "start": "Start",
    "complete": "Complete", "finalize": "Finalise", "cancel": "Cancel",
    "release": "Release",
}
STEPS = [
    ("draft", "Draft"),
    ("confirmed", "Confirmed"),
    ("in_progress", "In progress"),
    ("completed", "Completed"),
]
#: The button that takes an event onto each step.
STEP_ACTIONS = {"confirmed": "confirm", "in_progress": "start", "completed": "complete"}
#: What the activity log says when a step is reached, and back again.
LOG_WORDS = {
    "confirmed": "confirmed", "in_progress": "started",
    "completed": "completed", "cancelled": "cancelled",
}
LOG_STEPS = {word: step for step, word in LOG_WORDS.items()}
CURRENT_HINTS = {
    "draft": "Planning — add what it needs",
    "confirmed": "Booked — getting ready",
    "in_progress": "Happening now",
}
NEXT_HINTS = {
    "confirmed": "When the customer says yes",
    "completed": "When the crew is back",
}
#: Buttons that move an event onto a step, and the step they land on.
ARRIVES_AT = {
    "confirm": "confirmed", "start": "in_progress", "complete": "completed",
    "cancel": "cancelled", "finalize": "finalized",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rupees(amount):
    return f"−Rs. {-amount:,}" if amount < 0 else f"Rs. {amount:,}"


def _can_write(request):
    return request.profile.at_least("editor")


def _denied(request, event=None, role="editor"):
    messages.error(
        request, f"Changing events needs the {role} role — yours is {request.profile.role}."
    )
    return redirect(event.get_absolute_url() if event else "panel:events")


def _refused(request, error):
    for message in error.messages:
        messages.error(request, message)


def _back(event, anchor=""):
    url = event.get_absolute_url()
    return redirect(f"{url}#{anchor}" if anchor else url)


def _after_action(request, event, anchor=""):
    """Back where the button was pressed: the list, if it came from there."""
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ) and target.startswith(reverse("panel:events")):
        return redirect(f"{target.split('#')[0]}#event-{event.pk}")
    return _back(event, anchor)


def available_actions(event):
    """The status buttons an event offers right now, most useful first."""
    actions = []
    for key in STATUS_ACTIONS.get(event.status, []):
        # Buttons with nothing to do stay off the page rather than failing.
        if key == "allocate" and not event.needs_allocation:
            continue
        # Starting is refused until the stock is reserved, so do not offer it.
        if key == "start" and event.needs_allocation:
            continue
        if key in ("finalize", "release") and not event.has_outstanding:
            continue
        actions.append(dict(ACTIONS[key], key=key, short=SHORT_LABELS[key]))
    return actions


def _date(raw):
    try:
        return parse_date(raw or "")
    except ValueError:  # well-formed but impossible, like 2026-02-30
        return None


def _event_or_404(pk):
    return get_object_or_404(
        Event.objects.select_related(
            "customer", "created_by", "occasion", "package", "package__category",
        ).prefetch_related(
            Prefetch(
                "items",
                queryset=EventItem.objects.select_related("inventory_item", "supplier"),
            ),
            Prefetch("expenses", queryset=EventExpense.objects.select_related("created_by")),
            Prefetch("payments", queryset=EventPayment.objects.select_related("received_by")),
            Prefetch("crew", queryset=StaffMember.objects.select_related("category")),
        ),
        pk=pk,
    )


# ---------------------------------------------------------------------------
# The list
# ---------------------------------------------------------------------------


def _filter_events(queryset, request, today, occasion=None):
    """Search, occasion and date filters, shared by the table and the status tab counts."""
    term = request.GET.get("q", "").strip()
    if term:
        queryset = queryset.filter(
            Q(number__icontains=term) | Q(name__icontains=term)
            | Q(customer__name__icontains=term) | Q(customer__phone__icontains=term)
            | Q(location__icontains=term) | Q(occasion__name__icontains=term)
        )
    if occasion is not None:
        queryset = queryset.filter(occasion=occasion)

    when = request.GET.get("when", "")
    if when == "upcoming":
        queryset = queryset.filter(event_date__gte=today)
    elif when == "week":
        queryset = queryset.filter(event_date__gte=today, event_date__lte=today + timedelta(days=6))
    elif when == "month":
        queryset = queryset.filter(event_date__year=today.year, event_date__month=today.month)
    elif when == "past":
        queryset = queryset.filter(event_date__lt=today)

    date_from = _date(request.GET.get("from"))
    date_to = _date(request.GET.get("to"))
    if date_from:
        queryset = queryset.filter(event_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(event_date__lte=date_to)
    return queryset, term, when, date_from, date_to


@panel_login_required
def event_list(request):
    today = timezone.localdate()

    # Every occasion, retired ones too: their past events still need finding.
    occasions = list(Category.objects.order_by("position", "name"))
    chosen_occasion = next(
        (o for o in occasions if o.slug == request.GET.get("occasion", "")), None
    )

    events, term, when, date_from, date_to = _filter_events(
        Event.objects.select_related("customer", "occasion").with_paid(),
        request, today, chosen_occasion,
    )

    # The tabs count what each would show with the other filters kept.
    counted, *_ = _filter_events(Event.objects.all(), request, today, chosen_occasion)
    per_status = dict(
        counted.order_by().values_list("status").annotate(n=Count("id")).values_list("status", "n")
    )
    tabs = [{"value": "", "label": "All", "count": sum(per_status.values())}] + [
        {"value": value, "label": label, "count": per_status.get(value, 0),
         "tone": Event.STATUS_TONES[value]}
        for value, label in Event.STATUS_CHOICES
    ]

    status = request.GET.get("status", "")
    if status in dict(Event.STATUS_CHOICES):
        events = events.filter(status=status)
    else:
        status = ""

    source = request.GET.get("source", "")
    if source in dict(Event.SOURCE_CHOICES):
        events = events.filter(source=source)
    else:
        source = ""
    only_new = request.GET.get("new") == "1"
    if only_new:
        events = events.filter(is_new=True)

    payment = request.GET.get("payment", "")
    if payment == "unpaid":
        events = events.filter(paid_total=0)
    elif payment == "partial":
        events = events.filter(paid_total__gt=0, paid_total__lt=F("revenue"))
    elif payment == "paid":
        events = events.filter(paid_total__gt=0, paid_total__gte=F("revenue"))
    else:
        payment = ""

    sort = request.GET.get("sort", "")
    if sort.lstrip("-") in SORTABLE:
        events = events.order_by(sort, "-id")
    else:
        sort = ""
        # Unopened website bookings first, so nobody has to go looking.
        events = events.order_by("-is_new", "-event_date", "-id")

    # Money across everything the filters matched, cancellations left out.
    live = events.exclude(status="cancelled")
    revenue = int(live.aggregate(total=Sum("revenue"))["total"] or 0)
    collected = int(
        EventPayment.objects.filter(event__in=live.values("pk"))
        .aggregate(total=Sum("amount"))["total"] or 0
    )
    cost = sum(
        event.total_cost
        for event in live.prefetch_related("items", "expenses")
    )
    live_count = live.count()

    kpis = [
        {
            "label": "Events", "value": events.count(), "icon": "sparkles", "tone": "blue",
            "foot": f"{events.filter(status__in=Event.OPEN_STATUSES, event_date__gte=today).count()} still to come",
        },
        {
            "label": "Revenue", "value": f"Rs. {revenue:,}", "icon": "trending-up", "tone": "green",
            "foot": f"Across {live_count} event{'s' if live_count != 1 else ''}, cancellations excluded",
        },
        {
            "label": "Collected", "value": f"Rs. {collected:,}", "icon": "receipt", "tone": "violet",
            "foot": f"Rs. {max(revenue - collected, 0):,} still to collect",
        },
        {
            "label": "Profit", "value": _rupees(revenue - cost), "icon": "activity",
            "tone": "green" if revenue >= cost else "red",
            "foot": f"After Rs. {cost:,} of items and expenses",
        },
    ]

    paginator = Paginator(events.prefetch_related("items", "expenses"), PAGE_SIZE)
    try:
        page_obj = paginator.page(request.GET.get("page", 1))
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    page_obj.object_list = list(page_obj.object_list)
    for event in page_obj.object_list:
        actions = available_actions(event)
        # One button moves the event on; cancelling sits apart, behind a prompt.
        event.next_action = next((a for a in actions if a["key"] != "cancel"), None)
        event.cancel_action = next((a for a in actions if a["key"] == "cancel"), None)

    is_filtered = bool(
        term or chosen_occasion or when or date_from or date_to
        or status or payment or source or only_new
    )
    return render(request, "panel/events/list.html", panel_context(
        request,
        title="Events",
        nav_key="events",
        kpis=kpis,
        tabs=tabs,
        rows=page_obj.object_list,
        page_obj=page_obj,
        q=term,
        status=status,
        source=source,
        only_new=only_new,
        new_count=Event.objects.filter(is_new=True).count(),
        source_choices=Event.SOURCE_CHOICES,
        occasions=occasions,
        occasion=chosen_occasion.slug if chosen_occasion else "",
        payment=payment,
        when=when,
        date_from=date_from.isoformat() if date_from else "",
        date_to=date_to.isoformat() if date_to else "",
        when_choices=WHEN_CHOICES,
        payment_choices=PAYMENT_CHOICES,
        sort=sort,
        is_filtered=is_filtered,
        can_write=_can_write(request),
    ))


# ---------------------------------------------------------------------------
# Create, edit, delete
# ---------------------------------------------------------------------------


def _from_enquiry(enquiry):
    """A new event's form, filled in from what the enquiry already says."""
    occasion = enquiry.occasion_match
    title = enquiry.package.title if enquiry.package_id else (
        f"{occasion.name} celebration" if occasion else (enquiry.occasion or "Event")
    )
    initial = {
        "name": f"{title} — {enquiry.name.split()[0] if enquiry.name else ''}".strip(" —"),
        "occasion": occasion.pk if occasion else None,
        "package": enquiry.package_id,
        "event_date": enquiry.event_date,
        "guests": enquiry.guests or None,
        "location": enquiry.city,
        "revenue": enquiry.package.price if enquiry.package_id else None,
        "notes": f"From an enquiry on {enquiry.created_at:%d %b %Y}:\n{enquiry.message}".strip(),
    }
    customer = Customer.find_by_phone(enquiry.phone)
    if customer:
        initial["customer"] = customer.pk
    else:
        initial["new_customer_name"] = enquiry.name
        initial["new_customer_phone"] = enquiry.phone
    return initial


@panel_login_required
def event_create(request):
    if not _can_write(request):
        return _denied(request)

    enquiry = None
    raw = request.POST.get("enquiry") or request.GET.get("enquiry", "")
    if raw.isdigit():
        enquiry = Enquiry.objects.select_related("package", "package__category", "event").filter(pk=raw).first()
    if enquiry and enquiry.event_id and request.method == "GET":
        messages.info(request, f"That enquiry is already {enquiry.event.number}.")
        return _back(enquiry.event)

    initial = _from_enquiry(enquiry) if enquiry else {}
    if request.GET.get("customer", "").isdigit():
        initial["customer"] = request.GET["customer"]
    form = f.EventForm(request.POST or None, initial=initial)
    if request.method == "POST":
        if form.is_valid():
            event = form.save(commit=False)
            event.created_by = request.user
            if enquiry and not enquiry.event_id:
                event.source = "enquiry"
            event.save()
            form.save_m2m()
            log(request, "create", obj=event, model_label="Event")
            if enquiry and not enquiry.event_id:
                enquiry.event = event
                if enquiry.status == "new":
                    enquiry.status = "read"
                enquiry.save(update_fields=["event", "status"])
            messages.success(
                request, f"{event.number} created as a draft. Add what it needs next."
            )
            return _back(event, "items")
        messages.error(request, "Some fields need another look.")

    return render(request, "panel/events/form.html", panel_context(
        request, title="New event", nav_key="events", form=form, event=None, enquiry=enquiry,
    ))


@panel_login_required
def event_edit(request, pk):
    event = get_object_or_404(Event.objects.select_related("customer"), pk=pk)
    if not _can_write(request):
        return _denied(request, event)
    if event.is_cancelled:
        messages.warning(request, "A cancelled event is kept as it was, for the record.")
        return _back(event)

    form = f.EventForm(request.POST or None, instance=event)
    if request.method == "POST":
        if form.is_valid():
            event = form.save()
            log(request, "update", obj=event, model_label="Event")
            messages.success(request, f"{event.number} saved.")
            return _back(event)
        messages.error(request, "Some fields need another look.")

    return render(request, "panel/events/form.html", panel_context(
        request, title=f"Edit {event.number}", nav_key="events", form=form, event=event,
    ))


@panel_login_required
@require_POST
def event_delete(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not request.profile.at_least("admin"):
        return _denied(request, event, role="admin")
    if not event.can_delete:
        messages.error(
            request,
            "Only a draft or a cancelled event holding no stock can be deleted. "
            "Cancel it first — that keeps its history and releases its stock.",
        )
        return _back(event)
    label = str(event)
    event.delete()
    log(request, "delete", model_label="Event", detail=label)
    messages.success(request, f"Deleted {label}.")
    return redirect("panel:events")


# ---------------------------------------------------------------------------
# One event
# ---------------------------------------------------------------------------


def _timeline(event, actions, arrived=""):
    """
    The progress track at the top of an event: every step with when it was
    reached and by whom, what is happening now, and — for the step after the
    current one — the button that gets there, or what is holding it up.

    Returns (steps, progress), progress being how far along the line to fill,
    from 0 to 1.
    """
    order = [key for key, _label in STEPS]
    at = order.index(event.reached)
    offered = {action["key"]: action for action in actions}

    # Who pressed each button, from the activity log the actions write.
    logged = {}
    if event.number:
        for entry in (
            ActivityLog.objects.filter(
                model_label="Event",
                object_label__startswith=f"{event.number} ·",
                detail__in=list(LOG_WORDS.values()),
            ).select_related("user").order_by("created_at")
        ):
            logged.setdefault(LOG_STEPS[entry.detail], entry)

    def person(user):
        return (user.get_full_name() or user.username) if user else ""

    def moment(key):
        if key == "draft":
            if event.created_by_id is None and event.from_website:
                return event.created_at, "the customer, online"
            return event.created_at, person(event.created_by)
        entry = logged.get(key)
        when = getattr(event, Event.STAMPS[key]) or (entry.created_at if entry else None)
        if entry and entry.user_id is None and event.source != "panel":
            # Only the website acts without a panel account.
            return when, "the customer, online"
        return when, person(entry.user) if entry else ""

    steps = []
    for index, (key, label) in enumerate(STEPS):
        if event.is_cancelled and index > at:
            break
        when, by = moment(key)
        step = {
            "key": key, "label": label, "when": when, "by": by,
            "state": "todo", "hint": "", "action": None, "arrived": arrived == key,
        }
        if index < at or (index == at and event.is_cancelled):
            step["state"] = "done"
        elif index == at and key == "completed":
            # The last step is finished — unless stock is still out there.
            if event.has_outstanding:
                step.update(state="warn", hint="Stock still out — record returns, then finalise")
            else:
                step.update(state="done", hint="All stock settled")
                step["arrived"] = arrived in ("completed", "finalized")
        elif index == at:
            step.update(state="current", hint=CURRENT_HINTS.get(key, ""))
        elif index == at + 1:
            wanted = STEP_ACTIONS[key]
            if wanted in offered:
                step["action"] = offered[wanted]
            if key == "in_progress" and "allocate" in offered:
                step["hint"] = "Reserve the stock first"
            elif key == "in_progress":
                days = (event.event_date - timezone.localdate()).days
                day = f"{event.event_date.day} {event.event_date:%b}"
                step["hint"] = (
                    "The event is today" if days == 0
                    else f"Was due on {day}" if days < 0
                    else f"On the day · {day}"
                )
            else:
                step["hint"] = NEXT_HINTS.get(key, "")
        steps.append(step)

    if event.is_cancelled:
        when, by = moment("cancelled")
        steps.append({
            "key": "cancelled", "label": "Cancelled", "when": when, "by": by,
            "state": "cancelled", "arrived": arrived == "cancelled",
            "hint": "Stock still held — release it" if event.has_outstanding else "Stock released",
            "action": None,
        })

    last = len(steps) - 1
    filled = last if event.is_cancelled else at
    # A string, so a locale's decimal comma never ends up in the CSS.
    progress = f"{filled / last if last > 0 else 1:.4f}"
    return steps, progress


def _render_detail(request, event, status=200, **forms):
    writable = _can_write(request)
    stock_pick = forms.get("stock_pick") or f.EventStockPickForm(event=event)
    external_form = forms.get("external_form") or f.EventExternalItemForm()
    expense_form = forms.get("expense_form") or f.EventExpenseForm()
    payment_form = forms.get("payment_form") or f.EventPaymentForm(event=event)

    actions = available_actions(event)
    arrived = request.session.pop("event_arrived", None)
    arrived = arrived[1] if arrived and arrived[0] == event.pk else ""
    steps, progress = _timeline(event, actions if writable else [], arrived)

    inventory_lines = event.inventory_lines
    stock_ids = [line.inventory_item_id for line in inventory_lines]
    stock = {
        item.pk: item
        for item in InventoryItem.objects.with_reserved().filter(pk__in=stock_ids)
    }
    for line in inventory_lines:
        line.stock = stock.get(line.inventory_item_id)

    expenses_by_category = {}
    for expense in event.expenses.all():
        bucket = expenses_by_category.setdefault(
            expense.category,
            {"label": expense.get_category_display(), "tone": expense.category_tone, "total": 0},
        )
        bucket["total"] += expense.amount

    return render(request, "panel/events/detail.html", panel_context(
        request,
        title=event.number,
        nav_key="events",
        event=event,
        steps=steps,
        progress=progress,
        actions=actions,
        inventory_lines=inventory_lines,
        external_lines=event.external_lines,
        items=list(event.items.all()),
        expenses=list(event.expenses.all()),
        expense_buckets=sorted(
            expenses_by_category.values(), key=lambda row: row["total"], reverse=True
        ),
        payments=list(event.payments.all()),
        enquiries=list(event.enquiries.order_by("-created_at")),
        movements=event.stock_movements.select_related("item", "created_by").order_by(
            "-created_at", "-id"
        )[:40],
        stock_pick=stock_pick,
        external_form=external_form,
        expense_form=expense_form,
        payment_form=payment_form,
        open_panel=forms.get("open_panel", ""),
        can_write=writable,
        can_delete=request.profile.at_least("admin") and event.can_delete,
    ), status=status)


@panel_login_required
def event_detail(request, pk):
    event = _event_or_404(pk)
    if event.is_new:
        # Opening it is what "new" was waiting for. The page still says where
        # it came from; only the badge in the sidebar and the list goes.
        Event.objects.filter(pk=event.pk).update(is_new=False)
        event.was_new = True
    return _render_detail(request, event)


@panel_login_required
@require_POST
def event_action(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not _can_write(request):
        return _denied(request, event)

    key = request.POST.get("action", "")
    if key not in STATUS_ACTIONS.get(event.status, []):
        messages.error(
            request,
            f"{event.number} is {event.get_status_display().lower()} now, so that "
            "button no longer applies.",
        )
        return _after_action(request, event)

    spec = ACTIONS[key]
    try:
        result = getattr(event, spec["method"])(user=request.user)
    except ValidationError as error:
        _refused(request, error)
        return _after_action(
            request, event, "inventory" if key in ("allocate", "start", "finalize") else ""
        )

    log(request, "update", obj=event, model_label="Event", detail=spec["done"])
    if key in ARRIVES_AT:
        # The event page celebrates the step it lands on, once.
        request.session["event_arrived"] = [event.pk, ARRIVES_AT[key]]
    if key == "allocate":
        messages.success(
            request,
            f"{event.number}: reserved stock on {result} line{'s' if result != 1 else ''}.",
        )
    elif key in ("cancel", "release"):
        tail = (
            f" and released {result} reserved line{'s' if result != 1 else ''}"
            if result else ""
        )
        messages.success(request, f"{event.number} {spec['done']}{tail}.")
    elif key == "finalize":
        messages.success(
            request,
            f"{event.number}: inventory finalised — {result} line{'s' if result != 1 else ''} settled.",
        )
    else:
        messages.success(request, f"{event.number} {spec['done']}.")
    return _after_action(request, event)


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------


@panel_login_required
@require_POST
def event_add_stock(request, pk):
    event = _event_or_404(pk)
    if not _can_write(request):
        return _denied(request, event)
    if not event.can_change_items:
        messages.error(request, "Items cannot be added to this event any more.")
        return _back(event, "items")

    form = f.EventStockPickForm(request.POST, event=event)
    if not form.is_valid():
        messages.error(request, "Nothing was added — see the ticked items.")
        return _render_detail(request, event, stock_pick=form, open_panel="stock")

    try:
        event.add_inventory_items(form.cleaned, user=request.user)
    except ValidationError as error:
        # Someone else took the stock between the page and the lock.
        event = _event_or_404(pk)
        form = f.EventStockPickForm(request.POST, event=event)
        form.is_valid()
        form.add_error(error.messages)
        messages.error(request, "Nothing was added — see the ticked items.")
        return _render_detail(request, event, stock_pick=form, open_panel="stock")

    added = ", ".join(
        f"{normalise_quantity(quantity)} × {item.name}" for item, quantity in form.cleaned
    )
    held = " and reserved" if event.status in Event.HOLDING_STATUSES else ""
    log(request, "update", obj=event, model_label="Event", detail=f"added {added}")
    messages.success(request, f"Added{held}: {added}.")
    return _back(event, "items")


@panel_login_required
@require_POST
def event_add_external(request, pk):
    event = _event_or_404(pk)
    if not _can_write(request):
        return _denied(request, event)
    if not event.can_change_items:
        messages.error(request, "Items cannot be added to this event any more.")
        return _back(event, "items")

    form = f.EventExternalItemForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "That item could not be added — see the form.")
        return _render_detail(request, event, external_form=form, open_panel="external")

    line = form.save(commit=False)
    line.event = event
    line.save()
    log(request, "update", obj=event, model_label="Event", detail=f"added external {line.name}")
    messages.success(request, f"{line.name} added as an external item.")
    return _back(event, "items")


@panel_login_required
def event_line_edit(request, pk, line_pk):
    line = get_object_or_404(
        EventItem.objects.select_related("event", "event__customer", "inventory_item", "supplier"),
        pk=line_pk, event_id=pk,
    )
    event = line.event
    if not _can_write(request):
        return _denied(request, event)
    if not event.can_change_items:
        messages.error(request, "This event's items are fixed now.")
        return _back(event, "items")

    if line.is_external:
        form = f.EventExternalItemForm(request.POST or None, request.FILES or None, instance=line)
    else:
        form = f.EventLineQuantityForm(
            request.POST or None,
            initial={"quantity": normalise_quantity(line.quantity), "notes": line.notes},
        )

    if request.method == "POST" and form.is_valid():
        if line.is_external:
            form.save()
        else:
            try:
                line.set_quantity(form.cleaned_data["quantity"], user=request.user)
            except ValidationError as error:
                form.add_error("quantity", error)
            else:
                EventItem.objects.filter(pk=line.pk).update(notes=form.cleaned_data["notes"])
        if not form.errors:
            log(request, "update", obj=event, model_label="Event", detail=f"changed {line.name}")
            messages.success(request, f"{line.name} updated.")
            return _back(event, "items")

    if request.method == "POST":
        messages.error(request, "That change needs another look.")

    stock = None
    if line.is_inventory:
        stock = InventoryItem.objects.with_reserved().get(pk=line.inventory_item_id)
    return render(request, "panel/events/line_form.html", panel_context(
        request,
        title=f"Edit {line.name}",
        nav_key="events",
        event=event,
        line=line,
        stock=stock,
        form=form,
    ))


@panel_login_required
@require_POST
def event_line_remove(request, pk, line_pk):
    line = get_object_or_404(EventItem.objects.select_related("event"), pk=line_pk, event_id=pk)
    event = line.event
    if not _can_write(request):
        return _denied(request, event)
    name = line.name
    try:
        line.remove(user=request.user)
    except ValidationError as error:
        _refused(request, error)
        return _back(event, "items")
    log(request, "update", obj=event, model_label="Event", detail=f"removed {name}")
    messages.success(request, f"{name} removed from the event.")
    return _back(event, "items")


@panel_login_required
@require_POST
def event_line_usage(request, pk, line_pk):
    line = get_object_or_404(EventItem.objects.select_related("event"), pk=line_pk, event_id=pk)
    event = line.event
    if not _can_write(request):
        return _denied(request, event)

    form = f.EventUsageForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Quantities have to be zero or more.")
        return _back(event, "inventory")
    data = form.cleaned_data
    try:
        line.record_usage(
            returned=data["returned"], consumed=data["consumed"],
            damaged=data["damaged"], lost=data["lost"], user=request.user,
        )
    except ValidationError as error:
        _refused(request, error)
        return _back(event, "inventory")

    bits = [
        f"{normalise_quantity(data[name])} {name}"
        for name in ("returned", "consumed", "damaged", "lost") if data[name]
    ]
    summary = ", ".join(bits)
    log(request, "update", obj=event, model_label="Event", detail=f"{line.name}: {summary}")
    messages.success(request, f"{line.name}: {summary}.")
    return _back(event, "inventory")


# ---------------------------------------------------------------------------
# Expenses and payments
# ---------------------------------------------------------------------------


@panel_login_required
@require_POST
def event_add_expense(request, pk):
    event = _event_or_404(pk)
    if not _can_write(request):
        return _denied(request, event)

    form = f.EventExpenseForm(request.POST)
    if not form.is_valid():
        messages.error(request, "That expense needs another look.")
        return _render_detail(request, event, expense_form=form, open_panel="expense")

    expense = form.save(commit=False)
    expense.event = event
    expense.created_by = request.user
    expense.save()
    log(request, "update", obj=event, model_label="Event",
        detail=f"expense {expense.name} Rs. {expense.amount:,}")
    messages.success(request, f"Expense added — {expense.name}, Rs. {expense.amount:,}.")
    return _back(event, "expenses")


@panel_login_required
@require_POST
def event_remove_expense(request, pk, expense_pk):
    expense = get_object_or_404(EventExpense.objects.select_related("event"), pk=expense_pk, event_id=pk)
    event = expense.event
    if not _can_write(request):
        return _denied(request, event)
    label = str(expense)
    expense.delete()
    log(request, "update", obj=event, model_label="Event", detail=f"removed expense {label}")
    messages.success(request, f"Removed the expense {label}.")
    return _back(event, "expenses")


@panel_login_required
@require_POST
def event_add_payment(request, pk):
    event = _event_or_404(pk)
    if not _can_write(request):
        return _denied(request, event)
    if not event.can_take_money:
        messages.error(request, "A cancelled event does not take payments.")
        return _back(event, "payments")

    form = f.EventPaymentForm(request.POST, event=event)
    if not form.is_valid():
        messages.error(request, "That payment needs another look.")
        return _render_detail(request, event, payment_form=form, open_panel="payment")

    payment = form.save(commit=False)
    payment.event = event
    payment.received_by = request.user
    payment.save()
    log(request, "update", obj=event, model_label="Event",
        detail=f"payment Rs. {payment.amount:,} by {payment.get_method_display()}")
    messages.success(request, f"Payment of Rs. {payment.amount:,} recorded.")
    return _back(event, "payments")


@panel_login_required
@require_POST
def event_remove_payment(request, pk, payment_pk):
    payment = get_object_or_404(EventPayment.objects.select_related("event"), pk=payment_pk, event_id=pk)
    event = payment.event
    if not _can_write(request):
        return _denied(request, event)
    label = str(payment)
    payment.delete()
    log(request, "update", obj=event, model_label="Event", detail=f"removed payment {label}")
    messages.success(request, f"Removed the payment of {label}.")
    return _back(event, "payments")
