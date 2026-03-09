from django.test import Client, TestCase, override_settings

from apps.accounts.constants import ROLE_IT_MANAGER, ROLE_STUDENT
from apps.accounts.models import Role, User


class StageTwoHostRoutingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        role, _ = Role.objects.get_or_create(code=ROLE_STUDENT, defaults={"name": "Student"})
        role_it, _ = Role.objects.get_or_create(code=ROLE_IT_MANAGER, defaults={"name": "IT Manager"})
        cls.student = User.objects.create_user(
            username="student_host",
            password="Password123!",
            primary_role=role,
            must_change_password=False,
        )
        cls.it_user = User.objects.create_user(
            username="it_host",
            password="Password123!",
            primary_role=role_it,
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

    def test_landing_modal_login_urls_preserve_dev_port(self):
        client = Client(HTTP_HOST="ndgakuje.org:8000")
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'href="http://staff.ndgakuje.org:8000/auth/login/?audience=staff"',
        )
        self.assertContains(
            response,
            'href="http://student.ndgakuje.org:8000/auth/login/?audience=student"',
        )

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

    def test_it_login_from_staff_host_redirects_to_it_host_with_dev_port(self):
        client = Client(HTTP_HOST="staff.ndgakuje.org:8000")
        response = client.post(
            "/auth/login/?audience=staff",
            {"username": "it_host", "password": "Password123!"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'http://it.ndgakuje.org:8000/')

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
        self.assertEqual(cbt_home.status_code, 200)
        self.assertContains(cbt_home, "CBT Portal")
