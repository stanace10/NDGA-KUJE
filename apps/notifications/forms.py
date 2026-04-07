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


class _StudentRecipientField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        profile = getattr(obj, "student_profile", None)
        admission_no = getattr(profile, "student_number", "") or "-"
        full_name = obj.get_full_name() or getattr(profile, "full_name", "") or obj.username
        return f"{full_name} | {admission_no}"


class _StaffRecipientField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        profile = getattr(obj, "staff_profile", None)
        staff_id = getattr(profile, "staff_id", "") or "-"
        full_name = obj.get_full_name() or obj.username
        return f"{full_name} | {staff_id}"


class MediaBroadcastForm(_StyledFormMixin, forms.Form):
    class Audience(models.TextChoices):
        EVERYONE = "EVERYONE", "Everyone"
        ALL_STUDENTS = "ALL_STUDENTS", "All Students + Parents"
        CLASS_STUDENTS = "CLASS_STUDENTS", "One Class + Parents"
        ALL_STAFF = "ALL_STAFF", "All Staff"
        SELECTED_STUDENTS = "SELECTED_STUDENTS", "Selected Student(s)"
        SELECTED_STAFF = "SELECTED_STAFF", "Selected Staff"

    audience = forms.ChoiceField(
        choices=Audience.choices,
        initial=Audience.CLASS_STUDENTS,
    )
    academic_class = forms.ModelChoiceField(
        queryset=AcademicClass.objects.filter(is_active=True, base_class__isnull=True).order_by("code"),
        required=False,
        label="Class",
    )
    student_recipients = _StudentRecipientField(
        queryset=User.objects.filter(
            is_active=True,
            student_profile__isnull=False,
        ).select_related("student_profile").order_by("student_profile__student_number", "username"),
        required=False,
        label="Students",
    )
    staff_recipients = _StaffRecipientField(
        queryset=User.objects.filter(
            is_active=True,
            staff_profile__isnull=False,
        ).select_related("staff_profile").order_by("staff_profile__staff_id", "username"),
        required=False,
        label="Staff",
    )
    subject = forms.CharField(max_length=140)
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}))
    send_portal = forms.BooleanField(required=False, initial=True)
    send_email = forms.BooleanField(required=False, initial=False)
    send_whatsapp = forms.BooleanField(required=False, initial=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_default_styles()
        self.fields["subject"].label = "Message Subject"
        self.fields["message"].label = "Message Body"
        self.fields["student_recipients"].widget.attrs["size"] = 12
        self.fields["staff_recipients"].widget.attrs["size"] = 12

    def clean_subject(self):
        return (self.cleaned_data.get("subject") or "").strip()

    def clean_message(self):
        return (self.cleaned_data.get("message") or "").strip()

    def clean(self):
        cleaned = super().clean()
        audience = cleaned.get("audience")
        class_obj = cleaned.get("academic_class")
        if audience == self.Audience.CLASS_STUDENTS and not class_obj:
            raise forms.ValidationError("Select a class for class-based broadcast.")
        if audience == self.Audience.SELECTED_STUDENTS and not cleaned.get("student_recipients"):
            raise forms.ValidationError("Select at least one student.")
        if audience == self.Audience.SELECTED_STAFF and not cleaned.get("staff_recipients"):
            raise forms.ValidationError("Select at least one staff member.")
        if not any(
            cleaned.get(flag)
            for flag in ("send_portal", "send_email", "send_whatsapp")
        ):
            raise forms.ValidationError("Select at least one delivery channel: portal, email, or WhatsApp.")
        return cleaned
