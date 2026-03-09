from datetime import date

from django import forms
from django.db import models

from apps.academics.models import AcademicClass, AcademicSession, FormTeacherAssignment, Term
from apps.attendance.models import Holiday, SchoolCalendar


class CalendarManagementForm(forms.Form):
    session = forms.ModelChoiceField(queryset=AcademicSession.objects.none())
    term = forms.ModelChoiceField(queryset=Term.objects.none())
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["session"].queryset = AcademicSession.objects.order_by("-name")
        self.fields["term"].queryset = Term.objects.select_related("session").order_by(
            "-session__name", "name"
        )
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "h-4 w-4 rounded border-slate-300 text-ndga-navy"
            else:
                field.widget.attrs["class"] = (
                    "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
                )

    def clean(self):
        cleaned_data = super().clean()
        session = cleaned_data.get("session")
        term = cleaned_data.get("term")
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError("End date cannot be before start date.")
        if term and session and term.session_id != session.id:
            raise forms.ValidationError("Selected term does not belong to selected session.")
        return cleaned_data


class HolidayCreateForm(forms.Form):
    class EntryMode(models.TextChoices):
        SINGLE = "SINGLE", "Single date"
        RANGE = "RANGE", "Date range"

    entry_mode = forms.ChoiceField(
        choices=EntryMode.choices,
        initial=EntryMode.SINGLE,
        label="Holiday Entry",
    )
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Required only when using date range.",
    )
    description = forms.CharField(max_length=140, required=False)
    exclude_weekends = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = (
                    "h-4 w-4 rounded border-slate-300 text-ndga-navy"
                )
            else:
                field.widget.attrs["class"] = (
                    "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
                )

    def clean(self):
        cleaned_data = super().clean()
        entry_mode = cleaned_data.get("entry_mode")
        start = cleaned_data.get("start_date")
        end = cleaned_data.get("end_date")
        if not start:
            return cleaned_data
        if entry_mode == self.EntryMode.SINGLE:
            cleaned_data["end_date"] = start
        else:
            if end is None:
                self.add_error("end_date", "End date is required for range mode.")
            elif end < start:
                self.add_error("end_date", "Range end date cannot be before start date.")
        return cleaned_data

    def clean_description(self):
        return self.cleaned_data.get("description", "").strip() or "School Holiday"


class AttendanceFilterForm(forms.Form):
    academic_class = forms.ModelChoiceField(
        queryset=AcademicClass.objects.none(),
        label="Class",
    )
    attendance_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Date",
    )

    def __init__(self, *args, **kwargs):
        assignments_qs = kwargs.pop("assignments_qs")
        super().__init__(*args, **kwargs)
        class_ids = assignments_qs.values_list("academic_class_id", flat=True).distinct()
        self.fields["academic_class"].queryset = AcademicClass.objects.filter(id__in=class_ids)
        self.fields["academic_class"].widget.attrs["class"] = (
            "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
        )
        self.fields["attendance_date"].widget.attrs["class"] = (
            "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
        )

    def selected_assignment(self, assignments_qs):
        if not self.is_valid():
            return None
        selected_class = self.cleaned_data["academic_class"]
        return assignments_qs.filter(academic_class=selected_class).first()


class HolidaySingleAddForm(forms.Form):
    holiday_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    description = forms.CharField(max_length=140, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = (
                "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
            )

    def clean_description(self):
        return self.cleaned_data.get("description", "").strip() or "School Holiday"


class HolidayRangeAddForm(forms.Form):
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    description = forms.CharField(max_length=140, required=False)
    exclude_weekends = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = (
                    "h-4 w-4 rounded border-slate-300 text-ndga-navy"
                )
            else:
                field.widget.attrs["class"] = (
                    "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
                )

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start_date")
        end = cleaned_data.get("end_date")
        if start and end and end < start:
            raise forms.ValidationError("Range end date cannot be before start date.")
        return cleaned_data

    def clean_description(self):
        return self.cleaned_data.get("description", "").strip() or "School Holiday"


class HolidayUpdateForm(forms.ModelForm):
    class Meta:
        model = Holiday
        fields = ("date", "description")
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = (
                "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
            )

    def clean_description(self):
        return self.cleaned_data.get("description", "").strip() or "School Holiday"
