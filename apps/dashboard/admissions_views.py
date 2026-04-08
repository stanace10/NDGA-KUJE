from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import TemplateView

from apps.accounts.constants import ROLE_BURSAR, ROLE_IT_MANAGER, ROLE_PRINCIPAL, ROLE_STUDENT, ROLE_VP
from apps.accounts.forms import (
    _generate_student_number,
    _generate_student_username,
    generate_temporary_password,
)
from apps.accounts.models import Role, StudentProfile, User
from apps.academics.models import AcademicClass, StudentClassEnrollment
from apps.dashboard.models import (
    PublicAdmissionPaymentStatus,
    PublicAdmissionWorkflowStatus,
    PublicSiteSubmission,
    PublicSubmissionType,
)
from apps.dashboard.views import PortalPageView
from apps.setup_wizard.services import get_setup_state


INTENDED_CLASS_CODE_MAP = {
    "JSS1": "JS1",
    "JSS2": "JS2",
    "JSS3": "JS3",
    "SS1": "SS1",
    "SS2": "SS2",
    "SS3": "SS3",
}


def _split_applicant_name(full_name: str):
    parts = [chunk.strip() for chunk in (full_name or "").split() if chunk.strip()]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _resolved_academic_class_for_submission(submission: PublicSiteSubmission):
    intended_code = INTENDED_CLASS_CODE_MAP.get((submission.intended_class or "").upper(), "")
    if not intended_code:
        return None
    direct = (
        AcademicClass.objects.filter(code__iexact=intended_code, is_active=True)
        .select_related("base_class")
        .order_by("base_class_id", "code")
        .first()
    )
    if direct:
        return direct
    return (
        AcademicClass.objects.filter(code__istartswith=intended_code, is_active=True)
        .select_related("base_class")
        .order_by("base_class_id", "code")
        .first()
    )


def _create_student_from_submission(submission: PublicSiteSubmission):
    role_student = Role.objects.get(code=ROLE_STUDENT)
    student_number = _generate_student_number()
    username = _generate_student_username(student_number)
    password = generate_temporary_password(student_number)
    first_name, last_name = _split_applicant_name(submission.applicant_name)
    user = User.objects.create_user(
        username=username,
        password=password,
        email=(submission.guardian_email or submission.contact_email or "").strip().lower(),
        first_name=first_name,
        last_name=last_name,
        primary_role=role_student,
        must_change_password=False,
        password_changed_count=0,
    )
    StudentProfile.objects.create(
        user=user,
        student_number=student_number,
        admission_date=timezone.localdate(),
        date_of_birth=submission.applicant_date_of_birth,
        guardian_name=submission.guardian_name,
        guardian_phone=submission.guardian_phone,
        guardian_email=submission.guardian_email,
        address=submission.residential_address,
        lifecycle_note=(
            f"Created from public admission application #{submission.id}. "
            f"Applicant approved through portal workflow."
        ),
        medical_notes=submission.medical_notes,
    )
    setup_state = get_setup_state()
    target_class = _resolved_academic_class_for_submission(submission)
    if target_class and setup_state.current_session_id:
        StudentClassEnrollment.objects.update_or_create(
            student=user,
            session=setup_state.current_session,
            defaults={"academic_class": target_class, "is_active": True},
        )
    return user, student_number, password


class AdmissionsWorkflowBaseView(PortalPageView, UserPassesTestMixin):
    template_name = "dashboard/admissions_board.html"
    allowed_roles: set[str] = set()
    board_mode = "admin"
    portal_name = "Admissions Workflow"
    portal_description = "Review online admission applications and fee status."

    def test_func(self):
        return any(self.request.user.has_role(code) for code in self.allowed_roles)

    def handle_no_permission(self):
        messages.error(self.request, "You do not have access to the admissions workflow.")
        return redirect("dashboard:landing")

    def _filtered_rows(self):
        rows = (
            PublicSiteSubmission.objects.filter(submission_type=PublicSubmissionType.ADMISSION)
            .select_related("reviewed_by", "linked_student", "linked_student__student_profile")
            .order_by("-created_at")
        )
        workflow_filter = (self.request.GET.get("workflow") or "").strip().upper()
        payment_filter = (self.request.GET.get("payment") or "").strip().upper()
        query = (self.request.GET.get("q") or "").strip()
        if workflow_filter in {value for value, _label in PublicAdmissionWorkflowStatus.choices}:
            rows = rows.filter(admissions_status=workflow_filter)
        if payment_filter in {value for value, _label in PublicAdmissionPaymentStatus.choices}:
            rows = rows.filter(payment_status=payment_filter)
        if query:
            rows = rows.filter(
                submission_type=PublicSubmissionType.ADMISSION
            ).filter(
                (
                    Q(applicant_name__icontains=query)
                    | Q(guardian_name__icontains=query)
                    | Q(guardian_phone__icontains=query)
                    | Q(guardian_email__icontains=query)
                    | Q(generated_admission_number__icontains=query)
                )
            )
        return rows

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        submissions = list(self._filtered_rows()[:150])
        all_rows = PublicSiteSubmission.objects.filter(
            submission_type=PublicSubmissionType.ADMISSION
        )
        context.update(
            {
                "board_mode": self.board_mode,
                "submissions": submissions,
                "query": (self.request.GET.get("q") or "").strip(),
                "workflow_filter": (self.request.GET.get("workflow") or "").strip().upper(),
                "payment_filter": (self.request.GET.get("payment") or "").strip().upper(),
                "counts": {
                    "new": all_rows.filter(admissions_status=PublicAdmissionWorkflowStatus.NEW).count(),
                    "pending": all_rows.filter(admissions_status=PublicAdmissionWorkflowStatus.PENDING).count(),
                    "approved": all_rows.filter(admissions_status=PublicAdmissionWorkflowStatus.APPROVED).count(),
                    "declined": all_rows.filter(admissions_status=PublicAdmissionWorkflowStatus.DECLINED).count(),
                    "paid": all_rows.filter(payment_status=PublicAdmissionPaymentStatus.PAID).count(),
                    "unpaid": all_rows.filter(payment_status=PublicAdmissionPaymentStatus.UNPAID).count(),
                },
                "workflow_options": PublicAdmissionWorkflowStatus.choices,
                "payment_options": PublicAdmissionPaymentStatus.choices,
                "can_review": self.board_mode == "admin",
                "can_manage_payment": self.board_mode == "bursar",
            }
        )
        return context


class AdmissionsWorkflowAdminView(AdmissionsWorkflowBaseView):
    allowed_roles = {ROLE_IT_MANAGER, ROLE_VP, ROLE_PRINCIPAL}
    board_mode = "admin"
    portal_description = (
        "New registrations, pending admissions, and approved applicants are tracked here."
    )

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()
        submission = get_object_or_404(
            PublicSiteSubmission,
            pk=request.POST.get("submission_id"),
            submission_type=PublicSubmissionType.ADMISSION,
        )
        if action == "mark_pending":
            submission.admissions_status = PublicAdmissionWorkflowStatus.PENDING
            submission.reviewed_by = request.user
            submission.reviewed_at = timezone.now()
            submission.save(update_fields=["admissions_status", "reviewed_by", "reviewed_at", "updated_at"])
            messages.success(request, "Applicant moved to pending review.")
            return redirect(request.path)
        if action == "decline":
            submission.admissions_status = PublicAdmissionWorkflowStatus.DECLINED
            submission.reviewed_by = request.user
            submission.reviewed_at = timezone.now()
            submission.approval_notes = (request.POST.get("approval_notes") or submission.approval_notes or "").strip()
            submission.save(
                update_fields=[
                    "admissions_status",
                    "reviewed_by",
                    "reviewed_at",
                    "approval_notes",
                    "updated_at",
                ]
            )
            messages.success(request, "Applicant marked as declined.")
            return redirect(request.path)
        if action == "approve":
            with transaction.atomic():
                student_user = submission.linked_student
                student_number = submission.generated_admission_number
                if student_user is None:
                    student_user, student_number, _password = _create_student_from_submission(submission)
                submission.admissions_status = PublicAdmissionWorkflowStatus.APPROVED
                submission.reviewed_by = request.user
                submission.reviewed_at = timezone.now()
                submission.linked_student = student_user
                submission.generated_admission_number = student_number
                submission.approval_notes = (request.POST.get("approval_notes") or submission.approval_notes or "").strip()
                submission.save(
                    update_fields=[
                        "admissions_status",
                        "reviewed_by",
                        "reviewed_at",
                        "linked_student",
                        "generated_admission_number",
                        "approval_notes",
                        "updated_at",
                    ]
                )
            messages.success(request, f"Applicant approved with admission number {student_number}.")
            return redirect(request.path)
        messages.error(request, "Invalid admissions action.")
        return redirect(request.path)


class AdmissionsWorkflowBursarView(AdmissionsWorkflowBaseView):
    allowed_roles = {ROLE_BURSAR}
    board_mode = "bursar"
    portal_name = "Bursar Portal"
    portal_description = "Track admission form payments for applicants before full school fees begin."

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()
        submission = get_object_or_404(
            PublicSiteSubmission,
            pk=request.POST.get("submission_id"),
            submission_type=PublicSubmissionType.ADMISSION,
        )
        if action == "mark_paid":
            amount_raw = (request.POST.get("application_fee_amount") or "").strip()
            reference = (request.POST.get("application_fee_reference") or "").strip()
            try:
                amount = Decimal(amount_raw or "0")
            except Exception:
                messages.error(request, "Enter a valid application fee amount.")
                return redirect(request.path)
            submission.application_fee_amount = amount
            submission.application_fee_reference = reference
            submission.payment_status = PublicAdmissionPaymentStatus.PAID
            submission.application_fee_paid_at = timezone.now()
            if submission.admissions_status == PublicAdmissionWorkflowStatus.NEW:
                submission.admissions_status = PublicAdmissionWorkflowStatus.PENDING
            submission.reviewed_by = request.user
            submission.reviewed_at = timezone.now()
            submission.save(
                update_fields=[
                    "application_fee_amount",
                    "application_fee_reference",
                    "payment_status",
                    "application_fee_paid_at",
                    "admissions_status",
                    "reviewed_by",
                    "reviewed_at",
                    "updated_at",
                ]
            )
            messages.success(request, "Applicant form fee recorded as paid.")
            return redirect(request.path)
        if action == "mark_unpaid":
            submission.payment_status = PublicAdmissionPaymentStatus.UNPAID
            submission.application_fee_paid_at = None
            submission.reviewed_by = request.user
            submission.reviewed_at = timezone.now()
            submission.save(
                update_fields=[
                    "payment_status",
                    "application_fee_paid_at",
                    "reviewed_by",
                    "reviewed_at",
                    "updated_at",
                ]
            )
            messages.success(request, "Applicant reset to unpaid form-fee status.")
            return redirect(request.path)
        messages.error(request, "Invalid bursar admissions action.")
        return redirect(request.path)


class ITAdmissionsWorkflowView(AdmissionsWorkflowAdminView):
    portal_name = "IT Manager Portal"


class VPAdmissionsWorkflowView(AdmissionsWorkflowAdminView):
    portal_name = "Vice Principal Portal"


class PrincipalAdmissionsWorkflowView(AdmissionsWorkflowAdminView):
    portal_name = "Principal Portal"
