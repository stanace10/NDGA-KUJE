from django.utils import timezone

from apps.results.models import (
    ClassCompilationStatus,
    ClassResultCompilation,
    ResultSheet,
    ResultSheetStatus,
    ResultSubmission,
)


TEACHER_EDITABLE_STATUSES = {
    ResultSheetStatus.DRAFT,
    ResultSheetStatus.REJECTED_BY_DEAN,
}


def is_teacher_editable_status(status):
    return status in TEACHER_EDITABLE_STATUSES


def transition_result_sheet(*, sheet: ResultSheet, to_status, actor, action, comment=""):
    from_status = sheet.status
    if from_status == to_status:
        return sheet
    sheet.status = to_status
    sheet.save(update_fields=["status", "updated_at"])
    ResultSubmission.objects.create(
        result_sheet=sheet,
        actor=actor,
        from_status=from_status,
        to_status=to_status,
        action=action,
        comment=comment,
    )
    return sheet


def transition_class_sheet_set(*, sheets_qs, to_status, actor, action, comment=""):
    for sheet in sheets_qs:
        transition_result_sheet(
            sheet=sheet,
            to_status=to_status,
            actor=actor,
            action=action,
            comment=comment,
        )


def mark_compilation_submitted_to_vp(compilation: ClassResultCompilation, actor, *, form_teacher=None):
    compilation.status = ClassCompilationStatus.SUBMITTED_TO_VP
    if form_teacher is not None:
        compilation.form_teacher = form_teacher
    elif compilation.form_teacher is None:
        compilation.form_teacher = actor
    compilation.submitted_to_vp_at = timezone.now()
    compilation.decision_comment = ""
    compilation.save(
        update_fields=[
            "status",
            "form_teacher",
            "submitted_to_vp_at",
            "decision_comment",
            "updated_at",
        ]
    )
    return compilation


def mark_compilation_rejected_by_vp(
    compilation: ClassResultCompilation,
    actor,
    comment,
    *,
    principal_override=False,
):
    compilation.status = ClassCompilationStatus.REJECTED_BY_VP
    if principal_override:
        compilation.principal_override_actor = actor
    else:
        compilation.vp_actor = actor
    compilation.decision_comment = comment
    compilation.save(
        update_fields=[
            "status",
            "vp_actor",
            "principal_override_actor",
            "decision_comment",
            "updated_at",
        ]
    )
    return compilation


def mark_compilation_published(
    compilation: ClassResultCompilation,
    actor,
    *,
    principal_override=False,
    comment="",
):
    compilation.status = ClassCompilationStatus.PUBLISHED
    compilation.published_at = timezone.now()
    if principal_override:
        compilation.principal_override_actor = actor
    else:
        compilation.vp_actor = actor
    compilation.decision_comment = (comment or "").strip()
    compilation.save(
        update_fields=[
            "status",
            "published_at",
            "vp_actor",
            "principal_override_actor",
            "decision_comment",
            "updated_at",
        ]
    )
    return compilation
