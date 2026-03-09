from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re

from django.db import transaction
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone

from apps.academics.models import (
    AcademicClass,
    AcademicSession,
    ClassSubject,
    GradeScale,
    SessionPromotionOutcome,
    SessionPromotionRecord,
    StudentClassEnrollment,
    StudentSubjectEnrollment,
    Subject,
    SubjectCategory,
    TeacherSubjectAssignment,
    Term,
    TermName,
    FormTeacherAssignment,
)
from apps.attendance.models import Holiday, SchoolCalendar
from apps.setup_wizard.models import SetupStateCode, SystemSetupState


WIZARD_STEPS = (
    "session",
    "term",
    "calendar",
    "classes",
    "subjects",
    "class-subjects",
    "grade-scale",
    "finalize",
)

STATE_TO_CURRENT_STEP = {
    SetupStateCode.BOOT_EMPTY: "session",
    SetupStateCode.SESSION_CREATED: "term",
    SetupStateCode.TERM_CREATED: "calendar",
    SetupStateCode.CALENDAR_CONFIGURED: "classes",
    SetupStateCode.CLASSES_CREATED: "subjects",
    SetupStateCode.SUBJECTS_CREATED: "class-subjects",
    SetupStateCode.CLASS_SUBJECTS_MAPPED: "grade-scale",
    SetupStateCode.GRADE_SCALE_CONFIGURED: "finalize",
    SetupStateCode.IT_READY: "finalize",
}

STEP_TO_NEXT_STATE = {
    "session": SetupStateCode.SESSION_CREATED,
    "term": SetupStateCode.TERM_CREATED,
    "calendar": SetupStateCode.CALENDAR_CONFIGURED,
    "classes": SetupStateCode.CLASSES_CREATED,
    "subjects": SetupStateCode.SUBJECTS_CREATED,
    "class-subjects": SetupStateCode.CLASS_SUBJECTS_MAPPED,
    "grade-scale": SetupStateCode.GRADE_SCALE_CONFIGURED,
    "finalize": SetupStateCode.IT_READY,
}

TERM_SEQUENCE = (TermName.FIRST, TermName.SECOND, TermName.THIRD)
CLASS_STAGE_SEQUENCE = ("JS1", "JS2", "JS3", "SS1", "SS2", "SS3")
TERMINAL_CLASS_STAGE = "SS3"


def get_setup_state():
    return SystemSetupState.get_solo()


def setup_is_ready():
    try:
        return get_setup_state().is_ready
    except (OperationalError, ProgrammingError):
        return False


def current_wizard_step(setup_state: SystemSetupState | None = None):
    setup_state = setup_state or get_setup_state()
    return STATE_TO_CURRENT_STEP.get(setup_state.state, "session")


def can_access_step(requested_step: str, setup_state: SystemSetupState | None = None):
    setup_state = setup_state or get_setup_state()
    current = current_wizard_step(setup_state)
    requested_index = WIZARD_STEPS.index(requested_step)
    current_index = WIZARD_STEPS.index(current)
    return requested_index <= current_index


def parse_bulk_lines(raw_value: str):
    values = []
    seen = set()
    for line in (raw_value or "").splitlines():
        parts = [part.strip() for part in line.replace(";", ",").split(",")]
        for cleaned in parts:
            if not cleaned:
                continue
            normalized = cleaned.upper()
            if normalized in seen:
                continue
            seen.add(normalized)
            values.append(cleaned)
    return values


@dataclass
class ParsedHoliday:
    date_value: date
    description: str


def parse_holiday_lines(raw_value: str):
    rows = []
    for line in (raw_value or "").splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        if "|" in cleaned:
            date_part, description_part = cleaned.split("|", 1)
        elif ":" in cleaned:
            date_part, description_part = cleaned.split(":", 1)
        else:
            date_part, description_part = cleaned, "School Holiday"
        date_value = date.fromisoformat(date_part.strip())
        description = description_part.strip() or "School Holiday"
        rows.append(ParsedHoliday(date_value=date_value, description=description))
    return rows


@transaction.atomic
def configure_session(*, actor, session_name):
    setup_state = get_setup_state()
    session, _ = AcademicSession.objects.update_or_create(
        name=session_name.strip(),
        defaults={},
    )
    for term_name in (TermName.FIRST, TermName.SECOND, TermName.THIRD):
        Term.objects.get_or_create(session=session, name=term_name)
    setup_state.current_session = session
    setup_state.current_term = Term.objects.filter(session=session, name=TermName.FIRST).first()
    setup_state.state = SetupStateCode.SESSION_CREATED
    setup_state.last_updated_by = actor
    setup_state.save(
        update_fields=[
            "current_session",
            "current_term",
            "state",
            "last_updated_by",
            "updated_at",
        ]
    )
    return setup_state


@transaction.atomic
def configure_term(*, actor, term_name):
    setup_state = get_setup_state()
    session = setup_state.current_session
    if not session:
        raise ValueError("Current session must be configured before term.")
    term, _ = Term.objects.update_or_create(
        session=session,
        name=term_name,
        defaults={},
    )
    setup_state.current_term = term
    setup_state.state = SetupStateCode.TERM_CREATED
    setup_state.last_updated_by = actor
    setup_state.save(
        update_fields=["current_term", "state", "last_updated_by", "updated_at"]
    )
    return setup_state


@transaction.atomic
def configure_calendar(*, actor, start_date, end_date, holidays):
    setup_state = get_setup_state()
    if not setup_state.current_session_id or not setup_state.current_term_id:
        raise ValueError("Current session and term must be configured first.")
    calendar, _ = SchoolCalendar.objects.update_or_create(
        term=setup_state.current_term,
        defaults={
            "session": setup_state.current_session,
            "start_date": start_date,
            "end_date": end_date,
        },
    )
    calendar.holidays.all().delete()
    Holiday.objects.bulk_create(
        [
            Holiday(
                calendar=calendar,
                date=row.date_value,
                description=row.description,
            )
            for row in holidays
        ]
    )
    setup_state.state = SetupStateCode.CALENDAR_CONFIGURED
    setup_state.last_updated_by = actor
    setup_state.save(update_fields=["state", "last_updated_by", "updated_at"])
    return setup_state


@transaction.atomic
def configure_classes(*, actor, class_codes):
    for class_code in class_codes:
        normalized = class_code.upper().replace(" ", "")
        AcademicClass.objects.update_or_create(
            code=normalized,
            defaults={"display_name": normalized, "is_active": True},
        )
    setup_state = get_setup_state()
    setup_state.state = SetupStateCode.CLASSES_CREATED
    setup_state.last_updated_by = actor
    setup_state.save(update_fields=["state", "last_updated_by", "updated_at"])
    return setup_state


def _generate_subject_code(name):
    letters = [char for char in name.upper() if char.isalnum()]
    base = "".join(letters)[:6] or "SUBJ"
    code = base
    suffix = 2
    while Subject.objects.filter(code=code).exists():
        code = f"{base[:4]}{suffix}"
        suffix += 1
    return code


@transaction.atomic
def configure_subjects(*, actor, subjects):
    for row in subjects:
        parts = [part.strip() for part in row.split("|")]
        name = parts[0] if parts else ""
        code = parts[1].upper() if len(parts) >= 2 and parts[1] else ""
        category = (
            parts[2].upper()
            if len(parts) >= 3 and parts[2]
            else SubjectCategory.GENERAL
        )
        if category not in {choice[0] for choice in SubjectCategory.choices}:
            category = SubjectCategory.GENERAL
        if not name:
            continue
        if code and Subject.objects.exclude(name=name).filter(code=code).exists():
            code = _generate_subject_code(name)
        if not code:
            code = _generate_subject_code(name)
        subject, created = Subject.objects.get_or_create(
            name=name,
            defaults={"code": code, "category": category, "is_active": True},
        )
        updates = []
        if not created and not subject.code:
            subject.code = code
            updates.append("code")
        if subject.category != category:
            subject.category = category
            updates.append("category")
        if not subject.is_active:
            subject.is_active = True
            updates.append("is_active")
        if updates:
            updates.append("updated_at")
            subject.save(update_fields=updates)

    setup_state = get_setup_state()
    setup_state.state = SetupStateCode.SUBJECTS_CREATED
    setup_state.last_updated_by = actor
    setup_state.save(update_fields=["state", "last_updated_by", "updated_at"])
    return setup_state


@transaction.atomic
def configure_class_subject_mappings(*, actor, class_subject_map):
    target_class_ids = set((class_subject_map or {}).keys())
    if not target_class_ids:
        raise ValueError("Select a class and map at least one subject.")

    for academic_class in AcademicClass.objects.filter(is_active=True, id__in=target_class_ids):
        selected_ids = set(class_subject_map.get(academic_class.id, []))
        existing = {
            row.subject_id: row
            for row in ClassSubject.objects.filter(academic_class=academic_class)
        }
        for subject_id in selected_ids:
            row = existing.get(subject_id)
            if row is None:
                ClassSubject.objects.create(
                    academic_class=academic_class,
                    subject_id=subject_id,
                    is_active=True,
                )
            elif not row.is_active:
                row.is_active = True
                row.save(update_fields=["is_active", "updated_at"])
        for subject_id, row in existing.items():
            if subject_id not in selected_ids and row.is_active:
                row.is_active = False
                row.save(update_fields=["is_active", "updated_at"])

    setup_state = get_setup_state()
    setup_state.state = SetupStateCode.CLASS_SUBJECTS_MAPPED
    setup_state.last_updated_by = actor
    setup_state.save(update_fields=["state", "last_updated_by", "updated_at"])
    return setup_state


@transaction.atomic
def configure_grade_scale(*, actor, apply_defaults=False, grade_ranges=None):
    if apply_defaults or not grade_ranges:
        GradeScale.ensure_default_scale()
    else:
        grade_labels = set(grade_ranges.keys())
        GradeScale.objects.filter(is_default=True).exclude(grade__in=grade_labels).delete()
        for grade, row in grade_ranges.items():
            GradeScale.objects.update_or_create(
                grade=grade,
                defaults={
                    "min_score": row["min_score"],
                    "max_score": row["max_score"],
                    "sort_order": row["sort_order"],
                    "is_default": True,
                },
            )
    setup_state = get_setup_state()
    setup_state.state = SetupStateCode.GRADE_SCALE_CONFIGURED
    setup_state.last_updated_by = actor
    setup_state.save(update_fields=["state", "last_updated_by", "updated_at"])
    return setup_state


@transaction.atomic
def finalize_setup(*, actor):
    setup_state = get_setup_state()
    if not setup_state.current_session_id or not setup_state.current_term_id:
        raise ValueError("Session and term are required before finalization.")
    if not SchoolCalendar.objects.filter(term=setup_state.current_term).exists():
        raise ValueError("School calendar is required before finalization.")
    if not AcademicClass.objects.filter(is_active=True).exists():
        raise ValueError("At least one class is required before finalization.")
    if not Subject.objects.filter(is_active=True).exists():
        raise ValueError("At least one subject is required before finalization.")
    if not ClassSubject.objects.filter(is_active=True).exists():
        raise ValueError("Map subjects to classes before finalization.")

    if not GradeScale.objects.filter(is_default=True).exists():
        GradeScale.ensure_default_scale()
    setup_state.state = SetupStateCode.IT_READY
    setup_state.last_updated_by = actor
    setup_state.finalized_by = actor
    setup_state.finalized_at = timezone.now()
    setup_state.save(
        update_fields=[
            "state",
            "last_updated_by",
            "finalized_by",
            "finalized_at",
            "updated_at",
        ]
    )
    return setup_state


def readable_term_choices():
    return [
        (TermName.FIRST, "First Term"),
        (TermName.SECOND, "Second Term"),
        (TermName.THIRD, "Third Term"),
    ]


def _derive_next_session_name(current_session_name):
    parts = current_session_name.strip().split("/")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        start = int(parts[0])
        end = int(parts[1])
        if end >= start:
            return f"{end}/{end + 1}"
    return f"{current_session_name}-NEXT"


def _ensure_unique_session_name(candidate_name):
    name = candidate_name
    suffix = 2
    while AcademicSession.objects.filter(name=name).exists():
        name = f"{candidate_name}-{suffix}"
        suffix += 1
    return name


def _ensure_session_terms(session):
    for term_name in TERM_SEQUENCE:
        Term.objects.get_or_create(session=session, name=term_name)


def _parse_class_stage(code):
    match = re.match(r"^(JS|SS)([1-3])(.*)$", (code or "").strip().upper())
    if not match:
        return None, ""
    stage = f"{match.group(1)}{match.group(2)}"
    suffix = match.group(3) or ""
    return stage, suffix


def _next_class_code(current_class_code):
    stage, suffix = _parse_class_stage(current_class_code)
    if not stage:
        return None
    if stage == TERMINAL_CLASS_STAGE:
        return None
    try:
        index = CLASS_STAGE_SEQUENCE.index(stage)
    except ValueError:
        return None
    if index >= len(CLASS_STAGE_SEQUENCE) - 1:
        return None
    next_stage = CLASS_STAGE_SEQUENCE[index + 1]
    return f"{next_stage}{suffix}"


def _is_terminal_class(current_class_code):
    stage, _ = _parse_class_stage(current_class_code)
    return stage == TERMINAL_CLASS_STAGE


def _next_active_class_for(academic_class):
    next_code = _next_class_code(academic_class.code)
    if not next_code:
        return None
    return AcademicClass.objects.filter(code=next_code, is_active=True).first()


def _apply_student_subject_enrollment_for_next_session(*, student, from_session, to_session, to_class):
    prior_subject_ids = set(
        StudentSubjectEnrollment.objects.filter(
            student=student,
            session=from_session,
            is_active=True,
        ).values_list("subject_id", flat=True)
    )
    mapped_next_subject_ids = set(
        ClassSubject.objects.filter(
            academic_class=to_class,
            is_active=True,
        ).values_list("subject_id", flat=True)
    )
    if prior_subject_ids:
        target_subject_ids = mapped_next_subject_ids & prior_subject_ids
    else:
        target_subject_ids = set()
    if not target_subject_ids:
        target_subject_ids = mapped_next_subject_ids

    existing_rows = {
        row.subject_id: row
        for row in StudentSubjectEnrollment.objects.filter(
            student=student,
            session=to_session,
        )
    }
    for subject_id in target_subject_ids:
        row = existing_rows.get(subject_id)
        if row is None:
            StudentSubjectEnrollment.objects.create(
                student=student,
                subject_id=subject_id,
                session=to_session,
                is_active=True,
            )
        elif not row.is_active:
            row.is_active = True
            row.save(update_fields=["is_active", "updated_at"])

    for subject_id, row in existing_rows.items():
        if subject_id not in target_subject_ids and row.is_active:
            row.is_active = False
            row.save(update_fields=["is_active", "updated_at"])

    StudentSubjectEnrollment.objects.filter(
        student=student,
        session=from_session,
        is_active=True,
    ).update(is_active=False, updated_at=timezone.now())


@dataclass
class SessionPromotionPreview:
    promoted_count: int
    retained_count: int
    graduated_count: int
    pending_target_classes: list[str]


def preview_session_promotion(*, session):
    enrollments = (
        StudentClassEnrollment.objects.select_related("academic_class")
        .filter(session=session, is_active=True)
        .order_by("academic_class__code")
    )
    promoted_count = 0
    retained_count = 0
    graduated_count = 0
    pending_target_classes = set()

    for enrollment in enrollments:
        current_class = enrollment.academic_class
        if _is_terminal_class(current_class.code):
            graduated_count += 1
            continue
        next_class = _next_active_class_for(current_class)
        if next_class:
            promoted_count += 1
        else:
            retained_count += 1
            pending_target_classes.add(current_class.code)

    return SessionPromotionPreview(
        promoted_count=promoted_count,
        retained_count=retained_count,
        graduated_count=graduated_count,
        pending_target_classes=sorted(pending_target_classes),
    )


@dataclass
class TermAdvanceResult:
    previous_session_name: str
    previous_term_name: str
    current_session_name: str
    current_term_name: str
    session_changed: bool


@dataclass
class SessionClosureResult:
    closed_session_name: str
    opened_session_name: str
    opened_term_name: str
    promoted_count: int
    retained_count: int
    graduated_count: int
    transcript_snapshot_count: int


@transaction.atomic
def advance_current_term(*, actor):
    setup_state = get_setup_state()
    if not setup_state.current_session_id or not setup_state.current_term_id:
        raise ValueError("Current session and current term must be configured.")

    current_session = setup_state.current_session
    current_term = setup_state.current_term
    previous_session_name = current_session.name
    previous_term_name = current_term.get_name_display()
    session_changed = False

    current_index = TERM_SEQUENCE.index(current_term.name)
    if current_index < len(TERM_SEQUENCE) - 1:
        next_term_name = TERM_SEQUENCE[current_index + 1]
        next_term, _ = Term.objects.get_or_create(
            session=current_session,
            name=next_term_name,
        )
        setup_state.current_term = next_term
    else:
        raise ValueError(
            "Third term is active. Use End Session to promote students and open next session."
        )

    setup_state.last_updated_by = actor
    setup_state.save(
        update_fields=[
            "current_session",
            "current_term",
            "last_updated_by",
            "updated_at",
        ]
    )

    return TermAdvanceResult(
        previous_session_name=previous_session_name,
        previous_term_name=previous_term_name,
        current_session_name=setup_state.current_session.name,
        current_term_name=setup_state.current_term.get_name_display(),
        session_changed=session_changed,
    )


@transaction.atomic
def end_current_session(*, actor):
    setup_state = get_setup_state()
    if not setup_state.current_session_id or not setup_state.current_term_id:
        raise ValueError("Current session and current term must be configured.")

    current_session = setup_state.current_session
    current_term = setup_state.current_term
    if current_term.name != TermName.THIRD:
        raise ValueError("End session is allowed only when current term is Third Term.")
    if current_session.is_closed:
        raise ValueError("Current session is already closed.")

    from apps.results.models import (
        ClassCompilationStatus,
        ClassResultCompilation,
        ResultSheet,
        ResultSheetStatus,
    )

    open_compilations = ClassResultCompilation.objects.filter(
        session=current_session,
        term=current_term,
    ).exclude(status=ClassCompilationStatus.PUBLISHED).count()
    open_result_sheets = ResultSheet.objects.filter(
        session=current_session,
        term=current_term,
    ).exclude(status=ResultSheetStatus.PUBLISHED).count()
    if open_compilations or open_result_sheets:
        raise ValueError(
            "Cannot close session while third-term results are not fully published."
        )

    proposed_name = _derive_next_session_name(current_session.name)
    next_session = AcademicSession.objects.filter(name=proposed_name).first()
    if next_session is None:
        next_session_name = _ensure_unique_session_name(proposed_name)
        next_session = AcademicSession.objects.create(name=next_session_name)
    _ensure_session_terms(next_session)
    next_term = Term.objects.get(session=next_session, name=TermName.FIRST)

    now = timezone.now()
    promoted_count = 0
    retained_count = 0
    graduated_count = 0
    enrollments = list(
        StudentClassEnrollment.objects.select_related("student", "academic_class")
        .filter(session=current_session, is_active=True)
        .order_by("id")
    )
    for enrollment in enrollments:
        student = enrollment.student
        from_class = enrollment.academic_class
        to_class = None
        if _is_terminal_class(from_class.code):
            outcome = SessionPromotionOutcome.GRADUATED
            graduated_count += 1
            profile = getattr(student, "student_profile", None)
            if profile is not None:
                profile.is_graduated = True
                profile.lifecycle_state = profile.LifecycleState.GRADUATED
                profile.graduation_session = current_session
                profile.graduated_at = now
                profile.save(
                    update_fields=[
                        "is_graduated",
                        "lifecycle_state",
                        "graduation_session",
                        "graduated_at",
                        "updated_at",
                    ]
                )
        else:
            next_class = _next_active_class_for(from_class)
            to_class = next_class or from_class
            if next_class:
                outcome = SessionPromotionOutcome.PROMOTED
                promoted_count += 1
            else:
                outcome = SessionPromotionOutcome.RETAINED
                retained_count += 1

            next_enrollment = StudentClassEnrollment.objects.filter(
                student=student,
                session=next_session,
                is_active=True,
            ).first()
            if next_enrollment:
                if next_enrollment.academic_class_id != to_class.id:
                    next_enrollment.academic_class = to_class
                    next_enrollment.save(update_fields=["academic_class", "updated_at"])
            else:
                StudentClassEnrollment.objects.create(
                    student=student,
                    academic_class=to_class,
                    session=next_session,
                    is_active=True,
                )
            _apply_student_subject_enrollment_for_next_session(
                student=student,
                from_session=current_session,
                to_session=next_session,
                to_class=to_class,
            )
            profile = getattr(student, "student_profile", None)
            if profile is not None and profile.is_graduated:
                profile.is_graduated = False
                if profile.lifecycle_state == profile.LifecycleState.GRADUATED:
                    profile.lifecycle_state = profile.LifecycleState.ACTIVE
                profile.graduation_session = None
                profile.graduated_at = None
                profile.save(
                    update_fields=[
                        "is_graduated",
                        "lifecycle_state",
                        "graduation_session",
                        "graduated_at",
                        "updated_at",
                    ]
                )

        enrollment.is_active = False
        enrollment.save(update_fields=["is_active", "updated_at"])
        SessionPromotionRecord.objects.update_or_create(
            session=current_session,
            student=student,
            defaults={
                "from_class": from_class,
                "to_class": to_class,
                "outcome": outcome,
                "generated_by": actor,
                "notes": "",
            },
        )

    TeacherSubjectAssignment.objects.filter(
        session=current_session,
        is_active=True,
    ).update(is_active=False, updated_at=now)
    FormTeacherAssignment.objects.filter(
        session=current_session,
        is_active=True,
    ).update(is_active=False, updated_at=now)

    current_session.is_closed = True
    current_session.closed_at = now
    current_session.closed_by = actor
    current_session.save(update_fields=["is_closed", "closed_at", "closed_by", "updated_at"])

    from apps.pdfs.services import snapshot_transcript_session_records

    transcript_snapshot_count = snapshot_transcript_session_records(
        session=current_session,
        generated_by=actor,
    )

    setup_state.current_session = next_session
    setup_state.current_term = next_term
    setup_state.last_updated_by = actor
    setup_state.save(
        update_fields=[
            "current_session",
            "current_term",
            "last_updated_by",
            "updated_at",
        ]
    )

    return SessionClosureResult(
        closed_session_name=current_session.name,
        opened_session_name=next_session.name,
        opened_term_name=next_term.get_name_display(),
        promoted_count=promoted_count,
        retained_count=retained_count,
        graduated_count=graduated_count,
        transcript_snapshot_count=transcript_snapshot_count,
    )


@transaction.atomic
def set_current_session_term(*, actor, session, term):
    if term.session_id != session.id:
        raise ValueError("Selected term does not belong to selected session.")
    if session.is_closed:
        raise ValueError("Closed session cannot be set as active context.")
    setup_state = get_setup_state()
    setup_state.current_session = session
    setup_state.current_term = term
    setup_state.last_updated_by = actor
    setup_state.save(
        update_fields=[
            "current_session",
            "current_term",
            "last_updated_by",
            "updated_at",
        ]
    )
    return setup_state
