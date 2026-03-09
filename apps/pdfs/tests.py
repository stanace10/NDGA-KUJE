from decimal import Decimal
from unittest.mock import patch

from django.test import Client, TestCase
from django.utils import timezone

from apps.accounts.constants import (
    ROLE_FORM_TEACHER,
    ROLE_PRINCIPAL,
    ROLE_STUDENT,
    ROLE_SUBJECT_TEACHER,
    ROLE_VP,
)
from apps.accounts.models import Role, User
from apps.academics.models import (
    AcademicClass,
    AcademicSession,
    ClassSubject,
    StudentClassEnrollment,
    Subject,
    TeacherSubjectAssignment,
    Term,
)
from apps.dashboard.models import SchoolProfile
from apps.pdfs.models import PDFArtifact, PDFDocumentType
from apps.pdfs.services import upsert_transcript_session_record
from apps.results.models import (
    ClassCompilationStatus,
    ClassResultCompilation,
    ClassResultStudentRecord,
    ResultAccessPin,
    ResultSheet,
    ResultSheetStatus,
    StudentSubjectScore,
)
from apps.setup_wizard.models import SetupStateCode, SystemSetupState


class PDFStageEightTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        student_role = Role.objects.get(code=ROLE_STUDENT)
        form_role = Role.objects.get(code=ROLE_FORM_TEACHER)
        subject_role = Role.objects.get(code=ROLE_SUBJECT_TEACHER)
        vp_role = Role.objects.get(code=ROLE_VP)
        principal_role = Role.objects.get(code=ROLE_PRINCIPAL)

        cls.student = User.objects.create_user(
            username="student-pdf",
            password="Password123!",
            primary_role=student_role,
            must_change_password=False,
            first_name="Ada",
            last_name="Ikenna",
        )
        cls.form_teacher = User.objects.create_user(
            username="form-pdf",
            password="Password123!",
            primary_role=form_role,
            must_change_password=False,
        )
        cls.subject_teacher = User.objects.create_user(
            username="subject-pdf",
            password="Password123!",
            primary_role=subject_role,
            must_change_password=False,
        )
        cls.other_teacher = User.objects.create_user(
            username="other-subject-pdf",
            password="Password123!",
            primary_role=subject_role,
            must_change_password=False,
        )
        cls.vp_user = User.objects.create_user(
            username="vp-pdf",
            password="Password123!",
            primary_role=vp_role,
            must_change_password=False,
        )
        cls.principal_user = User.objects.create_user(
            username="principal-pdf",
            password="Password123!",
            primary_role=principal_role,
            must_change_password=False,
        )

        cls.session = AcademicSession.objects.create(name="2025/2026")
        cls.first_term = Term.objects.create(session=cls.session, name="FIRST")
        cls.second_term = Term.objects.create(session=cls.session, name="SECOND")
        cls.academic_class = AcademicClass.objects.create(code="JS2A", display_name="JS2 Alpha")
        cls.subject = Subject.objects.create(name="English Language", code="ENG2")
        ClassSubject.objects.create(academic_class=cls.academic_class, subject=cls.subject)

        StudentClassEnrollment.objects.create(
            student=cls.student,
            academic_class=cls.academic_class,
            session=cls.session,
            is_active=True,
        )

        TeacherSubjectAssignment.objects.create(
            teacher=cls.subject_teacher,
            subject=cls.subject,
            academic_class=cls.academic_class,
            session=cls.session,
            term=cls.first_term,
            is_active=True,
        )

        cls.published_compilation = ClassResultCompilation.objects.create(
            academic_class=cls.academic_class,
            session=cls.session,
            term=cls.first_term,
            form_teacher=cls.form_teacher,
            status=ClassCompilationStatus.PUBLISHED,
        )
        cls.published_compilation.published_at = timezone.now()
        cls.published_compilation.save(update_fields=["published_at", "updated_at"])
        ClassResultStudentRecord.objects.create(
            compilation=cls.published_compilation,
            student=cls.student,
            attendance_percentage=Decimal("91.50"),
            behavior_rating=4,
            teacher_comment="Steady progress and consistent effort.",
        )
        sheet = ResultSheet.objects.create(
            academic_class=cls.academic_class,
            subject=cls.subject,
            session=cls.session,
            term=cls.first_term,
            status=ResultSheetStatus.PUBLISHED,
        )
        StudentSubjectScore.objects.create(
            result_sheet=sheet,
            student=cls.student,
            ca1=Decimal("10"),
            ca2=Decimal("9"),
            ca3=Decimal("8"),
            ca4=Decimal("9"),
            objective=Decimal("34"),
            theory=Decimal("16"),
        )

        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = cls.session
        setup_state.current_term = cls.second_term
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

    @staticmethod
    def _client(host, user=None):
        client = Client(HTTP_HOST=host)
        if user is not None:
            client.force_login(user)
        return client

    @patch("apps.pdfs.services.qr_code_data_uri", return_value="data:image/png;base64,AA==")
    @patch("apps.pdfs.services.render_pdf_bytes", return_value=b"%PDF-1.4 fake")
    def test_student_can_view_and_download_published_term_report(self, *_mocks):
        client = self._client("student.ndgakuje.org", self.student)

        list_response = client.get(
            "/pdfs/student/reports/",
            {"session_id": self.session.id, "term_id": self.first_term.id},
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, self.session.name)
        self.assertContains(list_response, "First Term")
        self.assertContains(list_response, "View Report")

        view_response = client.get(
            f"/pdfs/student/reports/{self.published_compilation.id}/"
        )
        self.assertEqual(view_response.status_code, 200)
        self.assertContains(view_response, "Subject Scores")
        self.assertContains(view_response, "English Language")

        download_response = client.get(
            f"/pdfs/student/reports/{self.published_compilation.id}/download/"
        )
        self.assertEqual(download_response.status_code, 200)
        self.assertEqual(download_response["Content-Type"], "application/pdf")
        artifact = PDFArtifact.objects.latest("created_at")
        self.assertEqual(artifact.document_type, PDFDocumentType.TERM_REPORT)
        self.assertEqual(artifact.student_id, self.student.id)

    @patch("apps.pdfs.services.qr_code_data_uri", return_value="data:image/png;base64,AA==")
    @patch("apps.pdfs.services.render_pdf_bytes", return_value=b"%PDF-1.4 fake")
    def test_verification_endpoint_marks_valid_hash(self, *_mocks):
        client = self._client("student.ndgakuje.org", self.student)
        client.get(f"/pdfs/student/reports/{self.published_compilation.id}/download/")
        artifact = PDFArtifact.objects.latest("created_at")

        verify_client = self._client("ndgakuje.org")
        verify_response = verify_client.get(f"/pdfs/verify/{artifact.id}/?hash={artifact.payload_hash}")
        self.assertEqual(verify_response.status_code, 200)
        self.assertContains(verify_response, "Valid PDF")
        self.assertContains(verify_response, artifact.payload_hash)

    @patch("apps.pdfs.services.qr_code_data_uri", return_value="data:image/png;base64,AA==")
    @patch("apps.pdfs.services.render_pdf_bytes", return_value=b"%PDF-1.4 fake")
    def test_staff_download_permissions_are_enforced(self, *_mocks):
        denied_client = self._client("staff.ndgakuje.org", self.other_teacher)
        denied_response = denied_client.get(
            f"/pdfs/staff/reports/{self.published_compilation.id}/student/{self.student.id}/download/"
        )
        self.assertEqual(denied_response.status_code, 302)

        vp_client = self._client("vp.ndgakuje.org", self.vp_user)
        allowed_response = vp_client.get(
            f"/pdfs/staff/reports/{self.published_compilation.id}/student/{self.student.id}/download/"
        )
        self.assertEqual(allowed_response.status_code, 200)
        self.assertEqual(allowed_response["Content-Type"], "application/pdf")

    @patch("apps.pdfs.services.qr_code_data_uri", return_value="data:image/png;base64,AA==")
    @patch("apps.pdfs.services.render_pdf_bytes", return_value=b"%PDF-1.4 fake")
    def test_past_term_reports_remain_accessible_after_term_rollover(self, *_mocks):
        client = self._client("student.ndgakuje.org", self.student)
        response = client.get("/pdfs/student/reports/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "First Term")
        self.assertContains(response, self.session.name)

        download_response = client.get(
            f"/pdfs/student/reports/{self.published_compilation.id}/download/"
        )
        self.assertEqual(download_response.status_code, 200)

    @patch("apps.pdfs.services.qr_code_data_uri", return_value="data:image/png;base64,AA==")
    @patch("apps.pdfs.services.render_pdf_bytes", return_value=b"%PDF-1.4 fake")
    def test_result_pin_required_blocks_student_report_until_verified(self, *_mocks):
        profile = SchoolProfile.load()
        profile.require_result_access_pin = True
        profile.save(update_fields=["require_result_access_pin", "updated_at"])
        ResultAccessPin.objects.create(
            student=self.student,
            session=self.session,
            term=self.first_term,
            pin_code="ABC123",
            generated_by=self.vp_user,
            is_active=True,
        )

        client = self._client("student.ndgakuje.org", self.student)
        locked_response = client.get(f"/pdfs/student/reports/{self.published_compilation.id}/")
        self.assertEqual(locked_response.status_code, 302)
        self.assertEqual(locked_response.headers["Location"], "/pdfs/student/reports/")

        unlock_response = client.post(
            "/pdfs/student/reports/",
            {
                "action": "verify_pin",
                "compilation_id": self.published_compilation.id,
                "pin_code": "ABC123",
            },
        )
        self.assertEqual(unlock_response.status_code, 302)

        unlocked_response = client.get(f"/pdfs/student/reports/{self.published_compilation.id}/")
        self.assertEqual(unlocked_response.status_code, 200)
        self.assertContains(unlocked_response, "Subject Scores")

    @patch("apps.pdfs.services.qr_code_data_uri", return_value="data:image/png;base64,AA==")
    @patch("apps.pdfs.services.render_pdf_bytes", return_value=b"%PDF-1.4 fake")
    def test_vp_can_download_staff_performance_analysis_pdf(self, *_mocks):
        vp_client = self._client("vp.ndgakuje.org", self.vp_user)
        response = vp_client.get(
            f"/pdfs/staff/reports/{self.published_compilation.id}/student/{self.student.id}/performance/download/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    @patch("apps.pdfs.services.qr_code_data_uri", return_value="data:image/png;base64,AA==")
    @patch("apps.pdfs.services.render_pdf_bytes", return_value=b"%PDF-1.4 fake")
    def test_transcript_download_for_student_and_vp(self, *_mocks):
        student_client = self._client("student.ndgakuje.org", self.student)
        student_response = student_client.get("/pdfs/student/transcript/download/")
        self.assertEqual(student_response.status_code, 200)

        vp_client = self._client("vp.ndgakuje.org", self.vp_user)
        vp_response = vp_client.get(f"/pdfs/staff/transcript/student/{self.student.id}/download/")
        self.assertEqual(vp_response.status_code, 200)

    @patch("apps.pdfs.services.qr_code_data_uri", return_value="data:image/png;base64,AA==")
    @patch("apps.pdfs.services.render_pdf_bytes", return_value=b"%PDF-1.4 fake")
    def test_session_transcript_download_for_student_and_vp(self, *_mocks):
        self.session.is_closed = True
        self.session.save(update_fields=["is_closed", "updated_at"])
        upsert_transcript_session_record(
            student=self.student,
            session=self.session,
            generated_by=self.vp_user,
        )

        student_client = self._client("student.ndgakuje.org", self.student)
        student_response = student_client.get(
            f"/pdfs/student/transcript/session/{self.session.id}/download/"
        )
        self.assertEqual(student_response.status_code, 200)

        vp_client = self._client("vp.ndgakuje.org", self.vp_user)
        vp_response = vp_client.get(
            f"/pdfs/staff/transcript/student/{self.student.id}/session/{self.session.id}/download/"
        )
        self.assertEqual(vp_response.status_code, 200)
