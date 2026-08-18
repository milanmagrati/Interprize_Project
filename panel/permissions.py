"""
Who may open the panel, and who may change things once inside.

Four roles, ranked: viewer < editor < admin < owner.

    viewer   read everything, write nothing
    editor   content and bookings
    admin    the above plus site settings, coupons, decorators
    owner    the above plus staff accounts and invite codes

Django's own `is_staff` / `is_superuser` are kept in step so the built-in
/admin/ never disagrees with what the panel shows.
"""

from functools import wraps

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from core.models import StaffProfile


def profile_for(user):
    """
    The caller's staff profile, created on demand.

    A superuser made with `createsuperuser` has no profile until the first time
    they open the panel; rather than lock them out, they are adopted as owner.
    """
    if not getattr(user, "is_authenticated", False):
        return None
    profile = StaffProfile.objects.filter(user=user).first()
    if profile is None:
        if not user.is_staff and not user.is_superuser:
            return None
        profile = StaffProfile.objects.create(
            user=user, role="owner" if user.is_superuser else "admin"
        )
    return profile


def sync_django_flags(profile):
    """Mirror the panel role onto the auth user, then save it."""
    user = profile.user
    user.is_staff = True
    user.is_superuser = profile.role == "owner"
    user.save(update_fields=["is_staff", "is_superuser"])


def panel_login_required(view):
    """Authenticated *and* carrying a staff profile, or you get the door."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            login_url = reverse("panel:login")
            return redirect(f"{login_url}?next={request.get_full_path()}")

        profile = profile_for(request.user)
        if profile is None or not request.user.is_active:
            messages.error(request, "That account has no access to the control panel.")
            return redirect("panel:login")

        # Cheap presence tracking; a minute's granularity is plenty and keeps
        # this from writing on every single request.
        now = timezone.now()
        if profile.last_seen is None or (now - profile.last_seen).total_seconds() > 60:
            StaffProfile.objects.filter(pk=profile.pk).update(last_seen=now)
            profile.last_seen = now

        request.profile = profile
        return view(request, *args, **kwargs)

    return wrapper


def require_role(role):
    """Stack under @panel_login_required."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            profile = getattr(request, "profile", None)
            if profile is None or not profile.at_least(role):
                raise PermissionDenied(
                    f"This needs the {role} role. Yours is {profile.role if profile else 'none'}."
                )
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def can_write(request):
    profile = getattr(request, "profile", None)
    return bool(profile and profile.can_write)
