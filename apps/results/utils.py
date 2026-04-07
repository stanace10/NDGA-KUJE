from django.conf import settings

from apps.accounts.constants import (
    ROLE_DEAN,
    ROLE_FORM_TEACHER,
    ROLE_IT_MANAGER,
    ROLE_PRINCIPAL,
    ROLE_SUBJECT_TEACHER,
    ROLE_VP,
)
from apps.academics.models import AcademicSession, FormTeacherAssignment, TeacherSubjectAssignment, Term
from apps.results.models import ResultSheet, ResultSheetStatus
from apps.setup_wizard.services import get_setup_state


def current_session_term():
    setup_state = get_setup_state()
    return setup_state.current_session, setup_state.current_term


def teacher_assignments_for_user(user, *, include_all_periods=False):
    session, term = current_session_term()
    qs = TeacherSubjectAssignment.objects.select_related(
        "teacher", "subject", "academic_class", "session", "term"
    ).filter(is_active=True)
    if not include_all_periods and session and term:
        qs = qs.filter(session=session, term=term)
    if user.has_role(ROLE_IT_MANAGER) or user.has_role(ROLE_PRINCIPAL):
        return qs
    return qs.filter(teacher=user)


def resolve_teacher_assignment_window(
    user,
    *,
    requested_session_id=None,
    requested_term_id=None,
):
    setup_state = get_setup_state()
    assignment_qs = teacher_assignments_for_user(user, include_all_periods=True)

    session_ids = list(
        assignment_qs.values_list("session_id", flat=True).distinct()
    )
    available_sessions = list(
        AcademicSession.objects.filter(id__in=session_ids).order_by("-name")
    )

    selected_session = None
    if requested_session_id:
        selected_session = next(
            (
                row
                for row in available_sessions
                if str(row.id) == str(requested_session_id)
            ),
            None,
        )
    if selected_session is None:
        selected_session = next(
            (
                row
                for row in available_sessions
                if setup_state.current_session_id and row.id == setup_state.current_session_id
            ),
            None,
        )
    if selected_session is None and available_sessions:
        selected_session = available_sessions[0]

    available_terms = []
    if selected_session:
        term_ids = list(
            assignment_qs.filter(session=selected_session)
            .values_list("term_id", flat=True)
            .distinct()
        )
        available_terms = list(
            Term.objects.filter(id__in=term_ids).order_by("name")
        )

    selected_term = None
    if requested_term_id:
        selected_term = next(
            (
                row
                for row in available_terms
                if str(row.id) == str(requested_term_id)
            ),
            None,
        )
    if selected_term is None:
        selected_term = next(
            (
                row
                for row in available_terms
                if setup_state.current_term_id and row.id == setup_state.current_term_id
            ),
            None,
        )
    if selected_term is None and available_terms:
        selected_term = available_terms[0]

    if selected_session:
        assignment_qs = assignment_qs.filter(session=selected_session)
    if selected_term:
        assignment_qs = assignment_qs.filter(term=selected_term)

    return {
        "assignments": assignment_qs,
        "available_sessions": available_sessions,
        "available_terms": available_terms,
        "selected_session": selected_session,
        "selected_term": selected_term,
    }


def form_teacher_classes_for_user(user, *, session=None):
    active_session = session
    if active_session is None:
        active_session, _term = current_session_term()
    qs = FormTeacherAssignment.objects.select_related("academic_class", "session").filter(
        is_active=True
    )
    if active_session:
        qs = qs.filter(session=active_session)
    if user.has_role(ROLE_IT_MANAGER) or user.has_role(ROLE_PRINCIPAL):
        return qs
    return qs.filter(teacher=user)


def sheet_is_editable_by_subject_owner(user, sheet: ResultSheet):
    if user.has_role(ROLE_IT_MANAGER):
        return True
    if sheet.session.is_closed:
        return False
    if sheet.status not in {ResultSheetStatus.DRAFT, ResultSheetStatus.REJECTED_BY_DEAN}:
        return False
    return TeacherSubjectAssignment.objects.filter(
        teacher=user,
        subject=sheet.subject,
        academic_class=sheet.academic_class,
        session=sheet.session,
        term=sheet.term,
        is_active=True,
    ).exists()


def principal_override_enabled():
    return settings.RESULTS_POLICY.get("PRINCIPAL_OVERRIDE_ENABLED", True)


def session_is_open_for_edits(session):
    return bool(session) and not session.is_closed


RESULTS_STAGE7_ROLES = {
    ROLE_SUBJECT_TEACHER,
    ROLE_DEAN,
    ROLE_FORM_TEACHER,
    ROLE_VP,
    ROLE_PRINCIPAL,
    ROLE_IT_MANAGER,
}
