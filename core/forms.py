"""
Public-site forms.

Only one so far: the enquiry form shared by the homepage and the contact page.
It validates rather than renders — `_inquiry_form.html` is hand-written markup
and stays that way, so this form exists to check what arrives and to turn it
into an `Enquiry` the panel can work through.
"""

from django import forms

from .models import Category, Enquiry


class EnquiryForm(forms.ModelForm):
    class Meta:
        model = Enquiry
        fields = ["name", "email", "phone", "city", "occasion", "event_date", "message"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone"].required = True

    def clean_occasion(self):
        """
        The <select> posts a category slug. Store the readable name instead, so
        the panel's list is legible without joining anything.
        """
        value = (self.cleaned_data.get("occasion") or "").strip()
        if not value:
            return ""
        match = Category.objects.filter(slug=value).first()
        return match.name if match else value.replace("-", " ").title()

    def clean(self):
        cleaned = super().clean()
        if not (cleaned.get("email") or cleaned.get("phone")):
            raise forms.ValidationError(
                "Leave a phone number or an email address, or we cannot reply."
            )
        return cleaned
