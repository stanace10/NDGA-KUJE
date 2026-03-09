from __future__ import annotations

from django import forms
from django.db import models

from apps.academics.models import AcademicClass
from apps.accounts.models import User


class _StyledFormMixin:
    base_input_class = (
        "w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm "
        "focus:border-ndga-navy/60 focus:ring-4 focus:ring-ndga-navy/10"
    )

    def apply_default_styles(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "h-4 w-4 rounded border-slate-300")
                continue
            if isinstance(widget, forms.SelectMultiple):
                widget.attrs.setdefault("class", f"{self.base_input_class} min-h-28")
                continue
            widget.attrs.setdefault("class", self.base_input_class)


class MediaBroadcastForm(_StyledFormMixin, forms.Form):
    class Audience(models.TextChoices):
        ALL_STUDENTS = "ALL_STUDENTS", "All Students + Parents"
        CLASS_STUDENTS = "CLASS_STUDENTS", "One Class + Parents"
        ALL_STAFF = "ALL_STAFF", "All Staff"
        SELECTED_USERS = "SELECTED_USERS", "Selected Users"

    audience = forms.ChoiceField(
        choices=Audience.choices,
        initial=Audience.CLASS_STUDENTS,
    )
    academic_class = forms.ModelChoiceField(
        queryset=AcademicClass.objects.filter(is_active=True).order_by("code"),
        required=False,
    )
    recipients = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).order_by("username"),
        required=False,
    )
    subject = forms.CharField(max_length=140)
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}))
    send_email = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_default_styles()

    def clean_subject(self):
        return (self.cleaned_data.get("subject") or "").strip()

    def clean_message(self):
        return (self.cleaned_data.get("message") or "").strip()

    def clean(self):
        cleaned = super().clean()
        audience = cleaned.get("audience")
        class_obj = cleaned.get("academic_class")
        recipients = cleaned.get("recipients")
        if audience == self.Audience.CLASS_STUDENTS and not class_obj:
            raise forms.ValidationError("Select a class for class-based broadcast.")
        if audience == self.Audience.SELECTED_USERS and not recipients:
            raise forms.ValidationError("Select at least one recipient.")
        return cleaned
