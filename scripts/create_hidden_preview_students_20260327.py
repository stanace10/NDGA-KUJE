from __future__ import annotations

from datetime import date
from decimal import Decimal
import os

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from django.utils import timezone

from apps.accounts.constants import ROLE_BURSAR, ROLE_IT_MANAGER, ROLE_STUDENT
from apps.accounts.models import Role, StudentProfile
from apps.academics.models import AcademicClass, ClassSubject, StudentClassEnrollment, StudentSubjectEnrollment
from apps.dashboard.models import SchoolProfile
from apps.finance.forms import GatewayPaymentInitForm
from apps.finance.models import (
    ChargeTargetType,
    Payment,
    PaymentGatewayTransaction,
    Receipt,
    StudentCharge,
)
from apps.finance.services import (
    configured_gateway_provider_choices,
    current_academic_window,
    initialize_gateway_payment_transaction,
    record_manual_payment,
    resolve_payment_plan_amount,
    student_finance_overview,
)
from apps.notifications.models import Notification
from apps.notifications.services import notify_results_published, send_email_event
from apps.pdfs.models import PDFArtifact
from apps.pdfs.services import generate_performance_analysis_pdf, generate_term_report_pdf
from apps.results.models import (
    ClassCompilationStatus,
    ClassResultCompilation,
    ClassResultStudentRecord,
    ResultAccessPin,
    ResultSheet,
    ResultSheetStatus,
    StudentResultManagementStatus,
    StudentSubjectScore,
)
from apps.results.insights import build_result_comment_bundle
from apps.setup_wizard.services import get_setup_state


User = get_user_model()
PREVIEW_PASSWORD = "Preview#2026"
PREVIEW_GUARDIAN_EMAIL = "szubby10@gmail.com"
PREVIEW_STUDENT_PREFIX = "preview-20260327-"
PREVIEW_CLASS_PREFIX = "TST-20260327-"
PRIMARY_PREVIEW_EMAIL_SLUG = os.getenv("NDGA_PREVIEW_EMAIL_SLUG", "ss3").strip().lower() or "ss3"
PREVIEW_ONLY_SLUG = os.getenv("NDGA_PREVIEW_ONLY_SLUG", "").strip().lower()

PREVIEW_STUDENTS = [
    {
        "slug": "js3",
        "class_code": "JS3",
        "username": f"{PREVIEW_STUDENT_PREFIX}js3@ndgakuje.org",
        "student_number": "NDGAK/PREVIEW/JS3",
        "first_name": "Preview",
        "last_name": "JS3",
        "gender": StudentProfile.Gender.FEMALE,
        "guardian_name": "Preview Parent JS3",
        "attendance": Decimal("92.00"),
        "manual_payment": Decimal("125000.00"),
        "payment_plan": GatewayPaymentInitForm.PaymentPlan.FULL,
        "item_seed": 3,
    },
    {
        "slug": "ss1",
        "class_code": "SS1",
        "username": f"{PREVIEW_STUDENT_PREFIX}ss1@ndgakuje.org",
        "student_number": "NDGAK/PREVIEW/SS1",
        "first_name": "Preview",
        "last_name": "SS1",
        "gender": StudentProfile.Gender.FEMALE,
        "guardian_name": "Preview Parent SS1",
        "attendance": Decimal("84.00"),
        "manual_payment": Decimal("0.00"),
        "payment_plan": GatewayPaymentInitForm.PaymentPlan.FEE_ITEM,
        "fee_item_name": "School Fees",
        "item_seed": 7,
    },
    {
        "slug": "ss3",
        "class_code": "SS3",
        "username": f"{PREVIEW_STUDENT_PREFIX}ss3@ndgakuje.org",
        "student_number": "NDGAK/PREVIEW/SS3",
        "first_name": "Preview",
        "last_name": "SS3",
        "gender": StudentProfile.Gender.FEMALE,
        "guardian_name": "Preview Parent SS3",
        "attendance": Decimal("77.00"),
        "manual_payment": Decimal("0.00"),
        "payment_plan": GatewayPaymentInitForm.PaymentPlan.PERCENTAGE,
        "percentage": 50,
        "item_seed": 11,
        "subject_codes": [
            "BIO",
            "CHM",
            "CRS",
            "CVC",
            "ECO",
            "ENG",
            "FDN",
            "FTM",
            "GEO",
            "GOV",
            "LIT",
            "MTH",
            "PHY",
        ],
    },
]


def _actor_for_preview():
    for role_code in (ROLE_IT_MANAGER, ROLE_BURSAR):
        actor = (
            User.objects.filter(primary_role__code=role_code, is_active=True)
            .order_by("id")
            .first()
        )
        if actor:
            return actor
    return User.objects.filter(is_superuser=True, is_active=True).order_by("id").first()


def _cleanup_existing_preview_data():
    preview_students = list(User.objects.filter(username__startswith=PREVIEW_STUDENT_PREFIX))
    preview_student_ids = [row.id for row in preview_students]
    preview_classes = list(AcademicClass.objects.filter(code__startswith=PREVIEW_CLASS_PREFIX))

    if preview_student_ids:
        ResultAccessPin.objects.filter(student_id__in=preview_student_ids).delete()
        PDFArtifact.objects.filter(student_id__in=preview_student_ids).delete()
        Notification.objects.filter(recipient_id__in=preview_student_ids).delete()
        Receipt.objects.filter(payment__student_id__in=preview_student_ids).delete()
        Payment.objects.filter(student_id__in=preview_student_ids).delete()
        PaymentGatewayTransaction.objects.filter(student_id__in=preview_student_ids).delete()
        StudentCharge.objects.filter(student_id__in=preview_student_ids).delete()
        StudentSubjectScore.objects.filter(student_id__in=preview_student_ids).delete()
        ClassResultStudentRecord.objects.filter(student_id__in=preview_student_ids).delete()
        StudentSubjectEnrollment.objects.filter(student_id__in=preview_student_ids).delete()
        StudentClassEnrollment.objects.filter(student_id__in=preview_student_ids).delete()
        User.objects.filter(id__in=preview_student_ids).delete()

    if preview_classes:
        preview_class_ids = [row.id for row in preview_classes]
        ResultSheet.objects.filter(academic_class_id__in=preview_class_ids).delete()
        ClassResultCompilation.objects.filter(academic_class_id__in=preview_class_ids).delete()
        ClassSubject.objects.filter(academic_class_id__in=preview_class_ids).delete()
        AcademicClass.objects.filter(id__in=preview_class_ids).delete()


def _preview_class_for(real_class):
    code = f"{PREVIEW_CLASS_PREFIX}{real_class.code}"
    preview_class, _ = AcademicClass.objects.update_or_create(
        code=code,
        defaults={
            "display_name": real_class.display_name or real_class.code,
            "campus": real_class.campus,
            "base_class": None,
            "arm_name": "",
            "is_active": False,
        },
    )
    return preview_class


def _score_bundle(subject_code: str, student_seed: int):
    seed = sum(ord(ch) for ch in f"{subject_code}-{student_seed}")
    ca1 = Decimal(6 + (seed % 5))
    ca2 = Decimal(7 + (seed % 4))
    ca3 = Decimal(6 + ((seed // 3) % 5))
    ca4 = Decimal(7 + ((seed // 5) % 4))
    objective = Decimal(12 + ((seed // 7) % 9))
    theory = Decimal(20 + ((seed // 11) % 19))
    return {
        "ca1": ca1.quantize(Decimal("0.01")),
        "ca2": ca2.quantize(Decimal("0.01")),
        "ca3": ca3.quantize(Decimal("0.01")),
        "ca4": ca4.quantize(Decimal("0.01")),
        "objective": objective.quantize(Decimal("0.01")),
        "theory": theory.quantize(Decimal("0.01")),
    }


def _request_for(host: str):
    return RequestFactory().get("/", secure=True, HTTP_HOST=host)


def _subject_names_for_preview(subject_rows):
    strongest = [row["subject"] for row in sorted(subject_rows, key=lambda item: item["grand_total"], reverse=True)[:3]]
    weakest = [row["subject"] for row in sorted(subject_rows, key=lambda item: item["grand_total"])[:3]]
    return strongest, weakest


def _mapped_subjects_for_preview(*, real_class, preview_row):
    mapped_subjects = list(
        ClassSubject.objects.filter(academic_class=real_class, is_active=True)
        .select_related("subject")
        .order_by("subject__name")
    )
    subject_codes = [str(code).strip().upper() for code in (preview_row.get("subject_codes") or []) if str(code).strip()]
    if not subject_codes:
        return mapped_subjects
    by_code = {row.subject.code.upper(): row for row in mapped_subjects}
    return [by_code[code] for code in subject_codes if code in by_code]


def _create_preview_student(*, actor, preview_row, session, term, student_role, pin_required, send_preview_email):
    real_class = AcademicClass.objects.get(code=preview_row["class_code"], base_class__isnull=True)
    preview_class = _preview_class_for(real_class)
    student = User.objects.create_user(
        username=preview_row["username"],
        password=PREVIEW_PASSWORD,
        first_name=preview_row["first_name"],
        last_name=preview_row["last_name"],
        display_name=f"{preview_row['class_code']} Preview Student",
        email=PREVIEW_GUARDIAN_EMAIL,
        primary_role=student_role,
        must_change_password=False,
        password_changed_count=1,
        is_active=True,
    )
    StudentProfile.objects.create(
        user=student,
        student_number=preview_row["student_number"],
        admission_date=date(2025, 9, 15),
        date_of_birth=date(2010 if preview_row["class_code"].startswith("SS") else 2012, 5, 14),
        gender=preview_row["gender"],
        guardian_name=preview_row["guardian_name"],
        guardian_email=PREVIEW_GUARDIAN_EMAIL,
        guardian_phone="08167111734",
        address="Preview Student Test Record",
        state_of_origin="FCT",
        nationality="Nigerian",
    )

    compilation = ClassResultCompilation.objects.create(
        academic_class=preview_class,
        session=session,
        term=term,
        form_teacher=actor,
        status=ClassCompilationStatus.PUBLISHED,
        published_at=timezone.now(),
        vp_actor=actor if actor and actor.has_role("VP") else None,
        principal_override_actor=actor if actor and actor.has_role("PRINCIPAL") else None,
        decision_comment="Preview result published for final QA review.",
    )

    mapped_subjects = _mapped_subjects_for_preview(real_class=real_class, preview_row=preview_row)
    subject_rows = []
    for subject_map in mapped_subjects:
        sheet = ResultSheet.objects.create(
            academic_class=preview_class,
            subject=subject_map.subject,
            session=session,
            term=term,
            status=ResultSheetStatus.PUBLISHED,
            created_by=actor,
        )
        score_kwargs = _score_bundle(subject_map.subject.code, preview_row["item_seed"])
        score = StudentSubjectScore.objects.create(
            result_sheet=sheet,
            student=student,
            **score_kwargs,
        )
        subject_rows.append(
            {
                "subject": subject_map.subject.name,
                "grand_total": Decimal(score.grand_total or 0),
            }
        )

    strongest, weakest = _subject_names_for_preview(subject_rows)
    average_score = (
        sum((row["grand_total"] for row in subject_rows), Decimal("0.00")) / Decimal(len(subject_rows))
    ).quantize(Decimal("0.01"))
    comment_bundle = build_result_comment_bundle(
        student_name=student.get_full_name() or student.username,
        average_score=average_score,
        attendance_percentage=preview_row["attendance"],
        fail_count=len([row for row in subject_rows if row["grand_total"] < Decimal("50.00")]),
        weak_subjects=weakest,
        strongest_subjects=strongest,
        predicted_score=average_score + Decimal("2.50"),
        risk_label="Low" if average_score >= Decimal("60.00") else "Moderate",
        teacher_guidance="Keep comments concise, parent-friendly, and specific to the student's real strengths and support areas.",
        principal_guidance="Keep the principal note warm, brief, and focused on next-step support.",
    )
    record = ClassResultStudentRecord.objects.create(
        compilation=compilation,
        student=student,
        attendance_percentage=preview_row["attendance"],
        behavior_rating=4,
        behavior_breakdown={
            "discipline": 4,
            "punctuality": 4,
            "respect": 5,
            "leadership": 4,
            "sports": 3,
            "neatness": 4,
            "participation": 4,
        },
        teacher_comment=comment_bundle["teacher_comment"],
        principal_comment=comment_bundle["principal_comment"],
        management_status=StudentResultManagementStatus.REVIEWED,
        management_comment="Preview result checked for QA.",
        management_actor=actor,
        club_membership="Jet Club",
        office_held="Class Prefect Assistant",
        notable_contribution="Participates actively in classroom discussions.",
    )

    if pin_required:
        ResultAccessPin.objects.update_or_create(
            student=student,
            session=session,
            term=term,
            defaults={
                "pin_code": "1234",
                "generated_by": actor,
                "is_active": True,
            },
        )

    for item_name, amount in (
        ("School Fees", Decimal("180000.00")),
        ("Hostel Fee", Decimal("90000.00")),
        ("Feeding", Decimal("70000.00")),
    ):
        StudentCharge.objects.create(
            item_name=item_name,
            description=f"Preview charge for {preview_row['class_code']} result/payment QA.",
            amount=amount,
            session=session,
            term=term,
            target_type=ChargeTargetType.STUDENT,
            student=student,
            created_by=actor,
            is_active=True,
        )

    if preview_row["manual_payment"] > Decimal("0.00"):
        record_manual_payment(
            student=student,
            session=session,
            term=term,
            amount=preview_row["manual_payment"],
            payment_method="TRANSFER",
            payment_date=timezone.localdate(),
            received_by=actor,
            note="Preview manual payment for QA.",
            request=_request_for("student.ndgakuje.org"),
        )

    overview = student_finance_overview(student=student, session=session, term=term)
    payment_plan = preview_row["payment_plan"]
    resolved_amount, payment_meta = resolve_payment_plan_amount(
        overview=overview,
        payment_plan=payment_plan,
        fee_item=preview_row.get("fee_item_name", ""),
        percentage=preview_row.get("percentage"),
        custom_amount=overview["total_outstanding"],
    )
    payment_link = None
    payment_reference = None
    provider_choices = configured_gateway_provider_choices()
    payment_error = ""
    if provider_choices:
        try:
            transaction_row = initialize_gateway_payment_transaction(
                student=student,
                session=session,
                term=term,
                amount=resolved_amount,
                initiated_by=actor,
                request=_request_for("student.ndgakuje.org"),
                provider=provider_choices[0][0],
                auto_email_link=True,
            )
            transaction_row.metadata = {**transaction_row.metadata, "payment_plan": payment_meta}
            transaction_row.save(update_fields=["metadata", "updated_at"])
            payment_link = transaction_row.authorization_url
            payment_reference = transaction_row.reference
        except ValidationError as exc:
            payment_error = "; ".join(exc.messages)

    notify_results_published(
        compilation=compilation,
        actor=actor,
        request=_request_for("student.ndgakuje.org"),
    )

    term_pdf, _term_artifact = generate_term_report_pdf(
        request=_request_for("student.ndgakuje.org"),
        student=student,
        compilation=compilation,
        generated_by=actor,
    )
    performance_pdf, _perf_artifact = generate_performance_analysis_pdf(
        request=_request_for("student.ndgakuje.org"),
        student=student,
        compilation=compilation,
        generated_by=actor,
    )
    reports_center_url = "https://student.ndgakuje.org/pdfs/student/reports/"
    report_view_url = f"https://student.ndgakuje.org/pdfs/student/reports/{compilation.id}/"
    report_download_url = f"https://student.ndgakuje.org/pdfs/student/reports/{compilation.id}/download/"
    performance_view_url = f"https://student.ndgakuje.org/pdfs/student/reports/{compilation.id}/performance/"
    email_result = None
    if send_preview_email:
        email_result = send_email_event(
            to_emails=[PREVIEW_GUARDIAN_EMAIL],
            subject=f"NDGA Preview Result Pack - {preview_row['class_code']}",
            body_text=(
                f"Please find attached the official report card and performance report for "
                f"{student.get_full_name() or student.username}.\n\n"
                f"Ward Name: {student.get_full_name() or student.username}\n"
                f"Login ID: {student.username}\n"
                f"Admission Number: {preview_row['student_number']}\n"
                f"Temporary Password: {PREVIEW_PASSWORD}\n\n"
                f"Student portal login: https://student.ndgakuje.org/auth/login/?audience=student\n"
                f"Result link: {report_view_url}\n\n"
                f"Attached: Official Report Card PDF and Performance Report PDF."
            ),
            actor=actor,
            request=_request_for("student.ndgakuje.org"),
            metadata={
                "event": "PREVIEW_RESULT_PACK",
                "student": student.username,
                "class_code": preview_row["class_code"],
            },
            attachments=[
                {
                    "name": f"NDGA-{preview_row['class_code']}-Official-Report-Card.pdf",
                    "content": term_pdf,
                    "mimetype": "application/pdf",
                },
                {
                    "name": f"NDGA-{preview_row['class_code']}-Performance-Report.pdf",
                    "content": performance_pdf,
                    "mimetype": "application/pdf",
                },
            ],
        )

    return {
        "student_id": student.id,
        "username": student.username,
        "student_number": preview_row["student_number"],
        "class_code": preview_row["class_code"],
        "compilation_id": compilation.id,
        "subject_count": len(mapped_subjects),
        "attendance": str(record.attendance_percentage),
        "average": str(average_score),
        "report_view_url": report_view_url,
        "report_download_url": report_download_url,
        "performance_view_url": performance_view_url,
        "payment_link": payment_link or "",
        "payment_reference": payment_reference or "",
        "payment_error": payment_error,
        "email_result": getattr(email_result, "detail", ""),
        "email_provider": getattr(email_result, "provider", ""),
    }


def main():
    setup_state = get_setup_state()
    session = setup_state.current_session
    term = setup_state.current_term
    if session is None or term is None:
        raise RuntimeError("Current session/term is not configured.")

    actor = _actor_for_preview()
    if actor is None:
        raise RuntimeError("No IT Manager/Bursar/Superuser account found to own preview artifacts.")

    student_role = Role.objects.get(code=ROLE_STUDENT)
    pin_required = bool(SchoolProfile.load().require_result_access_pin)

    _cleanup_existing_preview_data()

    preview_rows = PREVIEW_STUDENTS
    if PREVIEW_ONLY_SLUG:
        preview_rows = [row for row in PREVIEW_STUDENTS if row["slug"].lower() == PREVIEW_ONLY_SLUG]
        if not preview_rows:
            raise RuntimeError(f"No preview definition found for slug '{PREVIEW_ONLY_SLUG}'.")

    summaries = []
    for row in preview_rows:
        summaries.append(
            _create_preview_student(
                actor=actor,
                preview_row=row,
                session=session,
                term=term,
                student_role=student_role,
                pin_required=pin_required,
                send_preview_email=(row["slug"].lower() == PRIMARY_PREVIEW_EMAIL_SLUG),
            )
        )

    print("PREVIEW_STUDENTS_CREATED")
    for row in summaries:
        print(row)


main()
