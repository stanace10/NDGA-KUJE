import json
import io
import zipfile

from django.conf import settings
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template import Context, Template
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.accounts.constants import ROLE_DEAN, ROLE_IT_MANAGER, ROLE_SUBJECT_TEACHER
from apps.accounts.models import Role, User
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
from apps.cbt.models import (
    CBTAttemptStatus,
    CBTSimulationScoreMode,
    CBTSimulationWrapperStatus,
    CBTQuestionType,
    CBTWritebackTarget,
    CBTDocumentStatus,
    CBTExamStatus,
    ExamAttempt,
    ExamBlueprint,
    Exam,
    ExamDocumentImport,
    ExamSimulation,
    ExamQuestion,
    Option,
    Question,
    QuestionBank,
    SimulationAttemptRecord,
    SimulationWrapper,
)
from apps.cbt.services import _ordered_exam_question_rows, parse_objective_questions, student_available_exams
from apps.audit.models import AuditCategory, AuditEvent
from apps.results.models import StudentSubjectScore
from apps.sync.models import SyncOperationType, SyncQueue
from apps.setup_wizard.models import SetupStateCode, SystemSetupState


CBT_TEST_HOST_SETTINGS = {
    "ALLOWED_HOSTS": [
        "localhost",
        "127.0.0.1",
        "[::1]",
        "testserver",
        "ndgakuje.org",
        ".ndgakuje.org",
        ".ndga.local",
    ],
    "CSRF_TRUSTED_ORIGINS": [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://ndgakuje.org:8000",
        "http://ndgakuje.org",
        "http://*.ndgakuje.org",
        "https://ndgakuje.org",
        "https://*.ndgakuje.org",
    ],
}


@override_settings(**CBT_TEST_HOST_SETTINGS)
class StageTenCBTWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.role_it = Role.objects.get(code=ROLE_IT_MANAGER)
        cls.role_dean = Role.objects.get(code=ROLE_DEAN)
        cls.role_teacher = Role.objects.get(code=ROLE_SUBJECT_TEACHER)

        cls.it_user = User.objects.create_user(
            username="it-cbt",
            password="Password123!",
            primary_role=cls.role_it,
            must_change_password=False,
            email="it-cbt@ndgakuje.org",
        )
        cls.dean_user = User.objects.create_user(
            username="dean-cbt",
            password="Password123!",
            primary_role=cls.role_dean,
            must_change_password=False,
        )
        cls.teacher_user = User.objects.create_user(
            username="teacher-cbt",
            password="Password123!",
            primary_role=cls.role_teacher,
            must_change_password=False,
        )

        cls.session = AcademicSession.objects.create(name="2025/2026")
        cls.term = Term.objects.create(session=cls.session, name="FIRST")
        cls.academic_class = AcademicClass.objects.create(code="SS1A", display_name="SS1A")
        cls.subject = Subject.objects.create(name="Physics", code="PHY")
        ClassSubject.objects.create(
            academic_class=cls.academic_class,
            subject=cls.subject,
            is_active=True,
        )
        cls.assignment = TeacherSubjectAssignment.objects.create(
            teacher=cls.teacher_user,
            subject=cls.subject,
            academic_class=cls.academic_class,
            session=cls.session,
            term=cls.term,
            is_active=True,
        )

        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = cls.session
        setup_state.current_term = cls.term
        setup_state.save(
            update_fields=["state", "current_session", "current_term", "updated_at"]
        )

    def login_client(self, *, host, username):
        client = Client(HTTP_HOST=host)
        response = client.post(
            "/auth/login/?audience=staff",
            {"username": username, "password": "Password123!"},
        )
        if "/auth/login/verify/" in getattr(response, "url", ""):
            self.assertTrue(mail.outbox)
            code = mail.outbox[-1].body.split("verification code is:")[1].splitlines()[0].strip()
            response = client.post(
                "/auth/login/verify/",
                {"verification_code": code},
            )
        self.assertIn(response.status_code, {200, 302})
        return client

    def _create_minimal_exam(self):
        question_bank = QuestionBank.objects.create(
            name="Physics Bank",
            owner=self.teacher_user,
            assignment=self.assignment,
            subject=self.subject,
            academic_class=self.academic_class,
            session=self.session,
            term=self.term,
        )
        question = Question.objects.create(
            question_bank=question_bank,
            created_by=self.teacher_user,
            subject=self.subject,
            question_type="OBJECTIVE",
            stem="What is the SI unit of force?",
            topic="Mechanics",
            difficulty="EASY",
            marks=1,
        )
        question.options.create(label="A", option_text="Joule", sort_order=1)
        question.options.create(label="B", option_text="Newton", sort_order=2)
        answer = question.correct_answer if hasattr(question, "correct_answer") else None
        if answer is None:
            from apps.cbt.models import CorrectAnswer

            answer = CorrectAnswer.objects.create(question=question, is_finalized=True)
        answer.correct_options.set(question.options.filter(label="B"))

        exam = Exam.objects.create(
            title="Physics CA 1",
            description="Draft exam",
            exam_type="CA",
            status=CBTExamStatus.DRAFT,
            created_by=self.teacher_user,
            assignment=self.assignment,
            subject=self.subject,
            academic_class=self.academic_class,
            session=self.session,
            term=self.term,
            question_bank=question_bank,
        )
        from apps.cbt.models import ExamBlueprint

        ExamBlueprint.objects.create(
            exam=exam,
            duration_minutes=30,
            max_attempts=1,
            shuffle_questions=True,
            shuffle_options=True,
            instructions="Answer all questions.",
        )
        ExamQuestion.objects.create(
            exam=exam,
            question=question,
            sort_order=1,
            marks=1,
        )
        return exam, question_bank, question

    def test_stage10_full_workflow_teacher_to_dean_to_it_activation(self):
        teacher_client = self.login_client(host="staff.ndgakuje.org", username=self.teacher_user.username)

        bank_response = teacher_client.post(
            "/cbt/authoring/banks/new/",
            {
                "assignment": str(self.assignment.id),
                "name": "Teacher Authored Bank",
                "description": "CBT bank for SS1A Physics",
            },
        )
        self.assertEqual(bank_response.status_code, 302)
        question_bank = QuestionBank.objects.get(name="Teacher Authored Bank")

        question_response = teacher_client.post(
            "/cbt/authoring/questions/new/",
            {
                "question_bank": str(question_bank.id),
                "question_type": "OBJECTIVE",
                "stem": "Acceleration due to gravity is approximately?",
                "topic": "Motion",
                "difficulty": "EASY",
                "marks": "1",
                "option_a": "9.8 m/s^2",
                "option_b": "98 m/s^2",
                "option_c": "0.98 m/s^2",
                "option_d": "19.6 m/s^2",
                "correct_labels": ["A"],
                "is_active": "on",
            },
        )
        self.assertEqual(question_response.status_code, 302)
        question = Question.objects.filter(question_bank=question_bank).latest("created_at")

        exam_response = teacher_client.post(
            "/cbt/authoring/exams/new/",
            {
                "assignment": str(self.assignment.id),
                "title": "Physics Midterm",
                "description": "Stage 10 workflow exam",
                "exam_type": "EXAM",
                "question_bank": str(question_bank.id),
                "duration_minutes": "45",
                "max_attempts": "1",
                "shuffle_questions": "on",
                "shuffle_options": "on",
                "instructions": "Choose the best option.",
            },
        )
        self.assertEqual(exam_response.status_code, 302)
        exam = Exam.objects.get(title="Physics Midterm")

        attach_response = teacher_client.post(
            f"/cbt/authoring/exams/{exam.id}/attach-questions/",
            {"questions": [str(question.id)]},
        )
        self.assertEqual(attach_response.status_code, 302)
        self.assertTrue(ExamQuestion.objects.filter(exam=exam, question=question).exists())

        submit_response = teacher_client.post(
            f"/cbt/authoring/exams/{exam.id}/submit-to-dean/",
            {"comment": "Ready for vetting."},
        )
        self.assertEqual(submit_response.status_code, 302)
        exam.refresh_from_db()
        self.assertEqual(exam.status, CBTExamStatus.PENDING_DEAN)

        dean_client = self.login_client(host="staff.ndgakuje.org", username=self.dean_user.username)
        approve_response = dean_client.post(
            f"/cbt/dean/review/{exam.id}/",
            {"action": "APPROVE", "comment": "Approved."},
        )
        self.assertEqual(approve_response.status_code, 302)
        exam.refresh_from_db()
        self.assertEqual(exam.status, CBTExamStatus.APPROVED)
        self.assertEqual(exam.dean_reviewed_by_id, self.dean_user.id)

        it_client = self.login_client(host="it.ndgakuje.org", username=self.it_user.username)
        activate_response = it_client.post(
            f"/cbt/it/activation/{exam.id}/",
            {
                "action": "activate",
                "open_now": "on",
                "is_time_based": "on",
                "duration_minutes": "45",
                "max_attempts": "1",
                "shuffle_questions": "on",
                "shuffle_options": "on",
                "instructions": "Approved instructions",
                "activation_comment": "Open now.",
            },
        )
        self.assertEqual(activate_response.status_code, 302)
        exam.refresh_from_db()
        self.assertEqual(exam.status, CBTExamStatus.ACTIVE)
        self.assertEqual(exam.activated_by_id, self.it_user.id)
        self.assertTrue(exam.is_time_based)
        self.assertIsNotNone(exam.schedule_start)
        self.assertIsNotNone(exam.schedule_end)
        self.assertGreater(exam.schedule_end, exam.schedule_start)

    def test_it_activation_generates_immutable_snapshot_hash(self):
        exam, _, question = self._create_minimal_exam()
        exam.status = CBTExamStatus.APPROVED
        exam.dean_reviewed_by = self.dean_user
        exam.dean_reviewed_at = timezone.now()
        exam.save(update_fields=["status", "dean_reviewed_by", "dean_reviewed_at", "updated_at"])

        it_client = self.login_client(host="it.ndgakuje.org", username=self.it_user.username)
        response = it_client.post(
            f"/cbt/it/activation/{exam.id}/",
            {
                "action": "activate",
                "open_now": "on",
                "is_time_based": "on",
                "duration_minutes": "30",
                "max_attempts": "1",
                "shuffle_questions": "on",
                "shuffle_options": "on",
                "instructions": "Immutable snapshot test",
                "activation_comment": "Activate with snapshot.",
            },
        )
        self.assertEqual(response.status_code, 302)
        exam.refresh_from_db()
        self.assertEqual(exam.status, CBTExamStatus.ACTIVE)
        self.assertTrue(exam.activation_snapshot_hash)
        self.assertEqual(exam.activation_snapshot["exam"]["id"], exam.id)
        self.assertEqual(len(exam.activation_snapshot["questions"]), 1)
        self.assertEqual(exam.activation_snapshot["questions"][0]["question"]["stem"], question.stem)
        self.assertEqual(
            exam.activation_snapshot["blueprint"]["duration_minutes"],
            30,
        )

    def test_exam_cannot_be_activated_without_dean_approval(self):
        exam, _, _ = self._create_minimal_exam()
        it_client = self.login_client(host="it.ndgakuje.org", username=self.it_user.username)
        response = it_client.post(
            f"/cbt/it/activation/{exam.id}/",
            {
                "action": "activate",
                "open_now": "on",
                "is_time_based": "on",
                "duration_minutes": "30",
                "max_attempts": "1",
                "shuffle_questions": "on",
                "shuffle_options": "on",
                "instructions": "Test",
                "activation_comment": "Try activate draft",
            },
        )
        self.assertEqual(response.status_code, 302)
        exam.refresh_from_db()
        self.assertEqual(exam.status, CBTExamStatus.DRAFT)

    def test_teacher_cannot_self_activate_exam(self):
        exam, _, _ = self._create_minimal_exam()
        exam.status = CBTExamStatus.APPROVED
        exam.dean_reviewed_by = self.dean_user
        exam.save(update_fields=["status", "dean_reviewed_by", "updated_at"])

        teacher_client = self.login_client(host="staff.ndgakuje.org", username=self.teacher_user.username)
        response = teacher_client.post(
            f"/cbt/it/activation/{exam.id}/",
            {
                "action": "activate",
                "open_now": "on",
                "is_time_based": "on",
                "duration_minutes": "30",
                "max_attempts": "1",
                "shuffle_questions": "on",
                "shuffle_options": "on",
                "instructions": "No permission",
                "activation_comment": "Teacher should fail",
            },
        )
        self.assertEqual(response.status_code, 302)
        exam.refresh_from_db()
        self.assertEqual(exam.status, CBTExamStatus.APPROVED)

    def test_upload_document_generates_draft_exam(self):
        teacher_client = self.login_client(host="staff.ndgakuje.org", username=self.teacher_user.username)
        file_content = (
            "1. What is 2 + 2?\n"
            "A. 2\n"
            "B. 4\n"
            "C. 6\n"
            "D. 8\n"
            "2. Which is a primary color?\n"
            "A. Green\n"
            "B. Blue\n"
            "C. Orange\n"
            "D. Black\n"
        ).encode("utf-8")
        upload = SimpleUploadedFile("physics_questions.txt", file_content, content_type="text/plain")
        response = teacher_client.post(
            "/cbt/authoring/upload/",
            {
                "assignment": str(self.assignment.id),
                "title": "Imported Physics Quiz",
                "exam_type": "CA",
                "source_file": upload,
            },
        )
        self.assertEqual(response.status_code, 302)
        exam = Exam.objects.get(title="Imported Physics Quiz")
        self.assertEqual(exam.status, CBTExamStatus.DRAFT)
        self.assertGreater(ExamQuestion.objects.filter(exam=exam).count(), 0)
        import_row = ExamDocumentImport.objects.get(exam=exam)
        self.assertEqual(import_row.extraction_status, CBTDocumentStatus.SUCCESS)

    def test_teacher_can_delete_own_draft_exam(self):
        exam, _, _ = self._create_minimal_exam()
        teacher_client = self.login_client(host="staff.ndgakuje.org", username=self.teacher_user.username)
        response = teacher_client.post(f"/cbt/authoring/exams/{exam.id}/delete/")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Exam.objects.filter(id=exam.id).exists())

    def test_parser_accepts_unnumbered_questions_with_options_and_answer_lines(self):
        pasted_text = (
            "If 2x + 3 = 11, find x.\n"
            "A. 2\n"
            "B. 3\n"
            "C. 4\n"
            "D. 5\n"
            "Answer: C\n"
            "Evaluate 5 squared.\n"
            "A. 10\n"
            "B. 20\n"
            "C. 25\n"
            "D. 30\n"
            "Answer: C\n"
        )
        parsed = parse_objective_questions(pasted_text)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["question_type"], "OBJECTIVE")
        self.assertEqual(parsed[0]["correct_label"], "C")
        self.assertEqual(parsed[1]["question_type"], "OBJECTIVE")
        self.assertEqual(parsed[1]["correct_label"], "C")

    def test_parser_accepts_inline_option_blocks(self):
        pasted_text = (
            "1. What is 3 + 4? A. 6 B. 7 C. 8 D. 9 Answer: B\n"
            "2. Which angle is a right angle? A. 30 B. 45 C. 90 D. 120 Answer: C\n"
        )
        parsed = parse_objective_questions(pasted_text)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["question_type"], "OBJECTIVE")
        self.assertEqual(parsed[0]["correct_label"], "B")
        self.assertEqual(parsed[1]["question_type"], "OBJECTIVE")
        self.assertEqual(parsed[1]["correct_label"], "C")

    def test_parser_accepts_compact_inline_option_blocks_without_spaces(self):
        pasted_text = (
            "1.What is 3+4?A)6B)7C)8D)9Answer:B\n"
            "2.Which planet is known as the red planet?(A)Earth(B)Mars(C)Jupiter(D)Saturn Answer: B\n"
        )
        parsed = parse_objective_questions(pasted_text)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["question_type"], "OBJECTIVE")
        self.assertEqual(parsed[0]["correct_label"], "B")
        self.assertEqual(parsed[1]["question_type"], "OBJECTIVE")
        self.assertEqual(parsed[1]["correct_label"], "B")

    def test_parser_handles_pdf_style_wrapped_number_and_option_layout(self):
        pasted_text = (
            "1)\n"
            "If 2x + 3 = 11, find x.\n"
            "A. 2\n"
            "B. 3\n"
            "C. 4\n"
            "D. 5\n"
            "Answer: C\n\n"
            "2)\n"
            "Evaluate 5 squared.\n"
            "A. 10\n"
            "B. 20\n"
            "C. 25\n"
            "D. 30\n"
            "Answer: C\n"
        )
        parsed = parse_objective_questions(pasted_text)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["question_type"], "OBJECTIVE")
        self.assertEqual(parsed[0]["correct_label"], "C")
        self.assertEqual(parsed[1]["question_type"], "OBJECTIVE")
        self.assertEqual(parsed[1]["correct_label"], "C")

    def test_parser_rejects_low_confidence_single_blob(self):
        pasted_text = (
            "This is a long lesson note without clear numbering or A-D option structure. "
            "It discusses algebraic expressions, equations, and simplification methods. "
            "Students were taught to solve linear equations and interpret word problems. "
            "The content continues as prose and should not be treated as a parsed exam question set. "
            "No option markers are present and no question boundaries are clearly defined."
        )
        parsed = parse_objective_questions(pasted_text)
        self.assertEqual(parsed, [])

    def test_ai_draft_create_redirects_to_builder(self):
        teacher_client = self.login_client(host="staff.ndgakuje.org", username=self.teacher_user.username)
        response = teacher_client.post(
            "/cbt/authoring/ai-draft/",
            {
                "assignment": str(self.assignment.id),
                "title": "AI Draft Physics",
                "topic": "Motion and Force",
                "question_count": "5",
                "exam_type": "CA",
                "difficulty": "MEDIUM",
                "lesson_note_text": "Force equals mass times acceleration. Units are Newton.",
            },
        )
        self.assertEqual(response.status_code, 302)
        exam = Exam.objects.get(title="AI Draft Physics")
        self.assertEqual(exam.status, CBTExamStatus.DRAFT)
        self.assertGreater(ExamQuestion.objects.filter(exam=exam).count(), 0)

    def test_ai_draft_prefers_uploaded_lesson_material_objective_questions(self):
        teacher_client = self.login_client(host="staff.ndgakuje.org", username=self.teacher_user.username)
        lesson_material = (
            "1. What is acceleration?\n"
            "A. Change in velocity per unit time\n"
            "B. Distance covered per unit time\n"
            "C. A force acting upward\n"
            "D. Product of mass and time\n"
            "Answer: A\n\n"
            "2. Which unit measures force?\n"
            "A. Joule\n"
            "B. Watt\n"
            "C. Newton\n"
            "D. Pascal\n"
            "Answer: C\n"
        )
        response = teacher_client.post(
            "/cbt/authoring/ai-draft/",
            {
                "assignment": str(self.assignment.id),
                "title": "AI Draft From Material",
                "topic": "Motion and Force",
                "question_count": "2",
                "exam_type": "CA",
                "difficulty": "MEDIUM",
                "lesson_note_text": lesson_material,
            },
        )
        self.assertEqual(response.status_code, 302)
        exam = Exam.objects.get(title="AI Draft From Material")
        stems = list(
            ExamQuestion.objects.filter(exam=exam)
            .select_related("question")
            .order_by("sort_order")
            .values_list("question__stem", flat=True)
        )
        self.assertEqual(len(stems), 2)
        self.assertTrue(any("What is acceleration?" in stem for stem in stems))
        self.assertTrue(any("Which unit measures force?" in stem for stem in stems))

    def test_exam_create_upload_mode_ca_redirects_without_ca_target(self):
        teacher_client = self.login_client(host="staff.ndgakuje.org", username=self.teacher_user.username)
        response = teacher_client.post(
            "/cbt/authoring/exams/new/",
            {
                "assignment": str(self.assignment.id),
                "title": "Upload-Mode CA",
                "exam_type": "CA",
                "authoring_mode": "UPLOAD",
                "duration_minutes": "30",
                "max_attempts": "1",
                # CA target intentionally omitted: upload flow should still continue.
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/cbt/authoring/upload/", response.url)

    def test_exam_create_upload_mode_blank_title_auto_generates(self):
        teacher_client = self.login_client(host="staff.ndgakuje.org", username=self.teacher_user.username)
        response = teacher_client.post(
            "/cbt/authoring/exams/new/",
            {
                "assignment": str(self.assignment.id),
                "title": "",
                "exam_type": "CA",
                "authoring_mode": "UPLOAD",
                "duration_minutes": "30",
                "max_attempts": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/cbt/authoring/upload/", response.url)
        self.assertIn("title=", response.url)
        self.assertNotIn("title=&", response.url)

    def test_exam_create_ai_mode_ca_redirects_without_ca_target(self):
        teacher_client = self.login_client(host="staff.ndgakuje.org", username=self.teacher_user.username)
        response = teacher_client.post(
            "/cbt/authoring/exams/new/",
            {
                "assignment": str(self.assignment.id),
                "title": "AI-Mode CA",
                "exam_type": "CA",
                "authoring_mode": "AI",
                "duration_minutes": "30",
                "max_attempts": "1",
                # CA target intentionally omitted: AI flow should still continue.
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/cbt/authoring/ai-draft/", response.url)


@override_settings(
    FEATURE_FLAGS={
        **settings.FEATURE_FLAGS,
        "CBT_ENABLED": True,
    }
)
@override_settings(**CBT_TEST_HOST_SETTINGS)
class StageElevenCBTRunnerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.role_it = Role.objects.get(code="IT_MANAGER")
        cls.role_dean = Role.objects.get(code="DEAN")
        cls.role_teacher = Role.objects.get(code="SUBJECT_TEACHER")
        cls.role_student = Role.objects.get(code="STUDENT")

        cls.it_user = User.objects.create_user(
            username="it-stage11",
            password="Password123!",
            primary_role=cls.role_it,
            must_change_password=False,
            email="it-stage11@ndgakuje.org",
        )
        cls.dean_user = User.objects.create_user(
            username="dean-stage11",
            password="Password123!",
            primary_role=cls.role_dean,
            must_change_password=False,
        )
        cls.teacher_user = User.objects.create_user(
            username="teacher-stage11",
            password="Password123!",
            primary_role=cls.role_teacher,
            must_change_password=False,
        )
        cls.student_user = User.objects.create_user(
            username="student-stage11",
            password="Password123!",
            primary_role=cls.role_student,
            must_change_password=False,
        )

        cls.session = AcademicSession.objects.create(name="2026/2027")
        cls.term = Term.objects.create(session=cls.session, name="FIRST")
        cls.academic_class = AcademicClass.objects.create(code="SS2A", display_name="SS2A")
        cls.subject = Subject.objects.create(name="Chemistry", code="CHEM")
        ClassSubject.objects.create(
            academic_class=cls.academic_class,
            subject=cls.subject,
            is_active=True,
        )
        cls.assignment = TeacherSubjectAssignment.objects.create(
            teacher=cls.teacher_user,
            subject=cls.subject,
            academic_class=cls.academic_class,
            session=cls.session,
            term=cls.term,
            is_active=True,
        )
        StudentClassEnrollment.objects.create(
            student=cls.student_user,
            academic_class=cls.academic_class,
            session=cls.session,
            is_active=True,
        )
        StudentSubjectEnrollment.objects.create(
            student=cls.student_user,
            subject=cls.subject,
            session=cls.session,
            is_active=True,
        )

        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = cls.session
        setup_state.current_term = cls.term
        setup_state.save(
            update_fields=["state", "current_session", "current_term", "updated_at"]
        )

    def login_client(self, *, host, username, audience):
        client = Client(HTTP_HOST=host)
        response = client.post(
            f"/auth/login/?audience={audience}",
            {"username": username, "password": "Password123!"},
        )
        if "/auth/login/verify/" in getattr(response, "url", ""):
            self.assertTrue(mail.outbox)
            code = mail.outbox[-1].body.split("verification code is:")[1].splitlines()[0].strip()
            response = client.post(
                "/auth/login/verify/",
                {"verification_code": code},
            )
        self.assertIn(response.status_code, {200, 302})
        return client

    def _create_exam(self, *, theory_enabled=False, objective_target=CBTWritebackTarget.OBJECTIVE):
        suffix = QuestionBank.objects.count() + 1
        question_bank = QuestionBank.objects.create(
            name=f"Stage11 Bank {suffix}",
            owner=self.teacher_user,
            assignment=self.assignment,
            subject=self.subject,
            academic_class=self.academic_class,
            session=self.session,
            term=self.term,
        )
        objective_question = Question.objects.create(
            question_bank=question_bank,
            created_by=self.teacher_user,
            subject=self.subject,
            question_type=CBTQuestionType.OBJECTIVE,
            stem="Atomic number of oxygen?",
            topic="Atoms",
            difficulty="EASY",
            marks=5,
        )
        option_a = Option.objects.create(
            question=objective_question,
            label="A",
            option_text="8",
            sort_order=1,
        )
        Option.objects.create(
            question=objective_question,
            label="B",
            option_text="16",
            sort_order=2,
        )
        from apps.cbt.models import CorrectAnswer

        answer = CorrectAnswer.objects.create(question=objective_question, is_finalized=True)
        answer.correct_options.set([option_a])

        exam = Exam.objects.create(
            title=f"Stage11 Exam {suffix}",
            description="Runner integration exam",
            exam_type="EXAM",
            status=CBTExamStatus.ACTIVE,
            created_by=self.teacher_user,
            assignment=self.assignment,
            subject=self.subject,
            academic_class=self.academic_class,
            session=self.session,
            term=self.term,
            question_bank=question_bank,
            dean_reviewed_by=self.dean_user,
            activated_by=self.it_user,
            open_now=True,
            is_time_based=True,
        )
        ExamQuestion.objects.create(
            exam=exam,
            question=objective_question,
            sort_order=1,
            marks=5,
        )
        theory_question = None
        if theory_enabled:
            theory_question = Question.objects.create(
                question_bank=question_bank,
                created_by=self.teacher_user,
                subject=self.subject,
                question_type=CBTQuestionType.SHORT_ANSWER,
                stem="Explain ionic bonding in sodium chloride.",
                topic="Bonding",
                difficulty="MEDIUM",
                marks=5,
            )
            ExamQuestion.objects.create(
                exam=exam,
                question=theory_question,
                sort_order=2,
                marks=5,
            )

        ExamBlueprint.objects.update_or_create(
            exam=exam,
            defaults={
                "duration_minutes": 30,
                "max_attempts": 1,
                "shuffle_questions": False,
                "shuffle_options": False,
                "instructions": "Answer all questions.",
                "objective_writeback_target": objective_target,
                "theory_enabled": theory_enabled,
                "theory_writeback_target": CBTWritebackTarget.THEORY,
                "auto_show_result_on_submit": True,
                "finalize_on_logout": False,
                "allow_retake": False,
            },
        )
        return exam, objective_question, theory_question

    def test_objective_submission_writes_back_immediately(self):
        exam, objective_question, _ = self._create_exam(theory_enabled=False)
        student_client = self.login_client(
            host="cbt.ndgakuje.org",
            username=self.student_user.username,
            audience="cbt",
        )
        start_response = student_client.post(f"/cbt/exams/{exam.id}/start/")
        self.assertEqual(start_response.status_code, 302)
        attempt = ExamAttempt.objects.get(exam=exam, student=self.student_user)

        submit_response = student_client.post(
            f"/cbt/attempts/{attempt.id}/run/",
            {
                "q": "1",
                "action": "submit",
                "selected_options": [str(objective_question.options.get(label="A").id)],
            },
        )
        self.assertEqual(submit_response.status_code, 302)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, CBTAttemptStatus.SUBMITTED)
        self.assertTrue(attempt.auto_marking_completed)
        self.assertEqual(str(attempt.objective_score), "40.00")

        score = StudentSubjectScore.objects.get(student=self.student_user)
        self.assertEqual(str(score.objective), "40.00")

    def test_attempt_integrity_bundle_tracks_start_and_submit(self):
        exam, objective_question, _ = self._create_exam(theory_enabled=False)
        student_client = self.login_client(
            host="cbt.ndgakuje.org",
            username=self.student_user.username,
            audience="cbt",
        )
        start_response = student_client.post(f"/cbt/exams/{exam.id}/start/")
        self.assertEqual(start_response.status_code, 302)
        attempt = ExamAttempt.objects.get(exam=exam, student=self.student_user)
        self.assertTrue(attempt.integrity_bundle.get("bundle_hash"))
        self.assertEqual(attempt.integrity_bundle["events"][0]["event_type"], "ATTEMPT_STARTED")

        submit_response = student_client.post(
            f"/cbt/attempts/{attempt.id}/run/",
            {
                "q": "1",
                "action": "submit",
                "selected_options": [str(objective_question.options.get(label="A").id)],
            },
        )
        self.assertEqual(submit_response.status_code, 302)
        attempt.refresh_from_db()
        event_types = [row["event_type"] for row in attempt.integrity_bundle["events"]]
        self.assertIn("ATTEMPT_STARTED", event_types)
        self.assertIn("ATTEMPT_SUBMITTED", event_types)
        self.assertEqual(attempt.integrity_bundle["summary"]["status"], CBTAttemptStatus.SUBMITTED)
        self.assertTrue(all(row.get("event_hash") for row in attempt.integrity_bundle["events"]))

    def test_theory_remains_pending_until_teacher_marks(self):
        exam, _, theory_question = self._create_exam(
            theory_enabled=True,
            objective_target=CBTWritebackTarget.CA1,
        )
        student_client = self.login_client(
            host="cbt.ndgakuje.org",
            username=self.student_user.username,
            audience="cbt",
        )
        start_response = student_client.post(f"/cbt/exams/{exam.id}/start/")
        self.assertEqual(start_response.status_code, 302)
        attempt = ExamAttempt.objects.get(exam=exam, student=self.student_user)

        answer_row = attempt.answers.get(exam_question__question=theory_question)
        submit_response = student_client.post(
            f"/cbt/attempts/{attempt.id}/run/",
            {
                "q": "1",
                "action": "save_next",
                "selected_options": [str(attempt.answers.get(exam_question__sort_order=1).exam_question.question.options.get(label='A').id)],
            },
        )
        self.assertEqual(submit_response.status_code, 302)
        submit_response = student_client.post(
            f"/cbt/attempts/{attempt.id}/run/?q=2",
            {
                "q": "2",
                "action": "submit",
                "response_text": "Ionic bond forms between sodium and chlorine ions.",
            },
        )
        self.assertEqual(submit_response.status_code, 302)
        attempt.refresh_from_db()
        self.assertFalse(attempt.theory_marking_completed)

        score = StudentSubjectScore.objects.get(student=self.student_user)
        self.assertEqual(str(score.ca1), "10.00")
        self.assertEqual(str(score.theory), "0.00")

        teacher_client = self.login_client(
            host="cbt.ndgakuje.org",
            username=self.teacher_user.username,
            audience="cbt",
        )
        mark_response = teacher_client.post(
            f"/cbt/marking/theory/{attempt.id}/",
            {
                f"score_{answer_row.id}": "5.00",
            },
        )
        self.assertEqual(mark_response.status_code, 302)
        attempt.refresh_from_db()
        self.assertTrue(attempt.theory_marking_completed)
        self.assertEqual(str(attempt.theory_score), "20.00")
        score.refresh_from_db()
        self.assertEqual(str(score.theory), "20.00")

    def test_shuffle_keeps_theory_after_objective_questions(self):
        exam, _, theory_question = self._create_exam(theory_enabled=True)
        extra_objective = Question.objects.create(
            question_bank=exam.question_bank,
            created_by=self.teacher_user,
            subject=self.subject,
            question_type=CBTQuestionType.OBJECTIVE,
            stem="Atomic number of neon?",
            topic="Atoms",
            difficulty="EASY",
            marks=5,
        )
        extra_option = Option.objects.create(
            question=extra_objective,
            label="A",
            option_text="10",
            sort_order=1,
        )
        Option.objects.create(
            question=extra_objective,
            label="B",
            option_text="20",
            sort_order=2,
        )
        from apps.cbt.models import CorrectAnswer

        answer = CorrectAnswer.objects.create(question=extra_objective, is_finalized=True)
        answer.correct_options.set([extra_option])
        exam.exam_questions.filter(question=theory_question).update(sort_order=3)
        ExamQuestion.objects.create(
            exam=exam,
            question=extra_objective,
            sort_order=2,
            marks=5,
        )
        blueprint = exam.blueprint
        blueprint.shuffle_questions = True
        blueprint.save(update_fields=["shuffle_questions", "updated_at"])

        ordered_rows = _ordered_exam_question_rows(exam, shuffle_questions=True)
        question_types = [row.question.question_type for row in ordered_rows]
        self.assertEqual(question_types[-1], CBTQuestionType.SHORT_ANSWER)
        self.assertTrue(
            all(
                question_type in {CBTQuestionType.OBJECTIVE, CBTQuestionType.MULTI_SELECT}
                for question_type in question_types[:-1]
            )
        )

    def test_theory_runner_keeps_theory_display_only_with_on_screen_controls(self):
        exam, _, _ = self._create_exam(theory_enabled=True)
        student_client = self.login_client(
            host="cbt.ndgakuje.org",
            username=self.student_user.username,
            audience="cbt",
        )
        start_response = student_client.post(f"/cbt/exams/{exam.id}/start/")
        self.assertEqual(start_response.status_code, 302)
        attempt = ExamAttempt.objects.get(exam=exam, student=self.student_user)

        run_response = student_client.get(f"/cbt/attempts/{attempt.id}/run/")
        self.assertEqual(run_response.status_code, 200)
        html = run_response.content.decode()
        self.assertIn("Finish Objective", html)
        self.assertIn("Keyboard Disabled", html)
        self.assertIn("Theory questions will display on screen only and must be answered on paper.", html)
        self.assertNotIn('name="response_text"', html)

    def test_student_exam_board_shows_only_today_rows_and_marks_done_after_auto_close(self):
        now = timezone.now()

        open_exam, _, _ = self._create_exam(theory_enabled=False)
        open_exam.open_now = False
        open_exam.schedule_start = now - timezone.timedelta(minutes=15)
        open_exam.schedule_end = now + timezone.timedelta(minutes=45)
        open_exam.save(update_fields=["open_now", "schedule_start", "schedule_end", "updated_at"])

        upcoming_exam, _, _ = self._create_exam(theory_enabled=False)
        upcoming_exam.open_now = False
        upcoming_exam.schedule_start = now + timezone.timedelta(minutes=60)
        upcoming_exam.schedule_end = now + timezone.timedelta(minutes=120)
        upcoming_exam.save(update_fields=["open_now", "schedule_start", "schedule_end", "updated_at"])

        done_exam, _, _ = self._create_exam(theory_enabled=False)
        done_exam.open_now = False
        done_exam.schedule_start = now - timezone.timedelta(hours=3)
        done_exam.schedule_end = now - timezone.timedelta(hours=1)
        done_exam.save(update_fields=["open_now", "schedule_start", "schedule_end", "updated_at"])
        ExamAttempt.objects.create(
            exam=done_exam,
            student=self.student_user,
            status=CBTAttemptStatus.SUBMITTED,
            attempt_number=1,
            submitted_at=now - timezone.timedelta(minutes=50),
        )

        yesterday_exam, _, _ = self._create_exam(theory_enabled=False)
        yesterday_exam.status = CBTExamStatus.CLOSED
        yesterday_exam.open_now = False
        yesterday_exam.schedule_start = now - timezone.timedelta(days=2, hours=3)
        yesterday_exam.schedule_end = now - timezone.timedelta(days=2, hours=1)
        yesterday_exam.save(update_fields=["status", "open_now", "schedule_start", "schedule_end", "updated_at"])
        yesterday_attempt = ExamAttempt.objects.create(
            exam=yesterday_exam,
            student=self.student_user,
            status=CBTAttemptStatus.SUBMITTED,
            attempt_number=1,
            submitted_at=now - timezone.timedelta(days=2, minutes=30),
        )
        ExamAttempt.objects.filter(pk=yesterday_attempt.pk).update(
            created_at=now - timezone.timedelta(days=2, minutes=30),
            updated_at=now - timezone.timedelta(days=2, minutes=30),
        )

        rows = student_available_exams(self.student_user)
        row_map = {row["exam"].id: row for row in rows}

        done_exam.refresh_from_db()
        self.assertEqual(done_exam.status, CBTExamStatus.CLOSED)
        self.assertIn(open_exam.id, row_map)
        self.assertTrue(row_map[open_exam.id]["can_start"])
        self.assertEqual(row_map[open_exam.id]["status_label"], "Open")
        self.assertIn(upcoming_exam.id, row_map)
        self.assertFalse(row_map[upcoming_exam.id]["can_start"])
        self.assertEqual(row_map[upcoming_exam.id]["status_label"], "Not Yet")
        self.assertIn("Exam opens at", row_map[upcoming_exam.id]["reason"])
        self.assertIn(done_exam.id, row_map)
        self.assertTrue(row_map[done_exam.id]["is_done"])
        self.assertTrue(row_map[done_exam.id]["is_closed"])
        self.assertEqual(row_map[done_exam.id]["status_label"], "Done")
        self.assertNotIn(yesterday_exam.id, row_map)

    def test_student_exam_board_respects_class_and_subject_registration(self):
        now = timezone.now()

        allowed_exam, _, _ = self._create_exam(theory_enabled=False)
        allowed_exam.open_now = False
        allowed_exam.schedule_start = now - timezone.timedelta(minutes=15)
        allowed_exam.schedule_end = now + timezone.timedelta(minutes=45)
        allowed_exam.save(update_fields=["open_now", "schedule_start", "schedule_end", "updated_at"])

        other_class = AcademicClass.objects.create(code="SS1A", display_name="SS1A")
        other_subject = Subject.objects.create(name="Mathematics", code="MTH")
        ClassSubject.objects.create(academic_class=other_class, subject=other_subject, is_active=True)
        other_assignment = TeacherSubjectAssignment.objects.create(
            teacher=self.teacher_user,
            subject=other_subject,
            academic_class=other_class,
            session=self.session,
            term=self.term,
            is_active=True,
        )
        other_bank = QuestionBank.objects.create(
            name="Hidden Class Bank",
            owner=self.teacher_user,
            assignment=other_assignment,
            subject=other_subject,
            academic_class=other_class,
            session=self.session,
            term=self.term,
        )
        other_question = Question.objects.create(
            question_bank=other_bank,
            created_by=self.teacher_user,
            subject=other_subject,
            question_type=CBTQuestionType.OBJECTIVE,
            stem="2 + 2 = ?",
            topic="Numbers",
            difficulty="EASY",
            marks=5,
        )
        other_option = Option.objects.create(
            question=other_question,
            label="A",
            option_text="4",
            sort_order=1,
        )
        other_question.options.create(label="B", option_text="5", sort_order=2)
        from apps.cbt.models import CorrectAnswer

        other_answer = CorrectAnswer.objects.create(question=other_question, is_finalized=True)
        other_answer.correct_options.set([other_option])
        hidden_class_exam = Exam.objects.create(
            title="SS1 Maths",
            description="Other class exam",
            exam_type="CA",
            status=CBTExamStatus.ACTIVE,
            created_by=self.teacher_user,
            assignment=other_assignment,
            subject=other_subject,
            academic_class=other_class,
            session=self.session,
            term=self.term,
            question_bank=other_bank,
            open_now=False,
            is_time_based=True,
            schedule_start=now - timezone.timedelta(minutes=15),
            schedule_end=now + timezone.timedelta(minutes=45),
        )
        ExamBlueprint.objects.create(
            exam=hidden_class_exam,
            duration_minutes=30,
            max_attempts=1,
            shuffle_questions=True,
            shuffle_options=True,
            instructions="Answer all questions.",
        )
        ExamQuestion.objects.create(exam=hidden_class_exam, question=other_question, sort_order=1, marks=5)

        same_class_subject = Subject.objects.create(name="Biology", code="BIO")
        ClassSubject.objects.create(academic_class=self.academic_class, subject=same_class_subject, is_active=True)
        same_class_assignment = TeacherSubjectAssignment.objects.create(
            teacher=self.teacher_user,
            subject=same_class_subject,
            academic_class=self.academic_class,
            session=self.session,
            term=self.term,
            is_active=True,
        )
        same_class_bank = QuestionBank.objects.create(
            name="Hidden Subject Bank",
            owner=self.teacher_user,
            assignment=same_class_assignment,
            subject=same_class_subject,
            academic_class=self.academic_class,
            session=self.session,
            term=self.term,
        )
        same_class_question = Question.objects.create(
            question_bank=same_class_bank,
            created_by=self.teacher_user,
            subject=same_class_subject,
            question_type=CBTQuestionType.OBJECTIVE,
            stem="Cell is the unit of?",
            topic="Cells",
            difficulty="EASY",
            marks=5,
        )
        same_class_option = Option.objects.create(
            question=same_class_question,
            label="A",
            option_text="Life",
            sort_order=1,
        )
        same_class_question.options.create(label="B", option_text="Energy", sort_order=2)
        same_class_answer = CorrectAnswer.objects.create(question=same_class_question, is_finalized=True)
        same_class_answer.correct_options.set([same_class_option])
        hidden_subject_exam = Exam.objects.create(
            title="SS2 Biology",
            description="Same class but unregistered subject",
            exam_type="CA",
            status=CBTExamStatus.ACTIVE,
            created_by=self.teacher_user,
            assignment=same_class_assignment,
            subject=same_class_subject,
            academic_class=self.academic_class,
            session=self.session,
            term=self.term,
            question_bank=same_class_bank,
            open_now=False,
            is_time_based=True,
            schedule_start=now - timezone.timedelta(minutes=15),
            schedule_end=now + timezone.timedelta(minutes=45),
        )
        ExamBlueprint.objects.create(
            exam=hidden_subject_exam,
            duration_minutes=30,
            max_attempts=1,
            shuffle_questions=True,
            shuffle_options=True,
            instructions="Answer all questions.",
        )
        ExamQuestion.objects.create(exam=hidden_subject_exam, question=same_class_question, sort_order=1, marks=5)

        rows = student_available_exams(self.student_user)
        exam_ids = {row["exam"].id for row in rows}

        self.assertIn(allowed_exam.id, exam_ids)
        self.assertNotIn(hidden_class_exam.id, exam_ids)
        self.assertNotIn(hidden_subject_exam.id, exam_ids)

    def test_student_cannot_start_exam_outside_schedule(self):
        exam, _, _ = self._create_exam(theory_enabled=False)
        exam.open_now = False
        exam.schedule_start = timezone.now() + timezone.timedelta(hours=2)
        exam.schedule_end = timezone.now() + timezone.timedelta(hours=4)
        exam.save(update_fields=["open_now", "schedule_start", "schedule_end", "updated_at"])

        student_client = self.login_client(
            host="cbt.ndgakuje.org",
            username=self.student_user.username,
            audience="cbt",
        )
        response = student_client.post(f"/cbt/exams/{exam.id}/start/")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ExamAttempt.objects.filter(exam=exam, student=self.student_user).exists())

    @override_settings(
        FEATURE_FLAGS={
            **settings.FEATURE_FLAGS,
            "CBT_ENABLED": True,
            "LOCKDOWN_ENABLED": False,
        }
    )
    def test_deadline_change_closes_open_attempt_via_heartbeat_without_lockdown(self):
        exam, _, _ = self._create_exam(theory_enabled=False)
        now = timezone.now()
        exam.open_now = False
        exam.schedule_start = now - timezone.timedelta(minutes=5)
        exam.schedule_end = now + timezone.timedelta(minutes=20)
        exam.save(update_fields=["open_now", "schedule_start", "schedule_end", "updated_at"])

        student_client = self.login_client(
            host="cbt.ndgakuje.org",
            username=self.student_user.username,
            audience="cbt",
        )
        start_response = student_client.post(f"/cbt/exams/{exam.id}/start/")
        self.assertEqual(start_response.status_code, 302)
        attempt = ExamAttempt.objects.get(exam=exam, student=self.student_user)

        exam.schedule_end = timezone.now() - timezone.timedelta(seconds=1)
        exam.save(update_fields=["schedule_end", "updated_at"])

        response = student_client.post(
            f"/cbt/attempts/{attempt.id}/heartbeat/",
            data=json.dumps({"tab_token": "runtime-tab"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("attempt_closed"))
        self.assertEqual(payload.get("remaining_seconds"), 0)
        self.assertIn(f"/cbt/attempts/{attempt.id}/result/", payload.get("redirect_url", ""))

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, CBTAttemptStatus.SUBMITTED)
        self.assertIsNotNone(attempt.submitted_at)

    def test_logout_keeps_open_cbt_attempt_running(self):
        exam, objective_question, _ = self._create_exam(theory_enabled=False)
        student_client = self.login_client(
            host="cbt.ndgakuje.org",
            username=self.student_user.username,
            audience="cbt",
        )
        student_client.post(f"/cbt/exams/{exam.id}/start/")
        attempt = ExamAttempt.objects.get(exam=exam, student=self.student_user)
        run_response = student_client.post(
            f"/cbt/attempts/{attempt.id}/run/",
            {
                "q": "1",
                "action": "save_stay",
                "selected_options": [str(objective_question.options.get(label="A").id)],
            },
        )
        self.assertEqual(run_response.status_code, 302)
        logout_response = student_client.get("/auth/logout/")
        self.assertEqual(logout_response.status_code, 302)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, CBTAttemptStatus.IN_PROGRESS)
        self.assertIsNone(attempt.submitted_at)

    def test_ca_split_combines_objective_and_theory_into_same_ca_target(self):
        exam, objective_question, theory_question = self._create_exam(
            theory_enabled=True,
            objective_target=CBTWritebackTarget.CA1,
        )
        exam.exam_type = "CA"
        exam.save(update_fields=["exam_type", "updated_at"])
        blueprint = ExamBlueprint.objects.get(exam=exam)
        blueprint.theory_writeback_target = CBTWritebackTarget.CA1
        blueprint.section_config = {
            "flow_type": "OBJECTIVE_THEORY",
            "objective_count": 1,
            "theory_count": 1,
            "theory_response_mode": "TYPING",
            "ca_target": CBTWritebackTarget.CA1,
            "manual_score_split": True,
            "objective_target_max": "5.00",
            "theory_target_max": "5.00",
        }
        blueprint.save(update_fields=["theory_writeback_target", "section_config", "updated_at"])

        student_client = self.login_client(
            host="cbt.ndgakuje.org",
            username=self.student_user.username,
            audience="cbt",
        )
        start_response = student_client.post(f"/cbt/exams/{exam.id}/start/")
        self.assertEqual(start_response.status_code, 302)
        attempt = ExamAttempt.objects.get(exam=exam, student=self.student_user)

        submit_response = student_client.post(
            f"/cbt/attempts/{attempt.id}/run/?q=1",
            {
                "q": "1",
                "action": "save_next",
                "selected_options": [str(objective_question.options.get(label="A").id)],
            },
        )
        self.assertEqual(submit_response.status_code, 302)
        submit_response = student_client.post(
            f"/cbt/attempts/{attempt.id}/run/?q=2",
            {
                "q": "2",
                "action": "submit",
                "response_text": "Theory answer",
            },
        )
        self.assertEqual(submit_response.status_code, 302)
        attempt.refresh_from_db()
        self.assertEqual(str(attempt.objective_score), "5.00")

        answer_row = attempt.answers.get(exam_question__question=theory_question)
        teacher_client = self.login_client(
            host="cbt.ndgakuje.org",
            username=self.teacher_user.username,
            audience="cbt",
        )
        mark_response = teacher_client.post(
            f"/cbt/marking/theory/{attempt.id}/",
            {f"score_{answer_row.id}": "5.00"},
        )
        self.assertEqual(mark_response.status_code, 302)
        attempt.refresh_from_db()
        self.assertEqual(str(attempt.theory_score), "5.00")

        score = StudentSubjectScore.objects.get(student=self.student_user)
        self.assertEqual(str(score.ca1), "10.00")


@override_settings(
    FEATURE_FLAGS={
        **settings.FEATURE_FLAGS,
        "CBT_ENABLED": True,
        "LOCKDOWN_ENABLED": True,
    }
)
@override_settings(**CBT_TEST_HOST_SETTINGS)
class StageTwelveLockdownTests(StageElevenCBTRunnerTests):
    def test_multiple_tab_heartbeat_locks_attempt_and_logs_device_ip(self):
        exam, _, _ = self._create_exam(theory_enabled=False)
        student_client = self.login_client(
            host="cbt.ndgakuje.org",
            username=self.student_user.username,
            audience="cbt",
        )
        student_client.post(f"/cbt/exams/{exam.id}/start/")
        attempt = ExamAttempt.objects.get(exam=exam, student=self.student_user)

        first = student_client.post(
            f"/cbt/attempts/{attempt.id}/heartbeat/",
            data=json.dumps({"tab_token": "tab-one"}),
            content_type="application/json",
            HTTP_USER_AGENT="NDGA-Lockdown-Test-Agent/1.0",
        )
        self.assertEqual(first.status_code, 200)
        first_payload = first.json()
        self.assertTrue(first_payload.get("ok"))
        self.assertFalse(first_payload.get("paused"))
        self.assertIn("remaining_seconds", first_payload)

        second = student_client.post(
            f"/cbt/attempts/{attempt.id}/heartbeat/",
            data=json.dumps({"tab_token": "tab-two"}),
            content_type="application/json",
            HTTP_USER_AGENT="NDGA-Lockdown-Test-Agent/1.0",
        )
        self.assertEqual(second.status_code, 200)
        payload = second.json()
        self.assertTrue(payload.get("locked"))

        attempt.refresh_from_db()
        self.assertTrue(attempt.is_locked)
        self.assertEqual(attempt.status, CBTAttemptStatus.FINALIZED)

        log = AuditEvent.objects.filter(
            category=AuditCategory.LOCKDOWN,
            event_type="LOCKDOWN_VIOLATION",
        ).latest("created_at")
        self.assertEqual(log.metadata.get("event_type"), "MULTIPLE_TAB")
        self.assertEqual(log.metadata.get("attempt_id"), str(attempt.id))
        self.assertEqual(log.metadata.get("device"), "NDGA-Lockdown-Test-Agent/1.0")
        self.assertIsNotNone(log.ip_address)

    def test_lockdown_events_are_recorded_in_attempt_integrity_bundle(self):
        exam, _, _ = self._create_exam(theory_enabled=False)
        student_client = self.login_client(
            host="cbt.ndgakuje.org",
            username=self.student_user.username,
            audience="cbt",
        )
        student_client.post(f"/cbt/exams/{exam.id}/start/")
        attempt = ExamAttempt.objects.get(exam=exam, student=self.student_user)

        student_client.post(
            f"/cbt/attempts/{attempt.id}/heartbeat/",
            data=json.dumps({"tab_token": "tab-one"}),
            content_type="application/json",
            HTTP_USER_AGENT="NDGA-Lockdown-Test-Agent/1.0",
        )
        student_client.post(
            f"/cbt/attempts/{attempt.id}/heartbeat/",
            data=json.dumps({"tab_token": "tab-two"}),
            content_type="application/json",
            HTTP_USER_AGENT="NDGA-Lockdown-Test-Agent/1.0",
        )

        attempt.refresh_from_db()
        event_types = [row["event_type"] for row in attempt.integrity_bundle["events"]]
        self.assertIn("LOCKDOWN_HEARTBEAT", event_types)
        self.assertIn("MULTIPLE_TAB", event_types)
        self.assertGreaterEqual(attempt.integrity_bundle["summary"]["violation_count"], 1)
        self.assertTrue(attempt.integrity_bundle.get("bundle_hash"))

    def test_locked_attempt_redirects_to_contact_it_screen(self):
        exam, _, _ = self._create_exam(theory_enabled=False)
        student_client = self.login_client(
            host="cbt.ndgakuje.org",
            username=self.student_user.username,
            audience="cbt",
        )
        student_client.post(f"/cbt/exams/{exam.id}/start/")
        attempt = ExamAttempt.objects.get(exam=exam, student=self.student_user)
        violation = student_client.post(
            f"/cbt/attempts/{attempt.id}/violation/",
            data=json.dumps({"event_type": "FOCUS_LOSS"}),
            content_type="application/json",
        )
        self.assertEqual(violation.status_code, 200)
        self.assertTrue(violation.json().get("locked"))

        run_response = student_client.get(f"/cbt/attempts/{attempt.id}/run/")
        self.assertEqual(run_response.status_code, 302)
        self.assertIn(f"/cbt/attempts/{attempt.id}/locked/", run_response.url)

    def test_it_can_unlock_grant_time_and_allow_resume(self):
        exam, _, _ = self._create_exam(theory_enabled=False)
        student_client = self.login_client(
            host="cbt.ndgakuje.org",
            username=self.student_user.username,
            audience="cbt",
        )
        student_client.post(f"/cbt/exams/{exam.id}/start/")
        attempt = ExamAttempt.objects.get(exam=exam, student=self.student_user)
        student_client.post(
            f"/cbt/attempts/{attempt.id}/violation/",
            data=json.dumps({"event_type": "TAB_SWITCH"}),
            content_type="application/json",
        )
        attempt.refresh_from_db()
        self.assertTrue(attempt.is_locked)

        it_client = self.login_client(
            host="it.ndgakuje.org",
            username=self.it_user.username,
            audience="staff",
        )
        unlock_response = it_client.post(
            f"/cbt/it/lockdown/{attempt.id}/action/",
            {
                "action": "unlock",
                "allow_resume": "on",
                "extra_time_minutes": "15",
            },
        )
        self.assertEqual(unlock_response.status_code, 302)
        attempt.refresh_from_db()
        self.assertFalse(attempt.is_locked)
        self.assertTrue(attempt.allow_resume_by_it)
        self.assertEqual(attempt.extra_time_minutes, 15)
        self.assertEqual(attempt.status, CBTAttemptStatus.IN_PROGRESS)


@override_settings(
    FEATURE_FLAGS={
        **settings.FEATURE_FLAGS,
        "CBT_ENABLED": True,
    }
)
@override_settings(**CBT_TEST_HOST_SETTINGS)
class StageThirteenSimulationTests(StageElevenCBTRunnerTests):
    def _create_simulation_wrapper(self, *, score_mode, max_score="10.00", evidence_required=False):
        suffix = SimulationWrapper.objects.count() + 1
        return SimulationWrapper.objects.create(
            tool_name=f"Simulation Tool {suffix}",
            tool_type="Iframe Tool",
            tool_category="SCIENCE",
            description="Simulation wrapper for stage 13 tests.",
            online_url="https://example.org/sim",
            offline_asset_path="",
            score_mode=score_mode,
            max_score=max_score,
            scoring_callback_type="POST_MESSAGE",
            evidence_required=evidence_required,
            status=CBTSimulationWrapperStatus.APPROVED,
            created_by=self.it_user,
        )

    def _start_attempt(self, exam):
        student_client = self.login_client(
            host="cbt.ndgakuje.org",
            username=self.student_user.username,
            audience="cbt",
        )
        start_response = student_client.post(f"/cbt/exams/{exam.id}/start/")
        self.assertEqual(start_response.status_code, 302)
        attempt = ExamAttempt.objects.get(exam=exam, student=self.student_user)
        return student_client, attempt

    def test_it_registry_submission_and_dean_approval_flow(self):
        it_client = self.login_client(
            host="it.ndgakuje.org",
            username=self.it_user.username,
            audience="staff",
        )
        create_response = it_client.post(
            "/cbt/it/simulations/",
            {
                "action": "create",
                "tool_name": "PhET Circuit Lab",
                "tool_type": "iframe",
                "tool_category": "SCIENCE",
                "description": "Virtual circuit practical.",
                "online_url": "https://example.org/phet-circuit",
                "offline_asset_path": "",
                "score_mode": CBTSimulationScoreMode.AUTO,
                "max_score": "10.00",
                "scoring_callback_type": "POST_MESSAGE",
                "evidence_required": "",
                "is_active": "on",
            },
        )
        self.assertEqual(create_response.status_code, 302)
        wrapper = SimulationWrapper.objects.get(tool_name="PhET Circuit Lab")
        self.assertEqual(wrapper.status, CBTSimulationWrapperStatus.DRAFT)

        submit_response = it_client.post(
            "/cbt/it/simulations/",
            {
                "action": "submit_to_dean",
                "wrapper_id": str(wrapper.id),
                "comment": "Ready for dean review",
            },
        )
        self.assertEqual(submit_response.status_code, 302)
        wrapper.refresh_from_db()
        self.assertEqual(wrapper.status, CBTSimulationWrapperStatus.PENDING_DEAN)

        dean_client = self.login_client(
            host="staff.ndgakuje.org",
            username=self.dean_user.username,
            audience="staff",
        )
        approve_response = dean_client.post(
            f"/cbt/dean/simulations/{wrapper.id}/",
            {
                "action": "APPROVE",
                "comment": "Simulation tool approved.",
            },
        )
        self.assertEqual(approve_response.status_code, 302)
        wrapper.refresh_from_db()
        self.assertEqual(wrapper.status, CBTSimulationWrapperStatus.APPROVED)
        self.assertEqual(wrapper.dean_reviewed_by_id, self.dean_user.id)

    def test_it_registry_create_accepts_html5_zip_bundle(self):
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("index.html", "<html><body>Local Sim</body></html>")
            archive.writestr("assets/info.txt", "offline simulation")
        bundle_upload = SimpleUploadedFile(
            "local-sim.zip",
            zip_buffer.getvalue(),
            content_type="application/zip",
        )

        it_client = self.login_client(
            host="it.ndgakuje.org",
            username=self.it_user.username,
            audience="staff",
        )
        create_response = it_client.post(
            "/cbt/it/simulations/",
            {
                "action": "create",
                "tool_name": "Offline Local Sim",
                "tool_type": "HTML5",
                "tool_category": "SCIENCE",
                "description": "Offline bundle test.",
                "online_url": "",
                "offline_asset_path": "",
                "score_mode": CBTSimulationScoreMode.VERIFY,
                "max_score": "10.00",
                "scoring_callback_type": "POST_MESSAGE",
                "evidence_required": "on",
                "is_active": "on",
                "bundle_zip": bundle_upload,
            },
        )
        self.assertEqual(create_response.status_code, 302)

        wrapper = SimulationWrapper.objects.get(tool_name="Offline Local Sim")
        self.assertTrue(wrapper.offline_asset_path.startswith("/media/sims/"))
        self.assertEqual(wrapper.status, CBTSimulationWrapperStatus.DRAFT)

    def test_auto_simulation_score_is_stored(self):
        exam, _, _ = self._create_exam(theory_enabled=False)
        wrapper = self._create_simulation_wrapper(score_mode=CBTSimulationScoreMode.AUTO)
        exam_simulation = ExamSimulation.objects.create(
            exam=exam,
            simulation_wrapper=wrapper,
            sort_order=1,
            writeback_target=CBTWritebackTarget.CA3,
            is_required=True,
        )
        student_client, attempt = self._start_attempt(exam)

        auto_score_response = student_client.post(
            f"/cbt/attempts/{attempt.id}/simulations/{exam_simulation.id}/auto-score/",
            data=json.dumps({"score": "8.50", "type": "POST_MESSAGE"}),
            content_type="application/json",
        )
        self.assertEqual(auto_score_response.status_code, 200)
        self.assertTrue(auto_score_response.json().get("ok"))

        record = SimulationAttemptRecord.objects.get(
            attempt=attempt,
            exam_simulation=exam_simulation,
        )
        self.assertEqual(record.status, "AUTO_CAPTURED")
        self.assertEqual(str(record.final_score), "8.50")

    def test_auto_simulation_score_accepts_xapi_statement_payload(self):
        exam, _, _ = self._create_exam(theory_enabled=False)
        wrapper = self._create_simulation_wrapper(score_mode=CBTSimulationScoreMode.AUTO)
        exam_simulation = ExamSimulation.objects.create(
            exam=exam,
            simulation_wrapper=wrapper,
            sort_order=1,
            writeback_target=CBTWritebackTarget.CA3,
            is_required=True,
        )
        student_client, attempt = self._start_attempt(exam)

        auto_score_response = student_client.post(
            f"/cbt/attempts/{attempt.id}/simulations/{exam_simulation.id}/auto-score/",
            data=json.dumps(
                {
                    "type": "POST_MESSAGE",
                    "statement": {
                        "verb": {
                            "id": "http://adlnet.gov/expapi/verbs/completed",
                            "display": {"en-US": "completed"},
                        },
                        "result": {
                            "score": {"scaled": 0.82},
                        },
                    },
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(auto_score_response.status_code, 200)
        self.assertTrue(auto_score_response.json().get("ok"))

        record = SimulationAttemptRecord.objects.get(
            attempt=attempt,
            exam_simulation=exam_simulation,
        )
        self.assertEqual(record.status, "AUTO_CAPTURED")
        self.assertEqual(str(record.final_score), "8.20")
        self.assertEqual(
            record.callback_payload.get("_score_extraction", {}).get("method"),
            "xapi_statement_result",
        )

    def test_it_registry_seed_free_library_action(self):
        it_client = self.login_client(
            host="it.ndgakuje.org",
            username=self.it_user.username,
            audience="staff",
        )
        seed_response = it_client.post(
            "/cbt/it/simulations/",
            {"action": "seed_free_library"},
        )
        self.assertEqual(seed_response.status_code, 302)
        self.assertTrue(
            SimulationWrapper.objects.filter(
                source_provider__in=["PHET", "H5P", "GEOGEBRA"],
            ).exists()
        )

    def test_verify_mode_requires_evidence_and_allows_teacher_validation_and_import(self):
        exam, _, _ = self._create_exam(theory_enabled=False)
        wrapper = self._create_simulation_wrapper(
            score_mode=CBTSimulationScoreMode.VERIFY,
            evidence_required=True,
        )
        exam_simulation = ExamSimulation.objects.create(
            exam=exam,
            simulation_wrapper=wrapper,
            sort_order=1,
            writeback_target=CBTWritebackTarget.CA4,
            max_score_override="10.00",
            is_required=True,
        )
        student_client, attempt = self._start_attempt(exam)

        missing_evidence = student_client.post(
            f"/cbt/attempts/{attempt.id}/simulations/{exam_simulation.id}/",
            {"evidence_note": "No file yet"},
        )
        self.assertEqual(missing_evidence.status_code, 200)
        self.assertContains(missing_evidence, "Evidence upload is required")

        upload = SimpleUploadedFile(
            "verify_evidence.txt",
            b"NDGA verify evidence payload",
            content_type="text/plain",
        )
        evidence_submit = student_client.post(
            f"/cbt/attempts/{attempt.id}/simulations/{exam_simulation.id}/",
            {
                "evidence_note": "Practical evidence upload",
                "evidence_file": upload,
            },
        )
        self.assertEqual(evidence_submit.status_code, 302)
        record = SimulationAttemptRecord.objects.get(
            attempt=attempt,
            exam_simulation=exam_simulation,
        )
        self.assertEqual(record.status, "VERIFY_PENDING")
        self.assertTrue(bool(record.evidence_file))

        teacher_client = self.login_client(
            host="cbt.ndgakuje.org",
            username=self.teacher_user.username,
            audience="cbt",
        )
        verify_score = teacher_client.post(
            f"/cbt/marking/simulations/{record.id}/",
            {
                "action": "verify_score",
                "verified_score": "7.50",
                "comment": "Evidence validated",
            },
        )
        self.assertEqual(verify_score.status_code, 302)
        record.refresh_from_db()
        self.assertEqual(record.status, "VERIFIED")
        self.assertEqual(str(record.final_score), "7.50")

        import_score = teacher_client.post(
            f"/cbt/marking/simulations/{record.id}/",
            {
                "action": "import_score",
                "writeback_target": CBTWritebackTarget.CA4,
                "manual_raw_score": "",
            },
        )
        self.assertEqual(import_score.status_code, 302)
        record.refresh_from_db()
        self.assertEqual(record.status, "IMPORTED")
        self.assertEqual(record.imported_target, CBTWritebackTarget.CA4)

        score = StudentSubjectScore.objects.get(student=self.student_user, result_sheet__subject=self.subject)
        self.assertEqual(str(score.ca4), "7.50")

    def test_rubric_scoring_is_deterministic_and_importable(self):
        exam, _, _ = self._create_exam(theory_enabled=False)
        wrapper = self._create_simulation_wrapper(
            score_mode=CBTSimulationScoreMode.RUBRIC,
            max_score="20.00",
            evidence_required=False,
        )
        exam_simulation = ExamSimulation.objects.create(
            exam=exam,
            simulation_wrapper=wrapper,
            sort_order=1,
            writeback_target=CBTWritebackTarget.CA3,
            is_required=True,
        )
        student_client, attempt = self._start_attempt(exam)

        rubric_submit = student_client.post(
            f"/cbt/attempts/{attempt.id}/simulations/{exam_simulation.id}/",
            {"evidence_note": "Rubric simulation completed"},
        )
        self.assertEqual(rubric_submit.status_code, 302)
        record = SimulationAttemptRecord.objects.get(
            attempt=attempt,
            exam_simulation=exam_simulation,
        )
        self.assertEqual(record.status, "RUBRIC_PENDING")

        teacher_client = self.login_client(
            host="cbt.ndgakuje.org",
            username=self.teacher_user.username,
            audience="cbt",
        )
        rubric_score = teacher_client.post(
            f"/cbt/marking/simulations/{record.id}/",
            {
                "action": "rubric_score",
                "criterion_accuracy": "80",
                "criterion_completion": "70",
                "criterion_analysis": "90",
                "criterion_safety": "60",
                "comment": "Rubric graded",
            },
        )
        self.assertEqual(rubric_score.status_code, 302)
        record.refresh_from_db()
        self.assertEqual(record.status, "RUBRIC_SCORED")
        self.assertEqual(str(record.final_score), "15.00")
        self.assertEqual(record.rubric_breakdown.get("average_percent"), "75.00")

        import_score = teacher_client.post(
            f"/cbt/marking/simulations/{record.id}/",
            {
                "action": "import_score",
                "writeback_target": CBTWritebackTarget.CA3,
                "manual_raw_score": "",
            },
        )
        self.assertEqual(import_score.status_code, 302)
        score = StudentSubjectScore.objects.get(student=self.student_user, result_sheet__subject=self.subject)
        self.assertEqual(str(score.ca3), "7.50")

    def test_submit_is_blocked_until_required_simulation_is_completed(self):
        exam, objective_question, _ = self._create_exam(theory_enabled=False)
        wrapper = self._create_simulation_wrapper(score_mode=CBTSimulationScoreMode.AUTO)
        exam_simulation = ExamSimulation.objects.create(
            exam=exam,
            simulation_wrapper=wrapper,
            sort_order=1,
            writeback_target=CBTWritebackTarget.CA3,
            is_required=True,
        )
        student_client, attempt = self._start_attempt(exam)

        blocked_submit = student_client.post(
            f"/cbt/attempts/{attempt.id}/run/",
            {
                "q": "1",
                "action": "submit",
                "selected_options": [str(objective_question.options.get(label="A").id)],
            },
        )
        self.assertEqual(blocked_submit.status_code, 302)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, CBTAttemptStatus.IN_PROGRESS)

        auto_score_response = student_client.post(
            f"/cbt/attempts/{attempt.id}/simulations/{exam_simulation.id}/auto-score/",
            data=json.dumps({"score": "9.00", "type": "POST_MESSAGE"}),
            content_type="application/json",
        )
        self.assertEqual(auto_score_response.status_code, 200)

        submit_ok = student_client.post(
            f"/cbt/attempts/{attempt.id}/run/",
            {
                "q": "1",
                "action": "submit",
                "selected_options": [str(objective_question.options.get(label="A").id)],
            },
        )
        self.assertEqual(submit_ok.status_code, 302)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, CBTAttemptStatus.SUBMITTED)


@override_settings(
    FEATURE_FLAGS={
        **settings.FEATURE_FLAGS,
        "CBT_ENABLED": True,
        "OFFLINE_MODE_ENABLED": True,
    }
)
@override_settings(**CBT_TEST_HOST_SETTINGS)
class StageFourteenOfflineSyncTests(StageElevenCBTRunnerTests):
    def _create_simulation_wrapper(self):
        suffix = SimulationWrapper.objects.count() + 1
        return SimulationWrapper.objects.create(
            tool_name=f"Sync Simulation Tool {suffix}",
            tool_type="iframe",
            tool_category="SCIENCE",
            online_url="https://example.org/sync-sim",
            score_mode=CBTSimulationScoreMode.AUTO,
            max_score="10.00",
            scoring_callback_type="POST_MESSAGE",
            status=CBTSimulationWrapperStatus.APPROVED,
            created_by=self.it_user,
        )

    def test_exam_attempt_submission_enqueues_outbox_row(self):
        exam, objective_question, _ = self._create_exam(theory_enabled=False)
        student_client = self.login_client(
            host="cbt.ndgakuje.org",
            username=self.student_user.username,
            audience="cbt",
        )
        student_client.post(f"/cbt/exams/{exam.id}/start/")
        attempt = ExamAttempt.objects.get(exam=exam, student=self.student_user)

        submit_response = student_client.post(
            f"/cbt/attempts/{attempt.id}/run/",
            {
                "q": "1",
                "action": "submit",
                "selected_options": [str(objective_question.options.get(label="A").id)],
            },
        )
        self.assertEqual(submit_response.status_code, 302)

        rows = list(SyncQueue.objects.filter(operation_type=SyncOperationType.CBT_EXAM_ATTEMPT))
        self.assertTrue(rows)
        self.assertTrue(
            any(
                row.payload.get("event_type") == "ATTEMPT_SUBMITTED"
                and row.payload.get("attempt_id") == str(attempt.id)
                for row in rows
            )
        )

    def test_simulation_capture_enqueues_outbox_row(self):
        exam, _, _ = self._create_exam(theory_enabled=False)
        wrapper = self._create_simulation_wrapper()
        exam_simulation = ExamSimulation.objects.create(
            exam=exam,
            simulation_wrapper=wrapper,
            sort_order=1,
            writeback_target=CBTWritebackTarget.CA3,
            is_required=True,
        )
        student_client = self.login_client(
            host="cbt.ndgakuje.org",
            username=self.student_user.username,
            audience="cbt",
        )
        student_client.post(f"/cbt/exams/{exam.id}/start/")
        attempt = ExamAttempt.objects.get(exam=exam, student=self.student_user)

        auto_score_response = student_client.post(
            f"/cbt/attempts/{attempt.id}/simulations/{exam_simulation.id}/auto-score/",
            data=json.dumps({"score": "8.00", "type": "POST_MESSAGE"}),
            content_type="application/json",
        )
        self.assertEqual(auto_score_response.status_code, 200)

        rows = list(
            SyncQueue.objects.filter(
                operation_type=SyncOperationType.CBT_SIMULATION_ATTEMPT
            )
        )
        self.assertTrue(rows)
        self.assertTrue(
            any(
                row.payload.get("event_type") == "SIMULATION_AUTO_CAPTURED"
                and row.payload.get("attempt_id") == str(attempt.id)
                for row in rows
            )
        )


@override_settings(**CBT_TEST_HOST_SETTINGS)
class CBTNotationRenderingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        StageElevenCBTRunnerTests.setUpTestData.__func__(cls)

    def login_client(self, *, host, username, audience):
        return StageElevenCBTRunnerTests.login_client(
            self,
            host=host,
            username=username,
            audience=audience,
        )

    def _create_exam(self, *, theory_enabled=False, objective_target=CBTWritebackTarget.OBJECTIVE):
        return StageElevenCBTRunnerTests._create_exam(
            self,
            theory_enabled=theory_enabled,
            objective_target=objective_target,
        )

    def _start_attempt(self, exam):
        student_client = self.login_client(
            host="cbt.ndgakuje.org",
            username=self.student_user.username,
            audience="cbt",
        )
        start_response = student_client.post(f"/cbt/exams/{exam.id}/start/")
        self.assertEqual(start_response.status_code, 302)
        attempt = ExamAttempt.objects.get(exam=exam, student=self.student_user)
        return student_client, attempt

    def test_template_filter_preserves_html_and_formats_base_digits(self):
        rendered = Template(
            "{% load cbt_text %}{{ value|safe|cbt_notation }}"
        ).render(Context({"value": "Base <strong>1111\u2082</strong> and x\u00b2"}))
        self.assertIn("<strong>1111<sub>2</sub></strong>", rendered)
        self.assertIn("x<sup>2</sup>", rendered)

    def test_attempt_run_renders_number_bases_as_subscripts(self):
        exam, objective_question, _ = self._create_exam(theory_enabled=False)
        objective_question.stem = "Add: 1111\u2082 + 101\u2082"
        objective_question.save(update_fields=["stem", "updated_at"])
        objective_question.options.filter(label="A").update(option_text="11111\u2082")
        objective_question.options.filter(label="B").update(option_text="10100\u2082")

        student_client, attempt = self._start_attempt(exam)
        response = student_client.get(f"/cbt/attempts/{attempt.id}/run/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("1111<sub>2</sub> + 101<sub>2</sub>", content)
        self.assertIn("10100<sub>2</sub>", content)
