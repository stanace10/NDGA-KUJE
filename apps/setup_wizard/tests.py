import io
import json
from io import StringIO
from pathlib import Path
import tempfile
import zipfile

from django.core.management import call_command
from django.test import Client, TestCase, override_settings

from apps.accounts.constants import ROLE_IT_MANAGER, ROLE_STUDENT
from apps.accounts.models import Role, StudentProfile, User
from apps.academics.models import (
    AcademicClass,
    AcademicSession,
    ClassSubject,
    GradeScale,
    StudentClassEnrollment,
    Subject,
    Term,
)
from apps.attendance.models import SchoolCalendar
from apps.setup_wizard.models import RuntimeFeatureFlags, SetupStateCode, SystemSetupState


class SetupWizardFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        it_role = Role.objects.get(code=ROLE_IT_MANAGER)
        student_role = Role.objects.get(code=ROLE_STUDENT)
        cls.it_user = User.objects.create_user(
            username="admin@ndgakuje.org",
            password="admin",
            primary_role=it_role,
            must_change_password=False,
        )
        cls.student_user = User.objects.create_user(
            username="student-stage3",
            password="Password123!",
            primary_role=student_role,
            must_change_password=False,
        )

    def test_it_wizard_enforces_step_order(self):
        client = Client(HTTP_HOST="it.ndgakuje.org")
        login_response = client.post(
            "/auth/login/?audience=staff",
            {"username": "admin@ndgakuje.org", "password": "admin"},
        )
        self.assertEqual(login_response.status_code, 302)

        response = client.get("/setup/wizard/subjects/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith("/setup/wizard/session/"))

    def test_it_can_complete_stage_three_setup_flow(self):
        client = Client(HTTP_HOST="it.ndgakuje.org")
        login_response = client.post(
            "/auth/login/?audience=staff",
            {"username": "admin@ndgakuje.org", "password": "admin"},
        )
        self.assertEqual(login_response.status_code, 302)

        self.assertEqual(client.post("/setup/wizard/session/", {"session_name": "2025/2026"}).status_code, 302)
        self.assertEqual(client.post("/setup/wizard/term/", {"term_name": "FIRST"}).status_code, 302)
        self.assertEqual(
            client.post(
                "/setup/wizard/calendar/",
                {
                    "start_date": "2026-01-13",
                    "end_date": "2026-04-11",
                    "holidays": "2026-02-18|Mid-term Break",
                },
            ).status_code,
            302,
        )
        self.assertEqual(
            client.post("/setup/wizard/classes/", {"class_codes": "JS1A\nJS1B\nSS1A"}).status_code,
            302,
        )
        self.assertEqual(
            client.post("/setup/wizard/subjects/", {"subjects": "Mathematics|MTH\nEnglish Language|ENG"}).status_code,
            302,
        )
        created_session = AcademicSession.objects.get(name="2025/2026")
        class_rows = list(
            AcademicClass.objects.filter(code__in=["JS1A", "JS1B", "SS1A"]).order_by("code")
        )
        subject_rows = list(Subject.objects.filter(code__in=["MTH", "ENG"]).order_by("code"))
        self.assertEqual(len(class_rows), 3)
        self.assertEqual(len(subject_rows), 2)
        for class_row in class_rows:
            if class_row.code == "SS1A":
                selected = [str(subject_rows[0].id)]
            else:
                selected = [str(subject.id) for subject in subject_rows]
            response = client.post(
                "/setup/wizard/class-subjects/",
                {
                    "academic_class": str(class_row.id),
                    "subjects": selected,
                },
            )
            self.assertEqual(response.status_code, 302)
        self.assertEqual(
            client.post(
                "/setup/wizard/class-subjects/",
                {
                    "academic_class": str(class_rows[0].id),
                    "subjects": [str(subject.id) for subject in subject_rows],
                    "continue_next": "1",
                },
            ).status_code,
            302,
        )
        self.assertEqual(
            client.post("/setup/wizard/grade-scale/", {"apply_defaults": "on"}).status_code,
            302,
        )
        finalize_response = client.post(
            "/setup/wizard/finalize/",
            {"confirm_finalize": "on"},
        )
        self.assertEqual(finalize_response.status_code, 302)

        setup_state = SystemSetupState.get_solo()
        self.assertEqual(setup_state.state, SetupStateCode.IT_READY)
        self.assertIsNotNone(setup_state.current_session)
        self.assertIsNotNone(setup_state.current_term)
        self.assertTrue(
            SchoolCalendar.objects.filter(term=setup_state.current_term).exists()
        )
        self.assertEqual(Term.objects.filter(session=setup_state.current_session).count(), 3)
        self.assertTrue(ClassSubject.objects.filter(is_active=True).exists())

    def test_session_step_auto_creates_all_three_terms(self):
        client = Client(HTTP_HOST="it.ndgakuje.org")
        login_response = client.post(
            "/auth/login/?audience=staff",
            {"username": "admin@ndgakuje.org", "password": "admin"},
        )
        self.assertEqual(login_response.status_code, 302)
        response = client.post("/setup/wizard/session/", {"session_name": "2026/2027"})
        self.assertEqual(response.status_code, 302)
        session = AcademicSession.objects.get(name="2026/2027")
        term_names = set(Term.objects.filter(session=session).values_list("name", flat=True))
        self.assertEqual(term_names, {"FIRST", "SECOND", "THIRD"})

    def test_non_it_user_cannot_access_setup_wizard(self):
        client = Client(HTTP_HOST="student.ndgakuje.org")
        login_response = client.post(
            "/auth/login/?audience=student",
            {"username": "student-stage3", "password": "Password123!"},
        )
        self.assertEqual(login_response.status_code, 302)

        response = client.get("/setup/wizard/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "http://student.ndgakuje.org/")

    def test_global_banner_visible_for_non_it_before_ready(self):
        client = Client(HTTP_HOST="student.ndgakuje.org")
        login_response = client.post(
            "/auth/login/?audience=student",
            {"username": "student-stage3", "password": "Password123!"},
        )
        self.assertEqual(login_response.status_code, 302)

        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "System not configured.")

    def test_end_term_advances_within_session_and_end_session_opens_next_session(self):
        session = AcademicSession.objects.create(name="2025/2026")
        first = Term.objects.create(session=session, name="FIRST")
        second = Term.objects.create(session=session, name="SECOND")
        Term.objects.create(session=session, name="THIRD")
        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = session
        setup_state.current_term = first
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_user)
        response_one = client.post(
            "/setup/session-term/",
            {"action": "end-term", "confirm_end_term": "on"},
        )
        self.assertEqual(response_one.status_code, 302)
        setup_state.refresh_from_db()
        self.assertEqual(setup_state.current_session.name, "2025/2026")
        self.assertEqual(setup_state.current_term.name, "SECOND")

        response_two = client.post(
            "/setup/session-term/",
            {"action": "set-context", "session": str(session.id), "term": str(second.id)},
        )
        self.assertEqual(response_two.status_code, 302)
        setup_state.refresh_from_db()
        self.assertEqual(setup_state.current_term.name, "SECOND")

        third_term = Term.objects.get(session=session, name="THIRD")
        client.post(
            "/setup/session-term/",
            {"action": "set-context", "session": str(session.id), "term": str(third_term.id)},
        )
        response_three = client.post(
            "/setup/session-term/",
            {"action": "end-term", "confirm_end_term": "on"},
        )
        self.assertEqual(response_three.status_code, 200)
        self.assertContains(response_three, "Use End Session")

        response_four = client.post(
            "/setup/session-term/",
            {"action": "end-session", "confirm_end_session": "on"},
        )
        self.assertEqual(response_four.status_code, 302)
        setup_state.refresh_from_db()
        self.assertEqual(setup_state.current_session.name, "2026/2027")
        self.assertEqual(setup_state.current_term.name, "FIRST")
        session.refresh_from_db()
        self.assertTrue(session.is_closed)
        self.assertEqual(
            set(Term.objects.filter(session=setup_state.current_session).values_list("name", flat=True)),
            {"FIRST", "SECOND", "THIRD"},
        )

    def test_end_session_promotes_and_graduates_students(self):
        session = AcademicSession.objects.create(name="2027/2028")
        third_term = Term.objects.create(session=session, name="THIRD")
        AcademicClass.objects.create(code="JS2A", display_name="JS2A")
        js1 = AcademicClass.objects.create(code="JS1A", display_name="JS1A")
        ss3 = AcademicClass.objects.create(code="SS3A", display_name="SS3A")

        student_role = Role.objects.get(code=ROLE_STUDENT)
        js1_student = User.objects.create_user(
            username="js1-student",
            password="Password123!",
            primary_role=student_role,
            must_change_password=False,
        )
        ss3_student = User.objects.create_user(
            username="ss3-student",
            password="Password123!",
            primary_role=student_role,
            must_change_password=False,
        )
        StudentProfile.objects.create(user=js1_student, student_number="NDGAK/27/001")
        StudentProfile.objects.create(user=ss3_student, student_number="NDGAK/27/002")

        StudentClassEnrollment.objects.create(
            student=js1_student,
            academic_class=js1,
            session=session,
            is_active=True,
        )
        StudentClassEnrollment.objects.create(
            student=ss3_student,
            academic_class=ss3,
            session=session,
            is_active=True,
        )

        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = session
        setup_state.current_term = third_term
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_user)
        response = client.post(
            "/setup/session-term/",
            {"action": "end-session", "confirm_end_session": "on"},
        )
        self.assertEqual(response.status_code, 302)

        setup_state.refresh_from_db()
        self.assertEqual(setup_state.current_session.name, "2028/2029")
        self.assertEqual(setup_state.current_term.name, "FIRST")
        session.refresh_from_db()
        self.assertTrue(session.is_closed)

        promoted_enrollment = StudentClassEnrollment.objects.get(
            student=js1_student,
            session=setup_state.current_session,
            is_active=True,
        )
        self.assertEqual(promoted_enrollment.academic_class.code, "JS2A")

        self.assertFalse(
            StudentClassEnrollment.objects.filter(
                student=ss3_student,
                session=setup_state.current_session,
                is_active=True,
            ).exists()
        )
        ss3_student.student_profile.refresh_from_db()
        self.assertTrue(ss3_student.student_profile.is_graduated)

    @override_settings(
        FEATURE_FLAGS={
            "CBT_ENABLED": True,
            "ELECTION_ENABLED": True,
            "OFFLINE_MODE_ENABLED": True,
            "LOCKDOWN_ENABLED": True,
        }
    )
    def test_runtime_feature_flags_sync_to_env_when_singleton_is_untouched(self):
        flags = RuntimeFeatureFlags.get_solo()
        flags.cbt_enabled = False
        flags.election_enabled = False
        flags.offline_mode_enabled = False
        flags.lockdown_enabled = False
        flags.last_updated_by = None
        flags.save(
            update_fields=[
                "cbt_enabled",
                "election_enabled",
                "offline_mode_enabled",
                "lockdown_enabled",
                "last_updated_by",
                "updated_at",
            ]
        )
        resolved = RuntimeFeatureFlags.get_solo()
        self.assertEqual(resolved.id, flags.id)
        self.assertTrue(resolved.cbt_enabled)
        self.assertTrue(resolved.election_enabled)
        self.assertTrue(resolved.offline_mode_enabled)
        self.assertTrue(resolved.lockdown_enabled)

    def test_grade_scale_step_accepts_custom_ranges(self):
        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_user)
        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.CLASS_SUBJECTS_MAPPED
        setup_state.save(update_fields=["state", "updated_at"])

        response = client.post(
            "/setup/wizard/grade-scale/",
            {
                "a_min": 75,
                "a_max": 100,
                "b_min": 65,
                "b_max": 74,
                "c_min": 55,
                "c_max": 64,
                "d_min": 45,
                "d_max": 54,
                "f_min": 0,
                "f_max": 44,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            GradeScale.objects.get(grade="A", is_default=True).min_score,
            75,
        )
        self.assertEqual(
            GradeScale.objects.get(grade="F", is_default=True).max_score,
            44,
        )

    def test_closed_session_cannot_be_set_as_active_context(self):
        closed_session = AcademicSession.objects.create(name="2030/2031", is_closed=True)
        closed_term = Term.objects.create(session=closed_session, name="FIRST")
        open_session = AcademicSession.objects.create(name="2031/2032")
        open_term = Term.objects.create(session=open_session, name="FIRST")

        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = open_session
        setup_state.current_term = open_term
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_user)
        response = client.post(
            "/setup/session-term/",
            {
                "action": "set-context",
                "session": str(closed_session.id),
                "term": str(closed_term.id),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Closed session cannot be set as active context.")
        setup_state.refresh_from_db()
        self.assertEqual(setup_state.current_session_id, open_session.id)


class BackupCenterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        it_role = Role.objects.get(code=ROLE_IT_MANAGER)
        student_role = Role.objects.get(code=ROLE_STUDENT)
        cls.it_user = User.objects.create_user(
            username="backup-it@ndga.local",
            password="Password123!",
            primary_role=it_role,
            must_change_password=False,
        )
        cls.student_user = User.objects.create_user(
            username="backup-student@ndga.local",
            password="Password123!",
            primary_role=student_role,
            must_change_password=False,
        )
        StudentProfile.objects.create(user=cls.student_user, student_number="NDGAK/26/501")
        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.save(update_fields=["state", "updated_at"])

    def test_it_can_open_backup_center(self):
        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_user)
        response = client.get("/setup/backup/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Backup Now")
        self.assertContains(response, "backup_lan_recovery_bundle.ps1")

    def test_backup_download_contains_db_and_media_manifest(self):
        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_user)
        response = client.post("/setup/backup/", {"action": "backup-now"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        members = set(archive.namelist())
        self.assertIn("metadata.json", members)
        self.assertIn("database/db.json", members)
        self.assertIn("media/manifest.json", members)

class RestoreDrillCommandTests(TestCase):
    def test_run_restore_drill_creates_valid_archive_without_mutating_data(self):
        user_count_before = User.objects.count()
        with tempfile.TemporaryDirectory() as media_dir, tempfile.TemporaryDirectory() as output_dir:
            receipt_dir = Path(media_dir) / "receipts"
            receipt_dir.mkdir(parents=True, exist_ok=True)
            (receipt_dir / "sample.txt").write_text("ndga-restore-drill", encoding="utf-8")

            with override_settings(MEDIA_ROOT=media_dir):
                stdout = StringIO()
                call_command(
                    "run_restore_drill",
                    "--output-dir",
                    output_dir,
                    "--keep-archive",
                    stdout=stdout,
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "ok")
            self.assertTrue(payload["archive_kept"])
            self.assertEqual(User.objects.count(), user_count_before)
            self.assertGreaterEqual(payload["inspection"]["media_file_count"], 1)
            self.assertTrue(Path(payload["archive_path"]).exists())
            self.assertTrue(payload["inspection"]["required_entries_present"])

