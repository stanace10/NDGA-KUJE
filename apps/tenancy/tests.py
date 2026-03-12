from django.core import mail
from django.test import Client, RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.accounts.constants import ROLE_IT_MANAGER, ROLE_STUDENT, ROLE_SUBJECT_TEACHER
from apps.accounts.models import Role, User
from apps.setup_wizard.models import SetupStateCode, SystemSetupState
from apps.tenancy.utils import build_portal_url, current_portal_key


@override_settings(
    ALLOWED_HOSTS=[
        "localhost",
        "127.0.0.1",
        "[::1]",
        "172.20.10.3",
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
    FEATURE_FLAGS={
        "CBT_ENABLED": True,
        "ELECTION_ENABLED": True,
        "OFFLINE_MODE_ENABLED": True,
        "LOCKDOWN_ENABLED": True,
    },
)
class StageTwoHostRoutingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        role, _ = Role.objects.get_or_create(code=ROLE_STUDENT, defaults={"name": "Student"})
        role_it, _ = Role.objects.get_or_create(code=ROLE_IT_MANAGER, defaults={"name": "IT Manager"})
        role_teacher, _ = Role.objects.get_or_create(code=ROLE_SUBJECT_TEACHER, defaults={"name": "Subject Teacher"})
        cls.student = User.objects.create_user(
            username="student_host",
            password="Password123!",
            primary_role=role,
            must_change_password=False,
        )
        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.finalized_at = timezone.now()
        setup_state.save(update_fields=["state", "finalized_at", "updated_at"])
        cls.it_user = User.objects.create_user(
            username="it_host",
            password="Password123!",
            primary_role=role_it,
            must_change_password=False,
            email="it-host@ndgakuje.org",
        )
        cls.teacher_user = User.objects.create_user(
            username="teacher_host",
            password="Password123!",
            primary_role=role_teacher,
            must_change_password=False,
        )

    def test_landing_host_renders_landing_page(self):
        client = Client(HTTP_HOST="ndgakuje.org")
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Access NDGA Portal")

    def test_student_host_requires_login(self):
        client = Client(HTTP_HOST="student.ndgakuje.org")
        response = client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            "http://student.ndgakuje.org/auth/login/",
            response.url,
        )


    def test_localhost_staff_cbt_page_keeps_portal_shell(self):
        request = RequestFactory().get("/cbt/authoring/", HTTP_HOST="localhost:8000")
        request.user = self.teacher_user
        self.assertEqual(current_portal_key(request), "cbt")

    def test_localhost_it_cbt_authoring_routes_stay_in_it_portal(self):
        request = RequestFactory().get("/cbt/authoring/", HTTP_HOST="localhost:8000")
        request.user = self.it_user
        self.assertEqual(current_portal_key(request), "it")

    def test_localhost_student_cbt_runtime_uses_cbt_portal(self):
        request = RequestFactory().get("/cbt/exams/available/", HTTP_HOST="localhost:8000")
        request.user = self.student
        self.assertEqual(current_portal_key(request), "cbt")

    def test_localhost_election_routes_use_election_portal(self):
        request = RequestFactory().get("/elections/", HTTP_HOST="localhost:8000")
        request.user = self.teacher_user
        self.assertEqual(current_portal_key(request), "election")

    def test_private_ip_student_cbt_runtime_uses_cbt_portal(self):
        request = RequestFactory().get("/cbt/exams/available/", HTTP_HOST="172.20.10.3")
        request.user = self.student
        self.assertEqual(current_portal_key(request), "cbt")

    def test_localhost_it_cbt_activation_uses_it_portal(self):
        request = RequestFactory().get("/cbt/it/activation/", HTTP_HOST="localhost:8000")
        request.user = self.it_user
        self.assertEqual(current_portal_key(request), "it")
    def test_localhost_modal_login_urls_stay_on_localhost(self):
        client = Client(HTTP_HOST="localhost:8000")
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'href="http://localhost:8000/auth/login/?audience=staff"',
        )
        self.assertContains(
            response,
            'href="http://localhost:8000/auth/login/?audience=student"',
        )

    def test_public_domain_links_do_not_leak_dev_port(self):
        client = Client(HTTP_HOST="ndgakuje.org:8000")
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'href="http://staff.ndgakuje.org/auth/login/?audience=staff"',
        )
        self.assertNotContains(response, "staff.ndgakuje.org:8000")

    def test_public_secure_verification_links_use_live_domain(self):
        request = RequestFactory().get(
            "/portal/student/id-card/",
            HTTP_HOST="ndgakuje.org",
            secure=True,
        )
        request.user = self.student
        self.assertEqual(
            build_portal_url(request, "landing", "/id/verify/DEMO-STU-001/"),
            "https://ndgakuje.org/id/verify/DEMO-STU-001/",
        )

    def test_localhost_staff_cbt_response_keeps_sidebar_shell(self):
        client = Client(HTTP_HOST="localhost:8000")
        client.force_login(self.teacher_user)
        session = client.session
        session["fresh_auth_cbt"] = True
        session.save()
        response = client.get("/cbt/authoring/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "portal-sidebar")
        self.assertContains(response, "CBT Entry Center")

    def test_localhost_election_home_renders_without_redirect_loop(self):
        client = Client(HTTP_HOST="localhost:8000")
        client.force_login(self.teacher_user)
        session = client.session
        session["fresh_auth_election"] = True
        session.save()
        response = client.get("/elections/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "portal-sidebar")
        self.assertContains(response, "Election Operations Center")

    def test_localhost_it_election_management_keeps_it_shell(self):
        client = Client(HTTP_HOST="localhost:8000")
        client.force_login(self.it_user)
        response = client.get("/elections/it/manage/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "portal-sidebar")

    def test_localhost_it_cbt_activation_keeps_it_shell(self):
        client = Client(HTTP_HOST="localhost:8000")
        client.force_login(self.it_user)
        response = client.get("/cbt/it/activation/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "IT Manager Portal")
        self.assertContains(response, "CBT Setup")

    def test_localhost_it_cbt_authoring_no_fresh_login_redirect(self):
        client = Client(HTTP_HOST="localhost:8000")
        client.force_login(self.it_user)
        response = client.get("/cbt/authoring/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "IT Manager Portal")
    def test_staff_login_page_copy_is_staff_only(self):
        client = Client(HTTP_HOST="staff.ndgakuje.org")
        response = client.get("/auth/login/?audience=staff")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Use your Staff ID (or portal username) and your login password.",
        )
        self.assertNotContains(response, "Student ID (or portal username)")

    def test_student_login_page_copy_is_student_only(self):
        client = Client(HTTP_HOST="student.ndgakuje.org")
        response = client.get("/auth/login/?audience=student")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Use your Student ID (or portal username) and your login password.",
        )
        self.assertNotContains(response, "Staff ID (or portal username)")

    def test_it_login_from_localhost_staff_audience_redirects_to_local_it_path(self):
        self.it_user.two_factor_enabled = True
        self.it_user.two_factor_email = "it-host@ndgakuje.org"
        self.it_user.save(update_fields=["two_factor_enabled", "two_factor_email"])

        client = Client(HTTP_HOST="localhost:8000")
        response = client.post(
            "/auth/login/?audience=staff",
            {"username": "it_host", "password": "Password123!"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/auth/login/verify/")
        self.assertTrue(mail.outbox)
        code = mail.outbox[-1].body.split("verification code is:")[1].splitlines()[0].strip()
        verify_response = client.post(
            "/auth/login/verify/",
            {"verification_code": code},
        )
        self.assertEqual(verify_response.status_code, 302)
        self.assertEqual(verify_response.url, "http://localhost:8000/portal/it/")

    def test_authenticated_user_opening_login_redirects_to_role_home(self):
        client = Client(HTTP_HOST="staff.ndgakuje.org")
        client.force_login(self.it_user)
        response = client.get("/auth/login/?audience=staff")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'http://it.ndgakuje.org/')

    def test_student_host_login_and_access(self):
        client = Client(HTTP_HOST="student.ndgakuje.org")
        login_response = client.post(
            "/auth/login/?audience=student",
            {"username": "student_host", "password": "Password123!"},
        )
        self.assertEqual(login_response.status_code, 302)
        home_response = client.get("/")
        self.assertEqual(home_response.status_code, 200)
        self.assertContains(home_response, "Student Portal")

    def test_non_student_login_from_student_portal_redirects_to_staff_login(self):
        client = Client(HTTP_HOST="student.ndgakuje.org")
        response = client.post(
            "/auth/login/?audience=student",
            {"username": "it_host", "password": "Password123!"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            "http://staff.ndgakuje.org/auth/login/?audience=staff",
        )
        self.assertNotIn("_auth_user_id", client.session)

    def test_student_login_from_staff_portal_redirects_to_student_login(self):
        client = Client(HTTP_HOST="staff.ndgakuje.org")
        response = client.post(
            "/auth/login/?audience=staff",
            {"username": "student_host", "password": "Password123!"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            "http://student.ndgakuje.org/auth/login/?audience=student",
        )
        self.assertNotIn("_auth_user_id", client.session)

    def test_staff_host_blocks_it_only_route_even_for_it_user(self):
        client = Client(HTTP_HOST="staff.ndgakuje.org")
        client.force_login(self.it_user)
        response = client.get("/auth/it/user-provisioning/staff/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "http://it.ndgakuje.org/")

    @override_settings(
        FEATURE_FLAGS={
            "CBT_ENABLED": False,
            "ELECTION_ENABLED": False,
            "OFFLINE_MODE_ENABLED": True,
            "LOCKDOWN_ENABLED": True,
        }
    )
    def test_disabled_cbt_and_election_never_404(self):
        cbt_client = Client(HTTP_HOST="cbt.ndgakuje.org")
        cbt_root = cbt_client.get("/")
        cbt_unknown = cbt_client.get("/unknown/deep/path/")
        self.assertEqual(cbt_root.status_code, 200)
        self.assertEqual(cbt_unknown.status_code, 200)
        self.assertContains(cbt_unknown, "currently unavailable")

        election_client = Client(HTTP_HOST="election.ndgakuje.org")
        election_root = election_client.get("/")
        election_unknown = election_client.get("/any/random/path/")
        self.assertEqual(election_root.status_code, 200)
        self.assertEqual(election_unknown.status_code, 200)
        self.assertContains(election_unknown, "currently unavailable")

    @override_settings(
        FEATURE_FLAGS={
            "CBT_ENABLED": True,
            "ELECTION_ENABLED": True,
            "OFFLINE_MODE_ENABLED": True,
            "LOCKDOWN_ENABLED": True,
        }
    )
    def test_cbt_requires_fresh_login(self):
        client = Client()
        login_student = client.post(
            "/auth/login/?audience=student",
            {"username": "student_host", "password": "Password123!"},
            HTTP_HOST="student.ndgakuje.org",
        )
        self.assertEqual(login_student.status_code, 302)

        cbt_attempt = client.get("/", HTTP_HOST="cbt.ndgakuje.org")
        self.assertEqual(cbt_attempt.status_code, 302)
        self.assertIn("http://cbt.ndgakuje.org/auth/login/", cbt_attempt.url)
        self.assertIn("fresh=1", cbt_attempt.url)

        login_cbt = client.post(
            "/auth/login/?audience=cbt&fresh=1&next=/",
            {"username": "student_host", "password": "Password123!"},
            HTTP_HOST="cbt.ndgakuje.org",
        )
        self.assertEqual(login_cbt.status_code, 302)
        cbt_home = client.get("/", HTTP_HOST="cbt.ndgakuje.org")
        self.assertEqual(cbt_home.status_code, 302)
        self.assertEqual(cbt_home.url, "/cbt/")
