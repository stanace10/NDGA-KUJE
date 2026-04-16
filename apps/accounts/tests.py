import base64
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.urls import reverse

from docx import Document

from apps.accounts.constants import (
    ROLE_BURSAR,
    ROLE_DEAN,
    ROLE_FORM_TEACHER,
    ROLE_IT_MANAGER,
    ROLE_PRINCIPAL,
    ROLE_STUDENT,
    ROLE_SUBJECT_TEACHER,
    ROLE_VP,
)
from apps.accounts.forms import _instructional_class_id_for_selection
from apps.accounts.models import Role, StaffProfile, StudentProfile, User
from apps.academics.models import (
    AcademicClass,
    AcademicSession,
    ClassSubject,
    FormTeacherAssignment,
    StudentClassEnrollment,
    Subject,
    Term,
)
from apps.audit.models import AuditEvent
from apps.setup_wizard.models import SetupStateCode, SystemSetupState


class StageOneAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.roles = {}
        for code, label in Role._meta.get_field("code").choices:
            cls.roles[code], _ = Role.objects.get_or_create(code=code, defaults={"name": label})

        cls.student = User.objects.create_user(
            username="student1",
            password="Password123!",
            primary_role=cls.roles[ROLE_STUDENT],
            must_change_password=False,
        )
        cls.subject_teacher = User.objects.create_user(
            username="teacher1",
            password="Password123!",
            primary_role=cls.roles[ROLE_SUBJECT_TEACHER],
            must_change_password=False,
            email="teacher1@gmail.com",
        )
        StaffProfile.objects.create(user=cls.subject_teacher, staff_id="NDGAK/SNB/00000001")
        cls.bursar = User.objects.create_user(
            username="bursar1",
            password="Password123!",
            primary_role=cls.roles[ROLE_BURSAR],
            must_change_password=False,
        )
        cls.it_manager = User.objects.create_user(
            username="it1",
            password="Password123!",
            primary_role=cls.roles[ROLE_IT_MANAGER],
            must_change_password=False,
        )
        cls.principal = User.objects.create_user(
            username="principal1",
            password="Password123!",
            primary_role=cls.roles[ROLE_PRINCIPAL],
            must_change_password=False,
        )

    def test_student_cannot_access_staff_portal(self):
        client = Client()
        client.force_login(self.student)
        response = client.get(reverse("dashboard:staff-portal"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "http://student.ndgakuje.org/")
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="PERMISSION_DENIED_REDIRECT",
                actor=self.student,
            ).exists()
        )

    def test_subject_teacher_cannot_access_finance_or_it_pages(self):
        client = Client()
        client.force_login(self.subject_teacher)
        finance_response = client.get(reverse("dashboard:bursar-portal"))
        it_response = client.get(reverse("dashboard:it-portal"))
        self.assertEqual(finance_response.status_code, 302)
        self.assertEqual(finance_response.url, "http://staff.ndgakuje.org/")
        self.assertEqual(it_response.status_code, 302)
        self.assertEqual(it_response.url, "http://staff.ndgakuje.org/")

    def test_audit_view_restricted_to_it_and_principal(self):
        teacher_client = Client()
        teacher_client.force_login(self.subject_teacher)
        denied_response = teacher_client.get(reverse("audit:event-list"))
        self.assertEqual(denied_response.status_code, 302)
        self.assertEqual(denied_response.url, "http://staff.ndgakuje.org/")

        principal_client = Client()
        principal_client.force_login(self.principal)
        allowed_response = principal_client.get(reverse("audit:event-list"))
        self.assertEqual(allowed_response.status_code, 200)

    def test_login_success_is_logged(self):
        client = Client()
        login_response = client.post(
            reverse("accounts:login"),
            {"username": "student1", "password": "Password123!"},
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertContains(login_response, "http://student.ndgakuje.org/")
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="LOGIN_SUCCESS",
                actor=self.student,
            ).exists()
        )

    def test_login_failure_is_logged(self):
        client = Client()
        client.post(
            reverse("accounts:login"),
            {"username": "student1", "password": "Wrong123!"},
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="LOGIN_FAILED",
                actor_identifier="student1",
            ).exists()
        )

    def test_logout_get_is_allowed(self):
        client = Client()
        client.force_login(self.student)
        response = client.get(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "http://testserver/auth/login/?audience=student")

    def test_normal_user_password_change_limit_is_enforced(self):
        user = self.student
        user.password_changed_count = 1
        user.save(update_fields=["password_changed_count"])
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse("accounts:password-change"),
            {
                "old_password": "Password123!",
                "new_password1": "Password456!",
                "new_password2": "Password456!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="PASSWORD_CHANGE_DENIED",
                actor=user,
            ).exists()
        )

    def test_principal_can_change_password_multiple_times(self):
        user = self.principal
        user.password_changed_count = 3
        user.set_password("Password123!")
        user.save(update_fields=["password_changed_count", "password"])
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse("accounts:password-change"),
            {
                "old_password": "Password123!",
                "new_password1": "Password456!",
                "new_password2": "Password456!",
            },
        )
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.password_changed_count, 4)

    def test_it_manager_can_issue_login_code(self):
        client = Client()
        client.force_login(self.it_manager)
        response = client.post(
            reverse("accounts:it-reset-credentials"),
            {
                "target_user": str(self.student.id),
                "reset_mode": "LOGIN_CODE",
                "temporary_password": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        generated_code = response.context["generated_code"]
        self.assertTrue(bool(generated_code))
        self.student.refresh_from_db()
        self.assertTrue(bool(self.student.login_code_hash))
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="CREDENTIALS_RESET",
                actor=self.it_manager,
            ).exists()
        )
        login_client = Client()
        login_response = login_client.post(
            reverse("accounts:login"),
            {
                "username": "student1",
                "password": "",
                "login_code": generated_code,
            },
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertContains(login_response, "http://student.ndgakuje.org/")

    def test_it_manager_can_register_staff_and_student_accounts(self):
        session = AcademicSession.objects.create(name="2025/2026")
        term = Term.objects.create(session=session, name="FIRST")
        academic_class = AcademicClass.objects.create(code="JS1A", display_name="JS1A")
        subject = Subject.objects.create(name="Mathematics", code="MTH")
        ClassSubject.objects.create(academic_class=academic_class, subject=subject, is_active=True)
        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = session
        setup_state.current_term = term
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_manager)
        staff_response = client.post(
            reverse("accounts:it-staff-provisioning"),
            {
                "role_group": "STAFF",
                "first_name": "Grace",
                "last_name": "Obi",
                "email": "grace@ndga.local",
                "primary_role": str(self.roles[ROLE_SUBJECT_TEACHER].id),
                "phone_number": "08000000000",
                "teaching_loads": [str(ClassSubject.objects.get(academic_class=academic_class, subject=subject).id)],
            },
        )
        self.assertEqual(staff_response.status_code, 302)
        staff_user = User.objects.filter(first_name="Grace", last_name="Obi").first()
        self.assertIsNotNone(staff_user)
        self.assertTrue(StaffProfile.objects.filter(user=staff_user).exists())
        self.assertIn("@ndgakuje.org", staff_user.username)

        webcam_payload = "data:image/png;base64," + base64.b64encode(
            b"ndga-image-bytes"
        ).decode("utf-8")
        student_response = client.post(
            reverse("accounts:it-student-provisioning"),
            {
                "first_name": "Amara",
                "last_name": "Ife",
                "email": "amara@ndga.local",
                "date_of_birth": "2012-10-10",
                "admission_date": "2026-01-10",
                "gender": "F",
                "guardian_name": "Mother One",
                "guardian_phone": "08011111111",
                "guardian_email": "guardian@example.com",
                "address": "Kuje, Abuja",
                "state_of_origin": "FCT",
                "nationality": "Nigerian",
                "current_class": str(academic_class.id),
                "offered_subjects": [str(subject.id)],
                "webcam_image_data": webcam_payload,
            },
        )
        self.assertEqual(student_response.status_code, 302)
        student_user = User.objects.filter(first_name="Amara", last_name="Ife").first()
        self.assertIsNotNone(student_user)
        self.assertEqual(student_user.primary_role.code, ROLE_STUDENT)
        profile = StudentProfile.objects.get(user=student_user)
        self.assertTrue(profile.student_number.startswith("NDGAK/"))
        self.assertTrue(
            StudentClassEnrollment.objects.filter(
                student=student_user,
                session=session,
                academic_class=academic_class,
                is_active=True,
            ).exists()
        )

    def test_student_registration_accepts_manual_admission_number(self):
        session = AcademicSession.objects.create(name="2025/2026")
        term = Term.objects.create(session=session, name="FIRST")
        academic_class = AcademicClass.objects.create(code="JS1B", display_name="JS1B")
        subject = Subject.objects.create(name="English", code="ENG")
        ClassSubject.objects.create(academic_class=academic_class, subject=subject, is_active=True)
        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = session
        setup_state.current_term = term
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_manager)
        webcam_payload = "data:image/png;base64," + base64.b64encode(
            b"manual-admission-image"
        ).decode("utf-8")
        response = client.post(
            reverse("accounts:it-student-provisioning"),
            {
                "student_number": "ndgak/25/422",
                "first_name": "Manual",
                "last_name": "Admission",
                "date_of_birth": "2011-10-10",
                "admission_date": "2025-09-15",
                "gender": "F",
                "guardian_name": "Parent Manual",
                "guardian_phone": "08022222222",
                "guardian_email": "manual-parent@example.com",
                "address": "Kuje",
                "state_of_origin": "FCT",
                "nationality": "Nigerian",
                "current_class": str(academic_class.id),
                "offered_subjects": [str(subject.id)],
                "webcam_image_data": webcam_payload,
            },
        )
        self.assertEqual(response.status_code, 302)
        student_user = User.objects.get(first_name="Manual", last_name="Admission")
        profile = StudentProfile.objects.get(user=student_user)
        self.assertEqual(profile.student_number, "NDGAK/25/422")
        creds = client.session.get("generated_student_credentials", {})
        self.assertEqual(creds.get("student_number"), "NDGAK/25/422")
        self.assertEqual(creds.get("password"), "NDGAK/422")

    def test_student_auto_number_uses_global_last_serial_with_current_session_year(self):
        session = AcademicSession.objects.create(name="2026/2027")
        term = Term.objects.create(session=session, name="FIRST")
        academic_class = AcademicClass.objects.create(code="JS2B", display_name="JS2B")
        subject = Subject.objects.create(name="Basic Science", code="BSC")
        ClassSubject.objects.create(academic_class=academic_class, subject=subject, is_active=True)
        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = session
        setup_state.current_term = term
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

        existing_one = User.objects.create_user(
            username="legacy1@ndgakuje.org",
            password="Password123!",
            primary_role=self.roles[ROLE_STUDENT],
            must_change_password=False,
        )
        existing_two = User.objects.create_user(
            username="legacy2@ndgakuje.org",
            password="Password123!",
            primary_role=self.roles[ROLE_STUDENT],
            must_change_password=False,
        )
        StudentProfile.objects.create(
            user=existing_one,
            student_number="NDGAK/24/300",
            guardian_email="legacy1@example.com",
        )
        StudentProfile.objects.create(
            user=existing_two,
            student_number="NDGAK/25/422",
            guardian_email="legacy2@example.com",
        )

        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_manager)
        webcam_payload = "data:image/png;base64," + base64.b64encode(
            b"auto-sequence-image"
        ).decode("utf-8")
        response = client.post(
            reverse("accounts:it-student-provisioning"),
            {
                "first_name": "Auto",
                "last_name": "Sequence",
                "date_of_birth": "2011-11-11",
                "admission_date": "2026-01-20",
                "gender": "F",
                "guardian_name": "Parent Auto",
                "guardian_phone": "08033333333",
                "guardian_email": "auto-parent@example.com",
                "address": "Kuje",
                "state_of_origin": "FCT",
                "nationality": "Nigerian",
                "current_class": str(academic_class.id),
                "offered_subjects": [str(subject.id)],
                "webcam_image_data": webcam_payload,
            },
        )
        self.assertEqual(response.status_code, 302)
        student_user = User.objects.get(first_name="Auto", last_name="Sequence")
        profile = StudentProfile.objects.get(user=student_user)
        self.assertEqual(profile.student_number, "NDGAK/26/423")
        creds = client.session.get("generated_student_credentials", {})
        self.assertEqual(creds.get("student_number"), "NDGAK/26/423")
        self.assertEqual(creds.get("password"), "NDGAK/423")

    def test_staff_registration_accepts_manual_staff_id(self):
        session = AcademicSession.objects.create(name="2025/2026")
        term = Term.objects.create(session=session, name="FIRST")
        academic_class = AcademicClass.objects.create(code="JS3A", display_name="JS3A")
        subject = Subject.objects.create(name="Agriculture", code="AGR")
        mapped = ClassSubject.objects.create(academic_class=academic_class, subject=subject, is_active=True)
        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = session
        setup_state.current_term = term
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_manager)
        response = client.post(
            reverse("accounts:it-staff-provisioning"),
            {
                "role_group": "STAFF",
                "first_name": "Manual",
                "last_name": "Staff",
                "email": "manual-staff@example.com",
                "primary_role": str(self.roles[ROLE_SUBJECT_TEACHER].id),
                "staff_id": "ndgak/stf/017",
                "phone_number": "08044444444",
                "teaching_loads": [str(mapped.id)],
            },
        )
        self.assertEqual(response.status_code, 302)
        staff_user = User.objects.get(first_name="Manual", last_name="Staff")
        profile = StaffProfile.objects.get(user=staff_user)
        self.assertEqual(profile.staff_id, "NDGAK/STF/017")
        creds = client.session.get("generated_staff_credentials", {})
        self.assertEqual(creds.get("staff_id"), "NDGAK/STF/017")
        self.assertEqual(creds.get("password"), "NDGAK/017")

    def test_singleton_staff_roles_use_fixed_login_ids_and_passwords(self):
        session = AcademicSession.objects.create(name="2025/2026")
        term = Term.objects.create(session=session, name="FIRST")
        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = session
        setup_state.current_term = term
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_manager)

        cases = [
            (ROLE_VP, "ADMIN", "Vice", "Principal", "vp@ndgakuje.org", "NDGAK/VP", "admin/vp"),
            (ROLE_PRINCIPAL, "ADMIN", "School", "Principal", "principal@ndgakuje.org", "NDGAK/PRINCIPAL", "admin"),
            (ROLE_BURSAR, "ADMIN", "Main", "Bursar", "bursar@ndgakuje.org", "NDGAK/BURSAR", "bursar1804"),
            (ROLE_DEAN, "STAFF", "Senior", "Dean", "ndgak/staff/dean", "NDGAK/STAFF/DEAN", "NDGAK/DEAN"),
        ]

        for role_code, role_group, first_name, last_name, expected_username, expected_staff_id, expected_password in cases:
            response = client.post(
                reverse("accounts:it-staff-provisioning"),
                {
                    "role_group": role_group,
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": f"{first_name.lower()}@example.com",
                    "primary_role": str(self.roles[role_code].id),
                    "phone_number": "08055555555",
                },
            )
            self.assertEqual(response.status_code, 302)
            staff_user = User.objects.get(first_name=first_name, last_name=last_name)
            profile = StaffProfile.objects.get(user=staff_user)
            self.assertEqual(staff_user.username, expected_username)
            self.assertEqual(profile.staff_id, expected_staff_id)
            self.assertTrue(staff_user.check_password(expected_password))

        dean_user = User.objects.get(first_name="Senior", last_name="Dean")
        self.assertNotEqual(dean_user.username, "dean@ndgakuje.org")

    def test_staff_profile_upload_blocks_dangerous_file_types(self):
        session = AcademicSession.objects.create(name="2026/2027")
        term = Term.objects.create(session=session, name="FIRST")
        academic_class = AcademicClass.objects.create(code="JS2A", display_name="JS2A")
        subject = Subject.objects.create(name="English", code="ENG")
        mapped = ClassSubject.objects.create(
            academic_class=academic_class,
            subject=subject,
            is_active=True,
        )
        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = session
        setup_state.current_term = term
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_manager)
        bad_upload = SimpleUploadedFile(
            "malware.exe",
            b"MZ\x90\x00\x03\x00\x00\x00",
            content_type="application/octet-stream",
        )
        response = client.post(
            reverse("accounts:it-staff-provisioning"),
            {
                "role_group": "STAFF",
                "first_name": "Danger",
                "last_name": "File",
                "email": "danger@example.com",
                "primary_role": str(self.roles[ROLE_SUBJECT_TEACHER].id),
                "phone_number": "08000000000",
                "teaching_loads": [str(mapped.id)],
                "profile_photo": bad_upload,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload a valid image")

    def test_non_it_cannot_access_it_user_provisioning(self):
        client = Client(HTTP_HOST="staff.ndgakuje.org")
        client.force_login(self.subject_teacher)
        response = client.get(reverse("accounts:it-user-provisioning"))
        self.assertEqual(response.status_code, 302)
        staff_page = client.get(reverse("accounts:it-staff-provisioning"))
        student_page = client.get(reverse("accounts:it-student-provisioning"))
        self.assertEqual(staff_page.status_code, 302)
        self.assertEqual(student_page.status_code, 302)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_reset_via_email_code_works_with_staff_id(self):
        client = Client(HTTP_HOST="staff.ndgakuje.org")
        request_response = client.post(
            reverse("accounts:password-reset-request"),
            {"login_id": "NDGAK/SNB/00000001"},
        )
        self.assertEqual(request_response.status_code, 302)
        self.assertEqual(request_response.url, reverse("accounts:password-reset-confirm"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("NDGA password reset code is:", mail.outbox[0].body)
        code = mail.outbox[0].body.split("NDGA password reset code is:")[1].splitlines()[0].strip()

        confirm_response = client.post(
            reverse("accounts:password-reset-confirm"),
            {
                "reset_code": code,
                "new_password1": "NewPassword987!",
                "new_password2": "NewPassword987!",
            },
        )
        self.assertEqual(confirm_response.status_code, 302)
        self.assertEqual(confirm_response.url, reverse("accounts:login"))
        self.subject_teacher.refresh_from_db()
        self.assertTrue(self.subject_teacher.check_password("NewPassword987!"))

    def test_student_self_service_password_reset_is_blocked(self):
        student_profile = StudentProfile.objects.create(
            user=self.student,
            student_number="NDGAK/26/001",
            guardian_email="parent@example.com",
        )
        self.student.email = student_profile.guardian_email
        self.student.save(update_fields=["email"])
        client = Client(HTTP_HOST="student.ndgakuje.org")
        response = client.post(
            reverse("accounts:password-reset-request"),
            {"login_id": student_profile.student_number},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Student password reset is managed by IT Manager only.")

    def test_mobile_capture_session_submit_and_status_flow(self):
        manager_client = Client(HTTP_HOST="it.ndgakuje.org")
        manager_client.force_login(self.it_manager)

        session_response = manager_client.post(reverse("accounts:it-mobile-capture-session"))
        self.assertEqual(session_response.status_code, 200)
        payload = session_response.json()
        self.assertTrue(payload.get("ok"))
        token = payload.get("token")
        self.assertTrue(token)

        tiny_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7+3nQAAAAASUVORK5CYII="
        )
        upload = SimpleUploadedFile("capture.png", tiny_png, content_type="image/png")
        submit_response = Client(HTTP_HOST="it.ndgakuje.org").post(
            reverse("accounts:mobile-capture-submit", kwargs={"token": token}),
            {"photo": upload},
        )
        self.assertEqual(submit_response.status_code, 200)
        self.assertTrue(submit_response.json().get("ok"))

        status_response = manager_client.get(
            reverse("accounts:it-mobile-capture-status"),
            {"token": token},
        )
        self.assertEqual(status_response.status_code, 200)
        status_payload = status_response.json()
        self.assertTrue(status_payload.get("ok"))
        self.assertTrue(status_payload.get("ready"))
        self.assertIn("data:image/png;base64,", status_payload.get("data_url", ""))


    def test_staff_id_edit_resets_password_to_new_serial(self):
        session = AcademicSession.objects.create(name="2027/2028")
        term = Term.objects.create(session=session, name="FIRST")
        academic_class = AcademicClass.objects.create(code="JS2", display_name="JS2")
        subject = Subject.objects.create(name="Basic Science", code="BSC-EDIT")
        mapped = ClassSubject.objects.create(academic_class=academic_class, subject=subject, is_active=True)
        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = session
        setup_state.current_term = term
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

        staff_user = User.objects.create_user(
            username="edit-staff@ndgakuje.org",
            password="OldPassword123!",
            primary_role=self.roles[ROLE_SUBJECT_TEACHER],
            first_name="Edit",
            last_name="Staff",
            must_change_password=False,
        )
        StaffProfile.objects.create(user=staff_user, staff_id="NDGAK/SNB/017")

        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_manager)
        response = client.post(
            reverse("accounts:it-staff-edit", args=[staff_user.id]),
            {
                "staff_id": "NDGAK/SNB/020",
                "first_name": "Edit",
                "last_name": "Staff",
                "email": "edit-staff@example.com",
                "primary_role": str(self.roles[ROLE_SUBJECT_TEACHER].id),
                "designation": "",
                "phone_number": "08099999999",
                "employment_status": "ACTIVE",
                "lifecycle_note": "",
                "form_class_assignment": "",
                "teaching_loads": [str(mapped.id)],
            },
        )
        self.assertEqual(response.status_code, 302)
        staff_user.refresh_from_db()
        profile = StaffProfile.objects.get(user=staff_user)
        self.assertEqual(profile.staff_id, "NDGAK/SNB/020")
        self.assertTrue(staff_user.check_password("NDGAK/020"))

    def test_student_edit_allows_blank_guardian_email(self):
        session = AcademicSession.objects.create(name="2028/2029")
        term = Term.objects.create(session=session, name="FIRST")
        level_class = AcademicClass.objects.create(code="JS1X", display_name="JS1X")
        arm_class = AcademicClass.objects.create(
            code="JS1XBLUE",
            display_name="JS1X BLUE",
            base_class=level_class,
            arm_name="BLUE",
        )
        subject = Subject.objects.create(name="English Language X", code="ENG-EDIT-X")
        ClassSubject.objects.create(academic_class=level_class, subject=subject, is_active=True)
        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = session
        setup_state.current_term = term
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

        student_user = User.objects.create_user(
            username="blank-email-student@ndgakuje.org",
            password="OldPassword123!",
            primary_role=self.roles[ROLE_STUDENT],
            first_name="Blank",
            last_name="Email",
            must_change_password=False,
        )
        StudentProfile.objects.create(
            user=student_user,
            student_number="NDGAK/25/600",
            guardian_email="parent@example.com",
        )
        StudentClassEnrollment.objects.create(
            student=student_user,
            session=session,
            academic_class=arm_class,
            is_active=True,
        )

        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_manager)
        response = client.post(
            reverse("accounts:it-student-edit", args=[student_user.id]),
            {
                "first_name": "Blank",
                "last_name": "Email",
                "middle_name": "",
                "student_number": "NDGAK/25/600",
                "date_of_birth": "",
                "admission_date": "",
                "gender": "F",
                "guardian_name": "",
                "guardian_phone": "",
                "guardian_email": "",
                "address": "Kuje",
                "state_of_origin": "FCT",
                "nationality": "Nigerian",
                "lifecycle_state": "ACTIVE",
                "lifecycle_note": "",
                "medical_notes": "",
                "disciplinary_notes": "",
                "current_class": str(arm_class.id),
                "subject_category": "",
                "offered_subjects": [str(subject.id)],
            },
        )
        self.assertEqual(response.status_code, 302)
        student_user.refresh_from_db()
        profile = StudentProfile.objects.get(user=student_user)
        self.assertEqual(student_user.email, "")
        self.assertEqual(profile.guardian_email, "")

    def test_it_student_detail_renders_without_current_enrollment(self):
        session = AcademicSession.objects.create(name="2029/2030")
        term = Term.objects.create(session=session, name="FIRST")
        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = session
        setup_state.current_term = term
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

        student_user = User.objects.create_user(
            username="detail-no-enrollment@ndgakuje.org",
            password="Password123!",
            primary_role=self.roles[ROLE_STUDENT],
            first_name="No",
            last_name="Enrollment",
            must_change_password=False,
        )
        StudentProfile.objects.create(
            user=student_user,
            student_number="NDGAK/29/777",
            guardian_email="guardian@example.com",
        )

        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_manager)
        response = client.get(reverse("accounts:it-student-detail", args=[student_user.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No photo yet")

    def test_student_number_edit_resets_password_to_new_serial(self):
        session = AcademicSession.objects.create(name="2028/2029")
        term = Term.objects.create(session=session, name="FIRST")
        level_class = AcademicClass.objects.create(code="JS1", display_name="JS1")
        arm_class = AcademicClass.objects.create(
            code="JS1BLUE",
            display_name="JS1 BLUE",
            base_class=level_class,
            arm_name="BLUE",
        )
        subject = Subject.objects.create(name="English Language", code="ENG-EDIT")
        ClassSubject.objects.create(academic_class=level_class, subject=subject, is_active=True)
        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = session
        setup_state.current_term = term
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

        student_user = User.objects.create_user(
            username="edit-student@ndgakuje.org",
            password="OldPassword123!",
            primary_role=self.roles[ROLE_STUDENT],
            first_name="Edit",
            last_name="Student",
            must_change_password=False,
        )
        StudentProfile.objects.create(
            user=student_user,
            student_number="NDGAK/25/422",
            guardian_email="parent@example.com",
        )
        StudentClassEnrollment.objects.create(
            student=student_user,
            session=session,
            academic_class=arm_class,
            is_active=True,
        )

        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_manager)
        response = client.post(
            reverse("accounts:it-student-edit", args=[student_user.id]),
            {
                "first_name": "Edit",
                "last_name": "Student",
                "middle_name": "",
                "student_number": "NDGAK/25/500",
                "date_of_birth": "",
                "admission_date": "",
                "gender": "F",
                "guardian_name": "",
                "guardian_phone": "08088888888",
                "guardian_email": "parent@example.com",
                "address": "Kuje",
                "state_of_origin": "FCT",
                "nationality": "Nigerian",
                "lifecycle_state": "ACTIVE",
                "lifecycle_note": "",
                "medical_notes": "",
                "disciplinary_notes": "",
                "current_class": str(arm_class.id),
                "subject_category": "",
                "offered_subjects": [str(subject.id)],
            },
        )
        self.assertEqual(response.status_code, 302)
        student_user.refresh_from_db()
        profile = StudentProfile.objects.get(user=student_user)
        self.assertEqual(profile.student_number, "NDGAK/25/500")
        self.assertTrue(student_user.check_password("NDGAK/500"))

    def test_import_school_register_command_creates_minimal_accounts(self):
        session = AcademicSession.objects.create(name="2025/2026")
        term = Term.objects.create(session=session, name="FIRST")
        level_class = AcademicClass.objects.create(code="JS1", display_name="JS1")
        arm_class = AcademicClass.objects.create(
            code="JS1BLUE",
            display_name="JS1 BLUE",
            base_class=level_class,
            arm_name="BLUE",
        )
        subject = Subject.objects.create(name="Mathematics", code="MTH-IMPORT")
        ClassSubject.objects.create(academic_class=level_class, subject=subject, is_active=True)
        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = session
        setup_state.current_term = term
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "student.txt").write_text(
                "S/N \u2014 Student Name \u2014 Admission No \u2014 Class\n"
                "JS1 BLUE\n\n"
                "1 \u2014 Alozie Chiziterem Christine \u2014 NDGAK/25/381 \u2014 JS1 BLUE\n"
                "2 \u2014 Beta Example Person \u2014 NIL \u2014 JS1 BLUE\n",
                encoding="utf-8",
            )
            document = Document()
            table = document.add_table(rows=2, cols=4)
            table.rows[0].cells[0].text = "No"
            table.rows[0].cells[1].text = "Teacher Name"
            table.rows[0].cells[2].text = "Subject Taken"
            table.rows[0].cells[3].text = "Class"
            table.rows[1].cells[0].text = "1"
            table.rows[1].cells[1].text = "Ukairo Juliana"
            table.rows[1].cells[2].text = "Mathematics"
            table.rows[1].cells[3].text = "JS1"
            document.save(temp_path / "SUBJECT TEACHERS.docx")

            output = StringIO()
            call_command("import_school_register", source_dir=str(temp_path), stdout=output)

        imported_student = User.objects.get(last_name="Alozie", first_name="Chiziterem")
        imported_student_profile = StudentProfile.objects.get(user=imported_student)
        self.assertEqual(imported_student_profile.student_number, "NDGAK/25/381")
        self.assertTrue(imported_student.check_password("NDGAK/381"))
        self.assertTrue(
            StudentClassEnrollment.objects.filter(
                student=imported_student,
                session=session,
                academic_class=arm_class,
                is_active=True,
            ).exists()
        )

        nil_student = User.objects.get(last_name="Beta", first_name="Example")
        nil_profile = StudentProfile.objects.get(user=nil_student)
        self.assertEqual(nil_profile.student_number, "NDGAK/25/382")
        self.assertEqual(nil_profile.middle_name, "Person")
        self.assertTrue(nil_student.check_password("NDGAK/382"))

        imported_staff = User.objects.get(last_name="Ukairo", first_name="Juliana")
        imported_staff_profile = StaffProfile.objects.get(user=imported_staff)
        self.assertEqual(imported_staff_profile.staff_id, "NDGAK/STAFF/001")
        self.assertTrue(imported_staff.check_password("NDGAK/001"))


@override_settings(
    ALLOWED_HOSTS=["localhost", "testserver", "ndgakuje.org", ".ndgakuje.org", ".ndga.local"],
)
class PortalLogoutRedirectTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        role, _ = Role.objects.get_or_create(code=ROLE_STUDENT, defaults={"name": "Student"})
        cls.student = User.objects.create_user(
            username="student-logout",
            password="Password123!",
            primary_role=role,
            must_change_password=False,
        )

    def test_logout_defaults_to_student_entry(self):
        client = Client()
        client.force_login(self.student)

        response = client.get(reverse("accounts:logout"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "http://testserver/auth/login/?audience=student")

    @override_settings(NDGA_LOCAL_SIMPLE_HOST_MODE=True)
    def test_logout_keeps_cbt_login_target_on_local_host(self):
        client = Client(HTTP_HOST="localhost")
        client.force_login(self.student)
        session = client.session
        session["last_authenticated_portal"] = "cbt"
        session.save()

        response = client.get(reverse("accounts:logout"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "http://localhost/auth/login/?audience=cbt")

    @override_settings(NDGA_LOCAL_SIMPLE_HOST_MODE=True)
    def test_authenticated_user_can_open_fresh_cbt_login_page(self):
        client = Client(HTTP_HOST="localhost")
        client.force_login(self.student)

        response = client.get("/auth/login/?audience=cbt&fresh=1&next=/portal/cbt/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Entry Channel: cbt")


class DefaultPortalAccountBootstrapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.roles = {}
        for code, label in Role._meta.get_field("code").choices:
            cls.roles[code], _ = Role.objects.get_or_create(code=code, defaults={"name": label})

    def test_command_creates_fixed_portal_accounts(self):
        output = StringIO()
        call_command("ensure_default_portal_accounts", stdout=output)

        cases = [
            (ROLE_VP, "vp@ndgakuje.org", "NDGAK/VP", "admin/vp"),
            (ROLE_PRINCIPAL, "principal@ndgakuje.org", "NDGAK/PRINCIPAL", "admin"),
            (ROLE_BURSAR, "bursar@ndgakuje.org", "NDGAK/BURSAR", "bursar1804"),
        ]
        for role_code, expected_username, expected_staff_id, expected_password in cases:
            user = User.objects.get(primary_role=self.roles[role_code])
            self.assertEqual(user.username, expected_username)
            self.assertTrue(user.check_password(expected_password))
            self.assertEqual(user.staff_profile.staff_id, expected_staff_id)

    def test_command_preserves_existing_password_without_sync_flag(self):
        vp_user = User.objects.create_user(
            username="legacy-vp",
            password="CustomPass123!",
            primary_role=self.roles[ROLE_VP],
            must_change_password=False,
        )
        StaffProfile.objects.create(user=vp_user, staff_id="LEGACY-VP")

        call_command("ensure_default_portal_accounts")

        vp_user.refresh_from_db()
        self.assertEqual(vp_user.username, "vp@ndgakuje.org")
        self.assertTrue(vp_user.check_password("CustomPass123!"))
        self.assertEqual(vp_user.staff_profile.staff_id, "NDGAK/VP")

    def test_command_can_sync_passwords_on_existing_accounts(self):
        principal_user = User.objects.create_user(
            username="principal@ndgakuje.org",
            password="LegacyAdmin123!",
            primary_role=self.roles[ROLE_PRINCIPAL],
            must_change_password=False,
        )
        StaffProfile.objects.create(user=principal_user, staff_id="NDGAK/PRINCIPAL")

        call_command("ensure_default_portal_accounts", sync_passwords=True)

        principal_user.refresh_from_db()
        self.assertTrue(principal_user.check_password("admin"))


class OperationalPortalProvisioningTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.roles = {}
        for code, label in Role._meta.get_field("code").choices:
            cls.roles[code], _ = Role.objects.get_or_create(code=code, defaults={"name": label})

        cls.session = AcademicSession.objects.create(name="2025/2026")
        Term.objects.create(session=cls.session, name="THIRD")
        cls.js1 = AcademicClass.objects.create(code="JS1", display_name="JS1")
        cls.ss3 = AcademicClass.objects.create(code="SS3", display_name="SS3")

        cls.dean_source = User.objects.create_user(
            username="gabriel@ndgakuje.org",
            password="Password123!",
            primary_role=cls.roles[ROLE_DEAN],
            first_name="Emmanuel",
            last_name="Gabriel",
            must_change_password=False,
        )
        cls.dean_source.secondary_roles.add(cls.roles[ROLE_FORM_TEACHER])
        StaffProfile.objects.create(user=cls.dean_source, staff_id="NDGAK/STAFF/002")

        cls.vp_source = User.objects.create_user(
            username="vp@ndgakuje.org",
            password="Password123!",
            primary_role=cls.roles[ROLE_VP],
            first_name="Vice",
            last_name="Principal",
            must_change_password=False,
        )
        cls.vp_source.secondary_roles.add(cls.roles[ROLE_FORM_TEACHER])
        StaffProfile.objects.create(user=cls.vp_source, staff_id="NDGAK/VP")

        FormTeacherAssignment.objects.create(
            teacher=cls.vp_source,
            academic_class=cls.js1,
            session=cls.session,
            is_active=True,
        )
        FormTeacherAssignment.objects.create(
            teacher=cls.dean_source,
            academic_class=cls.ss3,
            session=cls.session,
            is_active=True,
        )

    def test_command_creates_dedicated_dean_and_form_accounts_and_cleans_source_roles(self):
        call_command("provision_operational_portals")

        dean_portal = User.objects.get(primary_role=self.roles[ROLE_DEAN])
        self.assertEqual(dean_portal.staff_profile.staff_id, "NDGAK/STAFF/DEAN")
        self.assertTrue(dean_portal.check_password("NDGAK/DEAN"))

        js1_portal = User.objects.get(staff_profile__staff_id="NDGAK/STAFF/JS1")
        self.assertEqual(js1_portal.primary_role, self.roles[ROLE_FORM_TEACHER])
        self.assertTrue(js1_portal.check_password("NDGAK/JS1"))

        ss3_portal = User.objects.get(staff_profile__staff_id="NDGAK/STAFF/SS3")
        self.assertEqual(ss3_portal.primary_role, self.roles[ROLE_FORM_TEACHER])
        self.assertTrue(ss3_portal.check_password("NDGAK/SS3"))

        self.dean_source.refresh_from_db()
        self.vp_source.refresh_from_db()

        self.assertEqual(self.dean_source.primary_role, self.roles[ROLE_SUBJECT_TEACHER])
        self.assertNotIn(ROLE_DEAN, self.dean_source.get_all_role_codes())
        self.assertNotIn(ROLE_FORM_TEACHER, self.dean_source.get_all_role_codes())
        self.assertNotIn(ROLE_FORM_TEACHER, self.vp_source.get_all_role_codes())

        js1_assignment = FormTeacherAssignment.objects.get(
            academic_class=self.js1,
            session=self.session,
            is_active=True,
        )
        ss3_assignment = FormTeacherAssignment.objects.get(
            academic_class=self.ss3,
            session=self.session,
            is_active=True,
        )
        self.assertEqual(js1_assignment.teacher_id, js1_portal.id)
        self.assertEqual(ss3_assignment.teacher_id, ss3_portal.id)



@override_settings(
    ALLOWED_HOSTS=[
        "localhost",
        "127.0.0.1",
        "[::1]",
        "testserver",
        "ndgakuje.org",
        ".ndgakuje.org",
        ".ndga.local",
    ],
    CSRF_TRUSTED_ORIGINS=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://ndgakuje.org:8000",
        "http://ndgakuje.org",
        "http://*.ndgakuje.org",
        "https://ndgakuje.org",
        "https://*.ndgakuje.org",
    ],
)
class StageNineteenSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.role_it = Role.objects.get(code=ROLE_IT_MANAGER)
        cls.role_student = Role.objects.get(code=ROLE_STUDENT)
        cls.it_user = User.objects.create_user(
            username="security-it",
            password="Password123!",
            primary_role=cls.role_it,
            must_change_password=False,
        )
        cls.student_user = User.objects.create_user(
            username="security-student",
            password="Password123!",
            primary_role=cls.role_student,
            must_change_password=False,
        )
        session = AcademicSession.objects.create(name="2032/2033")
        term = Term.objects.create(session=session, name="FIRST")
        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = session
        setup_state.current_term = term
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

    def test_security_headers_are_applied(self):
        client = Client(HTTP_HOST="ndgakuje.org")
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Content-Security-Policy", response)
        self.assertIn("Permissions-Policy", response)
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    @override_settings(
        RATE_LIMIT_ENABLED=True,
        RATE_LIMIT_RULES=(
            {
                "name": "auth_login_test",
                "path_prefix": "/auth/login/",
                "methods": ("POST",),
                "scope": "ip",
                "limit": 2,
                "window_seconds": 120,
            },
        ),
    )
    def test_login_rate_limit_blocks_excess_attempts(self):
        cache.clear()
        client = Client(HTTP_HOST="student.ndgakuje.org")
        first = client.post(
            "/auth/login/?audience=student",
            {"username": "security-student", "password": "wrong-password"},
        )
        second = client.post(
            "/auth/login/?audience=student",
            {"username": "security-student", "password": "wrong-password"},
        )
        third = client.post(
            "/auth/login/?audience=student",
            {"username": "security-student", "password": "wrong-password"},
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(third.status_code, 429)

    def test_session_control_post_requires_csrf(self):
        client = Client(HTTP_HOST="it.ndgakuje.org", enforce_csrf_checks=True)
        client.force_login(self.it_user)
        response = client.post(
            "/setup/session-term/",
            {"action": "end-term", "confirm_end_term": "on"},
        )
        self.assertEqual(response.status_code, 403)

    def test_login_post_without_csrf_redirects_to_fresh_login_page(self):
        client = Client(HTTP_HOST="staff.ndgakuje.org", enforce_csrf_checks=True)
        response = client.post(
            "/auth/login/?audience=staff",
            {"username": "security-student", "password": "Password123!"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/auth/login/?audience=staff")


    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_privileged_roles_require_email_two_factor_verification(self):
        cache.clear()
        self.it_user.email = "security-it@ndgakuje.org"
        self.it_user.two_factor_enabled = True
        self.it_user.two_factor_email = "security-it@ndgakuje.org"
        self.it_user.save(update_fields=["email", "two_factor_enabled", "two_factor_email"])

        client = Client(HTTP_HOST="it.ndgakuje.org")
        response = client.post(
            "/auth/login/?audience=it",
            {"username": "security-it", "password": "Password123!"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:login-verify"))
        self.assertNotIn("_auth_user_id", client.session)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("privileged-login verification code is:", mail.outbox[0].body)
        code = mail.outbox[0].body.split("verification code is:")[1].splitlines()[0].strip()

        verify_response = client.post(
            reverse("accounts:login-verify"),
            {"verification_code": code},
        )
        self.assertEqual(verify_response.status_code, 302)
        self.assertEqual(verify_response.url, "http://it.ndgakuje.org/")
        self.assertEqual(int(client.session["_auth_user_id"]), self.it_user.id)
        self.assertTrue(
            AuditEvent.objects.filter(
                actor=self.it_user,
                event_type="LOGIN_2FA_VERIFIED",
            ).exists()
        )

    def test_privileged_roles_without_opt_in_two_factor_log_in_directly(self):
        cache.clear()
        client = Client(HTTP_HOST="it.ndgakuje.org")
        response = client.post(
            "/auth/login/?audience=it",
            {"username": "security-it", "password": "Password123!"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "http://it.ndgakuje.org/")
        self.assertEqual(int(client.session["_auth_user_id"]), self.it_user.id)


class StudentInstructionalClassSelectionTests(TestCase):
    def test_returns_instructional_class_id_for_arm_selection(self):
        base_class = AcademicClass.objects.create(code="SS1", display_name="SS1")
        arm_class = AcademicClass.objects.create(
            code="SS1A",
            display_name="SS1 A",
            base_class=base_class,
            arm_name="A",
        )

        self.assertEqual(_instructional_class_id_for_selection(arm_class.id), base_class.id)

    def test_accepts_academic_class_instance(self):
        academic_class = AcademicClass.objects.create(code="JSS1", display_name="JSS1")

        self.assertEqual(
            _instructional_class_id_for_selection(academic_class),
            academic_class.id,
        )

    def test_returns_none_for_invalid_selection(self):
        self.assertIsNone(_instructional_class_id_for_selection("missing"))
