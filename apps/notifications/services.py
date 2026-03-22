from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from django.utils import timezone

from apps.audit.services import log_event
from apps.audit.models import AuditCategory, AuditStatus
from apps.notifications.email_adapters import EmailSendResult, get_email_provider
from apps.notifications.whatsapp_adapters import WhatsAppSendResult, get_whatsapp_provider
from apps.notifications.models import Notification, NotificationCategory
from apps.tenancy.utils import build_portal_url


def _normalized_emails(emails):
    seen = set()
    clean = []
    for email in emails:
        value = (email or "").strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        clean.append(value)
    return clean


def normalize_whatsapp_phone(raw_phone):
    digits = "".join(ch for ch in str(raw_phone or "") if ch.isdigit())
    if not digits:
        return ""
    if digits.startswith("234"):
        return digits
    if digits.startswith("0") and len(digits) == 11:
        return f"234{digits[1:]}"
    if len(digits) == 10:
        return f"234{digits}"
    return digits


def _normalized_phones(phones):
    seen = set()
    clean = []
    for phone in phones:
        value = normalize_whatsapp_phone(phone)
        if not value or value in seen:
            continue
        seen.add(value)
        clean.append(value)
    return clean


@dataclass
class WhatsAppBulkDispatchResult:
    success: bool
    provider: str
    sent_count: int = 0
    failed_count: int = 0
    detail: str = ""
    results: list[WhatsAppSendResult] | None = None


def create_notification(
    *,
    recipient,
    category,
    title,
    message,
    created_by=None,
    action_url="",
    metadata=None,
):
    return Notification.objects.create(
        recipient=recipient,
        category=category,
        title=title,
        message=message,
        created_by=created_by if getattr(created_by, "is_authenticated", False) else None,
        action_url=action_url,
        metadata=metadata or {},
    )


def create_bulk_notifications(
    *,
    recipients: Iterable,
    category,
    title,
    message,
    created_by=None,
    action_url="",
    metadata=None,
):
    notifications = []
    for user in recipients:
        notifications.append(
            create_notification(
                recipient=user,
                category=category,
                title=title,
                message=message,
                created_by=created_by,
                action_url=action_url,
                metadata=metadata,
            )
        )
    return notifications


def send_email_event(
    *,
    to_emails,
    subject,
    body_text,
    actor=None,
    request=None,
    metadata=None,
    body_html="",
):
    provider = get_email_provider()
    emails = _normalized_emails(to_emails)
    if not emails:
        return None
    try:
        result = provider.send(
            to_emails=emails,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )
    except Exception as exc:  # noqa: BLE001
        result = EmailSendResult(
            success=False,
            provider=getattr(provider, "provider_name", "unknown"),
            detail=f"{type(exc).__name__}: {exc}",
        )
    status = AuditStatus.SUCCESS if result.success else AuditStatus.FAILURE
    log_event(
        category=AuditCategory.SYSTEM,
        event_type="EMAIL_EVENT",
        status=status,
        actor=actor,
        request=request,
        message=f"Email dispatch via {result.provider}.",
        metadata={
            "provider": result.provider,
            "detail": result.detail,
            "to_count": len(emails),
            "to_emails": emails,
            **(metadata or {}),
        },
    )
    return result


def send_whatsapp_event(
    *,
    to_numbers,
    body_text,
    actor=None,
    request=None,
    metadata=None,
    preview_url=True,
):
    provider = get_whatsapp_provider()
    numbers = _normalized_phones(to_numbers)
    if not numbers:
        return WhatsAppBulkDispatchResult(
            success=False,
            provider=getattr(provider, "provider_name", "unknown"),
            detail="No WhatsApp numbers available.",
            results=[],
        )

    results = []
    sent_count = 0
    failed_count = 0
    for number in numbers:
        try:
            result = provider.send(
                to_number=number,
                body_text=body_text,
                preview_url=preview_url,
            )
        except Exception as exc:  # noqa: BLE001
            result = WhatsAppSendResult(
                success=False,
                provider=getattr(provider, "provider_name", "unknown"),
                detail=f"{type(exc).__name__}: {exc}",
            )
        results.append(result)
        if result.success:
            sent_count += 1
        else:
            failed_count += 1

    dispatch_result = WhatsAppBulkDispatchResult(
        success=sent_count > 0 and failed_count == 0,
        provider=getattr(provider, "provider_name", "unknown"),
        sent_count=sent_count,
        failed_count=failed_count,
        detail=f"sent={sent_count} failed={failed_count}",
        results=results,
    )
    log_event(
        category=AuditCategory.SYSTEM,
        event_type="WHATSAPP_EVENT",
        status=AuditStatus.SUCCESS if sent_count > 0 else AuditStatus.FAILURE,
        actor=actor,
        request=request,
        message=f"WhatsApp dispatch via {dispatch_result.provider}.",
        metadata={
            "provider": dispatch_result.provider,
            "detail": dispatch_result.detail,
            "to_count": len(numbers),
            "to_numbers": numbers,
            "sent_count": sent_count,
            "failed_count": failed_count,
            **(metadata or {}),
        },
    )
    return dispatch_result


def notify_results_published(*, compilation, actor, request=None):
    records = compilation.student_records.select_related("student", "student__student_profile").all()
    recipients = [row.student for row in records]
    action_url = "/pdfs/student/reports/"
    title = "Result Published"
    message = (
        f"Your {compilation.term.get_name_display()} result for session "
        f"{compilation.session.name} is now available."
    )
    created = create_bulk_notifications(
        recipients=recipients,
        category=NotificationCategory.RESULTS,
        title=title,
        message=message,
        created_by=actor,
        action_url=action_url,
        metadata={
            "compilation_id": str(compilation.id),
            "session": compilation.session.name,
            "term": compilation.term.name,
            "class_code": compilation.academic_class.code,
            "published_at": (compilation.published_at or timezone.now()).isoformat(),
        },
    )

    guardian_emails = []
    for row in records:
        profile = getattr(row.student, "student_profile", None)
        if profile and profile.guardian_email:
            guardian_emails.append(profile.guardian_email)
        elif row.student.email:
            guardian_emails.append(row.student.email)

    if guardian_emails:
        report_url = build_portal_url(request, "student", action_url) if request else action_url
        send_email_event(
            to_emails=guardian_emails,
            subject=f"NDGA Result Published: {compilation.term.get_name_display()}",
            body_text=(
                f"Results are now published for {compilation.academic_class.code} "
                f"({compilation.session.name}, {compilation.term.get_name_display()}). "
                f"Access the portal: {report_url}"
            ),
            actor=actor,
            request=request,
            metadata={
                "event": "RESULT_PUBLISHED",
                "compilation_id": str(compilation.id),
            },
        )
    return created


def notify_payment_receipt(*, student, receipt_number, amount, actor, request=None, message=""):
    title = "Payment Receipt Issued"
    base_message = (
        message
        or f"Receipt {receipt_number} has been issued for payment of {amount}."
    )
    notification = create_notification(
        recipient=student,
        category=NotificationCategory.PAYMENT,
        title=title,
        message=base_message,
        created_by=actor,
        action_url="/finance/student/overview/",
        metadata={"receipt_number": receipt_number, "amount": str(amount)},
    )
    emails = []
    profile = getattr(student, "student_profile", None)
    if profile and profile.guardian_email:
        emails.append(profile.guardian_email)
    if student.email:
        emails.append(student.email)
    if emails:
        send_email_event(
            to_emails=emails,
            subject=f"NDGA Payment Receipt {receipt_number}",
            body_text=base_message,
            actor=actor,
            request=request,
            metadata={"event": "PAYMENT_RECEIPT", "receipt_number": receipt_number},
        )
    return notification


def notify_election_announcement(*, recipients, title, message, actor, request=None, action_url=""):
    created = create_bulk_notifications(
        recipients=recipients,
        category=NotificationCategory.ELECTION,
        title=title,
        message=message,
        created_by=actor,
        action_url=action_url or "/portal/election/",
        metadata={"event": "ELECTION_ANNOUNCEMENT"},
    )
    emails = [user.email for user in recipients if user.email]
    if emails:
        send_email_event(
            to_emails=emails,
            subject=title,
            body_text=message,
            actor=actor,
            request=request,
            metadata={"event": "ELECTION_ANNOUNCEMENT"},
        )
    return created



def _guardian_emails_for_student(student):
    emails = []
    profile = getattr(student, "student_profile", None)
    if profile and profile.guardian_email:
        emails.append(profile.guardian_email)
    if student.email:
        emails.append(student.email)
    return _normalized_emails(emails)



def notify_attendance_alert(*, student, attendance_date, status, actor, request=None, academic_class=None):
    if status != "ABSENT":
        return None
    title = "Attendance Alert"
    class_code = getattr(academic_class, "code", "your class")
    message = f"Attendance was marked ABSENT for {attendance_date} in {class_code}."
    notification = create_notification(
        recipient=student,
        category=NotificationCategory.SYSTEM,
        title=title,
        message=message,
        created_by=actor,
        action_url="/portal/student/attendance/",
        metadata={
            "event": "ATTENDANCE_ALERT",
            "attendance_date": str(attendance_date),
            "class_code": class_code,
        },
    )
    emails = _guardian_emails_for_student(student)
    if emails:
        send_email_event(
            to_emails=emails,
            subject=f"NDGA Attendance Alert: {class_code}",
            body_text=message,
            actor=actor,
            request=request,
            metadata={
                "event": "ATTENDANCE_ALERT",
                "attendance_date": str(attendance_date),
                "student": student.username,
            },
        )
    return notification



def notify_cbt_schedule_published(*, exam, actor, request=None):
    from apps.academics.models import StudentClassEnrollment, StudentSubjectEnrollment

    class_enrollment_qs = StudentClassEnrollment.objects.filter(
        academic_class_id__in=exam.academic_class.cohort_class_ids(),
        session=exam.session,
        is_active=True,
    ).select_related("student", "student__student_profile")
    student_ids = list(class_enrollment_qs.values_list("student_id", flat=True))
    subject_ids = set(
        StudentSubjectEnrollment.objects.filter(
            student_id__in=student_ids,
            session=exam.session,
            subject=exam.subject,
            is_active=True,
        ).values_list("student_id", flat=True)
    )
    recipients = [row.student for row in class_enrollment_qs if (not subject_ids or row.student_id in subject_ids)]
    if not recipients:
        return []
    action_url = "/cbt/exams/available/"
    if exam.schedule_start and exam.schedule_end:
        time_message = (
            f"Opens {exam.schedule_start:%d %b %Y %H:%M} and closes {exam.schedule_end:%d %b %Y %H:%M}."
        )
    else:
        time_message = "Check the CBT portal for the active window."
    title = f"CBT Scheduled: {exam.subject.name}"
    message = f"{exam.title} is scheduled for {exam.academic_class.code}. {time_message}"
    created = create_bulk_notifications(
        recipients=recipients,
        category=NotificationCategory.SYSTEM,
        title=title,
        message=message,
        created_by=actor,
        action_url=action_url,
        metadata={
            "event": "CBT_SCHEDULED",
            "exam_id": str(exam.id),
            "class_code": exam.academic_class.code,
            "subject": exam.subject.name,
        },
    )
    emails = []
    for student in recipients:
        emails.extend(_guardian_emails_for_student(student))
    if emails:
        portal_url = build_portal_url(request, "cbt", action_url) if request else action_url
        send_email_event(
            to_emails=emails,
            subject=title,
            body_text=f"{message} Access the CBT portal: {portal_url}",
            actor=actor,
            request=request,
            metadata={
                "event": "CBT_SCHEDULED",
                "exam_id": str(exam.id),
            },
        )
    return created



def notify_assignment_deadline(*, academic_class, subject, topic, due_date, actor, request=None, session=None):
    from apps.academics.models import StudentClassEnrollment, StudentSubjectEnrollment

    enrollment_qs = StudentClassEnrollment.objects.filter(
        academic_class_id__in=academic_class.cohort_class_ids(),
        is_active=True,
    ).select_related("student", "student__student_profile")
    if session is not None:
        enrollment_qs = enrollment_qs.filter(session=session)
    subject_enrollment_qs = StudentSubjectEnrollment.objects.filter(
        student_id__in=enrollment_qs.values_list("student_id", flat=True),
        subject=subject,
        is_active=True,
    )
    if session is not None:
        subject_enrollment_qs = subject_enrollment_qs.filter(session=session)
    subject_student_ids = set(subject_enrollment_qs.values_list("student_id", flat=True))
    recipients = [row.student for row in enrollment_qs if (not subject_student_ids or row.student_id in subject_student_ids)]
    if not recipients:
        return []
    due_label = f" due {due_date}" if due_date else ""
    title = f"Assignment Deadline: {subject.name}"
    message = f"A new assignment on {topic} has been published for {academic_class.code}{due_label}."
    created = create_bulk_notifications(
        recipients=recipients,
        category=NotificationCategory.SYSTEM,
        title=title,
        message=message,
        created_by=actor,
        action_url="/portal/student/learning-hub/",
        metadata={
            "event": "ASSIGNMENT_DEADLINE",
            "class_code": academic_class.code,
            "subject": subject.name,
            "topic": topic,
            "due_date": str(due_date) if due_date else "",
        },
    )
    emails = []
    for student in recipients:
        emails.extend(_guardian_emails_for_student(student))
    if emails:
        portal_url = build_portal_url(request, "student", "/portal/student/learning-hub/") if request else "/portal/student/learning-hub/"
        send_email_event(
            to_emails=emails,
            subject=title,
            body_text=f"{message} Open the learning hub: {portal_url}",
            actor=actor,
            request=request,
            metadata={
                "event": "ASSIGNMENT_DEADLINE",
                "class_code": academic_class.code,
                "subject": subject.name,
                "topic": topic,
            },
        )
    return created
