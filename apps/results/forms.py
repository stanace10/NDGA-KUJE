from django import forms

from apps.results.models import ClassResultStudentRecord, StudentSubjectScore
from apps.results.services import compute_grade_payload


class StudentSubjectScoreForm(forms.ModelForm):
    class Meta:
        model = StudentSubjectScore
        fields = (
            "ca1",
            "ca2",
            "ca3",
            "ca4",
            "objective",
            "theory",
            "has_override",
            "override_reason",
        )
        widgets = {
            "override_reason": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        self.actor = kwargs.pop("actor", None)
        self.request = kwargs.pop("request", None)
        self.locked_fields = set(kwargs.pop("locked_fields", set()) or set())
        super().__init__(*args, **kwargs)

        numeric_fields = {
            "ca1": "10",
            "ca2": "10",
            "ca3": "10",
            "ca4": "10",
            "objective": "40",
            "theory": "20",
        }
        for field_name, field_max in numeric_fields.items():
            self.fields[field_name].widget.attrs.update(
                {
                    "class": (
                        "score-input w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
                    ),
                    "step": "0.01",
                    "min": "0",
                    "max": field_max,
                    "data-max": field_max,
                }
            )
            if field_name in self.locked_fields:
                self.fields[field_name].disabled = True
                self.fields[field_name].widget.attrs["title"] = "Locked by CBT auto-marking"
                self.fields[field_name].widget.attrs["class"] += " cursor-not-allowed bg-slate-100 text-slate-500"
        self.fields["has_override"].widget.attrs.update(
            {"class": "h-4 w-4 rounded border-slate-300 text-ndga-navy"}
        )
        self.fields["override_reason"].widget.attrs.update(
            {
                "class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm",
                "placeholder": "State reason for overriding score limits.",
            }
        )

    def clean(self):
        cleaned_data = super().clean()
        for field_name in self.locked_fields:
            if field_name in self.fields:
                cleaned_data[field_name] = getattr(self.instance, field_name)
        payload = compute_grade_payload(
            ca1=cleaned_data.get("ca1"),
            ca2=cleaned_data.get("ca2"),
            ca3=cleaned_data.get("ca3"),
            ca4=cleaned_data.get("ca4"),
            objective=cleaned_data.get("objective"),
            theory=cleaned_data.get("theory"),
            allow_override=cleaned_data.get("has_override", False),
            override_reason=cleaned_data.get("override_reason", ""),
            actor=self.actor,
        )
        self.computed_payload = payload
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        payload = getattr(self, "computed_payload", None)
        if payload is not None:
            instance.total_ca = payload.total_ca
            instance.total_exam = payload.total_exam
            instance.grand_total = payload.grand_total
            instance.grade = payload.grade
            if instance.has_override:
                instance.override_by = self.actor
            else:
                instance.override_by = None
        if commit:
            instance.save()
        return instance


class ResultActionForm(forms.Form):
    comment = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["comment"].widget.attrs.update(
            {
                "class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm",
                "placeholder": "Optional comment",
            }
        )


class RejectActionForm(ResultActionForm):
    comment = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["comment"].widget.attrs["placeholder"] = "Rejection reason is required."


class ClassRecordForm(forms.ModelForm):
    class Meta:
        model = ClassResultStudentRecord
        fields = ("behavior_rating", "teacher_comment")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["behavior_rating"].widget.attrs.update(
            {
                "class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm",
                "min": "1",
                "max": "5",
            }
        )
        self.fields["teacher_comment"].widget.attrs.update(
            {
                "class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm",
                "rows": 2,
                "placeholder": "Form teacher comment",
            }
        )
