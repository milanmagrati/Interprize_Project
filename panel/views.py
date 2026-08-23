"""
Control panel views.

Three kinds of thing live here:

  * account flow  — signup (invite-gated), login, logout, profile, password
  * generic CRUD  — one list / form / delete view driving every entry in
                    `resources.RESOURCES`
  * bespoke pages — dashboard, schedule board, settings, staff, activity, media

The generic views are the reason the panel covers eighteen models without
eighteen copies of the same code. Anything a model needs beyond the defaults is
expressed in its `Resource` declaration or its `ModelForm`, not here.
"""

import csv
from collections import OrderedDict
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth import get_user_model
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Count, ProtectedError, Q, Sum
from django.db.models.functions import TruncDate
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from core.models import (
    ActivityLog,
    Booking,
    Category,
    Enquiry,
    HeroSlide,
    InviteCode,
    Package,
    PackageImage,
    SiteSettings,
    StaffProfile,
)

from . import forms as f
from . import resources
from .permissions import panel_login_required, profile_for, require_role

User = get_user_model()
PAGE_SIZE = 20


# ---------------------------------------------------------------------------
# Shared context
# ---------------------------------------------------------------------------


def panel_context(request, **extra):
    """
    Everything the chrome needs: sidebar, the signed-in user, and the two
    counters that earn a dot in the sidebar (new bookings, unread enquiries).
    """
    profile = getattr(request, "profile", None)
    context = {
        "profile": profile,
        "groups": resources.grouped(profile),
        "panel_theme": getattr(profile, "theme", "light"),
        "counts": {
            "bookings": Booking.objects.filter(status="new").count(),
            "enquiries": Enquiry.objects.filter(status="new").count(),
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

    earning = Booking.objects.earning()

    this_month = earning.filter(event_date__gte=month_start, event_date__lte=today)
    last_month = earning.filter(event_date__gte=prev_month_start, event_date__lte=prev_month_end)

    revenue_now = _money(this_month.aggregate(total=Sum("amount"))["total"])
    revenue_prev = _money(last_month.aggregate(total=Sum("amount"))["total"])
    count_now = this_month.count()
    count_prev = last_month.count()
    aov_now = round(revenue_now / count_now) if count_now else 0
    aov_prev = round(revenue_prev / count_prev) if count_prev else 0

    open_bookings = Booking.objects.open()
    overdue = [b for b in open_bookings.filter(event_date__lt=today).select_related("package")]

    kpis = [
        {
            "label": "Revenue this month", "value": f"₹{revenue_now:,}", "icon": "trending-up",
            "trend": _trend(revenue_now, revenue_prev),
            "foot": f"₹{revenue_prev:,} in the same stretch last month", "tone": "green",
        },
        {
            "label": "Bookings this month", "value": count_now, "icon": "calendar",
            "trend": _trend(count_now, count_prev),
            "foot": f"{count_prev} last month", "tone": "blue",
        },
        {
            "label": "Average booking", "value": f"₹{aov_now:,}", "icon": "tag",
            "trend": _trend(aov_now, aov_prev),
            "foot": "Value per event, cancellations excluded", "tone": "violet",
        },
        {
            "label": "Open jobs", "value": open_bookings.count(), "icon": "activity",
            "trend": {"pct": None, "direction": "flat"},
            "foot": f"{len(overdue)} past their date" if overdue else "Nothing overdue",
            "tone": "red" if overdue else "grey",
        },
    ]

    # Fourteen days of bookings, as bar heights the template can render directly.
    since = today - timedelta(days=13)
    per_day = {
        row["day"]: row["n"]
        for row in Booking.objects.filter(created_at__date__gte=since)
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

    status_rows = (
        Booking.objects.values("status").annotate(n=Count("id")).order_by("-n")
    )
    status_total = sum(row["n"] for row in status_rows) or 1
    status_labels = dict(Booking.STATUS_CHOICES)
    statuses = [
        {
            "key": row["status"],
            "label": status_labels.get(row["status"], row["status"]),
            "count": row["n"],
            "pct": round(row["n"] * 100 / status_total),
            "tone": resources.STATUS_TONES.get(row["status"], "grey"),
        }
        for row in status_rows
    ]

    top_packages = (
        Package.objects.annotate(
            jobs=Count("bookings", filter=~Q(bookings__status="cancelled")),
            earned=Sum("bookings__amount", filter=~Q(bookings__status="cancelled")),
        )
        .filter(jobs__gt=0)
        .order_by("-earned")[:5]
    )

    return render(request, "panel/pages/dashboard.html", panel_context(
        request,
        title="Dashboard",
        kpis=kpis,
        chart=chart,
        chart_total=sum(row["value"] for row in chart),
        statuses=statuses,
        top_packages=top_packages,
        upcoming=Booking.objects.upcoming().select_related("package", "city", "decorator")[:8],
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
    if request.method == "POST" and not writable:
        return _guard(request, resource)

    if pk:
        instance = get_object_or_404(resource.model, pk=pk)
    else:
        if not resource.can_create or not writable:
            messages.error(
                request,
                f"{resource.plural} arrive from the website, not from here."
                if not resource.can_create
                else f"Creating {resource.plural.lower()} needs the {resource.permission} role.",
            )
            return redirect("panel:resource_list", slug=slug)
        instance = resource.model()

    form = resource.form_class(
        request.POST or None, request.FILES or None, instance=instance
    )

    if request.method == "POST" and form.is_valid():
        obj = form.save()
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
        related_images=(
            instance.images.all() if pk and resource.slug == "packages" else None
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
    Six weeks of the calendar with every booking placed on its date. This is
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

    bookings = (
        Booking.objects.filter(event_date__gte=start, event_date__lte=end)
        .select_related("package", "city", "decorator")
        .order_by("event_date", "time_slot")
    )
    by_day = OrderedDict()
    for booking in bookings:
        by_day.setdefault(booking.event_date, []).append(booking)

    weeks = []
    for week_index in range(6):
        days = []
        for day_index in range(7):
            day = start + timedelta(days=week_index * 7 + day_index)
            jobs = by_day.get(day, [])
            days.append({
                "date": day,
                "jobs": jobs,
                "value": sum(j.amount for j in jobs if j.status != "cancelled"),
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
        booked=bookings.count(),
        value=sum(b.amount for b in bookings if b.status != "cancelled"),
    ))


@panel_login_required
@require_role("admin")
def site_settings(request):
    instance = SiteSettings.objects.current()
    form = f.SiteSettingsForm(request.POST or None, instance=instance)
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
    profiles = StaffProfile.objects.select_related("user").order_by("-user__is_active", "role")
    invites = InviteCode.objects.select_related("used_by", "created_by")[:20]

    if request.method == "POST" and request.POST.get("form") == "invite":
        invite_form = f.InviteCodeForm(request.POST)
        if invite_form.is_valid():
            invite = invite_form.save(commit=False)
            invite.code = _new_invite_code()
            invite.created_by = request.user
            invite.save()
            log(request, "create", obj=invite, model_label="Invite code")
            messages.success(request, f"Invite {invite.code} created — share it with them.")
            return redirect("panel:staff")
    else:
        invite_form = f.InviteCodeForm()

    return render(request, "panel/pages/staff.html", panel_context(
        request,
        title="Staff & access",
        profiles=profiles,
        invites=invites,
        invite_form=invite_form,
        signup_url=request.build_absolute_uri(reverse("panel:signup")),
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
    form = f.StaffMemberForm(request.POST or None, instance=profile)

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
        for booking in Booking.objects.filter(
            Q(reference__icontains=term) | Q(customer_name__icontains=term) | Q(phone__icontains=term)
        ).select_related("package")[:5]:
            results.append({
                "group": "Bookings", "label": f"{booking.reference} · {booking.customer_name}",
                "meta": f"{booking.event_date:%d %b} · {booking.get_status_display()}",
                "url": reverse("panel:resource_edit", args=["bookings", booking.pk]),
            })
        for slide in HeroSlide.objects.filter(
            Q(eyebrow__icontains=term) | Q(heading__icontains=term)
        )[:4]:
            results.append({
                "group": "Hero slides", "label": slide.heading_line,
                "meta": slide.eyebrow,
                "url": reverse("panel:resource_edit", args=["hero-slides", slide.pk]),
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
    return JsonResponse({
        "new_bookings": Booking.objects.filter(status="new").count(),
        "new_enquiries": Enquiry.objects.filter(status="new").count(),
        "open_jobs": Booking.objects.open().count(),
        "revenue_today": _money(
            Booking.objects.earning()
            .filter(event_date=timezone.localdate())
            .aggregate(total=Sum("amount"))["total"]
        ),
    })
