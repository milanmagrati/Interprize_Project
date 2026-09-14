"""
Public-site forms.

They validate rather than render — the templates are hand-written markup and
stay that way — so these exist to check what arrives and to turn it into rows
the control panel works through:

* `BookingRequestForm` becomes a draft `Event` (and a `Customer`), which shows
  up on the panel's Events page flagged as new.
* `EnquiryForm` becomes an `Enquiry`, which the panel can turn into an event.
"""

from datetime import timedelta

from django import forms
from django.db import transaction
from django.utils import timezone

from .models import AddOn, Category, City, Customer, Enquiry, Event, Package, TimeSlot

#: How far ahead the site takes bookings.
BOOKING_HORIZON_DAYS = 365


class BookingRequestForm(forms.Form):
    """
    Everything a visitor fills in on /book/. Choices are checked against what is
    live right now, so a stale page cannot book a hidden setup or a full slot.
    """

    occasion = forms.CharField(required=False)
    package = forms.CharField(required=False)
    event_date = forms.DateField(error_messages={
        "required": "Pick the date of the event.",
        "invalid": "That date does not look right.",
    })
    time_slot = forms.CharField(required=False)
    city = forms.CharField(required=False)
    address = forms.CharField(
        max_length=200, error_messages={"required": "Tell us where the event is."},
    )
    guests = forms.IntegerField(
        required=False, min_value=0, max_value=100000,
        error_messages={"invalid": "Guests has to be a number."},
    )
    add_ons = forms.MultipleChoiceField(required=False)
    name = forms.CharField(max_length=120, error_messages={"required": "Tell us your name."})
    phone = forms.CharField(max_length=40, error_messages={"required": "We need a phone number to confirm."})
    email = forms.EmailField(required=False, error_messages={"invalid": "That email address does not look right."})
    notes = forms.CharField(required=False, max_length=2000)
    # Hidden from people; bots fill every field they find.
    website = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.occasions = list(Category.objects.filter(is_active=True))
        self.packages = list(Package.objects.live().select_related("category"))
        self.slots = list(TimeSlot.objects.all())
        self.cities = list(City.objects.filter(is_active=True))
        self.extras = list(AddOn.objects.filter(is_active=True))
        self.fields["add_ons"].choices = [(str(a.pk), a.name) for a in self.extras]

    # -- field checks -----------------------------------------------------

    def clean_occasion(self):
        slug = self.cleaned_data.get("occasion") or ""
        if not slug:
            return None
        match = next((o for o in self.occasions if o.slug == slug), None)
        if match is None:
            raise forms.ValidationError("That occasion is not one we book any more — pick another.")
        return match

    def clean_package(self):
        slug = self.cleaned_data.get("package") or ""
        if not slug:
            return None
        match = next((p for p in self.packages if p.slug == slug), None)
        if match is None:
            raise forms.ValidationError("That setup is no longer available — pick another, or leave it to us.")
        return match

    def clean_event_date(self):
        day = self.cleaned_data["event_date"]
        today = timezone.localdate()
        if day < today:
            raise forms.ValidationError("That date has already gone — pick one from today on.")
        if day > today + timedelta(days=BOOKING_HORIZON_DAYS):
            raise forms.ValidationError("We take bookings up to a year ahead. Send an enquiry for anything later.")
        return day

    def clean_time_slot(self):
        value = self.cleaned_data.get("time_slot") or ""
        if not value:
            return ""
        match = next((s for s in self.slots if s.value == value), None)
        if match is None:
            raise forms.ValidationError("Pick one of the arrival windows shown.")
        if not match.available:
            raise forms.ValidationError(f"{match.label} is full — pick another window.")
        return match.label

    def clean_city(self):
        value = (self.cleaned_data.get("city") or "").strip()
        if not value:
            return ""
        match = next((c for c in self.cities if value in (c.slug, c.name)), None)
        return match.name if match else value[:80]

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if len(Customer.phone_digits(phone)) < 10:
            raise forms.ValidationError("Enter a 10-digit phone number, so we can call to confirm.")
        return phone

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("website"):
            raise forms.ValidationError("Something went wrong — please try again.")
        occasion, package = cleaned.get("occasion"), cleaned.get("package")
        if not occasion and package and "occasion" not in self.errors:
            # A setup already says what the occasion is.
            cleaned["occasion"] = occasion = package.category
        if not occasion and "occasion" not in self.errors:
            self.add_error("occasion", "Pick what you are celebrating.")
        elif occasion and package and package.category_id != occasion.pk:
            self.add_error("package", f"{package.title} is a {package.category.name} setup — pick that occasion, or another setup.")
        return cleaned

    # -- what the page shows ---------------------------------------------

    @property
    def chosen_extras(self):
        picked = set(self.cleaned_data.get("add_ons") or [])
        return [a for a in self.extras if str(a.pk) in picked]

    @property
    def estimate(self):
        package = self.cleaned_data.get("package")
        base = package.price if package else 0
        return base + sum(a.price for a in self.chosen_extras)

    # -- the booking ------------------------------------------------------

    def save(self):
        data = self.cleaned_data
        occasion, package = data["occasion"], data.get("package")
        city = data.get("city") or ""
        location = data["address"].strip()
        if city and city.lower() not in location.lower():
            location = f"{location}, {city}"

        first_name = data["name"].split()[0]
        title = package.title if package else f"{occasion.name} celebration"
        extras = [{"name": a.name, "price": a.price} for a in self.chosen_extras]

        with transaction.atomic():
            customer = Customer.for_booking(
                data["name"], data["phone"], email=data.get("email") or "", address=location,
            )
            notes = data.get("notes", "").strip()
            if customer.name.lower() != data["name"].lower():
                notes = f"Booked as {data['name']}.\n{notes}".strip()
            event = Event.objects.create(
                name=f"{title} — {first_name}"[:160],
                customer=customer,
                event_date=data["event_date"],
                time_slot=data.get("time_slot") or "",
                location=location[:200],
                guests=data.get("guests") or 0,
                occasion=occasion,
                package=package,
                revenue=self.estimate,
                notes=notes,
                source="website",
                is_new=True,
                booked_extras=extras,
            )
        return event


class TrackBookingForm(forms.Form):
    number = forms.CharField(max_length=20, error_messages={"required": "Enter your booking number."})
    phone = forms.CharField(max_length=40, error_messages={"required": "Enter the phone number you booked with."})

    def clean_number(self):
        value = self.cleaned_data["number"].strip().upper().replace(" ", "")
        if value.isdigit():
            value = f"EVT-{int(value):05d}"
        return value

    def clean(self):
        cleaned = super().clean()
        number, phone = cleaned.get("number"), cleaned.get("phone")
        if number and phone:
            event = Event.objects.select_related("customer").filter(number=number).first()
            if event is None or not event.matches_phone(phone):
                # One message for both, so the form cannot be used to find numbers.
                raise forms.ValidationError(
                    "No booking matches that number and phone. Check both, or call us."
                )
            cleaned["event"] = event
        return cleaned


class EnquiryForm(forms.ModelForm):
    """A question about an occasion or a setup, from any page that carries the form."""

    package = forms.CharField(required=False)
    website = forms.CharField(required=False)

    class Meta:
        model = Enquiry
        fields = ["name", "email", "phone", "city", "occasion", "event_date", "guests", "message"]
        error_messages = {
            "name": {"required": "Tell us your name."},
            "email": {"invalid": "That email address does not look right."},
            "event_date": {"invalid": "That date does not look right."},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone"].required = True
        self.fields["phone"].error_messages["required"] = "Leave a phone number so we can reply."
        self.fields["guests"].required = False

    def clean_occasion(self):
        """
        The <select> posts an occasion slug. Store the readable name instead, so
        the panel's list is legible without joining anything.
        """
        value = (self.cleaned_data.get("occasion") or "").strip()
        if not value:
            return ""
        if value == "other":
            return "Something else"
        match = Category.objects.filter(slug=value).first()
        return match.name if match else value.replace("-", " ").title()[:120]

    def clean_package(self):
        slug = (self.cleaned_data.get("package") or "").strip()
        return Package.objects.live().filter(slug=slug).first() if slug else None

    def clean_guests(self):
        return self.cleaned_data.get("guests") or 0

    def clean_event_date(self):
        day = self.cleaned_data.get("event_date")
        if day and day < timezone.localdate():
            raise forms.ValidationError("That date has already gone.")
        return day

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("website"):
            raise forms.ValidationError("Something went wrong — please try again.")
        package = cleaned.get("package")
        if package and not cleaned.get("occasion"):
            cleaned["occasion"] = package.category.name
        return cleaned

    def save(self, commit=True):
        enquiry = super().save(commit=False)
        enquiry.package = self.cleaned_data.get("package")
        if commit:
            enquiry.save()
        return enquiry
