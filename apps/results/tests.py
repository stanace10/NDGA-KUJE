from django.test import Client, TestCase

from apps.accounts.constants import ROLE_BURSAR, ROLE_FORM_TEACHER, ROLE_IT_MANAGER, ROLE_PRINCIPAL, ROLE_VP
from apps.accounts.models import Role, User
from apps.academics.models import AcademicSession, Term
from apps.dashboard.models import PrincipalSignature, SchoolProfile
from apps.setup_wizard.models import SetupStateCode, SystemSetupState


class ResultSettingsEnhancementTests(TestCase):
    PASSWORD = "Password123!"

    @classmethod
    def setUpTestData(cls):
        role_it = Role.objects.get(code=ROLE_IT_MANAGER)
        role_principal = Role.objects.get(code=ROLE_PRINCIPAL)
        role_vp = Role.objects.get(code=ROLE_VP)
        role_bursar = Role.objects.get(code=ROLE_BURSAR)
        role_form_teacher = Role.objects.get(code=ROLE_FORM_TEACHER)
        cls.it_user = User.objects.create_user(
            username="it-settings-results",
            password=cls.PASSWORD,
            primary_role=role_it,
            must_change_password=False,
        )
        cls.principal_user = User.objects.create_user(
            username="principal-settings-results",
            password=cls.PASSWORD,
            primary_role=role_principal,
            must_change_password=False,
        )
        cls.vp_user = User.objects.create_user(
            username="vp-settings-results",
            password=cls.PASSWORD,
            primary_role=role_vp,
            must_change_password=False,
        )
        cls.bursar_user = User.objects.create_user(
            username="bursar-results",
            password=cls.PASSWORD,
            primary_role=role_bursar,
            must_change_password=False,
        )
        cls.form_teacher_user = User.objects.create_user(
            username="form-results",
            password=cls.PASSWORD,
            primary_role=role_form_teacher,
            must_change_password=False,
        )
        session = AcademicSession.objects.create(name="2025/2026")
        term = Term.objects.create(session=session, name="FIRST")
        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = session
        setup_state.current_term = term
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

    def test_it_can_update_school_profile_and_principal_signature(self):
        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_user)

        response = client.get("/results/settings/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "School Profile & Result Setup")

        save_profile = client.post(
            "/results/settings/",
            {
                "action": "save_school_profile",
                "school_name": "Notre Dame Girls Academy",
                "address": "Kuje, Abuja",
                "contact_email": "office@ndgakuje.org",
                "contact_phone": "09000000000",
                "website": "https://ndgakuje.org",
                "result_tagline": "Premium Report",
                "principal_name": "Rev. Sr. Principal",
                "report_footer": "Governance integrity is the product.",
                "ca1_label": "1st CA",
                "ca2_label": "2nd CA",
                "ca3_label": "3rd CA",
                "assignment_label": "Project/Assignment",
                "promotion_average_threshold": "45",
                "promotion_attendance_threshold": "75",
                "auto_comment_guidance": "Keep comments concise.",
                "require_result_access_pin": "on",
            },
            follow=False,
        )
        self.assertEqual(save_profile.status_code, 302)
        profile = SchoolProfile.load()
        self.assertTrue(profile.require_result_access_pin)
        self.assertEqual(profile.contact_email, "office@ndgakuje.org")

        signature_data = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4////fwAJ+wP+W6l/JwAAAABJRU5ErkJggg=="
        )
        save_signature = client.post(
            "/results/settings/",
            {
                "action": "save_principal_signature",
                "signature_data": signature_data,
            },
            follow=False,
        )
        self.assertEqual(save_signature.status_code, 302)
        signature = PrincipalSignature.objects.filter(user=self.principal_user).first()
        self.assertIsNotNone(signature)
        self.assertTrue(bool(signature.signature_image))

    def test_vp_has_view_only_access_to_result_settings(self):
        client = Client(HTTP_HOST="vp.ndgakuje.org")
        client.force_login(self.vp_user)
        response = client.get("/results/settings/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "View-only access")

    def test_bursar_can_open_report_analytics_and_send_results(self):
        client = Client(HTTP_HOST="bursar.ndgakuje.org")
        client.force_login(self.bursar_user)

        performance_response = client.get("/results/report/performance/")
        self.assertEqual(performance_response.status_code, 200)
        self.assertContains(performance_response, "Performance Analysis")

        send_response = client.get("/results/report/send-results/")
        self.assertEqual(send_response.status_code, 200)
        self.assertContains(send_response, "Send Results")

    def test_form_teacher_can_open_send_results_page(self):
        client = Client(HTTP_HOST="staff.ndgakuje.org")
        client.force_login(self.form_teacher_user)
        response = client.get("/results/report/send-results/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Send Results")
