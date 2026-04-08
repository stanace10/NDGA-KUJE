from datetime import timedelta

from django import forms
from django.db import models

from apps.academics.models import (
    AcademicClass,
    AcademicSession,
    ClassSubject,
    GradeScale,
    Subject,
    Term,
)
from apps.setup_wizard.services import (
    parse_bulk_lines,
    parse_holiday_lines,
    readable_term_choices,
)


class SessionSetupForm(forms.Form):
    session_name = forms.CharField(max_length=20, label="Session")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["session_name"].widget.attrs.update(
            {
                "class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm",
                "placeholder": "2025/2026",
            }
        )

    def clean_session_name(self):
        value = self.cleaned_data["session_name"].strip()
        if "/" not in value:
            raise forms.ValidationError("Session must be in format like 2025/2026.")
        return value


class TermSetupForm(forms.Form):
    term_name = forms.ChoiceField(choices=readable_term_choices(), label="Current Term")

    def __init__(self, *args, **kwargs):
        session = kwargs.pop("session", None)
        super().__init__(*args, **kwargs)
        if session is not None:
            choices = [
                (term.name, term.get_name_display())
                for term in session.terms.order_by("name")
            ]
            if choices:
                self.fields["term_name"].choices = choices
        self.fields["term_name"].widget.attrs.update(
            {
                "class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm",
            }
        )


class CalendarSetupForm(forms.Form):
    class HolidayEntryMode(models.TextChoices):
        NONE = "NONE", "No holiday now"
        SINGLE = "SINGLE", "Single date"
        RANGE = "RANGE", "Date range"

    start_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Term Start Date",
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Term End Date",
    )
    holiday_entry_mode = forms.ChoiceField(
        choices=HolidayEntryMode.choices,
        initial=HolidayEntryMode.NONE,
        required=False,
        label="Holiday Entry",
    )
    holiday_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Holiday Date",
    )
    holiday_range_start = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Holiday Range Start",
    )
    holiday_range_end = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Holiday Range End",
    )
    holiday_description = forms.CharField(
        max_length=140,
        required=False,
        label="Holiday Description",
        initial="School Holiday",
    )
    holidays = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 5}),
        help_text="Optional extra lines: one per line as YYYY-MM-DD|Description",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ("start_date", "end_date"):
            self.fields[field_name].widget.attrs.update(
                {"class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"}
            )
        self.fields["holidays"].widget.attrs.update(
            {
                "class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm",
                "placeholder": "2026-01-15|Founder's Day\n2026-02-10|Mid-term Break",
            }
        )
        for field_name in (
            "holiday_entry_mode",
            "holiday_date",
            "holiday_range_start",
            "holiday_range_end",
            "holiday_description",
        ):
            self.fields[field_name].widget.attrs.update(
                {"class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"}
            )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError("End date cannot be before start date.")
        holidays_raw = cleaned_data.get("holidays", "")
        entry_mode = cleaned_data.get("holiday_entry_mode") or self.HolidayEntryMode.NONE
        description = (cleaned_data.get("holiday_description") or "").strip() or "School Holiday"

        if entry_mode == self.HolidayEntryMode.SINGLE:
            holiday_date = cleaned_data.get("holiday_date")
            if not holiday_date:
                self.add_error("holiday_date", "Select holiday date.")
            else:
                holidays_raw = (
                    f"{holidays_raw.strip()}\n{holiday_date.isoformat()}|{description}".strip()
                )
        elif entry_mode == self.HolidayEntryMode.RANGE:
            range_start = cleaned_data.get("holiday_range_start")
            range_end = cleaned_data.get("holiday_range_end")
            if not range_start:
                self.add_error("holiday_range_start", "Select range start date.")
            if not range_end:
                self.add_error("holiday_range_end", "Select range end date.")
            if range_start and range_end and range_end < range_start:
                self.add_error("holiday_range_end", "Range end date cannot be before start date.")
            if range_start and range_end:
                for day in _date_range(range_start, range_end):
                    holidays_raw = (
                        f"{holidays_raw.strip()}\n{day.isoformat()}|{description}".strip()
                    )

        try:
            cleaned_data["parsed_holidays"] = parse_holiday_lines(holidays_raw)
        except ValueError as exc:
            raise forms.ValidationError(
                "Holiday lines must follow YYYY-MM-DD|Description."
            ) from exc

        if start_date:
            for row in cleaned_data["parsed_holidays"]:
                if row.date_value < start_date:
                    raise forms.ValidationError(
                        "Holiday dates must fall on or after the term start date."
                    )
                if end_date and row.date_value > end_date:
                    raise forms.ValidationError(
                        "Holiday dates must fall within term start and end dates."
                    )
        return cleaned_data


class ClassSetupForm(forms.Form):
    class_codes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 7}),
        help_text="Enter classes using newline or comma. Example: JS1A, JS1B, SS1A.",
        label="Classes",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["class_codes"].widget.attrs.update(
            {
                "class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm",
                "placeholder": "JS1A, JS1B, JS2A, SS1A",
            }
        )

    def clean_class_codes(self):
        rows = parse_bulk_lines(self.cleaned_data["class_codes"])
        if not rows:
            raise forms.ValidationError("Add at least one class.")
        return rows


class SubjectSetupForm(forms.Form):
    subjects = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 8}),
        help_text=(
            "Enter subjects using newline or comma. Format: Subject Name|CODE|CATEGORY "
            "(example: Physics|PHY|SCIENCE). CATEGORY is optional."
        ),
        label="Subjects",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["subjects"].widget.attrs.update(
            {
                "class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm",
                "placeholder": "Mathematics|MTH|SCIENCE, Literature|LIT|ARTS, Biology",
            }
        )

    def clean_subjects(self):
        rows = parse_bulk_lines(self.cleaned_data["subjects"])
        if not rows:
            raise forms.ValidationError("Add at least one subject.")
        return rows


class ClassSubjectMappingForm(forms.Form):
    academic_class = forms.ModelChoiceField(
        queryset=AcademicClass.objects.none(),
        label="Class",
    )
    subjects = forms.ModelMultipleChoiceField(
        queryset=Subject.objects.none(),
        required=False,
        label="Subjects Offered By Selected Class",
    )

    def __init__(self, *args, **kwargs):
        self.classes = list(
            kwargs.pop(
                "classes",
                AcademicClass.objects.filter(is_active=True).order_by("code"),
            )
        )
        self.subjects = list(
            kwargs.pop(
                "subjects",
                Subject.objects.filter(is_active=True).order_by("name"),
            )
        )
        super().__init__(*args, **kwargs)

        self.fields["academic_class"].queryset = AcademicClass.objects.filter(
            id__in=[row.id for row in self.classes]
        ).order_by("code")
        self.fields["subjects"].queryset = Subject.objects.filter(
            id__in=[row.id for row in self.subjects]
        ).order_by("name")
        self.fields["academic_class"].widget.attrs.update(
            {"class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"}
        )
        self.fields["subjects"].widget.attrs.update(
            {"class": "w-full min-h-44 rounded-xl border border-slate-300 px-3 py-2 text-sm"}
        )
        self.fields["subjects"].help_text = "Select all subjects offered by the selected class."

        selected_class = None
        if self.is_bound:
            selected_class = self.data.get("academic_class")
        else:
            selected_class = self.initial.get("academic_class")

        if selected_class:
            try:
                selected_class_id = int(selected_class)
            except (TypeError, ValueError):
                selected_class_id = None
            if selected_class_id:
                mapped_ids = list(
                    ClassSubject.objects.filter(
                        academic_class_id=selected_class_id,
                        is_active=True,
                    ).values_list("subject_id", flat=True)
                )
                self.initial.setdefault("subjects", mapped_ids)

    def clean(self):
        cleaned_data = super().clean()
        if not self.classes:
            raise forms.ValidationError("Add classes first before mapping subjects.")
        if not self.subjects:
            raise forms.ValidationError("Add subjects first before mapping subjects.")

        academic_class = cleaned_data.get("academic_class")
        selected_subjects = cleaned_data.get("subjects") or []
        if not academic_class:
            raise forms.ValidationError("Select a class to map subjects.")
        mapping = {academic_class.id: [row.id for row in selected_subjects]}
        cleaned_data["class_subject_map"] = mapping
        return cleaned_data


def _date_range(start_date, end_date):
    day = start_date
    while day <= end_date:
        yield day
        day = day + timedelta(days=1)


class GradeScaleDefaultsForm(forms.Form):
    DEFAULT_SCALE = (
        ("A", 70, 100, 1),
        ("B", 60, 69, 2),
        ("C", 50, 59, 3),
        ("D", 40, 49, 4),
        ("F", 0, 39, 5),
    )
    GRADE_ORDER = tuple(row[0] for row in DEFAULT_SCALE)

    apply_defaults = forms.BooleanField(
        required=False,
        initial=False,
        label="Reset grade ranges to NDGA defaults",
    )
    a_min = forms.IntegerField(min_value=0, max_value=100, label="A Minimum", required=False)
    a_max = forms.IntegerField(min_value=0, max_value=100, label="A Maximum", required=False)
    b_min = forms.IntegerField(min_value=0, max_value=100, label="B Minimum", required=False)
    b_max = forms.IntegerField(min_value=0, max_value=100, label="B Maximum", required=False)
    c_min = forms.IntegerField(min_value=0, max_value=100, label="C Minimum", required=False)
    c_max = forms.IntegerField(min_value=0, max_value=100, label="C Maximum", required=False)
    d_min = forms.IntegerField(min_value=0, max_value=100, label="D Minimum", required=False)
    d_max = forms.IntegerField(min_value=0, max_value=100, label="D Maximum", required=False)
    f_min = forms.IntegerField(min_value=0, max_value=100, label="F Minimum", required=False)
    f_max = forms.IntegerField(min_value=0, max_value=100, label="F Maximum", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        default_map = {grade: {"min": min_score, "max": max_score} for grade, min_score, max_score, _ in self.DEFAULT_SCALE}
        existing_scales = {
            row.grade: row
            for row in GradeScale.objects.filter(is_default=True)
        }
        for grade in self.GRADE_ORDER:
            row = existing_scales.get(grade)
            values = {
                "min": row.min_score if row else default_map[grade]["min"],
                "max": row.max_score if row else default_map[grade]["max"],
            }
            self.fields[f"{grade.lower()}_min"].initial = values["min"]
            self.fields[f"{grade.lower()}_max"].initial = values["max"]
        self.fields["apply_defaults"].widget.attrs.update(
            {"class": "h-4 w-4 rounded border-slate-300 text-ndga-navy"}
        )
        for grade in self.GRADE_ORDER:
            self.fields[f"{grade.lower()}_min"].widget.attrs.update(
                {"class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"}
            )
            self.fields[f"{grade.lower()}_max"].widget.attrs.update(
                {"class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"}
            )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("apply_defaults"):
            grade_ranges = {}
            for grade, min_score, max_score, sort_order in self.DEFAULT_SCALE:
                grade_ranges[grade] = {
                    "min_score": min_score,
                    "max_score": max_score,
                    "sort_order": sort_order,
                }
            cleaned_data["grade_ranges"] = grade_ranges
            return cleaned_data

        grade_ranges = {}
        previous_grade = None
        for sort_order, grade in enumerate(self.GRADE_ORDER, start=1):
            min_key = f"{grade.lower()}_min"
            max_key = f"{grade.lower()}_max"
            min_score = cleaned_data.get(min_key)
            max_score = cleaned_data.get(max_key)
            if min_score is None or max_score is None:
                self.add_error(min_key, f"Enter {grade} minimum.")
                self.add_error(max_key, f"Enter {grade} maximum.")
                continue
            if min_score > max_score:
                self.add_error(min_key, f"{grade} minimum cannot exceed maximum.")
            grade_ranges[grade] = {
                "min_score": min_score,
                "max_score": max_score,
                "sort_order": sort_order,
            }
            if previous_grade:
                previous_min = grade_ranges[previous_grade]["min_score"]
                expected_max = previous_min - 1
                if max_score != expected_max:
                    self.add_error(
                        max_key,
                        f"{grade} maximum must be {expected_max} to keep a continuous scale.",
                    )
            previous_grade = grade

        if not self.errors and all(grade in grade_ranges for grade in self.GRADE_ORDER):
            if grade_ranges["A"]["max_score"] != 100:
                self.add_error("a_max", "A maximum must be 100.")
            if grade_ranges["F"]["min_score"] != 0:
                self.add_error("f_min", "F minimum must be 0.")

        cleaned_data["grade_ranges"] = grade_ranges
        return cleaned_data


class SetupFinalizeForm(forms.Form):
    confirm_finalize = forms.BooleanField(
        required=True,
        label="I confirm setup is complete and ready for institution-wide use.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["confirm_finalize"].widget.attrs.update(
            {"class": "h-4 w-4 rounded border-slate-300 text-ndga-navy"}
        )


class SessionTermContextForm(forms.Form):
    session = forms.ModelChoiceField(queryset=AcademicSession.objects.none())
    term = forms.ModelChoiceField(queryset=Term.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["session"].queryset = AcademicSession.objects.order_by("-name")
        self.fields["term"].queryset = Term.objects.select_related("session").order_by(
            "-session__name",
            "name",
        )
        for field in self.fields.values():
            field.widget.attrs.update(
                {
                    "class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm",
                }
            )

    def clean(self):
        cleaned_data = super().clean()
        session = cleaned_data.get("session")
        term = cleaned_data.get("term")
        if session and term and term.session_id != session.id:
            raise forms.ValidationError("Selected term does not belong to selected session.")
        return cleaned_data


class EndTermProgressForm(forms.Form):
    confirm_end_term = forms.BooleanField(
        required=True,
        label="I confirm current term activities are closed and ready to move forward.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["confirm_end_term"].widget.attrs.update(
            {"class": "h-4 w-4 rounded border-slate-300 text-ndga-navy"}
        )


class EndSessionProgressForm(forms.Form):
    confirm_end_session = forms.BooleanField(
        required=True,
        label=(
            "I confirm Third Term is completed, results are published, and "
            "session closure/promotion should proceed."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["confirm_end_session"].widget.attrs.update(
            {"class": "h-4 w-4 rounded border-slate-300 text-ndga-navy"}
        )
