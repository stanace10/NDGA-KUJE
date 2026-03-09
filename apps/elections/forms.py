from django import forms
from django.db.models import Q

from apps.academics.models import AcademicClass, AcademicSession
from apps.accounts.models import Role, User
from apps.elections.models import Candidate, Election, Position, VoterGroup


class _StyledFormMixin:
    base_input_class = "w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm"

    def apply_default_styles(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "h-4 w-4 rounded border-slate-300")
                continue
            if isinstance(widget, forms.CheckboxSelectMultiple):
                widget.attrs.setdefault("class", "space-y-2 text-sm")
                continue
            if isinstance(widget, forms.SelectMultiple):
                widget.attrs.setdefault(
                    "class",
                    f"{self.base_input_class} min-h-28",
                )
                continue
            widget.attrs.setdefault("class", self.base_input_class)


class ElectionCreateForm(_StyledFormMixin, forms.ModelForm):
    session = forms.ModelChoiceField(
        queryset=AcademicSession.objects.order_by("-created_at"),
        required=False,
    )

    class Meta:
        model = Election
        fields = [
            "title",
            "description",
            "session",
            "starts_at",
            "ends_at",
            "allow_staff_admin_voting",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_default_styles()

    def clean_title(self):
        return (self.cleaned_data.get("title") or "").strip()


class PositionCreateForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Position
        fields = ["name", "description", "sort_order", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        self.election = kwargs.pop("election")
        super().__init__(*args, **kwargs)
        self.apply_default_styles()

    def clean_name(self):
        return (self.cleaned_data.get("name") or "").strip()

    def save(self, commit=True):
        row = super().save(commit=False)
        row.election = self.election
        if commit:
            row.save()
        return row


class CandidateCreateForm(_StyledFormMixin, forms.ModelForm):
    position = forms.ModelChoiceField(
        queryset=Position.objects.none(),
        required=True,
    )
    user = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=True,
        help_text="Choose from existing student/staff accounts. No re-registration.",
    )

    class Meta:
        model = Candidate
        fields = ["position", "user", "display_name", "manifesto", "is_active"]
        widgets = {"manifesto": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        self.election = kwargs.pop("election")
        super().__init__(*args, **kwargs)
        self.fields["position"].queryset = self.election.positions.filter(is_active=True)
        self.fields["user"].queryset = (
            User.objects.filter(
                Q(student_profile__isnull=False)
                | Q(staff_profile__isnull=False)
            )
            .distinct()
            .order_by("username")
        )
        self.apply_default_styles()

    def clean(self):
        cleaned = super().clean()
        position = cleaned.get("position")
        user = cleaned.get("user")
        if position and position.election_id != self.election.id:
            raise forms.ValidationError("Selected position does not belong to this election.")
        if position and user:
            if Candidate.objects.filter(position=position, user=user).exists():
                raise forms.ValidationError("This user is already a candidate for the selected position.")
        return cleaned


class VoterGroupCreateForm(_StyledFormMixin, forms.ModelForm):
    roles = forms.ModelMultipleChoiceField(
        queryset=Role.objects.exclude(code="IT_MANAGER").order_by("code"),
        required=False,
        help_text="Optional role filters.",
    )
    academic_classes = forms.ModelMultipleChoiceField(
        queryset=AcademicClass.objects.filter(is_active=True).order_by("code"),
        required=False,
        help_text="Optional class filters for students.",
    )
    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.order_by("username"),
        required=False,
        help_text="Optional direct user mapping.",
    )

    class Meta:
        model = VoterGroup
        fields = [
            "name",
            "description",
            "include_all_students",
            "include_all_staff",
            "roles",
            "academic_classes",
            "users",
            "is_active",
        ]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        self.election = kwargs.pop("election")
        super().__init__(*args, **kwargs)
        self.apply_default_styles()

    def clean_name(self):
        return (self.cleaned_data.get("name") or "").strip()

    def clean(self):
        cleaned = super().clean()
        include_all_students = cleaned.get("include_all_students")
        include_all_staff = cleaned.get("include_all_staff")
        roles = cleaned.get("roles")
        classes = cleaned.get("academic_classes")
        users = cleaned.get("users")
        if not include_all_students and not include_all_staff:
            if not roles and not classes and not users:
                raise forms.ValidationError(
                    "Choose at least one voter filter (roles/classes/users) or include all students/staff."
                )
        return cleaned

    def save(self, commit=True):
        row = super().save(commit=False)
        row.election = self.election
        if commit:
            row.save()
            self.save_m2m()
        return row


class PositionVoteForm(_StyledFormMixin, forms.Form):
    candidate = forms.ModelChoiceField(queryset=Candidate.objects.none(), empty_label=None)

    def __init__(self, *args, **kwargs):
        self.position = kwargs.pop("position")
        super().__init__(*args, **kwargs)
        self.fields["candidate"].queryset = (
            self.position.candidates.filter(is_active=True)
            .select_related("user", "user__student_profile", "user__staff_profile")
            .order_by("created_at", "user__username")
        )
        self.apply_default_styles()


class VoterResetForm(_StyledFormMixin, forms.Form):
    voter = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=True,
        empty_label="Select voter to reset",
        help_text="Deletes saved votes for this voter in this election only.",
    )

    def __init__(self, *args, **kwargs):
        election = kwargs.pop("election")
        super().__init__(*args, **kwargs)
        self.fields["voter"].queryset = (
            User.objects.filter(election_votes__election=election)
            .distinct()
            .order_by("username")
        )
        self.apply_default_styles()
