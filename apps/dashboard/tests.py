from datetime import date
import json
from io import StringIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase, override_settings

from apps.accounts.constants import ROLE_IT_MANAGER, ROLE_PRINCIPAL, ROLE_STUDENT, ROLE_SUBJECT_TEACHER
from apps.accounts.models import Role, StudentProfile, User
from apps.academics.models import (
    AcademicClass,
    AcademicSession,
    ClassSubject,
    StudentClassEnrollment,
    StudentSubjectEnrollment,
    Subject,
    TeacherSubjectAssignment,
    Term,
)
from apps.attendance.models import AttendanceRecord, AttendanceStatus, SchoolCalendar
from apps.results.models import ClassCompilationStatus, ClassResultCompilation, ClassResultStudentRecord
from apps.setup_wizard.models import SetupStateCode, SystemSetupState
from apps.dashboard.models import LearningResource, LessonPlanDraft, PortalDocument, PrincipalSignature, WeeklyChallenge, WeeklyChallengeSubmission
from apps.dashboard.intelligence import (
    build_school_intelligence,
    build_student_academic_analytics,
    build_teacher_performance_analytics,
)
from apps.cbt.models import CBTAttemptStatus, CBTExamStatus, CBTExamType, Exam, ExamAttempt
from apps.results.models import ResultSheet, StudentSubjectScore


class StudentDashboardAttendanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        student_role = Role.objects.get(code=ROLE_STUDENT)
        subject_role = Role.objects.get(code=ROLE_SUBJECT_TEACHER)
        cls.student = User.objects.create_user(
            username="student-dash",
            password="Password123!",
            primary_role=student_role,
            must_change_password=False,
        )
        cls.teacher = User.objects.create_user(
            username="teacher-dash",
            password="Password123!",
            primary_role=subject_role,
            must_change_password=False,
        )
        it_role = Role.objects.get(code=ROLE_IT_MANAGER)
        cls.it_user = User.objects.create_user(
            username="it-dash",
            password="Password123!",
            primary_role=it_role,
            must_change_password=False,
        )
        session = AcademicSession.objects.create(name="2025/2026")
        term = Term.objects.create(session=session, name="FIRST")
        academic_class = AcademicClass.objects.create(code="SS1A", display_name="SS1A")
        subject = Subject.objects.create(name="Biology", code="BIO")
        ClassSubject.objects.create(academic_class=academic_class, subject=subject, is_active=True)
        TeacherSubjectAssignment.objects.create(
            teacher=cls.teacher,
            subject=subject,
            academic_class=academic_class,
            session=session,
            term=term,
            is_active=True,
        )
        calendar = SchoolCalendar.objects.create(
            session=session,
            term=term,
            start_date=date(2026, 1, 5),
            end_date=date(2026, 1, 9),
        )
        StudentClassEnrollment.objects.create(
            student=cls.student,
            academic_class=academic_class,
            session=session,
            is_active=True,
        )
        AttendanceRecord.objects.create(
            calendar=calendar,
            academic_class=academic_class,
            student=cls.student,
            date=date(2026, 1, 5),
            status=AttendanceStatus.PRESENT,
            marked_by=None,
        )
        compilation = ClassResultCompilation.objects.create(
            academic_class=academic_class,
            session=session,
            term=term,
            status=ClassCompilationStatus.PUBLISHED,
        )
        ClassResultStudentRecord.objects.create(
            compilation=compilation,
            student=cls.student,
            attendance_percentage=80,
            behavior_rating=4,
            teacher_comment="Strong effort.",
        )
        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = session
        setup_state.current_term = term
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

    def test_student_portal_shows_attendance_percentage(self):
        client = Client(HTTP_HOST="student.ndgakuje.org")
        login = client.post(
            "/auth/login/?audience=student",
            {"username": "student-dash", "password": "Password123!"},
        )
        self.assertEqual(login.status_code, 302)
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Welcome back")
        self.assertContains(response, "Next Actions")
        self.assertContains(response, "Quick Access")
        self.assertContains(response, "Attendance")
        self.assertContains(response, "Attendance Metrics")
        self.assertNotContains(response, "CBT Entry")
        self.assertNotContains(response, "Election Entry")
        self.assertNotContains(response, "CBT:")
        self.assertNotContains(response, "Election:")

    def test_staff_portal_shows_role_specific_menu_cards(self):
        client = Client(HTTP_HOST="staff.ndgakuje.org")
        login = client.post(
            "/auth/login/?audience=staff",
            {"username": "teacher-dash", "password": "Password123!"},
        )
        self.assertEqual(login.status_code, 302)
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Next Actions")
        self.assertContains(response, "Quick Access")
        self.assertContains(response, "Profile")
        self.assertContains(response, "CBT Entry")
        self.assertContains(response, "Result Entry")
        self.assertContains(response, "Settings")
        self.assertNotContains(response, "Upload PDF/DOC")
        self.assertNotContains(response, "Submit To Dean")

    def test_it_portal_shows_operations_center_and_drill_commands(self):
        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_user)
        response = client.get("/portal/it/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Operations Center")
        self.assertContains(response, "Runtime Snapshot")
        self.assertContains(response, "Restore Drill")



class OpsEndpointsTests(TestCase):
    def test_healthz_returns_ok(self):
        client = Client(HTTP_HOST="ndgakuje.org")
        response = client.get("/ops/healthz/")
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"status": "ok"})

    def test_readyz_returns_check_payload(self):
        client = Client(HTTP_HOST="ndgakuje.org")
        response = client.get("/ops/readyz/")
        self.assertIn(response.status_code, {200, 503})
        payload = response.json()
        self.assertIn("status", payload)
        self.assertIn("checks", payload)
        self.assertIn("database", payload["checks"])
        self.assertIn("cache", payload["checks"])
        self.assertIn("disk", payload)
        self.assertIn("sync", payload)

    def test_ops_runtime_snapshot_command_outputs_json(self):
        stdout = StringIO()
        call_command("ops_runtime_snapshot", stdout=stdout)
        payload = json.loads(stdout.getvalue())
        self.assertIn("status", payload)
        self.assertIn("disk", payload)
        self.assertIn("sync", payload)


class PrincipalSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        principal_role = Role.objects.get(code=ROLE_PRINCIPAL)
        cls.principal = User.objects.create_user(
            username="principal-settings",
            password="Password123!",
            primary_role=principal_role,
            must_change_password=False,
        )

    def test_principal_can_open_settings_and_save_signature_pad(self):
        client = Client(HTTP_HOST="principal.ndgakuje.org")
        client.force_login(self.principal)

        response = client.get("/portal/principal/settings/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Principal Signature")

        signature_data = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4////fwAJ+wP+W6l/JwAAAABJRU5ErkJggg=="
        )
        post_response = client.post(
            "/portal/principal/settings/",
            {
                "action": "save_signature",
                "signature_data": signature_data,
            },
            follow=False,
        )
        self.assertEqual(post_response.status_code, 302)
        self.assertEqual(post_response["Location"], "/portal/principal/settings/")

        signature = PrincipalSignature.objects.filter(user=self.principal).first()
        self.assertIsNotNone(signature)
        self.assertTrue(bool(signature.signature_image))


class AccountSecuritySettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        it_role = Role.objects.get(code=ROLE_IT_MANAGER)
        cls.it_user = User.objects.create_user(
            username="it-security-settings",
            password="Password123!",
            primary_role=it_role,
            must_change_password=False,
            email="it-security@ndgakuje.org",
        )

    def test_privileged_user_can_toggle_email_two_factor(self):
        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_user)

        response = client.get("/portal/account/security/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Privileged Sign-In Security")

        post_response = client.post(
            "/portal/account/security/",
            {
                "action": "update_security",
                "two_factor_enabled": "on",
                "two_factor_email": "otp@ndgakuje.org",
            },
            follow=False,
        )
        self.assertEqual(post_response.status_code, 302)
        self.assertEqual(post_response["Location"], "/portal/account/security/")

        self.it_user.refresh_from_db()
        self.assertTrue(self.it_user.two_factor_enabled)
        self.assertEqual(self.it_user.two_factor_email, "otp@ndgakuje.org")


class DashboardIntelligenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        student_role = Role.objects.get(code=ROLE_STUDENT)
        subject_role = Role.objects.get(code=ROLE_SUBJECT_TEACHER)
        principal_role = Role.objects.get(code=ROLE_PRINCIPAL)

        cls.student = User.objects.create_user(
            username="analytics-student",
            password="Password123!",
            primary_role=student_role,
            must_change_password=False,
            first_name="Ada",
            last_name="Student",
        )
        cls.teacher = User.objects.create_user(
            username="analytics-teacher",
            password="Password123!",
            primary_role=subject_role,
            must_change_password=False,
            first_name="Grace",
            last_name="Teacher",
        )
        cls.principal = User.objects.create_user(
            username="analytics-principal",
            password="Password123!",
            primary_role=principal_role,
            must_change_password=False,
        )

        cls.session = AcademicSession.objects.create(name="2025/2026")
        cls.term_first = Term.objects.create(session=cls.session, name="FIRST")
        cls.term_second = Term.objects.create(session=cls.session, name="SECOND")
        cls.academic_class = AcademicClass.objects.create(code="SS1A", display_name="SS1A")
        cls.math = Subject.objects.create(name="Mathematics", code="MTH-AN")
        cls.english = Subject.objects.create(name="English Language", code="ENG-AN")
        ClassSubject.objects.create(academic_class=cls.academic_class, subject=cls.math, is_active=True)
        ClassSubject.objects.create(academic_class=cls.academic_class, subject=cls.english, is_active=True)

        StudentClassEnrollment.objects.create(
            student=cls.student,
            academic_class=cls.academic_class,
            session=cls.session,
            is_active=True,
        )
        StudentSubjectEnrollment.objects.create(student=cls.student, subject=cls.math, session=cls.session, is_active=True)
        StudentSubjectEnrollment.objects.create(student=cls.student, subject=cls.english, session=cls.session, is_active=True)

        cls.assignment_first_math = TeacherSubjectAssignment.objects.create(
            teacher=cls.teacher,
            subject=cls.math,
            academic_class=cls.academic_class,
            session=cls.session,
            term=cls.term_first,
            is_active=True,
        )
        TeacherSubjectAssignment.objects.create(
            teacher=cls.teacher,
            subject=cls.english,
            academic_class=cls.academic_class,
            session=cls.session,
            term=cls.term_first,
            is_active=True,
        )
        cls.assignment_second_math = TeacherSubjectAssignment.objects.create(
            teacher=cls.teacher,
            subject=cls.math,
            academic_class=cls.academic_class,
            session=cls.session,
            term=cls.term_second,
            is_active=True,
        )
        TeacherSubjectAssignment.objects.create(
            teacher=cls.teacher,
            subject=cls.english,
            academic_class=cls.academic_class,
            session=cls.session,
            term=cls.term_second,
            is_active=True,
        )

        cls.compilation_first = ClassResultCompilation.objects.create(
            academic_class=cls.academic_class,
            session=cls.session,
            term=cls.term_first,
            status=ClassCompilationStatus.PUBLISHED,
        )
        cls.compilation_second = ClassResultCompilation.objects.create(
            academic_class=cls.academic_class,
            session=cls.session,
            term=cls.term_second,
            status=ClassCompilationStatus.PUBLISHED,
        )
        ClassResultStudentRecord.objects.create(
            compilation=cls.compilation_first,
            student=cls.student,
            attendance_percentage=82,
            behavior_rating=4,
            teacher_comment="Good start.",
        )
        ClassResultStudentRecord.objects.create(
            compilation=cls.compilation_second,
            student=cls.student,
            attendance_percentage=61,
            behavior_rating=3,
            teacher_comment="Needs closer support.",
        )

        for term, math_marks, eng_marks in [
            (cls.term_first, (10, 10, 8, 8, 28, 10), (9, 9, 8, 8, 25, 10)),
            (cls.term_second, (5, 5, 5, 5, 15, 7), (8, 8, 8, 8, 20, 10)),
        ]:
            sheet_math = ResultSheet.objects.create(
                academic_class=cls.academic_class,
                subject=cls.math,
                session=cls.session,
                term=term,
                status="PUBLISHED",
                created_by=cls.teacher,
            )
            sheet_english = ResultSheet.objects.create(
                academic_class=cls.academic_class,
                subject=cls.english,
                session=cls.session,
                term=term,
                status="PUBLISHED",
                created_by=cls.teacher,
            )
            StudentSubjectScore.objects.create(
                result_sheet=sheet_math,
                student=cls.student,
                ca1=math_marks[0],
                ca2=math_marks[1],
                ca3=math_marks[2],
                ca4=math_marks[3],
                objective=math_marks[4],
                theory=math_marks[5],
            )
            StudentSubjectScore.objects.create(
                result_sheet=sheet_english,
                student=cls.student,
                ca1=eng_marks[0],
                ca2=eng_marks[1],
                ca3=eng_marks[2],
                ca4=eng_marks[3],
                objective=eng_marks[4],
                theory=eng_marks[5],
            )

        exam = Exam.objects.create(
            title="SS1 Math CA 2",
            exam_type=CBTExamType.CA,
            status=CBTExamStatus.CLOSED,
            created_by=cls.teacher,
            assignment=cls.assignment_second_math,
            subject=cls.math,
            academic_class=cls.academic_class,
            session=cls.session,
            term=cls.term_second,
        )
        ExamAttempt.objects.create(
            exam=exam,
            student=cls.student,
            status=CBTAttemptStatus.SUBMITTED,
            attempt_number=1,
        )

        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = cls.session
        setup_state.current_term = cls.term_second
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

    def test_student_analytics_builds_prediction_and_risk(self):
        payload = build_student_academic_analytics(
            student=self.student,
            current_session=self.session,
            current_term=self.term_second,
        )
        self.assertTrue(payload["available"])
        self.assertEqual(payload["current"]["term_id"], self.term_second.id)
        self.assertGreater(payload["prediction"]["score"], 0)
        self.assertTrue(payload["weak_subjects"])
        self.assertIn("Mathematics", [row["subject"] for row in payload["weak_subjects"]])

    def test_teacher_analytics_calculates_effectiveness_metrics(self):
        payload = build_teacher_performance_analytics(
            teacher=self.teacher,
            current_session=self.session,
            current_term=self.term_second,
        )
        self.assertTrue(payload["available"])
        self.assertEqual(payload["cbt_completion_rate"], 100.0)
        self.assertGreaterEqual(payload["effectiveness_score"], 0)

    def test_school_intelligence_exposes_principal_metrics(self):
        payload = build_school_intelligence(current_session=self.session, current_term=self.term_second)
        self.assertTrue(payload["available"])
        self.assertIn("fee_payment_rate", payload)
        self.assertIn("exam_participation_rate", payload)

    def test_student_portal_renders_academic_analytics_panel(self):
        client = Client(HTTP_HOST="student.ndgakuje.org")
        client.force_login(self.student)
        response = client.get("/portal/student/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Academic Analytics")
        self.assertContains(response, "Practice CBT")

    def test_staff_portal_renders_teacher_performance_dashboard(self):
        client = Client(HTTP_HOST="staff.ndgakuje.org")
        client.force_login(self.teacher)
        response = client.get("/portal/staff/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Teacher Performance Dashboard")

    def test_principal_portal_renders_school_data_intelligence(self):
        client = Client(HTTP_HOST="principal.ndgakuje.org")
        client.force_login(self.principal)
        response = client.get("/portal/principal/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "School Data Intelligence")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class LearningHubPortalFeatureTests(TestCase):
    PASSWORD = "Password123!"

    @classmethod
    def setUpTestData(cls):
        student_role = Role.objects.get(code=ROLE_STUDENT)
        subject_role = Role.objects.get(code=ROLE_SUBJECT_TEACHER)
        it_role = Role.objects.get(code=ROLE_IT_MANAGER)

        cls.teacher = User.objects.create_user(
            username="hub-teacher",
            password=cls.PASSWORD,
            primary_role=subject_role,
            must_change_password=False,
            first_name="Tola",
            last_name="Teacher",
        )
        cls.it_user = User.objects.create_user(
            username="hub-it",
            password=cls.PASSWORD,
            primary_role=it_role,
            must_change_password=False,
        )
        cls.student = User.objects.create_user(
            username="hub-student",
            password=cls.PASSWORD,
            primary_role=student_role,
            must_change_password=False,
            first_name="Ada",
            last_name="Learner",
            email="ada.student@example.com",
        )
        cls.other_student = User.objects.create_user(
            username="hub-student-other",
            password=cls.PASSWORD,
            primary_role=student_role,
            must_change_password=False,
            first_name="Bola",
            last_name="Learner",
        )
        cls.student_profile = StudentProfile.objects.create(
            user=cls.student,
            student_number="NDGAK/26/001",
            guardian_name="Parent One",
            guardian_email="parent.one@example.com",
        )
        StudentProfile.objects.create(
            user=cls.other_student,
            student_number="NDGAK/26/002",
            guardian_name="Parent Two",
            guardian_email="parent.two@example.com",
        )

        cls.session = AcademicSession.objects.create(name="2026/2027")
        cls.term = Term.objects.create(session=cls.session, name="FIRST")
        cls.class_one = AcademicClass.objects.create(code="SS1A-HUB", display_name="SS1A Hub")
        cls.class_two = AcademicClass.objects.create(code="SS2A-HUB", display_name="SS2A Hub")
        cls.subject_math = Subject.objects.create(name="Mathematics Hub", code="MTH-HUB")
        ClassSubject.objects.create(academic_class=cls.class_one, subject=cls.subject_math, is_active=True)
        ClassSubject.objects.create(academic_class=cls.class_two, subject=cls.subject_math, is_active=True)

        TeacherSubjectAssignment.objects.create(
            teacher=cls.teacher,
            subject=cls.subject_math,
            academic_class=cls.class_one,
            session=cls.session,
            term=cls.term,
            is_active=True,
        )

        StudentClassEnrollment.objects.create(
            student=cls.student,
            academic_class=cls.class_one,
            session=cls.session,
            is_active=True,
        )
        StudentClassEnrollment.objects.create(
            student=cls.other_student,
            academic_class=cls.class_two,
            session=cls.session,
            is_active=True,
        )
        StudentSubjectEnrollment.objects.create(
            student=cls.student,
            subject=cls.subject_math,
            session=cls.session,
            is_active=True,
        )
        StudentSubjectEnrollment.objects.create(
            student=cls.other_student,
            subject=cls.subject_math,
            session=cls.session,
            is_active=True,
        )

        LearningResource.objects.create(
            title="SS1 Algebra Support",
            description="Visible to SS1 only",
            category="STUDY_MATERIAL",
            academic_class=cls.class_one,
            subject=cls.subject_math,
            session=cls.session,
            term=cls.term,
            uploaded_by=cls.teacher,
            content_text="Work through the SS1 algebra notes.",
            is_published=True,
        )
        LearningResource.objects.create(
            title="SS2 Algebra Only",
            description="Must stay hidden from SS1",
            category="STUDY_MATERIAL",
            academic_class=cls.class_two,
            subject=cls.subject_math,
            session=cls.session,
            term=cls.term,
            uploaded_by=cls.teacher,
            content_text="SS2-only revision pack.",
            is_published=True,
        )
        LessonPlanDraft.objects.create(
            teacher=cls.teacher,
            academic_class=cls.class_one,
            subject=cls.subject_math,
            session=cls.session,
            term=cls.term,
            topic="Algebra Foundations",
            teaching_goal="Strengthen algebra basics.",
            teacher_notes="",
            lesson_objectives="- Solve simple algebra questions",
            lesson_outline="- Warm-up\n- Worked examples",
            class_activity="Pair exercise",
            assignment_text="Answer five algebra questions.",
            quiz_text="1. Solve x + 2 = 5",
            publish_to_learning_hub=True,
        )
        LessonPlanDraft.objects.create(
            teacher=cls.teacher,
            academic_class=cls.class_two,
            subject=cls.subject_math,
            session=cls.session,
            term=cls.term,
            topic="Advanced Algebra",
            teaching_goal="SS2-only revision.",
            teacher_notes="",
            lesson_objectives="- Factorise quadratic equations",
            lesson_outline="- Review\n- Practice",
            class_activity="Board work",
            assignment_text="Complete the SS2 factorisation sheet.",
            quiz_text="1. Factorise x2 + 5x + 6",
            publish_to_learning_hub=True,
        )

        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = cls.session
        setup_state.current_term = cls.term
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

    def test_learning_hub_scopes_resources_to_student_class_and_subject(self):
        client = Client(HTTP_HOST="student.ndgakuje.org")
        client.force_login(self.student)
        response = client.get("/portal/student/learning-hub/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SS1 Algebra Support")
        self.assertContains(response, "Algebra Foundations")
        self.assertNotContains(response, "SS2 Algebra Only")
        self.assertNotContains(response, "Advanced Algebra")

    def test_student_id_verification_supports_slash_student_numbers(self):
        client = Client(HTTP_HOST="ndgakuje.org")
        response = client.get(f"/id/verify/{self.student_profile.student_number}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Valid NDGA Student ID")
        self.assertContains(response, self.student_profile.student_number)
        self.assertContains(response, self.class_one.code)

    def test_student_document_vault_shows_only_visible_documents(self):
        PortalDocument.objects.create(
            title="Transcript Copy",
            category="TRANSCRIPT",
            student=self.student,
            academic_class=self.class_one,
            session=self.session,
            term=self.term,
            uploaded_by=self.it_user,
            document_file=SimpleUploadedFile("transcript.txt", b"official transcript", content_type="text/plain"),
            is_visible_to_student=True,
        )
        PortalDocument.objects.create(
            title="Internal Note",
            category="STUDENT_RECORD",
            student=self.student,
            academic_class=self.class_one,
            session=self.session,
            term=self.term,
            uploaded_by=self.it_user,
            document_file=SimpleUploadedFile("note.txt", b"internal only", content_type="text/plain"),
            is_visible_to_student=False,
        )

        client = Client(HTTP_HOST="student.ndgakuje.org")
        client.force_login(self.student)
        response = client.get("/portal/student/documents/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Transcript Copy")
        self.assertNotContains(response, "Internal Note")

    @patch("apps.dashboard.feature_views.notify_assignment_deadline")
    @patch("apps.dashboard.feature_views.generate_lesson_plan_bundle")
    def test_teacher_lesson_planner_generates_resource_for_assigned_class(self, mocked_generate, mocked_notify):
        mocked_generate.return_value = {
            "objectives": "- Explain algebra revision",
            "outline": "- Introduce\n- Practice",
            "activity": "Pair work",
            "assignment": "Complete algebra homework.",
            "quiz": "1. Solve x + 3 = 7",
            "generator": "test",
        }
        client = Client(HTTP_HOST="staff.ndgakuje.org")
        client.force_login(self.teacher)
        response = client.post(
            "/portal/staff/lesson-planner/",
            {
                "action": "generate",
                "academic_class": self.class_one.id,
                "subject": self.subject_math.id,
                "session": self.session.id,
                "term": self.term.id,
                "topic": "Algebra Revision",
                "teaching_goal": "Raise accuracy",
                "teacher_notes": "Focus on errors",
                "publish_to_learning_hub": "on",
                "assignment_due_date": "2026-01-20",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Generated Lesson Plan")
        self.assertTrue(LessonPlanDraft.objects.filter(topic="Algebra Revision", teacher=self.teacher).exists())
        self.assertTrue(LearningResource.objects.filter(title="Mathematics Hub: Algebra Revision").exists())
        mocked_notify.assert_called_once()
        self.assertEqual(mocked_notify.call_args.kwargs["session"], self.session)

    @patch("apps.dashboard.feature_views.notify_assignment_deadline")
    def test_manual_assignment_resource_upload_triggers_deadline_notification(self, mocked_notify):
        client = Client(HTTP_HOST="staff.ndgakuje.org")
        client.force_login(self.teacher)
        response = client.post(
            "/portal/staff/lesson-planner/",
            {
                "action": "upload_resource",
                "title": "Weekend Algebra Assignment",
                "description": "Manual assignment upload",
                "category": "ASSIGNMENT",
                "academic_class": self.class_one.id,
                "subject": self.subject_math.id,
                "session": self.session.id,
                "term": self.term.id,
                "content_text": "Attempt questions 1-10.",
                "external_url": "",
                "due_date": "2026-01-22",
                "is_published": "on",
            },
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(LearningResource.objects.filter(title="Weekend Algebra Assignment").exists())
        mocked_notify.assert_called_once()
        self.assertEqual(mocked_notify.call_args.kwargs["session"], self.session)

    def test_it_can_create_weekly_challenge_for_instructional_class(self):
        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_user)
        response = client.post(
            "/portal/it/weekly-challenge/",
            {
                "action": "create",
                "week_label": "Week 2",
                "title": "Algebra Brain Teaser",
                "instructions": "Solve the pattern before Friday.",
                "question_text": "If x + 3 = 7, what is x?",
                "answer_guidance": "Think about inverse operations.",
                "accepted_answer_keywords": "4,four",
                "academic_class": self.class_one.id,
                "session": self.session.id,
                "term": self.term.id,
                "reward_points": 7,
                "is_published": "on",
            },
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        challenge = WeeklyChallenge.objects.get(title="Algebra Brain Teaser")
        self.assertEqual(challenge.academic_class_id, self.class_one.id)
        self.assertEqual(challenge.reward_points, 7)

    def test_student_weekly_challenge_is_class_scoped_and_scores_submission(self):
        WeeklyChallenge.objects.create(
            week_label="Week 3",
            title="SS1 Logic",
            instructions="Answer for SS1 only.",
            question_text="Name the value of x if x + 3 = 7.",
            accepted_answer_keywords="4,four",
            academic_class=self.class_one,
            session=self.session,
            term=self.term,
            created_by=self.it_user,
            is_published=True,
        )
        WeeklyChallenge.objects.create(
            week_label="Week 3",
            title="SS2 Hidden Challenge",
            instructions="Should stay hidden.",
            question_text="This should not show for SS1 students.",
            accepted_answer_keywords="answer",
            academic_class=self.class_two,
            session=self.session,
            term=self.term,
            created_by=self.it_user,
            is_published=True,
        )

        client = Client(HTTP_HOST="student.ndgakuje.org")
        client.force_login(self.student)
        response = client.get("/portal/student/weekly-challenge/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SS1 Logic")
        self.assertNotContains(response, "SS2 Hidden Challenge")

        challenge = WeeklyChallenge.objects.get(title="SS1 Logic")
        submit_response = client.post(
            "/portal/student/weekly-challenge/",
            {
                "challenge_id": challenge.id,
                "response_text": "The correct answer is 4.",
            },
            follow=False,
        )
        self.assertEqual(submit_response.status_code, 302)
        submission = WeeklyChallengeSubmission.objects.get(challenge=challenge, student=self.student)
        self.assertTrue(submission.is_correct)
        self.assertEqual(submission.awarded_points, challenge.reward_points)

