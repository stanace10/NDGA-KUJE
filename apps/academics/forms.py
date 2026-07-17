from django import forms
from django.db.models import Q

from apps.accounts.constants import ROLE_DEAN, ROLE_FORM_TEACHER, ROLE_SUBJECT_TEACHER
from apps.accounts.models import User
from apps.academics.models import (
    AcademicClass,
    AcademicSession,
    Campus,
    ClassSubject,
    FormTeacherAssignment,
    Subject,
    TeacherSubjectAssignment,
    Term,
)
from apps.setup_wizard.services import get_setup_state
from apps.academics.timetable import DAY_LABELS


def _staff_queryset_for_roles(*role_codes):
    return (
        User.objects.select_related("primary_role")
        .filter(
            Q(primary_role__code__in=role_codes)
            | Q(secondary_roles__code__in=role_codes)
        )
        .distinct()
        .order_by("username")
    )


class StyledModelForm(forms.ModelForm):
    def _style_fields(self):
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault(
                    "class", "h-4 w-4 rounded border-slate-300 text-ndga-navy"
                )
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault(
                    "class", "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
                )
            else:
                widget.attrs.setdefault(
                    "class", "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
                )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()


class CampusForm(StyledModelForm):
    class Meta:
        model = Campus
        fields = ("name", "code", "address", "is_active")
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
        }


class AcademicClassForm(StyledModelForm):
    class Meta:
        model = AcademicClass
        fields = ("code", "display_name", "base_class", "arm_name", "campus", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["base_class"].queryset = AcademicClass.objects.filter(is_active=True, base_class__isnull=True).order_by("code")
        self.fields["base_class"].required = False
        self.fields["arm_name"].required = False
        self.fields["campus"].queryset = Campus.objects.filter(is_active=True).order_by("code")
        self.fields["campus"].required = False


class SubjectForm(StyledModelForm):
    class Meta:
        model = Subject
        fields = ("name", "code", "category", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].required = False
        if not self.initial.get("category"):
            self.initial["category"] = "GENERAL"


class ClassSubjectForm(StyledModelForm):
    class Meta:
        model = ClassSubject
        fields = ("academic_class", "subject", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["academic_class"].queryset = AcademicClass.objects.filter(is_active=True, base_class__isnull=True).select_related("campus").order_by("code")
        self.fields["subject"].queryset = Subject.objects.filter(is_active=True).order_by("name")


class ClassSubjectBulkMappingForm(forms.Form):
    academic_class = forms.ModelChoiceField(queryset=AcademicClass.objects.none())
    subjects = forms.ModelMultipleChoiceField(
        queryset=Subject.objects.none(),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["academic_class"].queryset = AcademicClass.objects.filter(is_active=True, base_class__isnull=True).select_related("campus").order_by("code")
        self.fields["subjects"].queryset = Subject.objects.filter(is_active=True).order_by("name")
        self.fields["academic_class"].widget.attrs["class"] = (
            "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
        )
        self.fields["subjects"].widget.attrs["class"] = (
            "w-full min-h-44 rounded-xl border border-slate-300 px-3 py-2 text-sm"
        )

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
                mapped_subject_ids = ClassSubject.objects.filter(
                    academic_class_id=selected_class_id,
                    is_active=True,
                ).values_list("subject_id", flat=True)
                self.initial.setdefault("subjects", list(mapped_subject_ids))

    def save(self):
        academic_class = self.cleaned_data["academic_class"]
        selected_subject_ids = set(self.cleaned_data["subjects"].values_list("id", flat=True))
        existing_rows = {
            row.subject_id: row
            for row in ClassSubject.objects.filter(academic_class=academic_class)
        }

        for subject_id in selected_subject_ids:
            row = existing_rows.get(subject_id)
            if row is None:
                ClassSubject.objects.create(
                    academic_class=academic_class,
                    subject_id=subject_id,
                    is_active=True,
                )
            elif not row.is_active:
                row.is_active = True
                row.save(update_fields=["is_active", "updated_at"])

        for subject_id, row in existing_rows.items():
            if subject_id not in selected_subject_ids and row.is_active:
                row.is_active = False
                row.save(update_fields=["is_active", "updated_at"])

        return academic_class


class TeacherSubjectAssignmentForm(StyledModelForm):
    class Meta:
        model = TeacherSubjectAssignment
        fields = (
            "teacher",
            "subject",
            "academic_class",
            "session",
            "term",
            "is_active",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["teacher"].queryset = _staff_queryset_for_roles(
            ROLE_SUBJECT_TEACHER, ROLE_DEAN, ROLE_FORM_TEACHER
        )
        self.fields["academic_class"].queryset = AcademicClass.objects.filter(is_active=True, base_class__isnull=True).select_related("campus").order_by("code")
        self.fields["subject"].queryset = Subject.objects.filter(is_active=True).order_by("name")
        self.fields["session"].queryset = AcademicSession.objects.order_by("-name")
        self.fields["term"].queryset = Term.objects.select_related("session").order_by(
            "-session__name", "name"
        )
        setup_state = get_setup_state()
        if setup_state.current_session_id and not self.initial.get("session"):
            self.initial["session"] = setup_state.current_session_id
        if setup_state.current_term_id and not self.initial.get("term"):
            self.initial["term"] = setup_state.current_term_id


class FormTeacherAssignmentForm(StyledModelForm):
    class Meta:
        model = FormTeacherAssignment
        fields = ("teacher", "academic_class", "session", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["teacher"].queryset = _staff_queryset_for_roles(ROLE_FORM_TEACHER)
        self.fields["academic_class"].queryset = AcademicClass.objects.filter(is_active=True).select_related("campus", "base_class").order_by("code")
        self.fields["session"].queryset = AcademicSession.objects.order_by("-name")
        setup_state = get_setup_state()
        if setup_state.current_session_id and not self.initial.get("session"):
            self.initial["session"] = setup_state.current_session_id


class TimetableGeneratorForm(forms.Form):
    DAY_CHOICES = [(code, label) for code, label in DAY_LABELS.items()]

    session = forms.ModelChoiceField(queryset=AcademicSession.objects.none())
    term = forms.ModelChoiceField(queryset=Term.objects.none())
    days = forms.MultipleChoiceField(choices=DAY_CHOICES, initial=["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"], widget=forms.CheckboxSelectMultiple)
    periods_per_day = forms.IntegerField(min_value=1, max_value=12, initial=6)
    periods_per_assignment = forms.IntegerField(min_value=1, max_value=5, initial=2)
    room_prefix = forms.CharField(required=False, initial="Room", max_length=40)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["session"].queryset = AcademicSession.objects.order_by("-name")
        self.fields["term"].queryset = Term.objects.select_related("session").order_by("-session__name", "name")
        setup_state = get_setup_state()
        if setup_state.current_session_id and not self.initial.get("session"):
            self.initial["session"] = setup_state.current_session_id
        if setup_state.current_term_id and not self.initial.get("term"):
            self.initial["term"] = setup_state.current_term_id
        for field_name in ("session", "term", "periods_per_day", "periods_per_assignment", "room_prefix"):
            self.fields[field_name].widget.attrs.setdefault(
                "class", "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
            )
        self.fields["days"].widget.attrs.setdefault("class", "grid gap-2 sm:grid-cols-3")
