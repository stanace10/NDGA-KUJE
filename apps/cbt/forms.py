from decimal import Decimal, InvalidOperation

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.academics.models import TeacherSubjectAssignment
from apps.cbt.models import (
    CBTExamStatus,
    CBTExamType,
    CBTQuestionDifficulty,
    CBTQuestionType,
    CBTSimulationCallbackType,
    CBTSimulationScoreMode,
    CBTSimulationSourceProvider,
    CBTSimulationToolCategory,
    CBTSimulationWrapperStatus,
    CBTWritebackTarget,
    CorrectAnswer,
    Exam,
    ExamBlueprint,
    ExamQuestion,
    ExamSimulation,
    Option,
    Question,
    QuestionBank,
    SimulationWrapper,
)
from apps.cbt.services import (
    authoring_assignment_queryset,
    has_completed_ca_target_exam,
    authoring_question_bank_queryset,
    recommended_simulation_queryset,
    store_simulation_bundle,
)


def _style_fields(form):
    base = (
        "w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm "
        "focus:border-ndga-navy/60 focus:ring-4 focus:ring-ndga-navy/10"
    )
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, forms.CheckboxInput):
            widget.attrs.setdefault("class", "h-4 w-4 rounded border-slate-300 text-ndga-navy")
            continue
        if isinstance(widget, forms.SelectMultiple):
            widget.attrs.setdefault("class", f"{base} min-h-32")
            continue
        widget.attrs.setdefault("class", base)


def _as_decimal(value, fallback=Decimal("0.00")):
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return fallback


def _uses_ss3_mock_exam_totals(assignment):
    class_code = (
        getattr(getattr(assignment, "academic_class", None), "code", "") or ""
    ).strip().upper()
    return class_code.startswith("SS3")


class QuestionBankCreateForm(forms.ModelForm):
    assignment = forms.ModelChoiceField(
        queryset=TeacherSubjectAssignment.objects.none(),
        label="Class & Subject",
    )

    class Meta:
        model = QuestionBank
        fields = ("assignment", "name", "description")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        self.actor = kwargs.pop("actor", None)
        super().__init__(*args, **kwargs)
        self.fields["assignment"].queryset = authoring_assignment_queryset(
            self.actor,
            include_all_periods=True,
        )
        self.fields["assignment"].label_from_instance = (
            lambda row: f"{row.academic_class.code} - {row.subject.name} ({row.session.name} / {row.term.get_name_display()})"
        )
        _style_fields(self)

    def clean_name(self):
        return (self.cleaned_data.get("name") or "").strip()

    def save(self, commit=True):
        assignment = self.cleaned_data["assignment"]
        instance = super().save(commit=False)
        instance.owner = self.actor
        instance.assignment = assignment
        instance.subject = assignment.subject
        instance.academic_class = assignment.academic_class
        instance.session = assignment.session
        instance.term = assignment.term
        instance.is_active = True
        instance.full_clean()
        if commit:
            instance.save()
        return instance


class QuestionAuthoringForm(forms.Form):
    question_bank = forms.ModelChoiceField(queryset=QuestionBank.objects.none(), label="Question Bank")
    question_type = forms.ChoiceField(
        choices=[
            (CBTQuestionType.OBJECTIVE, "Objective"),
            (CBTQuestionType.SHORT_ANSWER, "Short Answer"),
        ],
        initial=CBTQuestionType.OBJECTIVE,
    )
    stem = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}), label="Question Text")
    topic = forms.CharField(max_length=120, required=False)
    difficulty = forms.ChoiceField(choices=CBTQuestionDifficulty.choices)
    marks = forms.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal("0.01"), initial=Decimal("1.00"))
    option_a = forms.CharField(max_length=400, required=False, label="Option A")
    option_b = forms.CharField(max_length=400, required=False, label="Option B")
    option_c = forms.CharField(max_length=400, required=False, label="Option C")
    option_d = forms.CharField(max_length=400, required=False, label="Option D")
    correct_label = forms.ChoiceField(choices=[("A", "A"), ("B", "B"), ("C", "C"), ("D", "D")], required=False)

    def __init__(self, *args, **kwargs):
        self.actor = kwargs.pop("actor", None)
        self.question = kwargs.pop("question", None)
        super().__init__(*args, **kwargs)
        self.fields["question_bank"].queryset = authoring_question_bank_queryset(self.actor)
        if self.question is not None:
            self.initial.update(
                {
                    "question_bank": self.question.question_bank_id,
                    "question_type": self.question.question_type,
                    "stem": self.question.stem,
                    "topic": self.question.topic,
                    "difficulty": self.question.difficulty,
                    "marks": self.question.marks,
                }
            )
            option_map = {opt.label: opt.option_text for opt in self.question.options.all()}
            self.initial["option_a"] = option_map.get("A", "")
            self.initial["option_b"] = option_map.get("B", "")
            self.initial["option_c"] = option_map.get("C", "")
            self.initial["option_d"] = option_map.get("D", "")
            answer = getattr(self.question, "correct_answer", None)
            if answer:
                selected = answer.correct_options.order_by("sort_order", "label").first()
                if selected:
                    self.initial["correct_label"] = selected.label
        _style_fields(self)

    def clean_stem(self):
        value = (self.cleaned_data.get("stem") or "").strip()
        if not value:
            raise forms.ValidationError("Question text is required.")
        return value

    def clean_topic(self):
        return (self.cleaned_data.get("topic") or "").strip()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("question_type") == CBTQuestionType.OBJECTIVE:
            options = {
                "A": (cleaned.get("option_a") or "").strip(),
                "B": (cleaned.get("option_b") or "").strip(),
                "C": (cleaned.get("option_c") or "").strip(),
                "D": (cleaned.get("option_d") or "").strip(),
            }
            provided = [label for label, text in options.items() if text]
            if len(provided) < 2:
                raise forms.ValidationError("Provide at least two options for objective question.")
            correct_label = (cleaned.get("correct_label") or "").strip().upper()
            if correct_label not in provided:
                cleaned["correct_label"] = provided[0]
            cleaned["_option_payload"] = options
        else:
            cleaned["_option_payload"] = {}
            cleaned["correct_label"] = ""
        return cleaned

    def save(self):
        bank = self.cleaned_data["question_bank"]
        question = self.question or Question(created_by=self.actor)
        question.question_bank = bank
        question.subject = bank.subject
        question.question_type = self.cleaned_data["question_type"]
        question.stem = self.cleaned_data["stem"]
        question.topic = self.cleaned_data["topic"]
        question.difficulty = self.cleaned_data["difficulty"]
        question.marks = self.cleaned_data["marks"]
        question.source_type = Question.SourceType.MANUAL
        question.source_reference = question.source_reference or "CBT_AUTHORING"
        question.is_active = True
        question.full_clean()
        question.save()

        if question.question_type == CBTQuestionType.OBJECTIVE:
            payload = self.cleaned_data.get("_option_payload", {})
            for label, sort_order in (("A", 1), ("B", 2), ("C", 3), ("D", 4)):
                text = payload.get(label, "")
                if text:
                    Option.objects.update_or_create(
                        question=question,
                        label=label,
                        defaults={"option_text": text, "sort_order": sort_order},
                    )
                else:
                    Option.objects.filter(question=question, label=label).delete()
            answer, _ = CorrectAnswer.objects.get_or_create(question=question)
            answer.is_finalized = True
            answer.save(update_fields=["is_finalized", "updated_at"])
            answer.correct_options.set(question.options.filter(label=self.cleaned_data.get("correct_label") or "A"))
        else:
            question.options.all().delete()
            answer, _ = CorrectAnswer.objects.get_or_create(question=question)
            answer.is_finalized = False
            answer.save(update_fields=["is_finalized", "updated_at"])
            answer.correct_options.clear()

        return question

class ExamCreateForm(forms.Form):
    FLOW_OBJECTIVE_ONLY = "OBJECTIVE_ONLY"
    FLOW_OBJECTIVE_THEORY = "OBJECTIVE_THEORY"
    FLOW_THEORY_ONLY = "THEORY_ONLY"
    FLOW_SIMULATION = "SIMULATION"

    AUTHORING_MODE_SCRATCH = "SCRATCH"
    AUTHORING_MODE_UPLOAD = "UPLOAD"
    AUTHORING_MODE_AI = "AI"

    THEORY_RESPONSE_MODE_TYPING = "TYPING"
    THEORY_RESPONSE_MODE_PAPER = "PAPER"
    CALCULATOR_NONE = "NONE"
    CALCULATOR_BASIC = "BASIC"
    CALCULATOR_SCIENTIFIC = "SCIENTIFIC"
    CALCULATOR_GRAPH = "GRAPH"

    assignment = forms.ModelChoiceField(queryset=TeacherSubjectAssignment.objects.none(), label="Class & Subject")
    title = forms.CharField(max_length=200, required=False)
    exam_type = forms.ChoiceField(
        choices=[
            (CBTExamType.CA, "CA"),
            (CBTExamType.EXAM, "Exam"),
            (CBTExamType.PRACTICAL, "Practical"),
            (CBTExamType.FREE_TEST, "Free Test"),
        ],
        initial=CBTExamType.CA,
    )
    authoring_mode = forms.ChoiceField(
        choices=[
            (AUTHORING_MODE_SCRATCH, "Create From Scratch"),
            (AUTHORING_MODE_UPLOAD, "Upload/Paste Document"),
            (AUTHORING_MODE_AI, "AI Draft"),
        ],
        initial=AUTHORING_MODE_SCRATCH,
        required=False,
    )
    duration_minutes = forms.IntegerField(min_value=1, max_value=600, initial=60)
    schedule_start = forms.DateTimeField(
        required=False,
        label="Start time",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    schedule_end = forms.DateTimeField(
        required=False,
        label="End time",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    flow_type = forms.ChoiceField(
        choices=[
            (FLOW_OBJECTIVE_THEORY, "Objective + Theory"),
            (FLOW_SIMULATION, "Simulation"),
        ],
        initial=FLOW_OBJECTIVE_THEORY,
        required=False,
    )
    ca_target = forms.ChoiceField(
        choices=[
            ("", "Select CA Target"),
            (CBTWritebackTarget.CA1, "CA1"),
            (CBTWritebackTarget.CA2, "CA2 / CA3 (Joint)"),
            (CBTWritebackTarget.CA3, "CA3"),
            (CBTWritebackTarget.CA4, "CA4"),
        ],
        required=False,
    )
    objective_question_count = forms.IntegerField(min_value=0, max_value=400, initial=10, required=False)
    theory_question_count = forms.IntegerField(min_value=0, max_value=200, initial=3, required=False)
    theory_response_mode = forms.ChoiceField(
        choices=[
            (THEORY_RESPONSE_MODE_TYPING, "Student types in CBT"),
            (THEORY_RESPONSE_MODE_PAPER, "Display only, student answers on paper"),
        ],
        required=False,
        initial=THEORY_RESPONSE_MODE_PAPER,
    )
    manual_score_split = forms.BooleanField(required=False)
    objective_target_max = forms.DecimalField(max_digits=7, decimal_places=2, required=False)
    theory_target_max = forms.DecimalField(max_digits=7, decimal_places=2, required=False)
    max_attempts = forms.IntegerField(min_value=1, max_value=10, initial=1)
    shuffle_questions = forms.BooleanField(required=False, initial=True)
    shuffle_options = forms.BooleanField(required=False, initial=True)
    instructions = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    calculator_mode = forms.ChoiceField(
        choices=[
            (CALCULATOR_NONE, "No Calculator"),
            (CALCULATOR_BASIC, "Basic Calculator"),
            (CALCULATOR_SCIENTIFIC, "Scientific Calculator"),
            (CALCULATOR_GRAPH, "Graph + Scientific"),
        ],
        initial=CALCULATOR_NONE,
        required=False,
    )
    description = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        self.actor = kwargs.pop("actor", None)
        super().__init__(*args, **kwargs)
        self.fields["assignment"].queryset = authoring_assignment_queryset(self.actor, include_all_periods=True)
        self.fields["assignment"].label_from_instance = (
            lambda row: f"{row.academic_class.code} - {row.subject.name} ({row.session.name} / {row.term.get_name_display()})"
        )
        _style_fields(self)

    @staticmethod
    def _default_section_totals(*, exam_type, flow_type, assignment=None):
        if exam_type == CBTExamType.FREE_TEST:
            return Decimal("100.00"), Decimal("0.00")
        if exam_type in {CBTExamType.CA, CBTExamType.PRACTICAL}:
            if flow_type == ExamCreateForm.FLOW_OBJECTIVE_THEORY:
                return Decimal("5.00"), Decimal("5.00")
            return Decimal("10.00"), Decimal("0.00")
        if exam_type == CBTExamType.EXAM:
            if _uses_ss3_mock_exam_totals(assignment):
                if flow_type == ExamCreateForm.FLOW_OBJECTIVE_THEORY:
                    return Decimal("40.00"), Decimal("60.00")
                if flow_type == ExamCreateForm.FLOW_THEORY_ONLY:
                    return Decimal("0.00"), Decimal("60.00")
                return Decimal("40.00"), Decimal("0.00")
            if flow_type == ExamCreateForm.FLOW_OBJECTIVE_THEORY:
                return Decimal("20.00"), Decimal("40.00")
            if flow_type == ExamCreateForm.FLOW_THEORY_ONLY:
                return Decimal("0.00"), Decimal("40.00")
            return Decimal("20.00"), Decimal("0.00")
        return Decimal("10.00"), Decimal("0.00")

    @staticmethod
    def _auto_generated_title(*, assignment, exam_type):
        if assignment is None:
            return ""
        subject_label = (getattr(assignment.subject, "code", "") or "").strip() or (
            getattr(assignment.subject, "name", "") or "CBT"
        ).strip()
        class_code = (getattr(assignment.academic_class, "code", "") or "").strip()
        term_label = assignment.term.get_name_display() if getattr(assignment, "term_id", None) else "Term"
        session_label = (getattr(assignment.session, "name", "") or "").strip()
        exam_label = (exam_type or "CA").strip().upper()
        parts = [subject_label, class_code, session_label, term_label, exam_label]
        title = " ".join([part for part in parts if part]).strip()
        return title[:200]

    def clean_title(self):
        return (self.cleaned_data.get("title") or "").strip()

    def clean_description(self):
        return (self.cleaned_data.get("description") or "").strip()

    def clean_instructions(self):
        return (self.cleaned_data.get("instructions") or "").strip()

    def clean_calculator_mode(self):
        value = (self.cleaned_data.get("calculator_mode") or self.CALCULATOR_NONE).strip().upper()
        allowed = {
            self.CALCULATOR_NONE,
            self.CALCULATOR_BASIC,
            self.CALCULATOR_SCIENTIFIC,
            self.CALCULATOR_GRAPH,
        }
        if value not in allowed:
            return self.CALCULATOR_NONE
        return value

    def clean(self):
        cleaned = super().clean()
        assignment = cleaned.get("assignment")
        exam_type = cleaned.get("exam_type")
        authoring_mode = cleaned.get("authoring_mode") or self.AUTHORING_MODE_SCRATCH
        flow_type = cleaned.get("flow_type") or self.FLOW_OBJECTIVE_THEORY
        raw_objective_count = cleaned.get("objective_question_count")
        raw_theory_count = cleaned.get("theory_question_count")
        objective_count = int(raw_objective_count or 0)
        theory_count = int(raw_theory_count or 0)

        title = (cleaned.get("title") or "").strip()
        if not title:
            auto_title = self._auto_generated_title(
                assignment=assignment,
                exam_type=exam_type,
            )
            if auto_title:
                cleaned["title"] = auto_title
            else:
                self.add_error("title", "Title is required.")

        start = cleaned.get("schedule_start")
        end = cleaned.get("schedule_end")
        tz = timezone.get_current_timezone()
        if start and timezone.is_naive(start):
            cleaned["schedule_start"] = timezone.make_aware(start, tz)
            start = cleaned["schedule_start"]
        if end and timezone.is_naive(end):
            cleaned["schedule_end"] = timezone.make_aware(end, tz)
            end = cleaned["schedule_end"]
        if start and end and end <= start:
            self.add_error("schedule_end", "Schedule end must be after schedule start.")

        if exam_type == CBTExamType.FREE_TEST:
            cleaned["flow_type"] = self.FLOW_OBJECTIVE_ONLY
            flow_type = self.FLOW_OBJECTIVE_ONLY
            objective_count = int(raw_objective_count or 25)
            if objective_count <= 0:
                objective_count = 25
            objective_count = min(objective_count, 100)
            theory_count = 0
        elif flow_type == self.FLOW_SIMULATION and exam_type in {CBTExamType.CA, CBTExamType.PRACTICAL}:
            cleaned["authoring_mode"] = self.AUTHORING_MODE_SCRATCH
            authoring_mode = self.AUTHORING_MODE_SCRATCH
            cleaned["flow_type"] = self.FLOW_SIMULATION
            flow_type = self.FLOW_SIMULATION
            objective_count = 0
            theory_count = 0
        elif exam_type == CBTExamType.EXAM:
            cleaned["flow_type"] = self.FLOW_OBJECTIVE_THEORY
            flow_type = self.FLOW_OBJECTIVE_THEORY
        elif exam_type in {CBTExamType.CA, CBTExamType.PRACTICAL}:
            if flow_type not in {self.FLOW_OBJECTIVE_THEORY, self.FLOW_SIMULATION}:
                cleaned["flow_type"] = self.FLOW_OBJECTIVE_THEORY
                flow_type = self.FLOW_OBJECTIVE_THEORY
        else:
            cleaned["flow_type"] = self.FLOW_OBJECTIVE_THEORY
            flow_type = self.FLOW_OBJECTIVE_THEORY

        cleaned["manual_score_split"] = bool(
            flow_type == self.FLOW_OBJECTIVE_THEORY
            and exam_type in {CBTExamType.CA, CBTExamType.PRACTICAL, CBTExamType.EXAM}
        )

        if authoring_mode in {self.AUTHORING_MODE_UPLOAD, self.AUTHORING_MODE_AI}:
            objective_count = 0
            theory_count = 0
        elif flow_type == self.FLOW_OBJECTIVE_THEORY:
            if raw_objective_count in (None, ""):
                objective_count = 10
            if objective_count <= 0:
                self.add_error("objective_question_count", "Set at least one objective question.")
            if raw_theory_count in (None, ""):
                theory_count = 3
            if theory_count <= 0:
                self.add_error("theory_question_count", "Set at least one theory question.")
        elif flow_type == self.FLOW_SIMULATION:
            objective_count = 0
            theory_count = 0

        cleaned["objective_question_count"] = objective_count
        cleaned["theory_question_count"] = theory_count

        has_objective = objective_count > 0
        has_theory = theory_count > 0

        ca_target = (cleaned.get("ca_target") or "").strip()
        all_ca_targets = {
            CBTWritebackTarget.CA1,
            CBTWritebackTarget.CA2,
            CBTWritebackTarget.CA3,
            CBTWritebackTarget.CA4,
        }
        cleaned["ca_target"] = ca_target
        default_ca_target = (
            CBTWritebackTarget.CA4
            if exam_type == CBTExamType.PRACTICAL
            else CBTWritebackTarget.CA1
        )
        if exam_type in {CBTExamType.CA, CBTExamType.PRACTICAL}:
            if flow_type == self.FLOW_SIMULATION:
                if ca_target not in all_ca_targets:
                    if authoring_mode in {self.AUTHORING_MODE_UPLOAD, self.AUTHORING_MODE_AI}:
                        cleaned["ca_target"] = default_ca_target
                    else:
                        self.add_error("ca_target", "Select CA target.")
            else:
                # Objective/Theory CA2 and CA3 are a joint bucket.
                if ca_target == CBTWritebackTarget.CA3:
                    ca_target = CBTWritebackTarget.CA2
                cleaned["ca_target"] = ca_target
                valid_ca_targets = {
                    CBTWritebackTarget.CA1,
                    CBTWritebackTarget.CA2,
                    CBTWritebackTarget.CA4,
                }
                if authoring_mode in {self.AUTHORING_MODE_UPLOAD, self.AUTHORING_MODE_AI}:
                    # Upload/AI setup intentionally hides granular CA target in UI.
                    # Apply safe default so Create always routes to the next page.
                    cleaned["ca_target"] = ca_target if ca_target in valid_ca_targets else default_ca_target
                elif ca_target not in valid_ca_targets:
                    self.add_error("ca_target", "Select CA target.")
            if authoring_mode in {self.AUTHORING_MODE_UPLOAD, self.AUTHORING_MODE_AI}:
                target_for_duplicate_check = cleaned.get("ca_target") or default_ca_target
            else:
                target_for_duplicate_check = cleaned.get("ca_target")
            if assignment is not None and target_for_duplicate_check in all_ca_targets:
                if has_completed_ca_target_exam(
                    assignment=assignment,
                    ca_target=target_for_duplicate_check,
                    flow_type=flow_type,
                ):
                    self.add_error(
                        "ca_target",
                        f"{target_for_duplicate_check} CBT has already been completed for this class/subject. Create another type/target instead.",
                    )
        else:
            cleaned["ca_target"] = ""

        if not has_theory:
            cleaned["theory_response_mode"] = self.THEORY_RESPONSE_MODE_TYPING
        elif exam_type != CBTExamType.FREE_TEST:
            cleaned["theory_response_mode"] = self.THEORY_RESPONSE_MODE_PAPER

        defaults = self._default_section_totals(
            exam_type=exam_type,
            flow_type=flow_type,
            assignment=assignment,
        )
        manual = bool(cleaned.get("manual_score_split"))
        if manual:
            objective_total = _as_decimal(cleaned.get("objective_target_max"), Decimal("0.00"))
            theory_total = _as_decimal(cleaned.get("theory_target_max"), Decimal("0.00"))
            if has_objective and objective_total <= 0:
                self.add_error("objective_target_max", "Objective target max must be greater than zero.")
            if has_theory and theory_total <= 0:
                self.add_error("theory_target_max", "Theory target max must be greater than zero.")
            ca_limit = (
                Decimal("20.00")
                if cleaned.get("ca_target") == CBTWritebackTarget.CA2
                else Decimal("10.00")
            )
            if exam_type in {CBTExamType.CA, CBTExamType.PRACTICAL} and (objective_total + theory_total) > ca_limit:
                raise forms.ValidationError(f"Total CA target cannot exceed {ca_limit}.")
            exam_limit = (
                Decimal("100.00")
                if _uses_ss3_mock_exam_totals(assignment)
                else Decimal("60.00")
            )
            if exam_type == CBTExamType.EXAM and (objective_total + theory_total) > exam_limit:
                raise forms.ValidationError(f"Total exam target cannot exceed {exam_limit}.")
            if exam_type == CBTExamType.FREE_TEST and (objective_total + theory_total) > Decimal("100.00"):
                raise forms.ValidationError("Free Test total cannot exceed 100.")
        else:
            if exam_type == CBTExamType.FREE_TEST and has_objective:
                objective_total = Decimal(str(objective_count)).quantize(Decimal("0.01"))
            elif (
                exam_type in {CBTExamType.CA, CBTExamType.PRACTICAL}
                and has_objective
                and has_theory
                and cleaned.get("ca_target") == CBTWritebackTarget.CA2
            ):
                objective_total = Decimal("10.00")
                theory_total = Decimal("10.00")
            else:
                objective_total = defaults[0] if has_objective else Decimal("0.00")
                theory_total = defaults[1] if has_theory else Decimal("0.00")

        cleaned["_objective_total"] = objective_total
        cleaned["_theory_total"] = theory_total
        return cleaned

    def save(self):
        assignment = self.cleaned_data["assignment"]
        flow_type = self.cleaned_data.get("flow_type") or self.FLOW_OBJECTIVE_THEORY
        exam = Exam.objects.create(
            title=self.cleaned_data["title"],
            description=self.cleaned_data.get("description", ""),
            exam_type=self.cleaned_data["exam_type"],
            status=CBTExamStatus.DRAFT,
            created_by=self.actor,
            assignment=assignment,
            subject=assignment.subject,
            academic_class=assignment.academic_class,
            session=assignment.session,
            term=assignment.term,
            schedule_start=self.cleaned_data.get("schedule_start"),
            schedule_end=self.cleaned_data.get("schedule_end"),
            is_time_based=True,
            open_now=False,
            is_free_test=(self.cleaned_data["exam_type"] == CBTExamType.FREE_TEST),
        )

        ca_target = (self.cleaned_data.get("ca_target") or "").strip()
        if self.cleaned_data["exam_type"] in {CBTExamType.CA, CBTExamType.PRACTICAL}:
            fallback_ca_target = (
                CBTWritebackTarget.CA4
                if self.cleaned_data["exam_type"] == CBTExamType.PRACTICAL
                else CBTWritebackTarget.CA1
            )
            effective_target = ca_target or fallback_ca_target
            if flow_type == self.FLOW_SIMULATION:
                objective_target = CBTWritebackTarget.NONE
                theory_target = CBTWritebackTarget.NONE
            elif flow_type == self.FLOW_OBJECTIVE_THEORY:
                if effective_target in {CBTWritebackTarget.CA2, CBTWritebackTarget.CA3}:
                    objective_target = CBTWritebackTarget.CA2
                else:
                    objective_target = effective_target
                theory_target = CBTWritebackTarget.NONE
            elif effective_target in {CBTWritebackTarget.CA2, CBTWritebackTarget.CA3}:
                objective_target = CBTWritebackTarget.CA2
                theory_target = CBTWritebackTarget.CA3
            else:
                objective_target = effective_target
                theory_target = effective_target
        elif self.cleaned_data["exam_type"] == CBTExamType.EXAM:
            objective_target = CBTWritebackTarget.OBJECTIVE
            theory_target = CBTWritebackTarget.NONE
        elif self.cleaned_data["exam_type"] == CBTExamType.FREE_TEST:
            objective_target = CBTWritebackTarget.NONE
            theory_target = CBTWritebackTarget.NONE
        else:
            objective_target = CBTWritebackTarget.NONE
            theory_target = CBTWritebackTarget.NONE

        ExamBlueprint.objects.create(
            exam=exam,
            duration_minutes=self.cleaned_data["duration_minutes"],
            max_attempts=self.cleaned_data["max_attempts"],
            shuffle_questions=bool(self.cleaned_data.get("shuffle_questions")),
            shuffle_options=bool(self.cleaned_data.get("shuffle_options")),
            instructions=self.cleaned_data.get("instructions", ""),
            section_config={
                "flow_type": flow_type,
                "objective_count": int(self.cleaned_data.get("objective_question_count") or 0),
                "theory_count": int(self.cleaned_data.get("theory_question_count") or 0),
                "theory_response_mode": self.cleaned_data.get("theory_response_mode") or self.THEORY_RESPONSE_MODE_PAPER,
                "ca_target": (ca_target or effective_target) if self.cleaned_data["exam_type"] in {CBTExamType.CA, CBTExamType.PRACTICAL} else "",
                "is_free_test": self.cleaned_data["exam_type"] == CBTExamType.FREE_TEST,
                "manual_score_split": bool(self.cleaned_data.get("manual_score_split")),
                "objective_target_max": str(self.cleaned_data.get("_objective_total", Decimal("0.00"))),
                "theory_target_max": str(self.cleaned_data.get("_theory_total", Decimal("0.00"))),
                "calculator_mode": self.cleaned_data.get("calculator_mode") or self.CALCULATOR_NONE,
            },
            objective_writeback_target=objective_target,
            theory_enabled=bool(self.cleaned_data.get("theory_question_count")),
            theory_writeback_target=theory_target,
            passing_score=Decimal("0.00"),
        )
        return exam


class ExamAttachQuestionsForm(forms.Form):
    question_ids = forms.ModelMultipleChoiceField(queryset=Question.objects.none(), required=False, label="Question Set")

    def __init__(self, *args, **kwargs):
        self.actor = kwargs.pop("actor", None)
        self.exam = kwargs.pop("exam", None)
        super().__init__(*args, **kwargs)
        qs = Question.objects.select_related("question_bank", "subject").filter(
            subject=self.exam.subject,
            question_bank__academic_class=self.exam.academic_class,
            question_bank__session=self.exam.session,
            question_bank__term=self.exam.term,
            is_active=True,
        )
        if self.exam.question_bank_id:
            qs = qs.filter(question_bank=self.exam.question_bank)
        self.fields["question_ids"].queryset = qs.order_by("question_bank__name", "id")
        self.fields["question_ids"].initial = list(self.exam.exam_questions.order_by("sort_order").values_list("question_id", flat=True))
        _style_fields(self)

    def save(self):
        selected = list(self.cleaned_data.get("question_ids") or [])
        with transaction.atomic():
            self.exam.exam_questions.all().delete()
            for i, question in enumerate(selected, start=1):
                ExamQuestion.objects.create(exam=self.exam, question=question, sort_order=i, marks=question.marks)
        return len(selected)


class ExamAttachSimulationsForm(forms.Form):
    simulation_ids = forms.ModelMultipleChoiceField(queryset=SimulationWrapper.objects.none(), required=False, label="Approved Simulation Tools")
    writeback_target = forms.ChoiceField(choices=CBTWritebackTarget.choices, required=False)
    required_for_submission = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, **kwargs):
        self.exam = kwargs.pop("exam", None)
        super().__init__(*args, **kwargs)
        self.fields["simulation_ids"].queryset = recommended_simulation_queryset(self.exam.subject)
        self.fields["simulation_ids"].initial = list(self.exam.exam_simulations.order_by("sort_order").values_list("simulation_wrapper_id", flat=True))
        link = self.exam.exam_simulations.order_by("sort_order", "id").first()
        if link:
            self.fields["writeback_target"].initial = link.writeback_target
            self.fields["required_for_submission"].initial = link.is_required
        _style_fields(self)

    def save(self):
        selected = list(self.cleaned_data.get("simulation_ids") or [])
        target = (self.cleaned_data.get("writeback_target") or CBTWritebackTarget.CA3).strip()
        required = bool(self.cleaned_data.get("required_for_submission"))
        with transaction.atomic():
            self.exam.exam_simulations.all().delete()
            for i, wrapper in enumerate(selected, start=1):
                ExamSimulation.objects.create(
                    exam=self.exam,
                    simulation_wrapper=wrapper,
                    sort_order=i,
                    writeback_target=target,
                    is_required=required,
                )
        return len(selected)


class ExamSubmitToDeanForm(forms.Form):
    comment = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)

    def clean_comment(self):
        return (self.cleaned_data.get("comment") or "").strip()


class ExamUploadImportForm(forms.Form):
    assignment = forms.ModelChoiceField(queryset=TeacherSubjectAssignment.objects.none(), label="Class & Subject")
    title = forms.CharField(max_length=200)
    exam_type = forms.ChoiceField(
        choices=[
            (CBTExamType.CA, "CA"),
            (CBTExamType.EXAM, "Exam"),
            (CBTExamType.PRACTICAL, "Practical"),
            (CBTExamType.FREE_TEST, "Free Test"),
        ]
    )
    flow_type = forms.ChoiceField(
        choices=[
            (ExamCreateForm.FLOW_OBJECTIVE_ONLY, "Objective Only"),
            (ExamCreateForm.FLOW_OBJECTIVE_THEORY, "Objective + Theory"),
        ],
        initial=ExamCreateForm.FLOW_OBJECTIVE_THEORY,
        required=False,
    )
    ca_target = forms.ChoiceField(
        choices=[
            ("", "Select CA Target"),
            (CBTWritebackTarget.CA1, "CA1"),
            (CBTWritebackTarget.CA2, "CA2 / CA3 (Joint)"),
            (CBTWritebackTarget.CA4, "CA4"),
        ],
        required=False,
    )
    source_file = forms.FileField(required=False)
    pasted_text = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 8}))

    def __init__(self, *args, **kwargs):
        self.actor = kwargs.pop("actor", None)
        super().__init__(*args, **kwargs)
        self.fields["assignment"].queryset = authoring_assignment_queryset(self.actor, include_all_periods=True)
        self.fields["assignment"].label_from_instance = (
            lambda row: f"{row.academic_class.code} - {row.subject.name} ({row.session.name} / {row.term.get_name_display()})"
        )
        self.fields["source_file"].help_text = (
            "Best results: upload clean TXT, DOCX, or text-based PDF. Notes and handouts can also be used to draft questions. "
            "Legacy DOC is unreliable."
        )
        self.fields["pasted_text"].help_text = (
            "Paste clean numbered questions, or paste lesson notes and the system will draft from them."
        )
        _style_fields(self)

    def clean_title(self):
        value = (self.cleaned_data.get("title") or "").strip()
        if not value:
            raise forms.ValidationError("Title is required.")
        return value

    def clean_pasted_text(self):
        return (self.cleaned_data.get("pasted_text") or "").strip()

    def clean(self):
        cleaned = super().clean()
        source_file = cleaned.get("source_file")
        pasted_text = cleaned.get("pasted_text") or ""
        allowed_file_types = (
            ".pdf",
            ".doc",
            ".docx",
            ".txt",
            ".png",
            ".jpg",
            ".jpeg",
            ".bmp",
            ".tif",
            ".tiff",
            ".webp",
        )
        exam_type = cleaned.get("exam_type")
        flow_type = (cleaned.get("flow_type") or ExamCreateForm.FLOW_OBJECTIVE_THEORY).strip()
        if exam_type == CBTExamType.FREE_TEST:
            flow_type = ExamCreateForm.FLOW_OBJECTIVE_ONLY
        cleaned["flow_type"] = flow_type
        if exam_type in {CBTExamType.CA, CBTExamType.PRACTICAL}:
            assignment = cleaned.get("assignment")
            if assignment is not None:
                ca_target = (cleaned.get("ca_target") or "").strip()
                if ca_target == CBTWritebackTarget.CA3:
                    ca_target = CBTWritebackTarget.CA2
                if ca_target not in {
                    CBTWritebackTarget.CA1,
                    CBTWritebackTarget.CA2,
                    CBTWritebackTarget.CA4,
                }:
                    ca_target = (
                        CBTWritebackTarget.CA4
                        if cleaned.get("exam_type") == CBTExamType.PRACTICAL
                        else CBTWritebackTarget.CA1
                    )
                cleaned["ca_target"] = ca_target
                if has_completed_ca_target_exam(
                    assignment=assignment,
                    ca_target=ca_target,
                    flow_type=flow_type,
                ):
                    self.add_error(
                        "exam_type",
                        f"{ca_target} CBT has already been completed for this class/subject.",
                    )
        else:
            cleaned["ca_target"] = ""
        if not source_file and not pasted_text.strip():
            raise forms.ValidationError("Upload file or paste questions.")
        if source_file and not (source_file.name or "").lower().endswith(allowed_file_types):
            self.add_error(
                "source_file",
                "Upload PDF, DOC, DOCX, TXT, or question image (PNG/JPG/JPEG/BMP/TIFF/WEBP).",
            )
        return cleaned


class AIExamDraftForm(forms.Form):
    assignment = forms.ModelChoiceField(queryset=TeacherSubjectAssignment.objects.none(), label="Class & Subject")
    title = forms.CharField(max_length=200)
    topic = forms.CharField(max_length=160)
    question_count = forms.IntegerField(min_value=1, max_value=300, initial=10)
    exam_type = forms.ChoiceField(
        choices=[
            (CBTExamType.CA, "CA"),
            (CBTExamType.EXAM, "Exam"),
            (CBTExamType.PRACTICAL, "Practical"),
            (CBTExamType.FREE_TEST, "Free Test"),
        ]
    )
    flow_type = forms.ChoiceField(
        choices=[
            (ExamCreateForm.FLOW_OBJECTIVE_ONLY, "Objective Only"),
            (ExamCreateForm.FLOW_OBJECTIVE_THEORY, "Objective + Theory"),
        ],
        initial=ExamCreateForm.FLOW_OBJECTIVE_THEORY,
        required=False,
    )
    ca_target = forms.ChoiceField(
        choices=[
            ("", "Select CA Target"),
            (CBTWritebackTarget.CA1, "CA1"),
            (CBTWritebackTarget.CA2, "CA2 / CA3 (Joint)"),
            (CBTWritebackTarget.CA4, "CA4"),
        ],
        required=False,
    )
    difficulty = forms.ChoiceField(choices=CBTQuestionDifficulty.choices, initial=CBTQuestionDifficulty.MEDIUM)
    lesson_note_text = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 5}))
    lesson_note_file = forms.FileField(required=False)

    def __init__(self, *args, **kwargs):
        self.actor = kwargs.pop("actor", None)
        super().__init__(*args, **kwargs)
        self.fields["assignment"].queryset = authoring_assignment_queryset(self.actor, include_all_periods=True)
        self.fields["assignment"].label_from_instance = (
            lambda row: f"{row.academic_class.code} - {row.subject.name} ({row.session.name} / {row.term.get_name_display()})"
        )
        _style_fields(self)

    def clean_title(self):
        value = (self.cleaned_data.get("title") or "").strip()
        if not value:
            raise forms.ValidationError("Title is required.")
        return value

    def clean_topic(self):
        value = (self.cleaned_data.get("topic") or "").strip()
        if not value:
            raise forms.ValidationError("Topic is required.")
        return value

    def clean_lesson_note_text(self):
        return (self.cleaned_data.get("lesson_note_text") or "").strip()

    def clean(self):
        cleaned = super().clean()
        note_file = cleaned.get("lesson_note_file")
        allowed_file_types = (
            ".pdf",
            ".doc",
            ".docx",
            ".txt",
            ".png",
            ".jpg",
            ".jpeg",
            ".bmp",
            ".tif",
            ".tiff",
            ".webp",
        )
        if note_file and not (note_file.name or "").lower().endswith(allowed_file_types):
            self.add_error(
                "lesson_note_file",
                "Upload PDF, DOC, DOCX, TXT, or image file.",
            )
        exam_type = cleaned.get("exam_type")
        flow_type = (cleaned.get("flow_type") or ExamCreateForm.FLOW_OBJECTIVE_THEORY).strip()
        if exam_type == CBTExamType.FREE_TEST:
            flow_type = ExamCreateForm.FLOW_OBJECTIVE_ONLY
        cleaned["flow_type"] = flow_type
        if exam_type in {CBTExamType.CA, CBTExamType.PRACTICAL}:
            assignment = cleaned.get("assignment")
            if assignment is not None:
                ca_target = (cleaned.get("ca_target") or "").strip()
                if ca_target == CBTWritebackTarget.CA3:
                    ca_target = CBTWritebackTarget.CA2
                if ca_target not in {
                    CBTWritebackTarget.CA1,
                    CBTWritebackTarget.CA2,
                    CBTWritebackTarget.CA4,
                }:
                    ca_target = (
                        CBTWritebackTarget.CA4
                        if cleaned.get("exam_type") == CBTExamType.PRACTICAL
                        else CBTWritebackTarget.CA1
                    )
                cleaned["ca_target"] = ca_target
                if has_completed_ca_target_exam(
                    assignment=assignment,
                    ca_target=ca_target,
                    flow_type=flow_type,
                ):
                    self.add_error(
                        "exam_type",
                        f"{ca_target} CBT has already been completed for this class/subject.",
                    )
        else:
            cleaned["ca_target"] = ""
        return cleaned

class SimulationWrapperCreateForm(forms.ModelForm):
    simulation_bundle = forms.FileField(required=False)

    class Meta:
        model = SimulationWrapper
        fields = (
            "tool_name",
            "tool_type",
            "source_provider",
            "source_reference_url",
            "tool_category",
            "description",
            "score_mode",
            "max_score",
            "scoring_callback_type",
            "evidence_required",
            "online_url",
            "offline_asset_path",
            "is_active",
            "simulation_bundle",
        )
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source_provider"].required = False
        self.fields["source_reference_url"].required = False
        self.fields["source_provider"].initial = CBTSimulationSourceProvider.PHET
        self.fields["tool_category"].initial = CBTSimulationToolCategory.SCIENCE
        self.fields["score_mode"].initial = CBTSimulationScoreMode.AUTO
        self.fields["scoring_callback_type"].initial = CBTSimulationCallbackType.POST_MESSAGE
        self.fields["max_score"].initial = Decimal("10.00")
        _style_fields(self)

    def clean_tool_name(self):
        value = (self.cleaned_data.get("tool_name") or "").strip()
        if not value:
            raise forms.ValidationError("Tool name is required.")
        return value

    def clean_tool_type(self):
        return (self.cleaned_data.get("tool_type") or "").strip()

    def clean_description(self):
        return (self.cleaned_data.get("description") or "").strip()

    def clean_offline_asset_path(self):
        return (self.cleaned_data.get("offline_asset_path") or "").strip()

    def clean(self):
        cleaned = super().clean()
        bundle = cleaned.get("simulation_bundle") or self.files.get("bundle_zip")
        online_url = (cleaned.get("online_url") or "").strip()
        offline_path = (cleaned.get("offline_asset_path") or "").strip()
        source_provider = (cleaned.get("source_provider") or "").strip()

        if not bundle and not online_url and not offline_path:
            raise forms.ValidationError("Provide online URL, offline path, or upload simulation bundle ZIP.")
        if bundle and not (bundle.name or "").lower().endswith(".zip"):
            self.add_error("simulation_bundle", "Simulation bundle must be a ZIP file.")
        if bundle and not online_url and not offline_path:
            # Temporary placeholder so model validation passes before extraction writes real path.
            cleaned["offline_asset_path"] = "__bundle_pending__"
        if cleaned.get("score_mode") == CBTSimulationScoreMode.VERIFY:
            cleaned["evidence_required"] = True
        if not source_provider:
            cleaned["source_provider"] = CBTSimulationSourceProvider.OTHER
        cleaned["simulation_bundle"] = bundle
        return cleaned

    def save(self, *, actor):
        bundle = self.cleaned_data.get("simulation_bundle")
        instance = super().save(commit=False)
        if not instance.pk:
            instance.created_by = actor
            if not instance.status:
                instance.status = CBTSimulationWrapperStatus.DRAFT
        if instance.score_mode == CBTSimulationScoreMode.VERIFY:
            instance.evidence_required = True

        instance.save()
        if bundle:
            launch_path = store_simulation_bundle(wrapper=instance, uploaded_bundle=bundle)
            instance.offline_asset_path = launch_path
            instance.save(update_fields=["offline_asset_path", "updated_at"])
        return instance


class SimulationSubmitToDeanForm(forms.Form):
    comment = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)

    def clean_comment(self):
        return (self.cleaned_data.get("comment") or "").strip()


class DeanExamDecisionForm(forms.Form):
    ACTION_APPROVE = "APPROVE"
    ACTION_REJECT = "REJECT"

    action = forms.ChoiceField(
        choices=[
            (ACTION_APPROVE, "Approve"),
            (ACTION_REJECT, "Reject"),
        ],
        initial=ACTION_APPROVE,
    )
    comment = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)

    def clean_comment(self):
        return (self.cleaned_data.get("comment") or "").strip()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("action") == self.ACTION_REJECT and not cleaned.get("comment"):
            self.add_error("comment", "Rejection reason is required.")
        return cleaned


class DeanSimulationDecisionForm(forms.Form):
    ACTION_APPROVE = "APPROVE"
    ACTION_REJECT = "REJECT"

    action = forms.ChoiceField(
        choices=[
            (ACTION_APPROVE, "Approve"),
            (ACTION_REJECT, "Reject"),
        ],
        initial=ACTION_APPROVE,
    )
    comment = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)

    def clean_comment(self):
        return (self.cleaned_data.get("comment") or "").strip()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("action") == self.ACTION_REJECT and not cleaned.get("comment"):
            self.add_error("comment", "Rejection reason is required.")
        return cleaned


class ITExamActivationForm(forms.Form):
    open_now = forms.BooleanField(
        required=False,
        initial=False,
        label="Open now",
        help_text="Students can see scheduled exams immediately, but they can only start at the schedule time unless this is enabled.",
    )
    is_time_based = forms.BooleanField(required=False, initial=True, label="Use schedule window")
    schedule_start = forms.DateTimeField(
        required=False,
        label="Start time",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    schedule_end = forms.DateTimeField(
        required=False,
        label="End time",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    duration_minutes = forms.IntegerField(min_value=1, max_value=600)
    max_attempts = forms.IntegerField(min_value=1, max_value=10)
    shuffle_questions = forms.BooleanField(required=False, initial=True)
    shuffle_options = forms.BooleanField(required=False, initial=True)
    instructions = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    activation_comment = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        self.exam = kwargs.pop("exam", None)
        super().__init__(*args, **kwargs)

        blueprint = getattr(self.exam, "blueprint", None)
        if blueprint is not None:
            self.fields["duration_minutes"].initial = blueprint.duration_minutes
            self.fields["max_attempts"].initial = blueprint.max_attempts
            self.fields["shuffle_questions"].initial = blueprint.shuffle_questions
            self.fields["shuffle_options"].initial = blueprint.shuffle_options
            self.fields["instructions"].initial = blueprint.instructions
        else:
            self.fields["duration_minutes"].initial = 60
            self.fields["max_attempts"].initial = 1

        if self.exam is not None:
            self.fields["open_now"].initial = self.exam.open_now
            self.fields["is_time_based"].initial = self.exam.is_time_based
            self.fields["schedule_start"].initial = self.exam.schedule_start
            self.fields["schedule_end"].initial = self.exam.schedule_end

        _style_fields(self)

    def clean_instructions(self):
        return (self.cleaned_data.get("instructions") or "").strip()

    def clean_activation_comment(self):
        return (self.cleaned_data.get("activation_comment") or "").strip()

    def clean(self):
        cleaned = super().clean()
        is_time_based = bool(cleaned.get("is_time_based"))
        open_now = bool(cleaned.get("open_now"))
        start = cleaned.get("schedule_start")
        end = cleaned.get("schedule_end")
        duration_minutes = int(cleaned.get("duration_minutes") or 0)

        if self.exam is not None and getattr(self.exam, "is_free_test", False):
            cleaned["is_time_based"] = False
            cleaned["open_now"] = True
            cleaned["schedule_start"] = None
            cleaned["schedule_end"] = None
            return cleaned

        tz = timezone.get_current_timezone()
        if start and timezone.is_naive(start):
            cleaned["schedule_start"] = timezone.make_aware(start, tz)
            start = cleaned["schedule_start"]
        if end and timezone.is_naive(end):
            cleaned["schedule_end"] = timezone.make_aware(end, tz)
            end = cleaned["schedule_end"]

        cleaned["is_time_based"] = True
        is_time_based = True

        if open_now:
            now = timezone.now()
            if start and start > now:
                self.add_error("schedule_start", "Start time cannot be in the future when opening immediately.")
            if not start:
                cleaned["schedule_start"] = now
                start = now
            if not end and duration_minutes > 0 and start:
                cleaned["schedule_end"] = start + timezone.timedelta(minutes=duration_minutes)
                end = cleaned["schedule_end"]

        if not is_time_based:
            cleaned["schedule_start"] = None
            cleaned["schedule_end"] = None
        elif not open_now:
            if not start:
                self.add_error("schedule_start", "Schedule start is required when exam is not open immediately.")
            if not end:
                self.add_error("schedule_end", "Schedule end is required when exam is not open immediately.")
        elif not end:
            self.add_error("schedule_end", "End time is required so the exam can close automatically.")

        if start and end and end <= start:
            self.add_error("schedule_end", "Schedule end must be after schedule start.")

        return cleaned

    def save_blueprint(self):
        if self.exam is None:
            raise ValidationError("Exam context is required.")
        blueprint, _ = ExamBlueprint.objects.get_or_create(exam=self.exam)
        blueprint.duration_minutes = self.cleaned_data["duration_minutes"]
        blueprint.max_attempts = self.cleaned_data["max_attempts"]
        blueprint.shuffle_questions = bool(self.cleaned_data.get("shuffle_questions"))
        blueprint.shuffle_options = bool(self.cleaned_data.get("shuffle_options"))
        blueprint.instructions = self.cleaned_data.get("instructions", "")
        blueprint.save(
            update_fields=[
                "duration_minutes",
                "max_attempts",
                "shuffle_questions",
                "shuffle_options",
                "instructions",
                "updated_at",
            ]
        )
        return blueprint


class ITExamCloseForm(forms.Form):
    comment = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)

    def clean_comment(self):
        return (self.cleaned_data.get("comment") or "").strip()


class StudentSimulationEvidenceForm(forms.Form):
    evidence_file = forms.FileField(required=False)
    evidence_note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)

    def clean_evidence_note(self):
        return (self.cleaned_data.get("evidence_note") or "").strip()

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("evidence_file") and not cleaned.get("evidence_note"):
            raise forms.ValidationError("Add evidence file or note before submitting.")
        return cleaned


class SimulationVerifyScoringForm(forms.Form):
    verified_score = forms.DecimalField(max_digits=7, decimal_places=2, min_value=Decimal("0.00"))
    comment = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)

    def clean_comment(self):
        return (self.cleaned_data.get("comment") or "").strip()


class SimulationRubricScoringForm(forms.Form):
    criteria_accuracy = forms.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal("0.00"), max_value=Decimal("100.00"), initial=Decimal("0.00"), label="Accuracy (%)")
    criteria_procedure = forms.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal("0.00"), max_value=Decimal("100.00"), initial=Decimal("0.00"), label="Procedure (%)")
    criteria_analysis = forms.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal("0.00"), max_value=Decimal("100.00"), initial=Decimal("0.00"), label="Analysis (%)")
    criteria_presentation = forms.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal("0.00"), max_value=Decimal("100.00"), initial=Decimal("0.00"), label="Presentation (%)")
    comment = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        positional_args = list(args)
        data = kwargs.get("data")
        if data is None and positional_args:
            data = positional_args[0]
        if data is not None:
            mutable_data = data.copy()
            if not mutable_data.get("criteria_accuracy") and mutable_data.get("criterion_accuracy"):
                mutable_data["criteria_accuracy"] = mutable_data.get("criterion_accuracy")
            if not mutable_data.get("criteria_procedure") and mutable_data.get("criterion_completion"):
                mutable_data["criteria_procedure"] = mutable_data.get("criterion_completion")
            if not mutable_data.get("criteria_analysis") and mutable_data.get("criterion_analysis"):
                mutable_data["criteria_analysis"] = mutable_data.get("criterion_analysis")
            if not mutable_data.get("criteria_presentation") and mutable_data.get("criterion_safety"):
                mutable_data["criteria_presentation"] = mutable_data.get("criterion_safety")
            if kwargs.get("data") is not None:
                kwargs["data"] = mutable_data
            elif positional_args:
                positional_args[0] = mutable_data
            else:
                kwargs["data"] = mutable_data
        super().__init__(*positional_args, **kwargs)
        _style_fields(self)
        for field_name in (
            "criteria_accuracy",
            "criteria_procedure",
            "criteria_analysis",
            "criteria_presentation",
        ):
            self.fields[field_name].widget.attrs.update(
                {
                    "min": "0",
                    "max": "100",
                    "step": "1",
                    "inputmode": "decimal",
                    "autocomplete": "off",
                }
            )

    def clean_comment(self):
        return (self.cleaned_data.get("comment") or "").strip()

    def rubric_payload(self):
        payload = {}
        for key in (
            "criteria_accuracy",
            "criteria_procedure",
            "criteria_analysis",
            "criteria_presentation",
        ):
            value = self.cleaned_data.get(key)
            if value is not None:
                payload[key] = str(value)
        return payload


class SimulationImportScoreForm(forms.Form):
    writeback_target = forms.ChoiceField(choices=CBTWritebackTarget.choices, required=False)
    manual_raw_score = forms.DecimalField(max_digits=7, decimal_places=2, required=False, min_value=Decimal("0.00"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)

    def clean(self):
        cleaned = super().clean()
        if not (cleaned.get("writeback_target") or "").strip():
            cleaned["writeback_target"] = CBTWritebackTarget.NONE
        return cleaned
