"""
Control panel views.

Three kinds of thing live here:

  * account flow  — signup (invite-gated), login, logout, profile, password
  * generic CRUD  — one list / form / delete view driving every entry in
                    `resources.RESOURCES`
  * bespoke pages — dashboard, schedule board, the counter, the stock room,
                    settings, staff, activity, media

The generic views are the reason the panel covers two dozen models without two
dozen copies of the same code. Anything a model needs beyond the defaults is
expressed in its `Resource` declaration or its `ModelForm`, not here.

The counter is the one screen that is not a table: it holds a basket in the
session, and closing a sale is the only place in the panel where money and
stock move together.
"""

import csv
from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth import get_user_model
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import (
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    ProtectedError,
    Q,
    Sum,
)
from django.db.models.functions import TruncDate
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from core.models import (
    ActivityLog,
    Category,
    CounterSale,
    CounterSaleLine,
    Customer,
    Enquiry,
    Event,
    EventItem,
    HeroSlide,
    InventoryItem,
    InviteCode,
    Package,
    PackageImage,
    SiteSettings,
    StaffCategory,
    StaffMember,
    StaffProfile,
    StockCategory,
    StockMovement,
    normalise_quantity,
)

from . import forms as f
from . import resources
from .permissions import panel_login_required, profile_for, require_role

User = get_user_model()
PAGE_SIZE = 20


# ---------------------------------------------------------------------------
# Shared context
# ---------------------------------------------------------------------------


def _announce_new_arrivals(request, events_new, enquiries_new):
    """
    A soft live-update: if more website events or enquiries have landed since
    this session last looked, say so as a toast on whichever page loads next.
    A high-water mark in the session means it fires once per new arrival, not
    once per page — and never on the very first visit of a session.
    """
    seen_events = request.session.get("seen_new_events")
    seen_enquiries = request.session.get("seen_new_enquiries")

    if seen_events is not None and events_new > seen_events:
        gained = events_new - seen_events
        messages.info(
            request,
            f"{gained} new booking request{'s' if gained != 1 else ''} just came in from the website.",
            extra_tags="live",
        )
    if seen_enquiries is not None and enquiries_new > seen_enquiries:
        gained = enquiries_new - seen_enquiries
        messages.info(
            request,
            f"{gained} new enquir{'ies' if gained != 1 else 'y'} just came in from the website.",
            extra_tags="live",
        )

    request.session["seen_new_events"] = events_new
    request.session["seen_new_enquiries"] = enquiries_new


def panel_context(request, **extra):
    """
    Everything the chrome needs: sidebar, the signed-in user, and the two
    counters that earn a dot in the sidebar (new website events, unread enquiries).
    """
    profile = getattr(request, "profile", None)
    match = request.resolver_match
    events_new = Event.objects.filter(is_new=True).count()
    enquiries_new = Enquiry.objects.filter(status="new").count()
    if profile is not None:
        _announce_new_arrivals(request, events_new, enquiries_new)
    context = {
        "profile": profile,
        "groups": resources.grouped(profile),
        # What the sidebar highlights: a resource is known by its slug, a
        # bespoke page by its URL name.
        "nav_key": (match.kwargs.get("slug") or match.url_name) if match else "",
        "panel_theme": getattr(profile, "theme", "light"),
        "counts": {
            "enquiries": enquiries_new,
            # Website bookings (or cancellations) nobody has opened yet.
            "events": events_new,
            "low_stock": InventoryItem.objects.needs_attention().count(),
        },
        "can_write": bool(profile and profile.can_write),
        "can_configure": bool(profile and profile.can_configure),
        "can_manage_staff": bool(profile and profile.can_manage_staff),
    }
    context.update(extra)
    return context


def log(request, action, obj=None, model_label="", detail=""):
    ActivityLog.record(request.user, action, obj=obj, model_label=model_label, detail=detail)


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------


def panel_signup(request):
    """
    Open URL, closed panel: the first account bootstraps itself as owner and
    every later one has to present an invite code.
    """
    if request.user.is_authenticated and profile_for(request.user):
        return redirect("panel:dashboard")

    bootstrap = not StaffProfile.objects.exists()
    form = f.PanelSignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        ActivityLog.record(
            user, "auth", model_label="Account",
            detail="first account, bootstrapped as owner" if bootstrap else "signed up with an invite",
        )
        messages.success(
            request,
            "Welcome aboard. You are the owner of this panel." if bootstrap
            else "Account created. Here is your panel.",
        )
        return redirect("panel:dashboard")

    return render(request, "panel/auth/signup.html", {
        "form": form,
        "bootstrap": bootstrap,
        "invite_count": InviteCode.objects.filter(used_by__isnull=True).count(),
    })


def panel_login(request):
    if request.user.is_authenticated and profile_for(request.user):
        return redirect("panel:dashboard")

    form = f.PanelLoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if profile_for(user) is None:
            messages.error(request, "That account exists but has no panel access.")
        else:
            login(request, user)
            ActivityLog.record(user, "auth", model_label="Account", detail="signed in")
            next_url = request.GET.get("next") or request.POST.get("next")
            return redirect(next_url or "panel:dashboard")

    return render(request, "panel/auth/login.html", {
        "form": form,
        "next": request.GET.get("next", ""),
        "has_accounts": StaffProfile.objects.exists(),
    })


def panel_logout(request):
    if request.method == "POST":
        logout(request)
        messages.success(request, "Signed out.")
    return redirect("panel:login")


@panel_login_required
def account(request):
    profile = request.profile
    form = f.AccountForm(request.POST or None, instance=profile)
    password_form = f.PanelPasswordChangeForm(request.user)

    if request.method == "POST":
        if "change_password" in request.POST:
            password_form = f.PanelPasswordChangeForm(request.user, request.POST)
            form = f.AccountForm(instance=profile)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)  # stay signed in
                log(request, "auth", model_label="Account", detail="changed password")
                messages.success(request, "Password changed.")
                return redirect("panel:account")
        elif form.is_valid():
            form.save()
            messages.success(request, "Profile saved.")
            return redirect("panel:account")

    return render(request, "panel/pages/account.html", panel_context(
        request,
        title="Your account",
        form=form,
        password_form=password_form,
        recent=ActivityLog.objects.filter(user=request.user)[:12],
    ))


@panel_login_required
@require_POST
def set_theme(request):
    """Light/dark switch in the header. Stored per account, not in a cookie."""
    theme = "dark" if request.POST.get("theme") == "dark" else "light"
    StaffProfile.objects.filter(pk=request.profile.pk).update(theme=theme)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"theme": theme})
    return redirect(request.POST.get("next") or "panel:dashboard")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def _money(value):
    return int(value or 0)


def _trend(current, previous):
    """Percentage change, and which way to point the arrow."""
    if not previous:
        return {"pct": None, "direction": "flat" if not current else "up"}
    change = (current - previous) * 100.0 / previous
    return {
        "pct": abs(round(change)),
        "direction": "up" if change > 0.5 else "down" if change < -0.5 else "flat",
    }


@panel_login_required
def dashboard(request):
    today = timezone.localdate()
    month_start = today.replace(day=1)
    prev_month_end = month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)

    # Everything below reads events: an event is what the company delivers,
    # whether it was booked on the website, from an enquiry or in the panel.
    earning = Event.objects.live()

    this_month = earning.filter(event_date__gte=month_start, event_date__lte=today)
    last_month = earning.filter(event_date__gte=prev_month_start, event_date__lte=prev_month_end)

    revenue_now = _money(this_month.aggregate(total=Sum("revenue"))["total"])
    revenue_prev = _money(last_month.aggregate(total=Sum("revenue"))["total"])
    count_now = this_month.count()
    count_prev = last_month.count()
    aov_now = round(revenue_now / count_now) if count_now else 0
    aov_prev = round(revenue_prev / count_prev) if count_prev else 0

    open_events = Event.objects.open()
    overdue = list(
        open_events.filter(event_date__lt=today).select_related("customer").order_by("event_date")
    )

    kpis = [
        {
            "label": "Revenue this month", "value": f"₹{revenue_now:,}", "icon": "trending-up",
            "trend": _trend(revenue_now, revenue_prev),
            "foot": f"₹{revenue_prev:,} in the same stretch last month", "tone": "green",
        },
        {
            "label": "Events this month", "value": count_now, "icon": "calendar",
            "trend": _trend(count_now, count_prev),
            "foot": f"{count_prev} last month", "tone": "blue",
        },
        {
            "label": "Average event", "value": f"₹{aov_now:,}", "icon": "tag",
            "trend": _trend(aov_now, aov_prev),
            "foot": "Value per event, cancellations excluded", "tone": "violet",
        },
        {
            "label": "Open events", "value": open_events.count(), "icon": "activity",
            "trend": {"pct": None, "direction": "flat"},
            "foot": f"{len(overdue)} past their date" if overdue else "Nothing overdue",
            "tone": "red" if overdue else "grey",
        },
    ]

    # Fourteen days of events taken, as bar heights the template can render directly.
    since = today - timedelta(days=13)
    per_day = {
        row["day"]: row["n"]
        for row in Event.objects.filter(created_at__date__gte=since)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(n=Count("id"))
    }
    peak = max(per_day.values(), default=0) or 1
    chart = []
    for offset in range(14):
        day = since + timedelta(days=offset)
        value = per_day.get(day, 0)
        chart.append({
            "day": day,
            "label": day.strftime("%d %b"),
            "value": value,
            "height": max(round(value * 100 / peak), 4 if value else 2),
            "is_today": day == today,
        })

    per_status = dict(
        Event.objects.order_by().values_list("status").annotate(n=Count("id"))
    )
    status_total = sum(per_status.values()) or 1
    # Every status, in workflow order, so the bars read like the event page.
    statuses = [
        {
            "key": value,
            "label": label,
            "count": per_status.get(value, 0),
            "pct": round(per_status.get(value, 0) * 100 / status_total),
            "tone": Event.STATUS_TONES[value],
        }
        for value, label in Event.STATUS_CHOICES
        if per_status.get(value)
    ]

    live = ~Q(events__status="cancelled")
    top_occasions = (
        Category.objects.annotate(
            jobs=Count("events", filter=live),
            earned=Sum("events__revenue", filter=live),
        )
        .filter(jobs__gt=0)
        .order_by("-earned", "-jobs")[:5]
    )

    upcoming = (
        Event.objects.upcoming()
        .select_related("customer", "occasion", "package")
        .prefetch_related("crew")
        .order_by("event_date", "time_slot")[:8]
    )

    return render(request, "panel/pages/dashboard.html", panel_context(
        request,
        title="Dashboard",
        kpis=kpis,
        chart=chart,
        chart_total=sum(row["value"] for row in chart),
        statuses=statuses,
        top_occasions=top_occasions,
        upcoming=upcoming,
        overdue=overdue[:5],
        recent_enquiries=Enquiry.objects.filter(status="new")[:5],
        alerts=_alerts(),
        activity=ActivityLog.objects.select_related("user")[:8],
    ))


def _alerts():
    """
    The panel checking its own content. Each entry is something a human would
    otherwise only find by looking at the live site.
    """
    rows = []
    live_slides = [s for s in HeroSlide.objects.filter(is_active=True) if s.is_live]
    if not live_slides:
        rows.append({
            "tone": "red", "icon": "alert",
            "text": "No hero slide is live right now — the homepage opens on an empty deck.",
            "url": reverse("panel:resource_list", args=["hero-slides"]), "cta": "Fix the slider",
        })
    elif len(live_slides) == 1:
        rows.append({
            "tone": "amber", "icon": "slides",
            "text": "Only one hero slide is live, so the slider has nothing to rotate through.",
            "url": reverse("panel:resource_list", args=["hero-slides"]), "cta": "Add a slide",
        })

    stale = Package.objects.live().filter(image_file="", image_url="").count()
    if stale:
        rows.append({
            "tone": "amber", "icon": "image",
            "text": f"{stale} live product{'s' if stale > 1 else ''} still using a placeholder photo.",
            "url": reverse("panel:resource_list", args=["packages"]), "cta": "Review products",
        })

    fresh = Event.objects.filter(is_new=True).count()
    if fresh:
        rows.append({
            "tone": "blue", "icon": "sparkles",
            "text": f"{fresh} event{'s' if fresh > 1 else ''} from the website nobody has opened yet.",
            "url": f"{reverse('panel:events')}?new=1", "cta": "See them",
        })

    unanswered = Enquiry.objects.filter(status="new").count()
    if unanswered:
        rows.append({
            "tone": "blue", "icon": "message",
            "text": f"{unanswered} enquir{'ies' if unanswered > 1 else 'y'} nobody has opened yet.",
            "url": reverse("panel:resource_list", args=["enquiries"]), "cta": "Read them",
        })

    empty = Category.objects.filter(is_active=True).annotate(n=Count("packages")).filter(n=0)
    if empty.exists():
        names = ", ".join(c.name for c in empty[:3])
        rows.append({
            "tone": "amber", "icon": "layers",
            "text": f"Occasion pages with nothing to show: {names}.",
            "url": reverse("panel:resource_list", args=["packages"]), "cta": "Add a product",
        })

    short = InventoryItem.objects.needs_attention().count()
    if short:
        empty_count = InventoryItem.objects.active().out_of_stock().count()
        tail = f", {empty_count} of them empty." if empty_count else "."
        rows.append({
            "tone": "red" if empty_count else "amber", "icon": "package",
            "text": (
                f"{short} stock item{'s' if short > 1 else ''} at or below "
                f"the reorder level{tail}"
            ),
            "url": reverse("panel:stock"), "cta": "Open the stock room",
        })

    if SiteSettings.objects.current().maintenance_mode:
        rows.append({
            "tone": "red", "icon": "alert",
            "text": "Maintenance mode is on — the public site is showing the holding notice.",
            "url": reverse("panel:settings"), "cta": "Turn it off",
        })
    return rows


# ---------------------------------------------------------------------------
# Generic CRUD
# ---------------------------------------------------------------------------


def _resource_or_404(slug):
    resource = resources.get(slug)
    if resource is None:
        raise Http404("No such section.")
    return resource


def _guard(request, resource):
    """Returns None when the caller may write, otherwise a redirect."""
    profile = request.profile
    if not profile.at_least(resource.permission):
        messages.error(
            request,
            f"Changing {resource.plural.lower()} needs the "
            f"{resource.permission} role — yours is {profile.role}.",
        )
        return redirect("panel:resource_list", slug=resource.slug)
    return None


def _apply_query(request, resource, queryset):
    """Search, filters and sorting, shared by the list page and CSV export."""
    term = request.GET.get("q", "").strip()
    queryset = resource.search(queryset, term)

    dynamic = resources.dynamic_filter_choices()
    filters = []
    for spec in resource.filters:
        choices = spec.choices or dynamic.get(spec.param, [])
        value = request.GET.get(spec.param, "")
        if value:
            queryset = spec.apply(queryset, value)
        filters.append({
            "param": spec.param,
            "label": spec.label,
            "choices": choices,
            "value": value,
            "active_label": dict(choices).get(value, ""),
        })

    sortable = {c.sortable for c in resource.columns if c.sortable}
    sort = request.GET.get("sort", "")
    if sort.lstrip("-") in sortable:
        queryset = queryset.order_by(sort)
    else:
        sort = ""

    return queryset, term, filters, sort


@panel_login_required
def resource_list(request, slug):
    resource = _resource_or_404(slug)

    if request.method == "POST":
        return _bulk_action(request, resource)

    queryset, term, filters, sort = _apply_query(request, resource, resource.queryset())

    paginator = Paginator(queryset, PAGE_SIZE)
    try:
        page_obj = paginator.page(request.GET.get("page", 1))
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    params = request.GET.copy()
    params.pop("page", None)

    toggles = [c for c in resource.columns if c.kind == "toggle"]
    bulk_actions = []
    for column in toggles:
        bulk_actions.append({"value": f"on:{column.name}", "label": f"Turn on {column.label.lower()}"})
        bulk_actions.append({"value": f"off:{column.name}", "label": f"Turn off {column.label.lower()}"})
    if resource.can_delete:
        bulk_actions.append({"value": "delete", "label": f"Delete selected {resource.plural.lower()}"})

    return render(request, "panel/resources/list.html", panel_context(
        request,
        title=resource.plural,
        resource=resource,
        rows=page_obj.object_list,
        page_obj=page_obj,
        paginator=paginator,
        querystring=params.urlencode(),
        q=term,
        filters=filters,
        sort=sort,
        bulk_actions=bulk_actions,
        total=paginator.count,
        is_filtered=bool(term or any(row["value"] for row in filters)),
    ))


@require_POST
def _bulk_action(request, resource):
    redirect_to = f"{reverse('panel:resource_list', args=[resource.slug])}?{request.POST.get('querystring', '')}"
    denied = _guard(request, resource)
    if denied:
        return denied

    action = request.POST.get("action", "")
    ids = request.POST.getlist("ids")
    if not action or not ids:
        messages.warning(request, "Pick some rows and an action first.")
        return redirect(redirect_to)

    queryset = resource.model.objects.filter(pk__in=ids)
    count = queryset.count()

    if action == "delete":
        if not resource.can_delete:
            messages.error(request, f"{resource.plural} cannot be deleted here.")
            return redirect(redirect_to)
        try:
            queryset.delete()
        except ProtectedError:
            messages.error(
                request,
                "At least one of those still has records pointing at it, so "
                "nothing was deleted. Open them one at a time to see what.",
            )
            return redirect(redirect_to)
        log(request, "bulk", model_label=resource.plural, detail=f"deleted {count}")
        messages.success(request, f"Deleted {count} {resource.label.lower()}{'s' if count != 1 else ''}.")
        return redirect(redirect_to)

    if ":" in action:
        state, field_name = action.split(":", 1)
        valid = {c.name for c in resource.columns if c.kind == "toggle"}
        if field_name in valid:
            queryset.update(**{field_name: state == "on"})
            log(request, "bulk", model_label=resource.plural,
                detail=f"{field_name} → {state} on {count}")
            messages.success(request, f"Updated {count} row{'s' if count != 1 else ''}.")
            return redirect(redirect_to)

    messages.error(request, "That action is not available here.")
    return redirect(redirect_to)


@panel_login_required
def resource_form(request, slug, pk=None):
    resource = _resource_or_404(slug)

    # Viewers may open a record and read it; only saving is gated. Blocking the
    # page outright would leave them unable to see anything but list rows.
    writable = request.profile.at_least(resource.permission)
    frozen = bool(pk) and not resource.can_edit
    if frozen:
        # An append-only table: the row is history, and history is read.
        writable = False
    if request.method == "POST" and frozen:
        # `_guard` answers "may this person write?", which is the wrong
        # question here — nobody may, whatever role they hold.
        messages.error(
            request,
            f"{resource.plural} are never edited. Record another movement to "
            "correct this one.",
        )
        return redirect("panel:resource_list", slug=slug)
    if request.method == "POST" and not writable:
        return _guard(request, resource)

    if pk:
        instance = get_object_or_404(resource.model, pk=pk)
    else:
        if not resource.can_create or not writable:
            messages.error(
                request,
                (
                    resource.no_create_hint
                    or f"{resource.plural} arrive from the website, not from here."
                )
                if not resource.can_create
                else f"Creating {resource.plural.lower()} needs the {resource.permission} role.",
            )
            return redirect("panel:resource_list", slug=slug)
        instance = resource.model()

    # A new record can be seeded from the link that opened it, so "record a
    # movement" from a stock item arrives with that item already chosen.
    initial = {}
    if not pk:
        for name in resource.form_class.base_fields:
            if name in request.GET:
                initial[name] = request.GET[name]

    form = resource.form_class(
        request.POST or None, request.FILES or None, instance=instance, initial=initial
    )

    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        if resource.slug == "stock-ledger" and not pk:
            obj.created_by = request.user
        obj.save()
        form.save_m2m()
        log(request, "update" if pk else "create", obj=obj, model_label=resource.label)
        messages.success(
            request,
            f"{resource.label} “{obj}” {'updated' if pk else 'created'}.",
        )
        if "save_and_add" in request.POST:
            return redirect("panel:resource_create", slug=slug)
        if "save_and_stay" in request.POST:
            return redirect("panel:resource_edit", slug=slug, pk=obj.pk)
        return redirect("panel:resource_list", slug=slug)

    if request.method == "POST":
        messages.error(request, "Some fields need another look.")

    preview = ""
    if pk and resource.preview_url:
        getter = getattr(instance, resource.preview_url, None)
        if callable(getter):
            preview = getter()

    return render(request, "panel/resources/form.html", panel_context(
        request,
        title=f"Edit {resource.label.lower()}" if pk else resource.create_label,
        resource=resource,
        form=form,
        instance=instance if pk else None,
        sections=list(form.sections()) if hasattr(form, "sections") else None,
        preview_url=preview,
        writable=writable,
        readonly_reason=(
            f"{resource.plural} are a record of what happened, so rows are never "
            "edited. Correct a mistake by recording another movement."
            if frozen
            else ""
        ),
        related_images=(
            instance.images.all() if pk and resource.slug == "packages" else None
        ),
        # A stock item and a receipt are both worth more than their own fields:
        # one needs its ledger beside it, the other its lines.
        stock_item=instance if pk and resource.slug == "stock-items" else None,
        stock_history=(
            instance.movements.select_related("created_by", "event")[:8]
            if pk and resource.slug == "stock-items" else None
        ),
        stock_events=(
            instance.event_lines.filter(event__status__in=Event.OPEN_STATUSES)
            .select_related("event").order_by("event__event_date")[:8]
            if pk and resource.slug == "stock-items" else None
        ),
        customer_events=(
            instance.events.with_paid().order_by("-event_date")[:12]
            if pk and resource.slug == "customers" else None
        ),
        sale=instance if pk and resource.slug == "counter-sales" else None,
        sale_lines=(
            instance.lines.select_related("item")
            if pk and resource.slug == "counter-sales" else None
        ),
    ))


@panel_login_required
def resource_delete(request, slug, pk):
    resource = _resource_or_404(slug)
    denied = _guard(request, resource)
    if denied:
        return denied
    if not resource.can_delete:
        messages.error(request, f"{resource.plural} cannot be deleted.")
        return redirect("panel:resource_list", slug=slug)

    instance = get_object_or_404(resource.model, pk=pk)
    if request.method == "POST":
        label = str(instance)
        try:
            instance.delete()
        except ProtectedError as error:
            # PROTECT relations (packages under an occasion, say) refuse to go.
            blockers = ", ".join(sorted({str(obj) for obj in list(error.protected_objects)[:5]}))
            messages.error(
                request,
                f"“{label}” still has records pointing at it ({blockers}). "
                "Move or delete those first.",
            )
            return redirect("panel:resource_delete", slug=slug, pk=pk)
        log(request, "delete", model_label=resource.label, detail=label)
        messages.success(request, f"Deleted “{label}”.")
        return redirect("panel:resource_list", slug=slug)

    return render(request, "panel/resources/delete.html", panel_context(
        request,
        title=f"Delete {resource.label.lower()}",
        resource=resource,
        instance=instance,
        related=_related_summary(instance),
    ))


def _related_summary(instance):
    """What else points at this row — shown on the delete screen."""
    rows = []
    for relation in instance._meta.related_objects:
        accessor = relation.get_accessor_name()
        manager = getattr(instance, accessor, None)
        if manager is None or not hasattr(manager, "count"):
            continue
        count = manager.count()
        if count:
            # Many-to-many relations carry no on_delete at all, and nothing
            # about them blocks a delete.
            on_delete = getattr(relation, "on_delete", None)
            rows.append({
                "label": relation.related_model._meta.verbose_name_plural.title(),
                "count": count,
                "protects": getattr(on_delete, "__name__", "") == "PROTECT",
            })
    return rows


@panel_login_required
@require_POST
def resource_toggle(request, slug, pk, field_name):
    """Inline switch in the list table. Answers JSON so the row can update in place."""
    resource = _resource_or_404(slug)
    profile = request.profile
    if not profile.at_least(resource.permission):
        return JsonResponse({"error": "Your role cannot change this."}, status=403)

    valid = {c.name for c in resource.columns if c.kind == "toggle"}
    if field_name not in valid:
        return JsonResponse({"error": "Not a switchable field."}, status=400)

    instance = get_object_or_404(resource.model, pk=pk)
    value = not getattr(instance, field_name)
    setattr(instance, field_name, value)
    instance.save(update_fields=[field_name])
    log(request, "update", obj=instance, model_label=resource.label,
        detail=f"{field_name} → {'on' if value else 'off'}")
    return JsonResponse({"value": value, "label": str(instance)})


@panel_login_required
@require_POST
def resource_reorder(request, slug):
    """Drag-and-drop ordering. Body carries the ids in their new order."""
    resource = _resource_or_404(slug)
    if not resource.orderable:
        return JsonResponse({"error": "This list has a fixed order."}, status=400)
    if not request.profile.at_least(resource.permission):
        return JsonResponse({"error": "Your role cannot reorder this."}, status=403)

    ids = [pk for pk in request.POST.get("order", "").split(",") if pk.isdigit()]
    rows = {str(obj.pk): obj for obj in resource.model.objects.filter(pk__in=ids)}
    updated = []
    for position, pk in enumerate(ids):
        obj = rows.get(pk)
        if obj is not None and obj.position != position:
            obj.position = position
            updated.append(obj)
    if updated:
        resource.model.objects.bulk_update(updated, ["position"])
        log(request, "bulk", model_label=resource.plural, detail=f"reordered {len(updated)}")
    return JsonResponse({"moved": len(updated)})


@panel_login_required
def resource_export(request, slug):
    """CSV of the current view — same search, filters and sort as the screen."""
    resource = _resource_or_404(slug)
    queryset, *_ = _apply_query(request, resource, resource.queryset())

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    stamp = timezone.localdate().isoformat()
    response["Content-Disposition"] = f'attachment; filename="{resource.slug}-{stamp}.csv"'
    response.write("﻿")  # BOM, so Excel reads the rupee sign correctly

    writer = csv.writer(response)
    headers = [c.label or c.name for c in resource.columns if c.kind != "image"]
    writer.writerow(["ID"] + headers)
    for row in queryset[:5000]:
        line = [row.pk]
        for column in resource.columns:
            if column.kind == "image":
                continue
            line.append(_cell_value(row, column.name))
        writer.writerow(line)

    log(request, "bulk", model_label=resource.plural, detail="exported CSV")
    return response


def _cell_value(row, name):
    value = getattr(row, name, "")
    if callable(value):
        value = value()
    return "" if value is None else str(value)


# ---------------------------------------------------------------------------
# Bespoke pages
# ---------------------------------------------------------------------------


@panel_login_required
def schedule(request):
    """
    Six weeks of the calendar with every event placed on its date. This is
    the view that answers "what is happening on Saturday", which a table cannot.
    """
    today = timezone.localdate()
    try:
        offset = int(request.GET.get("w", 0))
    except ValueError:
        offset = 0
    offset = max(-26, min(26, offset))

    start = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
    end = start + timedelta(days=41)

    events = list(
        Event.objects.filter(event_date__gte=start, event_date__lte=end)
        .select_related("customer", "occasion")
        .prefetch_related("crew")
        .order_by("event_date", "time_slot", "id")
    )
    by_day = OrderedDict()
    for event in events:
        by_day.setdefault(event.event_date, []).append(event)

    weeks = []
    for week_index in range(6):
        days = []
        for day_index in range(7):
            day = start + timedelta(days=week_index * 7 + day_index)
            jobs = by_day.get(day, [])
            days.append({
                "date": day,
                "jobs": jobs,
                "value": sum(j.revenue for j in jobs if j.status != "cancelled"),
                "is_today": day == today,
                "is_past": day < today,
                "is_weekend": day_index >= 5,
            })
        weeks.append(days)

    return render(request, "panel/pages/schedule.html", panel_context(
        request,
        title="Schedule",
        weeks=weeks,
        range_start=start,
        range_end=end,
        offset=offset,
        booked=len(events),
        value=sum(e.revenue for e in events if e.status != "cancelled"),
        statuses=[(value, label, Event.STATUS_TONES[value]) for value, label in Event.STATUS_CHOICES],
    ))


@panel_login_required
def decorators_redirect(request):
    """`/manage/decorators/` was this section's address until staff types arrived."""
    query = request.GET.urlencode()
    target = reverse("panel:resource_list", args=["staffs"])
    return redirect(f"{target}?{query}" if query else target)


@panel_login_required
@require_role("admin")
def site_settings(request):
    instance = SiteSettings.objects.current()
    form = f.SiteSettingsForm(request.POST or None, request.FILES or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        form.save()
        log(request, "update", model_label="Site settings", detail="saved")
        messages.success(request, "Settings saved. The public site picks them up immediately.")
        return redirect("panel:settings")
    return render(request, "panel/pages/settings.html", panel_context(
        request, title="Site settings", form=form, sections=list(form.sections()),
    ))


@panel_login_required
@require_role("owner")
def staff_list(request):
    """
    Two halves of the same question. The left is who can sign in — accounts,
    the three ways to make one, and what each role may touch. The right ties
    those logins back to the Staffs page, because most of the people in this
    company are a staff record first and a login second, if ever.
    """
    profiles = StaffProfile.objects.select_related("user").order_by("-user__is_active", "role")
    invites = InviteCode.objects.select_related("used_by", "created_by", "staff_member")[:20]
    invite_form = f.InviteCodeForm()
    account_form = f.AccountCreateForm(initial={"staff_member": request.GET.get("staff") or None})

    if request.method == "POST":
        which = request.POST.get("form")
        if which == "invite":
            invite_form = f.InviteCodeForm(request.POST)
            if invite_form.is_valid():
                invite = invite_form.save(commit=False)
                invite.code = _new_invite_code()
                invite.created_by = request.user
                invite.save()
                log(request, "create", obj=invite, model_label="Invite code")
                messages.success(request, f"Invite {invite.code} created — share it with them.")
                return redirect("panel:staff")
        elif which == "account":
            account_form = f.AccountCreateForm(request.POST)
            if account_form.is_valid():
                user = account_form.save()
                log(request, "create", obj=user, model_label="Panel account",
                    detail=f"role {account_form.cleaned_data['role']}")
                messages.success(
                    request,
                    f"{user.get_full_name() or user.username} can sign in now as "
                    f"{account_form.cleaned_data['role']}. Give them the password you set.",
                )
                return redirect("panel:staff")
            messages.error(request, "The new account needs another look.")

    # Staff records and their logins, which is the join between the two pages.
    staff = StaffMember.objects.select_related("category", "account").order_by("name")
    types = (
        StaffCategory.objects.annotate(
            member_count=Count("members"),
            active_count=Count("members", filter=Q(members__is_active=True)),
        )
        .order_by("position", "id")
    )

    return render(request, "panel/pages/staff.html", panel_context(
        request,
        title="Staff & access",
        profiles=profiles,
        invites=invites,
        invite_form=invite_form,
        account_form=account_form,
        signup_url=request.build_absolute_uri(reverse("panel:signup")),
        types=types,
        staff_total=staff.count(),
        without_login=[member for member in staff if member.account_id is None][:12],
        without_login_total=sum(1 for member in staff if member.account_id is None),
    ))


def _new_invite_code():
    from secrets import choice

    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no look-alike characters
    while True:
        code = "".join(choice(alphabet) for _ in range(8))
        if not InviteCode.objects.filter(code=code).exists():
            return code


@panel_login_required
@require_role("owner")
def staff_edit(request, pk):
    profile = get_object_or_404(StaffProfile.objects.select_related("user"), pk=pk)
    is_self = profile.user_id == request.user.id
    form = f.StaffAccessForm(request.POST or None, instance=profile)

    if request.method == "POST" and form.is_valid():
        if is_self and form.cleaned_data["role"] != "owner":
            messages.error(request, "Demoting yourself would lock you out of this page.")
        elif is_self and not form.cleaned_data["is_active"]:
            messages.error(request, "You cannot disable your own account.")
        else:
            form.save()
            log(request, "update", obj=profile, model_label="Staff member")
            messages.success(request, f"{profile.display_name}'s access updated.")
            return redirect("panel:staff")

    return render(request, "panel/pages/staff_edit.html", panel_context(
        request,
        title=profile.display_name,
        form=form,
        member=profile,
        is_self=is_self,
        staff_record=profile.staff_member,
        activity=ActivityLog.objects.filter(user=profile.user)[:15],
    ))


@panel_login_required
@require_role("owner")
@require_POST
def invite_delete(request, pk):
    invite = get_object_or_404(InviteCode, pk=pk)
    code = invite.code
    invite.delete()
    log(request, "delete", model_label="Invite code", detail=code)
    messages.success(request, f"Invite {code} revoked.")
    return redirect("panel:staff")


@panel_login_required
def activity(request):
    rows = ActivityLog.objects.select_related("user")
    who = request.GET.get("user", "")
    what = request.GET.get("action", "")
    if who:
        rows = rows.filter(user_id=who)
    if what:
        rows = rows.filter(action=what)

    paginator = Paginator(rows, 40)
    try:
        page_obj = paginator.page(request.GET.get("page", 1))
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.page(1)

    return render(request, "panel/pages/activity.html", panel_context(
        request,
        title="Activity",
        page_obj=page_obj,
        rows=page_obj.object_list,
        people=StaffProfile.objects.select_related("user"),
        actions=ActivityLog.ACTION_CHOICES,
        selected_user=who,
        selected_action=what,
    ))


@panel_login_required
def media_library(request):
    """
    Everything uploaded through the panel, newest first, with what uses it.
    Uploads happen on the record that needs them; this is the audit view.
    """
    items = []
    for package in Package.objects.exclude(image_file="").only("id", "title", "image_file"):
        items.append({"url": package.image_file.url, "name": package.image_file.name,
                      "used_by": package.title, "kind": "Product",
                      "url_to": reverse("panel:resource_edit", args=["packages", package.pk])})
    for image in PackageImage.objects.exclude(image_file="").select_related("package"):
        items.append({"url": image.image_file.url, "name": image.image_file.name,
                      "used_by": str(image.package), "kind": "Gallery",
                      "url_to": reverse("panel:resource_edit", args=["gallery", image.pk])})
    for slide in HeroSlide.objects.exclude(image_file=""):
        items.append({"url": slide.image_file.url, "name": slide.image_file.name,
                      "used_by": slide.eyebrow, "kind": "Hero image",
                      "url_to": reverse("panel:resource_edit", args=["hero-slides", slide.pk])})
    for slide in HeroSlide.objects.exclude(video_file=""):
        items.append({"url": slide.video_file.url, "name": slide.video_file.name,
                      "used_by": slide.eyebrow, "kind": "Hero video", "is_video": True,
                      "url_to": reverse("panel:resource_edit", args=["hero-slides", slide.pk])})
    for category in Category.objects.exclude(image_file=""):
        items.append({"url": category.image_file.url, "name": category.image_file.name,
                      "used_by": category.name, "kind": "Occasion",
                      "url_to": reverse("panel:resource_edit", args=["categories", category.pk])})
    for stock_item in InventoryItem.objects.exclude(image_file="").only("id", "name", "image_file"):
        items.append({"url": stock_item.image_file.url, "name": stock_item.image_file.name,
                      "used_by": stock_item.name, "kind": "Stock item",
                      "url_to": reverse("panel:resource_edit", args=["stock-items", stock_item.pk])})
    for line in EventItem.objects.exclude(image_file="").select_related("event").only(
        "id", "name", "image_file", "event__id", "event__number"
    ):
        items.append({"url": line.image_file.url, "name": line.image_file.name,
                      "used_by": f"{line.name} · {line.event.number}", "kind": "Event item",
                      "url_to": reverse("panel:event_line_edit", args=[line.event_id, line.pk])})

    return render(request, "panel/pages/media.html", panel_context(
        request, title="Media", items=items,
    ))


@panel_login_required
def quick_search(request):
    """Backs the Ctrl-K palette. Searches the few models worth jumping to."""
    term = request.GET.get("q", "").strip()
    results = []

    if len(term) >= 2:
        for package in Package.objects.filter(
            Q(title__icontains=term) | Q(slug__icontains=term)
        ).select_related("category")[:5]:
            results.append({
                "group": "Products", "label": package.title,
                "meta": f"₹{package.price:,} · {package.category.name}",
                "url": reverse("panel:resource_edit", args=["packages", package.pk]),
            })
        for slide in HeroSlide.objects.filter(
            Q(eyebrow__icontains=term) | Q(heading__icontains=term)
        )[:4]:
            results.append({
                "group": "Hero slides", "label": slide.heading_line,
                "meta": slide.eyebrow,
                "url": reverse("panel:resource_edit", args=["hero-slides", slide.pk]),
            })
        for member in StaffMember.objects.filter(
            Q(name__icontains=term) | Q(phone__icontains=term) | Q(skills__icontains=term)
        ).select_related("category")[:5]:
            results.append({
                "group": "Staffs", "label": member.name,
                "meta": member.type_name or "No type yet",
                "url": reverse("panel:resource_edit", args=["staffs", member.pk]),
            })
        for item in InventoryItem.objects.filter(
            Q(name__icontains=term) | Q(sku__icontains=term) | Q(barcode__icontains=term)
        ).select_related("category")[:5]:
            results.append({
                "group": "Stock items", "label": item.name,
                "meta": f"{item.sku} · {item.quantity_label} on hand",
                "url": reverse("panel:resource_edit", args=["stock-items", item.pk]),
            })
        for event in Event.objects.filter(
            Q(number__icontains=term) | Q(name__icontains=term)
            | Q(customer__name__icontains=term) | Q(customer__phone__icontains=term)
            | Q(location__icontains=term)
        ).select_related("customer")[:6]:
            results.append({
                "group": "Events", "label": f"{event.number} · {event.name}",
                "meta": f"{event.event_date:%d %b} · {event.get_status_display()}",
                "url": reverse("panel:event_detail", args=[event.pk]),
            })
        for customer in Customer.objects.filter(
            Q(name__icontains=term) | Q(phone__icontains=term) | Q(email__icontains=term)
        )[:4]:
            results.append({
                "group": "Customers", "label": customer.name,
                "meta": customer.contact_line,
                "url": reverse("panel:resource_edit", args=["customers", customer.pk]),
            })
        for sale in CounterSale.objects.filter(
            Q(reference__icontains=term) | Q(customer_name__icontains=term)
            | Q(phone__icontains=term)
        )[:4]:
            results.append({
                "group": "Counter sales", "label": f"{sale.reference} · {sale.customer_label}",
                "meta": f"{sale.sold_label} · ₹{sale.total:,}",
                "url": reverse("panel:counter_sale", args=[sale.pk]),
            })
        for enquiry in Enquiry.objects.filter(
            Q(name__icontains=term) | Q(message__icontains=term)
        )[:4]:
            results.append({
                "group": "Enquiries", "label": enquiry.name,
                "meta": enquiry.occasion or "General",
                "url": reverse("panel:resource_edit", args=["enquiries", enquiry.pk]),
            })

    # Sections always match on their own name, so the palette doubles as nav.
    needle = slugify(term)
    if not term or needle in "events":
        results.append({
            "group": "Go to", "label": "Events", "meta": "Events",
            "url": reverse("panel:events"),
        })
    for resource in resources.RESOURCES:
        if not term or needle in slugify(resource.plural) or needle in resource.slug:
            results.append({
                "group": "Go to", "label": resource.plural, "meta": resource.group,
                "url": reverse("panel:resource_list", args=[resource.slug]),
            })

    return JsonResponse({"results": results[:18]})


@panel_login_required
def stats_json(request):
    """Small JSON feed the dashboard polls to keep its counters honest."""
    today = timezone.localdate()
    return JsonResponse({
        "new_events": Event.objects.filter(is_new=True).count(),
        "new_enquiries": Enquiry.objects.filter(status="new").count(),
        "open_events": Event.objects.open().count(),
        "revenue_today": _money(
            Event.objects.live()
            .filter(event_date=today)
            .aggregate(total=Sum("revenue"))["total"]
        ),
        "counter_today": _money(
            CounterSale.objects.earning().on(today).aggregate(total=Sum("total"))["total"]
        ),
        "low_stock": InventoryItem.objects.needs_attention().count(),
    })


# ---------------------------------------------------------------------------
# Inventory — the counter and the stock room
# ---------------------------------------------------------------------------

#: The basket lives in the session, so a half-rung sale survives a reload, a
#: lookup on another screen and the customer changing their mind twice.
CART_KEY = "counter_cart"


def _cart(request):
    return request.session.get(CART_KEY) or {}


def _save_cart(request, cart):
    request.session[CART_KEY] = cart
    request.session.modified = True


def _cart_lines(cart):
    """
    Resolve the session basket into rows the template can render.

    Anything that has since been deleted or retired quietly drops out — a stale
    session should never be able to break the till.
    """
    keys = [key for key in cart if key.isdigit()]
    items = {
        str(item.pk): item
        for item in InventoryItem.objects.filter(pk__in=keys)
        .with_reserved().select_related("category")
    }
    lines, subtotal, units = [], 0, Decimal("0")
    for key in list(cart):
        item = items.get(key)
        if item is None:
            continue
        row = cart[key]
        quantity = Decimal(str(row.get("qty", 1)))
        price = int(row.get("price", item.sale_price))
        total = int(round(quantity * price))
        lines.append({
            "item": item,
            "quantity": quantity,
            "quantity_label": normalise_quantity(quantity),
            "price": price,
            "total": total,
            "cost": int(round(quantity * item.cost_price)),
            # Units held for events are on the shelf but not for sale.
            "short": quantity > item.available_quantity,
            "available": item.available_label,
        })
        subtotal += total
        units += quantity
    return lines, subtotal, units


def _cart_add(cart, item, quantity):
    key = str(item.pk)
    row = cart.get(key)
    if row:
        row["qty"] = str(Decimal(str(row["qty"])) + quantity)
    else:
        cart[key] = {"qty": str(quantity), "price": item.sale_price}
    return cart


def _quantity(raw, fallback=Decimal("1")):
    """Counter input is typed in a hurry; anything unreadable is just a 1."""
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, AttributeError, TypeError):
        return fallback
    if value <= 0:
        return Decimal("0")
    return value.quantize(Decimal("0.01"))


@panel_login_required
@require_role("editor")
def counter(request):
    """
    The till. Search or scan on the left, basket on the right, one button to
    close the sale — which is also the only thing in the panel that moves stock
    and takes money in the same breath.
    """
    cart = _cart(request)

    if request.method == "POST":
        return _counter_action(request, cart)

    lines, subtotal, units = _cart_lines(cart)
    if len(lines) != len(cart):
        # Something in the basket has since been deleted or retired. It has
        # already been dropped from the view; drop it from the session too,
        # rather than leave a key nothing can ever resolve.
        keep = {str(line["item"].pk) for line in lines}
        _save_cart(request, {k: v for k, v in cart.items() if k in keep})

    term = request.GET.get("q", "").strip()
    group = request.GET.get("group", "")

    catalogue = InventoryItem.objects.sellable().with_reserved().select_related("category")
    if term:
        catalogue = catalogue.filter(
            Q(name__icontains=term) | Q(sku__icontains=term)
            | Q(barcode__icontains=term) | Q(category__name__icontains=term)
        )
    if group:
        catalogue = catalogue.filter(category__slug=group)
    if request.GET.get("stocked") == "1":
        catalogue = catalogue.filter(quantity__gt=0)

    matches = list(catalogue.order_by("name")[:48])
    today = timezone.localdate()
    takings = CounterSale.objects.earning().on(today).aggregate(
        total=Sum("total"), n=Count("id")
    )

    return render(request, "panel/pages/counter.html", panel_context(
        request,
        title="Counter",
        items=matches,
        item_total=catalogue.count(),
        groups_list=StockCategory.objects.filter(is_active=True).order_by("position", "id"),
        q=term,
        group=group,
        stocked=request.GET.get("stocked") == "1",
        lines=lines,
        subtotal=subtotal,
        units=normalise_quantity(units),
        form=f.CounterCheckoutForm(subtotal=subtotal),
        today_total=_money(takings["total"]),
        today_count=takings["n"] or 0,
        recent=CounterSale.objects.select_related("served_by").order_by("-sold_at")[:6],
    ))


@require_POST
def _counter_action(request, cart):
    """Every button on the counter screen posts here and then redirects back."""
    action = request.POST.get("action", "")
    back = f"{reverse('panel:counter')}?{request.POST.get('querystring', '')}"

    if action == "clear":
        _save_cart(request, {})
        messages.success(request, "Basket cleared.")
        return redirect(back)

    if action == "add":
        item = get_object_or_404(InventoryItem, pk=request.POST.get("item"))
        quantity = _quantity(request.POST.get("qty", "1"))
        if quantity <= 0:
            messages.warning(request, "Nothing added — the quantity has to be more than zero.")
            return redirect(back)
        _save_cart(request, _cart_add(cart, item, quantity))
        return redirect(back)

    if action == "scan":
        code = request.POST.get("code", "").strip()
        if not code:
            return redirect(back)
        found = list(
            InventoryItem.objects.sellable().filter(
                Q(sku__iexact=code) | Q(barcode__iexact=code) | Q(name__iexact=code)
            )[:2]
        )
        if len(found) == 1:
            _save_cart(request, _cart_add(cart, found[0], Decimal("1")))
            messages.success(request, f"Added {found[0].name}.")
            return redirect(back)
        messages.warning(
            request,
            f"No single item matches “{code}”." if not found
            else f"“{code}” matches more than one item — pick it from the list.",
        )
        return redirect(f"{reverse('panel:counter')}?q={code}")

    if action == "set":
        key = request.POST.get("item", "")
        quantity = _quantity(request.POST.get("qty", "1"), fallback=Decimal("0"))
        if key in cart:
            if quantity <= 0:
                cart.pop(key)
            else:
                cart[key]["qty"] = str(quantity)
                price = (request.POST.get("price") or "").strip()
                if price.isdigit():
                    cart[key]["price"] = min(int(price), 10_000_000)
            _save_cart(request, cart)
        return redirect(back)

    if action == "remove":
        cart.pop(request.POST.get("item", ""), None)
        _save_cart(request, cart)
        return redirect(back)

    if action == "checkout":
        return _counter_checkout(request, cart, back)

    messages.error(request, "That is not something the counter can do.")
    return redirect(back)


def _counter_checkout(request, cart, back):
    lines, subtotal, _units = _cart_lines(cart)
    if not lines:
        # Also the second half of a double submit: the first one emptied it.
        messages.warning(request, "The basket is empty.")
        return redirect(back)

    form = f.CounterCheckoutForm(request.POST, subtotal=subtotal)
    if not form.is_valid():
        first = next(iter(form.errors.values()))[0]
        messages.error(request, first)
        return redirect(back)

    def refuse(short):
        names = ", ".join(line["item"].name for line in short[:3])
        messages.error(
            request,
            f"Not enough free stock for {names}. Receive more on the stock ledger, "
            "or drop the quantity.",
        )
        return redirect(back)

    short = [line for line in lines if line["short"]]
    if short:
        return refuse(short)

    data = form.cleaned_data
    with transaction.atomic():
        # Check again under a lock on the items: between loading the basket and
        # getting here, another sale or an event may have taken the last units.
        ids = sorted(line["item"].pk for line in lines)
        locked = {
            item.pk: item
            for item in InventoryItem.objects.select_for_update().filter(pk__in=ids).order_by("pk")
        }
        held = EventItem.reserved_totals(ids, lock=True)
        short = [
            line for line in lines
            if line["item"].pk not in locked
            or line["quantity"] > locked[line["item"].pk].quantity - held.get(line["item"].pk, 0)
        ]
        if short:
            transaction.set_rollback(True)
            return refuse(short)

        sale = CounterSale.objects.create(
            customer_name=data["customer_name"],
            phone=data["phone"],
            served_by=data["served_by"],
            cashier=request.user,
            payment_method=data["payment_method"],
            discount=data["discount"],
            tax_percent=data["tax_percent"],
            amount_tendered=data["amount_tendered"],
            notes=data["notes"],
        )
        CounterSaleLine.objects.bulk_create([
            CounterSaleLine(
                sale=sale,
                item=line["item"],
                name=line["item"].name,
                sku=line["item"].sku,
                quantity=line["quantity"],
                unit_price=line["price"],
                unit_cost=line["item"].cost_price,
            )
            for line in lines
        ])
        sale.recalculate()
        sale.apply_stock(user=request.user)

    _save_cart(request, {})
    log(request, "create", obj=sale, model_label="Counter sale",
        detail=f"{len(lines)} lines, ₹{sale.total:,}")
    messages.success(request, f"{sale.reference} rung up — ₹{sale.total:,}.")
    return redirect("panel:counter_sale", pk=sale.pk)


@panel_login_required
def counter_sale(request, pk):
    """The receipt. Printable as it stands, and where a sale gets refunded."""
    sale = get_object_or_404(
        CounterSale.objects.select_related("served_by", "cashier"), pk=pk
    )
    return render(request, "panel/pages/counter_sale.html", panel_context(
        request,
        title=sale.reference,
        sale=sale,
        lines=sale.lines.select_related("item"),
        movements=sale.movements.select_related("item").order_by("created_at"),
    ))


@panel_login_required
@require_role("editor")
@require_POST
def counter_refund(request, pk):
    sale = get_object_or_404(CounterSale, pk=pk)
    if sale.is_refunded:
        messages.warning(request, f"{sale.reference} was already refunded.")
        return redirect("panel:counter_sale", pk=pk)

    returned = sale.refund(user=request.user, note=request.POST.get("note", ""))
    log(request, "update", obj=sale, model_label="Counter sale",
        detail=f"refunded, {returned} lines back on the shelf")
    messages.success(
        request,
        f"{sale.reference} refunded and {returned} line{'s' if returned != 1 else ''} "
        "put back into stock.",
    )
    return redirect("panel:counter_sale", pk=pk)


def _stock_totals(queryset):
    """Cost and retail value of a set of items, added up in the database."""
    money = DecimalField(max_digits=16, decimal_places=2)
    return queryset.aggregate(
        cost=Sum(ExpressionWrapper(F("quantity") * F("cost_price"), output_field=money)),
        retail=Sum(ExpressionWrapper(F("quantity") * F("sale_price"), output_field=money)),
        units=Sum("quantity"),
    )


@panel_login_required
def stock_room(request):
    """
    The inventory answer to the dashboard: what the shelves are worth, what is
    about to run out, and what the counter has been selling.
    """
    today = timezone.localdate()
    month_start = today.replace(day=1)
    prev_month_end = month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)

    items = InventoryItem.objects.active()
    totals = _stock_totals(items)
    stock_value = _money(totals["cost"])
    retail_value = _money(totals["retail"])

    low = list(
        InventoryItem.objects.needs_attention()
        .select_related("category", "supplier")
        .order_by("quantity", "name")[:12]
    )
    low_total = InventoryItem.objects.needs_attention().count()
    out_total = InventoryItem.objects.active().out_of_stock().count()

    sales = CounterSale.objects.earning()
    this_month = sales.filter(sold_at__date__gte=month_start, sold_at__date__lte=today)
    last_month = sales.filter(
        sold_at__date__gte=prev_month_start, sold_at__date__lte=prev_month_end
    )
    taken_now = _money(this_month.aggregate(total=Sum("total"))["total"])
    taken_prev = _money(last_month.aggregate(total=Sum("total"))["total"])
    today_total = _money(sales.on(today).aggregate(total=Sum("total"))["total"])

    kpis = [
        {
            "label": "Stock on hand", "value": f"₹{stock_value:,}", "icon": "package",
            "trend": {"pct": None, "direction": "flat"},
            "foot": f"{items.count()} items · worth ₹{retail_value:,} at retail",
            "tone": "blue",
        },
        {
            "label": "Counter takings", "value": f"₹{taken_now:,}", "icon": "trending-up",
            "trend": _trend(taken_now, taken_prev),
            "foot": f"₹{taken_prev:,} in the same stretch last month", "tone": "green",
        },
        {
            "label": "Sold today", "value": f"₹{today_total:,}", "icon": "cart",
            "trend": {"pct": None, "direction": "flat"},
            "foot": f"{sales.on(today).count()} sale{'s' if sales.on(today).count() != 1 else ''} so far",
            "tone": "violet",
        },
        {
            "label": "Needs ordering", "value": low_total, "icon": "alert",
            "trend": {"pct": None, "direction": "flat"},
            "foot": f"{out_total} of them completely out" if out_total else "Nothing has run out",
            "tone": "red" if low_total else "grey",
        },
    ]

    # Fourteen days of counter takings, as bar heights the template renders directly.
    since = today - timedelta(days=13)
    per_day = {
        row["day"]: row["total"]
        for row in sales.filter(sold_at__date__gte=since)
        .annotate(day=TruncDate("sold_at"))
        .values("day")
        .annotate(total=Sum("total"))
    }
    peak = max(per_day.values(), default=0) or 1
    chart = []
    for offset in range(14):
        day = since + timedelta(days=offset)
        value = _money(per_day.get(day, 0))
        chart.append({
            "day": day,
            "label": day.strftime("%d %b"),
            "value": f"₹{value:,}",
            "height": max(round(value * 100 / peak), 4 if value else 2),
            "is_today": day == today,
        })

    best = (
        CounterSaleLine.objects.filter(sale__status="completed")
        .values("name", "sku", "item_id")
        .annotate(
            units=Sum("quantity"),
            earned=Sum(ExpressionWrapper(
                F("quantity") * F("unit_price"),
                output_field=DecimalField(max_digits=16, decimal_places=2),
            )),
        )
        .order_by("-earned")[:6]
    )
    for row in best:
        row["units"] = normalise_quantity(row["units"])
        row["earned"] = _money(row["earned"])

    by_group = list(
        StockCategory.objects.annotate(item_count=Count("items"))
        .filter(item_count__gt=0)
        .order_by("position", "id")
    )
    group_rows = []
    for group in by_group:
        group_totals = _stock_totals(group.items.filter(is_active=True))
        value = _money(group_totals["cost"])
        group_rows.append({
            "group": group,
            "count": group.item_count,
            "value": value,
            "pct": round(value * 100 / stock_value) if stock_value else 0,
        })
    group_rows.sort(key=lambda row: row["value"], reverse=True)

    payment_rows = (
        sales.values("payment_method").annotate(n=Count("id"), total=Sum("total")).order_by("-total")
    )
    payment_labels = dict(CounterSale.PAYMENT_CHOICES)
    payments = [
        {
            "label": payment_labels.get(row["payment_method"], row["payment_method"]),
            "count": row["n"],
            "total": _money(row["total"]),
        }
        for row in payment_rows
    ]

    return render(request, "panel/pages/stock.html", panel_context(
        request,
        title="Stock room",
        kpis=kpis,
        chart=chart,
        chart_total=f"₹{_money(sum(per_day.values())):,}",
        low=low,
        low_total=low_total,
        best=best,
        group_rows=group_rows,
        payments=payments,
        restock_cost=sum(item.restock_cost for item in low),
        movements=StockMovement.objects.select_related("item", "created_by")[:10],
        recent_sales=CounterSale.objects.select_related("served_by")[:8],
        dead=InventoryItem.objects.active().filter(sale_lines__isnull=True).order_by("-quantity")[:6],
    ))
