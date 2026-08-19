"""
Forms for the control panel.

`PanelFormMixin` styles every widget once, so the templates can render any form
with the same partial and no per-field markup. Model forms below only declare
the things that are genuinely specific: field order, widgets that need rows or
a date picker, and validation the model cannot express on its own.
"""

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    UserCreationForm,
)
from django.utils import timezone

from core.models import (
    AddOn,
    Booking,
    Category,
    City,
    Coupon,
    Decorator,
    Enquiry,
    FAQ,
    Feature,
    HeroSlide,
    HowItWorksStep,
    InviteCode,
    NavLink,
    Package,
    PackageImage,
    PricingRow,
    SiteSettings,
    StaffProfile,
    Testimonial,
    TimeSlot,
    TrustBadge,
)

User = get_user_model()

# Routes a link can point at. A free-text field here would let a typo take down
# every page that renders the navbar, since {% url %} raises on a bad name.
ROUTE_CHOICES = [
    ("core:home", "Home"),
    ("core:products", "All products"),
    ("core:categories", "All categories"),
    ("core:category_detail", "A category page — needs a slug"),
    ("core:package_detail", "A package page — needs a slug"),
    ("core:how_it_works", "How it works"),
    ("core:contact", "Contact"),
    ("core:cart", "Cart"),
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


class StaffMemberForm(PanelModelForm):
    """An owner editing somebody else's access."""

    is_active = forms.BooleanField(
        required=False,
        label="Account enabled",
        help_text="Turn off to revoke access without deleting the history.",
    )

    class Meta:
        model = StaffProfile
        fields = ["role", "job_title", "phone"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["is_active"].initial = self.instance.user.is_active

    def save(self, commit=True):
        profile = super().save(commit=commit)
        user = profile.user
        user.is_active = self.cleaned_data["is_active"]
        user.is_staff = True
        user.is_superuser = profile.role == "owner"
        user.save(update_fields=["is_active", "is_staff", "is_superuser"])
        return profile


class InviteCodeForm(PanelModelForm):
    class Meta:
        model = InviteCode
        fields = ["role", "note", "expires_at"]
        widgets = {"expires_at": DateTimeInput()}


# ---------------------------------------------------------------------------
# Site configuration
# ---------------------------------------------------------------------------


class SiteSettingsForm(PanelModelForm):
    class Meta:
        model = SiteSettings
        fields = [
            "name", "tagline", "phone", "whatsapp", "email", "address", "hours",
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
        ("Contact", ["phone", "whatsapp", "email", "address", "hours", "default_city"]),
        ("Social", ["instagram", "facebook", "youtube", "twitter"]),
        ("Checkout", ["free_delivery_threshold", "delivery_fee", "tax_percent"]),
        ("Products on the homepage", [
            "home_products_eyebrow", "home_products_title", "home_products_lead",
            "home_products_source", "home_products_limit", "home_products_cta_label",
        ]),
        ("The products page", [
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


class BookingForm(PanelModelForm):
    class Meta:
        model = Booking
        fields = [
            "customer_name", "phone", "email",
            "package", "quantity", "add_ons", "amount",
            "city", "address", "event_date", "time_slot",
            "status", "payment_status", "decorator", "notes",
        ]
        widgets = {
            "event_date": DateInput(),
            "address": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "add_ons": forms.CheckboxSelectMultiple(),
        }

    SECTIONS = [
        ("Customer", ["customer_name", "phone", "email"]),
        ("What they booked", ["package", "quantity", "add_ons", "amount"]),
        ("Where and when", ["city", "address", "event_date", "time_slot"]),
        ("Operations", ["status", "payment_status", "decorator", "notes"]),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["package"].queryset = Package.objects.live().select_related("category")
        self.fields["decorator"].queryset = Decorator.objects.filter(is_active=True)
        self.fields["city"].queryset = City.objects.filter(is_active=True)
        self.fields["add_ons"].widget.attrs.pop("class", None)
        self.fields["amount"].help_text = "Leave at 0 to charge the package price."

    def sections(self):
        for title, names in self.SECTIONS:
            yield title, [self[name] for name in names]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("status") == "assigned" and not cleaned.get("decorator"):
            self.add_error("decorator", "Pick who is doing it, or leave the status as confirmed.")
        return cleaned


class EnquiryForm(PanelModelForm):
    class Meta:
        model = Enquiry
        fields = ["name", "phone", "email", "city", "occasion", "event_date", "message", "status"]
        widgets = {"event_date": DateInput(), "message": forms.Textarea(attrs={"rows": 5})}


class DecoratorForm(PanelModelForm):
    class Meta:
        model = Decorator
        fields = ["name", "phone", "email", "city", "rating", "is_verified", "is_active", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}


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
        fields = ["name", "city", "rating", "occasion", "package", "date", "text", "is_published", "position"]
        widgets = {"text": forms.Textarea(attrs={"rows": 5})}


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
