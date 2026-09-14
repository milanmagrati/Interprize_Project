"""
Forms for the control panel.

`PanelFormMixin` styles every widget once, so the templates can render any form
with the same partial and no per-field markup. Model forms below only declare
the things that are genuinely specific: field order, widgets that need rows or
a date picker, and validation the model cannot express on its own.
"""

from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    UserCreationForm,
)
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from core.models import (
    AddOn,
    Category,
    City,
    CounterSale,
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
    InviteCode,
    NavLink,
    Package,
    PackageImage,
    PricingRow,
    SiteSettings,
    StaffCategory,
    StaffMember,
    StaffProfile,
    StockCategory,
    StockMovement,
    Supplier,
    Testimonial,
    TimeSlot,
    TrustBadge,
    normalise_quantity,
)

User = get_user_model()

# Routes a link can point at. A free-text field here would let a typo take down
# every page that renders the navbar, since {% url %} raises on a bad name.
ROUTE_CHOICES = [
    ("core:home", "Home"),
    ("core:products", "All packages"),
    ("core:categories", "All occasions"),
    ("core:category_detail", "An occasion page — needs a slug"),
    ("core:package_detail", "A package page — needs a slug"),
    ("core:book", "Book an event"),
    ("core:track", "Track a booking"),
    ("core:enquire", "Ask a question"),
    ("core:how_it_works", "How it works"),
    ("core:contact", "Contact"),
]


class PanelFormMixin:
    """Adds the panel's field classes and a few usability defaults."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "switch__input")
                continue
            if isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", "field__input field__input--select")
            elif isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("class", "field__input field__input--area")
                widget.attrs.setdefault("rows", 4)
            elif isinstance(widget, forms.ClearableFileInput):
                widget.attrs.setdefault("class", "field__file")
            else:
                widget.attrs.setdefault("class", "field__input")
            if field.required:
                widget.attrs.setdefault("required", "required")


class PanelModelForm(PanelFormMixin, forms.ModelForm):
    pass


class DateInput(forms.DateInput):
    input_type = "date"


class DateTimeInput(forms.DateTimeInput):
    input_type = "datetime-local"

    def format_value(self, value):
        # <input type="datetime-local"> refuses anything but this exact shape.
        value = super().format_value(value)
        return value[:16].replace(" ", "T") if value else value


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


class PanelLoginForm(PanelFormMixin, AuthenticationForm):
    username = forms.CharField(
        label="Username or email",
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def clean_username(self):
        """Let people sign in with the email they registered, case-insensitively."""
        value = self.cleaned_data["username"].strip()
        lookup = "email__iexact" if "@" in value else "username__iexact"
        match = User.objects.filter(**{lookup: value}).values_list("username", flat=True)
        return match[0] if match else value

    def clean_password(self):
        """Trim accidental leading/trailing whitespace from a pasted password."""
        return self.cleaned_data.get("password", "").strip()


class PanelSignupForm(PanelFormMixin, UserCreationForm):
    """
    Registration for panel access.

    The first account ever created becomes the owner — someone has to be able
    to get in. Every account after that needs an invite code, which is what
    keeps a public signup URL from being a public admin panel.
    """

    first_name = forms.CharField(label="Full name", max_length=80)
    email = forms.EmailField()
    job_title = forms.CharField(max_length=80, required=False, help_text="Optional.")
    invite_code = forms.CharField(
        max_length=32,
        required=False,
        help_text="Ask an owner for one. Not needed for the very first account.",
    )

    class Meta:
        model = User
        fields = ["first_name", "email", "username"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_bootstrap = not StaffProfile.objects.exists()
        if self.is_bootstrap:
            del self.fields["invite_code"]
        self.fields["username"].help_text = "Letters, digits and @ . + - _ only."
        self.invite = None

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account already uses that email address.")
        return email

    def clean_invite_code(self):
        code = (self.cleaned_data.get("invite_code") or "").strip().upper()
        if not code:
            raise forms.ValidationError(
                "The panel already has accounts, so a new one needs an invite code."
            )
        invite = InviteCode.objects.filter(code=code).first()
        if invite is None:
            raise forms.ValidationError("No invite matches that code.")
        if not invite.is_usable:
            raise forms.ValidationError(f"That invite has already been {invite.state}.")
        self.invite = invite
        return code

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data["first_name"]
        user.email = self.cleaned_data["email"]
        user.is_staff = True
        role = "owner" if self.is_bootstrap else self.invite.role
        user.is_superuser = role == "owner"
        user.save()

        StaffProfile.objects.create(
            user=user, role=role, job_title=self.cleaned_data.get("job_title", "")
        )
        if self.invite is not None:
            self.invite.used_by = user
            self.invite.used_at = timezone.now()
            self.invite.save(update_fields=["used_by", "used_at"])
            # A code issued for a particular staff record joins the two here, so
            # nobody has to remember to link them by hand afterwards.
            if self.invite.staff_member_id:
                StaffMember.objects.filter(pk=self.invite.staff_member_id).update(account=user)
        return user


class PanelPasswordChangeForm(PanelFormMixin, PasswordChangeForm):
    #: Short labels for the configured validators. Django's own help text is a
    #: four-sentence list that dwarfs the form it belongs to, so the template
    #: renders these as a compact chip row above the fields instead.
    RULE_LABELS = {
        "MinimumLengthValidator": "8+ characters",
        "CommonPasswordValidator": "Not a common password",
        "NumericPasswordValidator": "Not all numbers",
        "UserAttributeSimilarityValidator": "Unlike your name or email",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Django autofocuses old_password by default. On this page it sits below
        # a separate "Your details" form, so autofocus yanks the page's focus to
        # a field the user didn't click and pops the browser's password-manager
        # suggestion UI open on load, which is the oversized box under the field.
        self.fields["old_password"].widget.attrs.pop("autofocus", None)
        self.fields["new_password1"].help_text = ""
        self.fields["new_password2"].help_text = "Type it once more."

    def clean_old_password(self):
        """Trim accidental leading/trailing whitespace from a pasted password."""
        old_password = self.cleaned_data.get("old_password", "").strip()
        if not self.user.check_password(old_password):
            raise forms.ValidationError(
                self.error_messages["password_incorrect"],
                code="password_incorrect",
            )
        return old_password

    @property
    def rules(self):
        """The active password rules, phrased short enough to sit on one line."""
        labels = []
        for validator in password_validation.get_default_password_validators():
            label = self.RULE_LABELS.get(type(validator).__name__)
            if label == "8+ characters":
                label = f"{getattr(validator, 'min_length', 8)}+ characters"
            if label:
                labels.append(label)
        return labels


class AccountForm(PanelModelForm):
    """The signed-in user editing their own details."""

    first_name = forms.CharField(label="Full name", max_length=80, required=False)
    email = forms.EmailField(required=False)

    class Meta:
        model = StaffProfile
        fields = ["job_title", "phone", "theme"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.instance.user
        self.fields["first_name"].initial = user.first_name
        self.fields["email"].initial = user.email
        self.order_fields(["first_name", "email", "job_title", "phone", "theme"])

    def save(self, commit=True):
        profile = super().save(commit=commit)
        user = profile.user
        user.first_name = self.cleaned_data["first_name"]
        user.email = self.cleaned_data["email"]
        user.save(update_fields=["first_name", "email"])
        return profile


def unlinked_staff(current=None):
    """
    Staff records that may be attached to a login: everyone without one, plus
    whoever is already attached here, so an edit form does not drop them.
    """
    if current is not None:
        return (
            StaffMember.objects.filter(Q(account__isnull=True) | Q(pk=current.pk))
            .select_related("category")
            .order_by("name")
        )
    return (
        StaffMember.objects.filter(account__isnull=True)
        .select_related("category")
        .order_by("name")
    )


class StaffAccessForm(PanelModelForm):
    """An owner editing somebody else's panel access."""

    is_active = forms.BooleanField(
        required=False,
        label="Account enabled",
        help_text="Turn off to revoke access without deleting the history.",
    )
    staff_member = forms.ModelChoiceField(
        queryset=StaffMember.objects.none(),
        required=False,
        label="Staff record",
        empty_label="Not linked to a staff record",
        help_text="Ties this login to the person on the Staffs page.",
    )

    class Meta:
        model = StaffProfile
        fields = ["role", "job_title", "phone"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["is_active"].initial = self.instance.user.is_active
        linked = self.instance.staff_member
        self.fields["staff_member"].queryset = unlinked_staff(linked)
        self.fields["staff_member"].initial = linked
        self.order_fields(["role", "staff_member", "job_title", "phone", "is_active"])

    def save(self, commit=True):
        profile = super().save(commit=commit)
        user = profile.user
        user.is_active = self.cleaned_data["is_active"]
        user.is_staff = True
        user.is_superuser = profile.role == "owner"
        user.save(update_fields=["is_active", "is_staff", "is_superuser"])

        # One login, one staff record: clear the old link before writing the new.
        chosen = self.cleaned_data.get("staff_member")
        StaffMember.objects.filter(account=user).exclude(
            pk=getattr(chosen, "pk", None)
        ).update(account=None)
        if chosen is not None:
            StaffMember.objects.filter(pk=chosen.pk).update(account=user)
        return profile


class AccountCreateForm(PanelFormMixin, UserCreationForm):
    """
    An owner creating a login outright, rather than sending an invite code.

    This is the path for somebody standing next to you: fill in who they are,
    pick the role, optionally point at their staff record, and they can sign in
    straight away.
    """

    full_name = forms.CharField(label="Full name", max_length=80)
    email = forms.EmailField()
    role = forms.ChoiceField(
        choices=StaffProfile.ROLE_CHOICES,
        initial="editor",
        help_text="What they may change once inside.",
    )
    staff_member = forms.ModelChoiceField(
        queryset=StaffMember.objects.none(),
        required=False,
        label="Staff record",
        empty_label="Not linked to a staff record",
        help_text="Link this login to somebody already on the Staffs page.",
    )
    job_title = forms.CharField(max_length=80, required=False)
    phone = forms.CharField(max_length=40, required=False)

    class Meta:
        model = User
        fields = ["full_name", "email", "username"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["staff_member"].queryset = unlinked_staff()
        self.fields["username"].help_text = "What they type to sign in."
        self.fields["password1"].help_text = "Share it with them; they can change it later."
        self.fields["password2"].label = "Confirm password"
        self.order_fields([
            "full_name", "email", "username", "password1", "password2",
            "role", "staff_member", "job_title", "phone",
        ])

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account already uses that email address.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data["full_name"]
        user.email = self.cleaned_data["email"]
        role = self.cleaned_data["role"]
        user.is_staff = True
        user.is_superuser = role == "owner"
        user.save()

        StaffProfile.objects.create(
            user=user,
            role=role,
            job_title=self.cleaned_data.get("job_title", ""),
            phone=self.cleaned_data.get("phone", ""),
        )
        chosen = self.cleaned_data.get("staff_member")
        if chosen is not None:
            StaffMember.objects.filter(pk=chosen.pk).update(account=user)
        return user


class InviteCodeForm(PanelModelForm):
    class Meta:
        model = InviteCode
        fields = ["role", "staff_member", "note", "expires_at"]
        widgets = {"expires_at": DateTimeInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["staff_member"].queryset = unlinked_staff()
        self.fields["staff_member"].empty_label = "Anyone"


# ---------------------------------------------------------------------------
# Site configuration
# ---------------------------------------------------------------------------


class SiteSettingsForm(PanelModelForm):
    class Meta:
        model = SiteSettings
        fields = [
            "name", "tagline", "logo_file", "logo_url", "logo_fit", "logo_focal",
            "logo_width", "logo_height", "logo_show_name",
            "phone", "whatsapp", "email", "address", "hours",
            "founded_year", "default_city", "announcement", "maintenance_mode",
            "instagram", "facebook", "youtube", "twitter",
            "free_delivery_threshold", "delivery_fee", "tax_percent",
            "home_products_eyebrow", "home_products_title", "home_products_lead",
            "home_products_limit", "home_products_source", "home_products_cta_label",
            "products_page_eyebrow", "products_page_title", "products_page_lead",
            "products_per_page",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "home_products_lead": forms.Textarea(attrs={"rows": 2}),
            "products_page_lead": forms.Textarea(attrs={"rows": 2}),
        }

    # Grouped so the settings page can render sections instead of one long column.
    SECTIONS = [
        ("Identity", ["name", "tagline", "founded_year", "announcement", "maintenance_mode"]),
        ("Logo", ["logo_file", "logo_url", "logo_fit", "logo_width", "logo_height", "logo_focal", "logo_show_name"]),
        ("Contact", ["phone", "whatsapp", "email", "address", "hours", "default_city"]),
        ("Social", ["instagram", "facebook", "youtube", "twitter"]),
        ("Checkout", ["free_delivery_threshold", "delivery_fee", "tax_percent"]),
        ("Packages on the homepage", [
            "home_products_eyebrow", "home_products_title", "home_products_lead",
            "home_products_source", "home_products_limit", "home_products_cta_label",
        ]),
        ("The packages page", [
            "products_page_eyebrow", "products_page_title", "products_page_lead",
            "products_per_page",
        ]),
    ]

    def sections(self):
        for title, names in self.SECTIONS:
            yield title, [self[name] for name in names]


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------


class CategoryForm(PanelModelForm):
    class Meta:
        model = Category
        fields = [
            "name", "slug", "icon", "blurb", "price_from", "package_count",
            "image_file", "image_url", "is_active", "position",
        ]
        widgets = {"blurb": forms.Textarea(attrs={"rows": 2})}


class PackageForm(PanelModelForm):
    class Meta:
        model = Package
        fields = [
            "title", "slug", "category", "price", "original_price", "badge",
            "duration", "rating", "review_count", "description", "includes_text",
            "image_file", "image_url", "is_featured", "is_active", "position",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "includes_text": forms.Textarea(attrs={"rows": 7}),
        }

    def clean(self):
        cleaned = super().clean()
        price = cleaned.get("price")
        original = cleaned.get("original_price")
        if price and original and original < price:
            self.add_error(
                "original_price",
                "The struck-through price has to be at least the selling price, "
                "otherwise the card would advertise a negative discount.",
            )
        return cleaned


class PackageImageForm(PanelModelForm):
    class Meta:
        model = PackageImage
        fields = ["package", "image_file", "image_url", "alt", "position"]


class HeroSlideForm(PanelModelForm):
    cta_url_name = forms.ChoiceField(choices=ROUTE_CHOICES, label="Button links to")
    cta2_url_name = forms.ChoiceField(
        choices=[("", "— no second button —")] + ROUTE_CHOICES,
        required=False,
        label="Second button links to",
    )

    class Meta:
        model = HeroSlide
        fields = [
            "eyebrow", "heading", "heading_accent", "description", "meta", "alt",
            "media_type", "image_file", "image_url", "video_file", "video_mp4", "video_webm",
            "tint", "focal", "duration",
            "cta_label", "cta_url_name", "cta_url_arg", "cta_anchor",
            "cta2_label", "cta2_url_name", "cta2_url_arg", "cta2_anchor",
            "is_active", "starts_at", "ends_at", "position",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "starts_at": DateTimeInput(),
            "ends_at": DateTimeInput(),
        }

    SECTIONS = [
        ("Copy", ["eyebrow", "heading", "heading_accent", "description", "meta", "alt"]),
        ("Media", ["media_type", "image_file", "image_url", "video_file", "video_mp4", "video_webm"]),
        ("Look", ["tint", "focal", "duration"]),
        ("Buttons", ["cta_label", "cta_url_name", "cta_url_arg", "cta_anchor",
                     "cta2_label", "cta2_url_name", "cta2_url_arg", "cta2_anchor"]),
        ("Scheduling", ["is_active", "starts_at", "ends_at", "position"]),
    ]

    def sections(self):
        for title, names in self.SECTIONS:
            yield title, [self[name] for name in names]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("media_type") == "video" and not (
            cleaned.get("video_file") or cleaned.get("video_mp4")
        ):
            self.add_error(
                "video_file",
                "A video slide needs a file or an MP4 URL. Without one it would "
                "silently fall back to showing the poster image.",
            )
        for route_field, arg_field in (("cta_url_name", "cta_url_arg"), ("cta2_url_name", "cta2_url_arg")):
            route = cleaned.get(route_field)
            arg = (cleaned.get(arg_field) or "").strip()
            if route in ("core:category_detail", "core:package_detail") and not arg:
                self.add_error(arg_field, "This route needs a slug, e.g. birthday.")
            if route and route not in ("core:category_detail", "core:package_detail") and arg:
                cleaned[arg_field] = ""
        starts, ends = cleaned.get("starts_at"), cleaned.get("ends_at")
        if starts and ends and ends <= starts:
            self.add_error("ends_at", "The end has to come after the start.")
        return cleaned


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


class EnquiryForm(PanelModelForm):
    class Meta:
        model = Enquiry
        fields = [
            "name", "phone", "email", "city", "occasion", "package", "event_date", "guests",
            "message", "status",
        ]
        widgets = {"event_date": DateInput(), "message": forms.Textarea(attrs={"rows": 5})}

    SECTIONS = [
        ("From", ["name", "phone", "email", "city"]),
        ("About", ["occasion", "package", "event_date", "guests", "message"]),
        ("Handling", ["status"]),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["package"].queryset = Package.objects.select_related("category").order_by("title")
        self.fields["package"].empty_label = "No particular package"
        self.fields["guests"].required = False
        self.fields["guests"].widget.attrs.pop("required", None)

    def clean_guests(self):
        return self.cleaned_data.get("guests") or 0

    def sections(self):
        return _sections(self)


class StaffCategoryForm(PanelModelForm):
    class Meta:
        model = StaffCategory
        fields = ["name", "slug", "kind", "tone", "description", "is_active", "position"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["slug"].help_text = "Left blank, it is made from the name."


class StaffMemberForm(PanelModelForm):
    """The operational record: who they are and what they do, not how they sign in."""

    class Meta:
        model = StaffMember
        fields = [
            "name", "phone", "email",
            "category", "employment", "skills", "city",
            "rating", "is_verified", "is_active",
            "account", "notes",
        ]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    SECTIONS = [
        ("Who they are", ["name", "phone", "email"]),
        ("What they do", ["category", "employment", "skills", "city"]),
        ("Standing", ["rating", "is_verified", "is_active"]),
        ("Panel access", ["account", "notes"]),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A retired type stays readable on the records that already carry it,
        # but is not offered to anybody else.
        types = StaffCategory.objects.filter(is_active=True)
        if self.instance.category_id:
            types = StaffCategory.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.category_id)
            )
        self.fields["category"].queryset = types.order_by("position", "id")
        self.fields["category"].empty_label = "No type yet"
        self.fields["city"].queryset = City.objects.filter(is_active=True)

        # Only logins that are not already somebody else's record.
        taken = (
            StaffMember.objects.exclude(pk=self.instance.pk or 0)
            .exclude(account__isnull=True)
            .values_list("account_id", flat=True)
        )
        self.fields["account"].queryset = User.objects.exclude(
            pk__in=list(taken)
        ).order_by("username")
        self.fields["account"].empty_label = "No panel login"

    def sections(self):
        for title, names in self.SECTIONS:
            yield title, [self[name] for name in names]


class CouponForm(PanelModelForm):
    class Meta:
        model = Coupon
        fields = ["code", "kind", "value", "min_order", "max_uses", "valid_from", "valid_to", "is_active"]
        widgets = {"valid_from": DateInput(), "valid_to": DateInput()}

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("kind") == "percent" and (cleaned.get("value") or 0) > 100:
            self.add_error("value", "A percentage discount cannot exceed 100.")
        start, end = cleaned.get("valid_from"), cleaned.get("valid_to")
        if start and end and end < start:
            self.add_error("valid_to", "The end date is before the start date.")
        return cleaned


# ---------------------------------------------------------------------------
# Content blocks — small enough to declare inline
# ---------------------------------------------------------------------------


class TestimonialForm(PanelModelForm):
    class Meta:
        model = Testimonial
        fields = ["name", "city", "rating", "package", "booked", "date", "text", "is_published", "position"]
        widgets = {"text": forms.Textarea(attrs={"rows": 5})}

    def clean(self):
        cleaned = super().clean()
        package = cleaned.get("package")
        if package and not (cleaned.get("booked") or "").strip():
            cleaned["booked"] = package.title
        return cleaned


class FAQForm(PanelModelForm):
    class Meta:
        model = FAQ
        fields = ["question", "answer", "is_active", "position"]
        widgets = {"answer": forms.Textarea(attrs={"rows": 5})}


class FeatureForm(PanelModelForm):
    class Meta:
        model = Feature
        fields = ["title", "icon", "text", "is_active", "position"]
        widgets = {"text": forms.Textarea(attrs={"rows": 3})}


class HowItWorksStepForm(PanelModelForm):
    class Meta:
        model = HowItWorksStep
        fields = ["step", "title", "icon", "text", "is_active", "position"]
        widgets = {"text": forms.Textarea(attrs={"rows": 3})}


class PricingRowForm(PanelModelForm):
    class Meta:
        model = PricingRow
        fields = ["category", "range", "popular", "setup_time", "is_active", "position"]


class CityForm(PanelModelForm):
    class Meta:
        model = City
        fields = ["name", "slug", "state", "is_metro", "is_active"]


class TimeSlotForm(PanelModelForm):
    class Meta:
        model = TimeSlot
        fields = ["label", "value", "available", "position"]


class AddOnForm(PanelModelForm):
    class Meta:
        model = AddOn
        fields = ["name", "price", "is_active", "position"]


class TrustBadgeForm(PanelModelForm):
    class Meta:
        model = TrustBadge
        fields = ["value", "label", "is_active", "position"]


class NavLinkForm(PanelModelForm):
    url_name = forms.ChoiceField(choices=ROUTE_CHOICES, label="Points at")

    class Meta:
        model = NavLink
        fields = ["label", "url_name", "anchor", "is_active", "position"]


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


class SupplierForm(PanelModelForm):
    class Meta:
        model = Supplier
        fields = [
            "name", "contact_name", "phone", "email",
            "gst_number", "lead_time_days", "address", "notes", "is_active",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    SECTIONS = [
        ("Who they are", ["name", "contact_name", "phone", "email"]),
        ("Trading details", ["gst_number", "lead_time_days", "address"]),
        ("Standing", ["notes", "is_active"]),
    ]

    def sections(self):
        for title, names in self.SECTIONS:
            yield title, [self[name] for name in names]


class StockCategoryForm(PanelModelForm):
    class Meta:
        model = StockCategory
        fields = ["name", "slug", "description", "tone", "is_active", "position"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["slug"].help_text = "Left blank, it is made from the name."


class InventoryItemForm(PanelModelForm):
    """
    Everything about an item except how much of it there is — that number is
    the ledger's to write, and a field here would let it be typed over.
    """

    class Meta:
        model = InventoryItem
        fields = [
            "name", "sku", "category", "supplier", "description",
            "unit", "usage_type", "barcode", "location", "reorder_level",
            "cost_price", "sale_price",
            "image_file", "image_url",
            "is_sellable", "is_active", "notes",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    SECTIONS = [
        ("What it is", ["name", "sku", "category", "supplier", "description"]),
        ("How it is counted", ["unit", "usage_type", "barcode", "location", "reorder_level"]),
        ("Money", ["cost_price", "sale_price"]),
        ("Picture", ["image_file", "image_url"]),
        ("Standing", ["is_sellable", "is_active", "notes"]),
    ]

    # Only on a new item: the count still comes from the ledger, this just
    # writes its first row in the same save.
    OPENING_FIELDS = ["opening_quantity", "opening_kind", "opening_reference"]

    opening_quantity = forms.DecimalField(
        required=False, min_value=0, max_digits=12, decimal_places=2,
        label="Units on hand now",
        help_text="Leave empty to start at zero.",
    )
    opening_kind = forms.ChoiceField(
        required=False, initial="opening", label="Where they came from",
        choices=[("opening", "Already in the store"), ("purchase", "Just bought from the supplier")],
    )
    opening_reference = forms.CharField(
        required=False, max_length=40, label="Reference",
        help_text="Optional invoice or delivery-note number.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            for name in self.OPENING_FIELDS:
                self.fields.pop(name)
        self.fields["sku"].required = False
        groups = StockCategory.objects.filter(is_active=True)
        if self.instance.category_id:
            groups = StockCategory.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.category_id)
            )
        self.fields["category"].queryset = groups.order_by("position", "id")
        self.fields["category"].empty_label = "No group yet"

        suppliers = Supplier.objects.filter(is_active=True)
        if self.instance.supplier_id:
            suppliers = Supplier.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.supplier_id)
            )
        self.fields["supplier"].queryset = suppliers.order_by("name")
        self.fields["supplier"].empty_label = "No supplier"

        if self.instance.pk:
            self.fields["sku"].help_text = "Changing this changes it on future receipts only."

    def sections(self):
        for title, names in self.SECTIONS:
            yield title, [self[name] for name in names]

    def opening_fields(self):
        return [self[name] for name in self.OPENING_FIELDS if name in self.fields]

    def clean_sku(self):
        return (self.cleaned_data.get("sku") or "").upper().strip()

    def clean(self):
        cleaned = super().clean()
        cost = cleaned.get("cost_price") or 0
        price = cleaned.get("sale_price") or 0
        if price and cost > price:
            self.add_error(
                "sale_price",
                "That sells for less than it costs. Fix the price, or leave it at 0 "
                "if the item is never sold.",
            )
        opening = cleaned.get("opening_quantity")
        if opening and cleaned.get("usage_type") == "reusable" and opening != opening.to_integral_value():
            self.add_error("opening_quantity", "Reusable stock is counted in whole units.")
        return cleaned

    def opening_movement(self, user):
        """The first ledger row for a new item, or None when it starts empty."""
        quantity = self.cleaned_data.get("opening_quantity")
        if not quantity or self.instance.pk is None:
            return None
        kind = self.cleaned_data.get("opening_kind") or "opening"
        return StockMovement(
            item=self.instance,
            kind=kind,
            change=quantity,
            unit_cost=self.cleaned_data.get("cost_price") or 0,
            supplier=self.cleaned_data.get("supplier") if kind == "purchase" else None,
            reference=self.cleaned_data.get("opening_reference") or "",
            note="Starting stock, entered with the new item",
            created_by=user,
        )


class StockMovementForm(PanelModelForm):
    """
    Receiving stock, writing off breakages, correcting a count.

    The reason decides the direction, so the quantity is typed as a plain
    positive number — except on an adjustment, where a signed number is the
    whole point.
    """

    class Meta:
        model = StockMovement
        fields = [
            "item", "kind", "change", "unit_cost",
            "supplier", "reference", "note",
        ]
        widgets = {"note": forms.Textarea(attrs={"rows": 2})}

    SECTIONS = [
        ("What moved", ["item", "kind", "change"]),
        ("Where it came from or went", ["unit_cost", "supplier"]),
        ("For the record", ["reference", "note"]),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = (
            InventoryItem.objects.active().select_related("category").order_by("name")
        )
        self.fields["item"].label_from_instance = (
            lambda item: f"{item.name} · {item.sku} · {item.quantity_label} on hand"
        )
        self.fields["supplier"].queryset = Supplier.objects.filter(is_active=True)
        self.fields["supplier"].empty_label = "Not from a supplier"
        if not self.instance.pk:
            # Reservations are written by events; a hand-typed one would move
            # nothing and mean nothing.
            self.fields["kind"].choices = [
                choice for choice in self.fields["kind"].choices
                if choice[0] not in StockMovement.EVENT_ONLY_KINDS
            ]
        self.fields["change"].help_text = (
            "How many units. Purchases and returns add stock, sales, damage and "
            "event use take it away — type a plain number and the reason sorts "
            "out the sign. On a stock-count adjustment, type a minus for a loss."
        )
        if self.instance.pk:
            # An existing ledger row is history; the form is a read-back only.
            for field in self.fields.values():
                field.disabled = True

    def sections(self):
        for title, names in self.SECTIONS:
            yield title, [self[name] for name in names]

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get("kind")
        change = cleaned.get("change")
        item = cleaned.get("item")
        if kind is None or change is None:
            return cleaned

        if change == 0:
            self.add_error("change", "A movement of zero would not change anything.")
            return cleaned

        if item is not None and item.is_reusable and change != change.to_integral_value():
            self.add_error("change", f"{item.name} is reusable stock, so it is counted in whole units.")
            return cleaned

        direction = StockMovement.DIRECTIONS.get(kind, 0)
        if direction:
            # "5 damaged" means five off the shelf however it was typed.
            cleaned["change"] = abs(change) * direction

        if item is not None and cleaned["change"] < 0:
            short = item.quantity + cleaned["change"]
            if short < 0:
                self.add_error(
                    "change",
                    f"There are only {item.quantity_label} of {item.name} on the shelf. "
                    "Receive more first, or correct the count with an adjustment.",
                )
        return cleaned


class CounterSaleForm(PanelModelForm):
    """
    A sale after the fact: who it was for, how it was paid, what was noted.

    The lines and the totals are not editable here — a receipt that could be
    rewritten is not a record. Refunds happen on the sale's own page.
    """

    class Meta:
        model = CounterSale
        fields = ["customer_name", "phone", "served_by", "payment_method", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["served_by"].queryset = StaffMember.objects.assignable().order_by("name")
        self.fields["served_by"].empty_label = "Nobody in particular"


class CounterCheckoutForm(PanelFormMixin, forms.Form):
    """The right-hand column of the counter screen — how this sale is closed."""

    customer_name = forms.CharField(
        max_length=120, required=False, label="Customer",
        widget=forms.TextInput(attrs={"placeholder": "Walk-in"}),
    )
    phone = forms.CharField(max_length=40, required=False)
    served_by = forms.ModelChoiceField(
        queryset=StaffMember.objects.none(), required=False,
        label="Sold by", empty_label="Nobody in particular",
    )
    payment_method = forms.ChoiceField(
        choices=CounterSale.PAYMENT_CHOICES,
        initial="cash",
        label="Paid by",
        # One tap beats opening a dropdown when there is a queue.
        widget=forms.RadioSelect,
    )
    discount = forms.IntegerField(
        min_value=0, initial=0, required=False, label="Discount (Rs.)"
    )
    tax_percent = forms.DecimalField(
        min_value=0, max_value=100, max_digits=5, decimal_places=2,
        initial=0, required=False, label="Tax %",
    )
    amount_tendered = forms.IntegerField(
        min_value=0, initial=0, required=False, label="Cash taken (Rs.)",
        help_text="Optional. Fills in the change line on the receipt.",
    )
    notes = forms.CharField(
        max_length=400, required=False, widget=forms.Textarea(attrs={"rows": 2})
    )

    def __init__(self, *args, **kwargs):
        self.subtotal = kwargs.pop("subtotal", 0)
        super().__init__(*args, **kwargs)
        self.fields["served_by"].queryset = StaffMember.objects.assignable().order_by("name")
        # The mixin dresses every widget as a text input; radios want neither
        # that class nor a `required` on each of the five of them.
        self.fields["payment_method"].widget.attrs = {"class": "segmented__input"}
        for name in ("discount", "tax_percent", "amount_tendered"):
            self.fields[name].widget.attrs.update({"inputmode": "decimal", "min": "0"})

    def clean_discount(self):
        discount = self.cleaned_data.get("discount") or 0
        if discount > self.subtotal:
            raise forms.ValidationError(
                f"The discount is more than the sale is worth (Rs. {self.subtotal:,})."
            )
        return discount

    def clean_tax_percent(self):
        return self.cleaned_data.get("tax_percent") or 0

    def clean_amount_tendered(self):
        return self.cleaned_data.get("amount_tendered") or 0


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


def _sections(form):
    for title, names in form.SECTIONS:
        yield title, [form[name] for name in names]


class CustomerForm(PanelModelForm):
    class Meta:
        model = Customer
        fields = ["name", "phone", "email", "address", "notes"]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    SECTIONS = [
        ("Who they are", ["name", "phone", "email"]),
        ("On file", ["address", "notes"]),
    ]

    def sections(self):
        return _sections(self)


class EventForm(PanelModelForm):
    """
    The event itself. Status is not here: it only moves through the buttons on
    the event page, because each step does something to stock.
    """

    new_customer_name = forms.CharField(
        max_length=120, required=False, label="…or a new customer",
        help_text="Type a name to add them to your customers as the event is saved.",
    )
    new_customer_phone = forms.CharField(
        max_length=40, required=False, label="New customer's phone",
    )

    class Meta:
        model = Event
        fields = [
            "name", "occasion", "package", "customer", "event_date", "time_slot",
            "location", "guests", "crew", "revenue", "notes",
        ]
        widgets = {
            "event_date": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 4}),
            "crew": forms.CheckboxSelectMultiple(),
        }

    SECTIONS = [
        ("The event", ["name", "occasion", "package", "event_date", "time_slot", "location", "guests"]),
        ("Customer", ["customer", "new_customer_name", "new_customer_phone"]),
        ("Crew", ["crew"]),
        ("Money and notes", ["revenue", "notes"]),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        customer = self.fields["customer"]
        customer.required = False
        customer.widget.attrs.pop("required", None)
        customer.queryset = Customer.objects.order_by("name")
        customer.empty_label = "Pick a customer"
        customer.help_text = "Somebody you have run an event for before."
        self.fields["name"].widget.attrs.setdefault(
            "placeholder", "Sharma wedding reception"
        )
        for name in ("guests", "revenue"):
            self.fields[name].widget.attrs.update({"inputmode": "numeric", "min": "0"})

        occasion = self.fields["occasion"]
        occasion.queryset = Category.objects.order_by("position", "name")
        occasion.empty_label = "Pick an occasion"
        # Every event is one occasion. A package on its own already says which,
        # so a submit with only a package gets its occasion filled in before
        # validation, and the browser is not asked to insist on the field.
        occasion.required = True
        occasion.widget.attrs.pop("required", None)
        occasion.error_messages["required"] = (
            "Pick the occasion — every event is one (Birthday, Wedding…)."
        )
        occasion.help_text = (
            "What kind of celebration this is. Picking a package below fills it in."
        )
        self._occasion_from_package()
        package = self.fields["package"]
        # A package that has since been unpublished stays selectable on its own event.
        current = self.instance.package_id if self.instance.pk else None
        package.queryset = (
            Package.objects.filter(Q(is_active=True) | Q(pk=current))
            .select_related("category").order_by("category__position", "title")
        )
        package.empty_label = "No package — planned from scratch"
        package.label_from_instance = lambda p: f"{p.title} · {p.category.name} · Rs. {p.price:,}"
        crew = self.fields["crew"]
        # Somebody since switched off stays ticked on the events they worked.
        current_crew = list(self.instance.crew.values_list("pk", flat=True)) if self.instance.pk else []
        crew.queryset = (
            StaffMember.objects.filter(Q(is_active=True) | Q(pk__in=current_crew))
            .select_related("category", "city").order_by("category__position", "name")
        )
        crew.label_from_instance = lambda member: member.assign_label
        crew.widget.attrs.pop("class", None)
        crew.help_text = "Tick everyone working it. Their open jobs count on the Staffs page follows."
        slots = [slot.label for slot in TimeSlot.objects.all()]
        if self.instance.time_slot and self.instance.time_slot not in slots:
            slots.append(self.instance.time_slot)
        self.fields["time_slot"].widget = forms.Select(
            choices=[("", "Any time")] + [(label, label) for label in slots],
            attrs={"class": "field__input field__input--select"},
        )

    def _occasion_from_package(self):
        if not self.is_bound or self.data.get("occasion"):
            return
        raw = str(self.data.get("package") or "")
        category_id = (
            Package.objects.filter(pk=raw).values_list("category_id", flat=True).first()
            if raw.isdigit() else None
        )
        if category_id:
            data = self.data.copy()
            data["occasion"] = str(category_id)
            self.data = data

    def sections(self):
        return _sections(self)

    def clean(self):
        cleaned = super().clean()
        customer = cleaned.get("customer")
        new_name = (cleaned.get("new_customer_name") or "").strip()
        if customer and new_name:
            self.add_error(
                "new_customer_name",
                "Pick an existing customer or type a new one — not both.",
            )
        elif not customer and not new_name:
            self.add_error("customer", "Pick a customer, or type a new one's name below.")
        cleaned["new_customer_name"] = new_name

        occasion, package = cleaned.get("occasion"), cleaned.get("package")
        if package and occasion and package.category_id != occasion.pk:
            self.add_error(
                "package", f"{package.title} is a {package.category.name} package, not {occasion.name}.",
            )
        return cleaned

    def save(self, commit=True):
        event = super().save(commit=False)
        event.occasion = self.cleaned_data.get("occasion")
        new_name = self.cleaned_data.get("new_customer_name")
        if new_name and not self.cleaned_data.get("customer"):
            phone = (self.cleaned_data.get("new_customer_phone") or "").strip()
            # Somebody already on file with that number is the same person.
            event.customer = Customer.find_by_phone(phone) or Customer.objects.create(
                name=new_name, phone=phone,
            )
        if commit:
            event.save()
            self.save_m2m()
        return event


class EventStockPickForm:
    """
    Add several stock items to an event at once — a tick and a quantity per
    item. It posts `pick=<pk>` for every ticked item and `qty-<pk>` for its
    quantity, so it is an ordinary form that works without JavaScript. Items
    are only ever picked from stock, never created here.
    """

    MAX_QUANTITY = Decimal("9999999999")

    def __init__(self, data=None, event=None):
        self.data = data
        self.event = event
        self.is_bound = data is not None
        self.errors = []
        self.cleaned = []

        lines = {}
        if event is not None and event.pk:
            for line in event.items.all():
                if line.is_inventory and line.inventory_item_id:
                    lines[line.inventory_item_id] = line

        picked = set(data.getlist("pick")) if self.is_bound else set()
        self.rows = []
        for item in (
            InventoryItem.objects.active().with_reserved()
            .select_related("category").order_by("name")
        ):
            key = str(item.pk)
            raw = (data.get(f"qty-{key}") or "").strip() if self.is_bound else ""
            line = lines.get(item.pk)
            self.rows.append({
                "item": item,
                "key": key,
                "checked": key in picked,
                "quantity": raw or "1",
                "line": line,
                "error": "",
                "soldout": item.is_unavailable,
                "search": f"{item.name} {item.sku} {item.category_name}".lower(),
            })
            picked.discard(key)
        # Anything ticked that is not on the list any more was retired meanwhile.
        self.unknown = [key for key in picked if key]

    @property
    def selected_count(self):
        return sum(1 for row in self.rows if row["checked"])

    @property
    def has_errors(self):
        return bool(self.errors) or any(row["error"] for row in self.rows)

    def add_error(self, messages):
        self.errors.extend(messages)

    def is_valid(self):
        if not self.is_bound:
            return False
        self.cleaned = []
        if self.unknown:
            self.errors.append(
                "Something you ticked is no longer on the stock list — look again."
            )
        if not self.selected_count and not self.unknown:
            self.errors.append("Tick at least one item to add.")

        for row in self.rows:
            if not row["checked"]:
                continue
            item = row["item"]
            try:
                quantity = Decimal(row["quantity"])
            except (InvalidOperation, ValueError):
                row["error"] = "Enter a number."
                continue
            if not quantity.is_finite() or quantity <= 0:
                row["error"] = "The quantity has to be more than zero."
                continue
            if quantity != quantity.quantize(Decimal("0.01")) or quantity > self.MAX_QUANTITY:
                row["error"] = "Use at most two decimal places."
                continue
            try:
                EventItem.check_quantity(item, quantity)
            except ValidationError as error:
                row["error"] = " ".join(error.messages)
                continue
            # Whatever this event's line already needs but does not hold yet
            # comes off the same free pile.
            line = row["line"]
            wanted = quantity + (line.unreserved if line is not None else Decimal("0"))
            free = item.available_quantity
            if wanted > free:
                row["error"] = f"Only {normalise_quantity(free)} units are available."
                continue
            self.cleaned.append((item, quantity))
        return not self.has_errors


class EventExternalItemForm(PanelModelForm):
    """Something arranged outside the company. It never enters stock."""

    class Meta:
        model = EventItem
        fields = [
            "name", "quantity", "unit_cost", "supplier", "vendor",
            "image_file", "image_url", "notes",
        ]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}
        labels = {"image_file": "Photo", "image_url": "…or paste a photo URL"}
        help_texts = {"image_file": "Optional. JPG, PNG, WebP, AVIF, GIF or SVG."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["quantity"].initial = 1
        self.fields["name"].widget.attrs.setdefault("placeholder", "Flower wall, rented sound…")
        suppliers = Supplier.objects.filter(is_active=True)
        if self.instance.supplier_id:
            suppliers = Supplier.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.supplier_id)
            )
        self.fields["supplier"].queryset = suppliers.order_by("name")
        self.fields["supplier"].empty_label = "Not from a listed supplier"
        self.fields["quantity"].widget.attrs.update({"inputmode": "decimal", "step": "any", "min": "0.01"})
        self.fields["unit_cost"].widget.attrs.update({"inputmode": "numeric", "min": "0"})

    def save(self, commit=True):
        line = super().save(commit=False)
        line.item_type = "external"
        if commit:
            line.save()
        return line


class EventLineQuantityForm(PanelFormMixin, forms.Form):
    """Change how many of a stock item an event needs."""

    quantity = forms.DecimalField(
        min_value=Decimal("0.01"), max_digits=12, decimal_places=2, label="Quantity needed",
    )
    notes = forms.CharField(
        max_length=2000, required=False, widget=forms.Textarea(attrs={"rows": 2}),
    )


class EventUsageForm(PanelFormMixin, forms.Form):
    """What came back from an event, and what did not."""

    returned = forms.DecimalField(min_value=0, max_digits=12, decimal_places=2, required=False)
    consumed = forms.DecimalField(min_value=0, max_digits=12, decimal_places=2, required=False)
    damaged = forms.DecimalField(min_value=0, max_digits=12, decimal_places=2, required=False)
    lost = forms.DecimalField(min_value=0, max_digits=12, decimal_places=2, required=False)

    def clean(self):
        cleaned = super().clean()
        for name in ("returned", "consumed", "damaged", "lost"):
            if cleaned.get(name) is None and name not in self.errors:
                cleaned[name] = Decimal("0")
        return cleaned


class EventExpenseForm(PanelModelForm):
    class Meta:
        model = EventExpense
        fields = ["name", "category", "amount", "spent_on", "notes"]
        widgets = {"spent_on": DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs.setdefault("placeholder", "Tempo hire to the venue")
        self.fields["amount"].widget.attrs.update({"inputmode": "numeric", "min": "1"})


class EventPaymentForm(PanelModelForm):
    class Meta:
        model = EventPayment
        fields = ["amount", "paid_on", "method", "reference", "notes"]
        widgets = {"paid_on": DateInput(), "method": forms.RadioSelect}

    def __init__(self, *args, event=None, **kwargs):
        self.event = event
        super().__init__(*args, **kwargs)
        # Radios want neither the text-input class nor `required` on each one.
        self.fields["method"].widget.attrs = {"class": "segmented__input"}
        self.fields["amount"].widget.attrs.update({"inputmode": "numeric", "min": "1"})
        if event is not None and event.remaining > 0 and not self.is_bound:
            self.fields["amount"].initial = event.remaining

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is None or self.event is None:
            return amount
        owed = self.event.remaining
        if owed <= 0:
            raise forms.ValidationError(
                "This event is already paid in full. Raise its revenue first if "
                "the customer owes more."
            )
        if amount > owed:
            raise forms.ValidationError(f"That is more than the Rs. {owed:,} still owed.")
        return amount
