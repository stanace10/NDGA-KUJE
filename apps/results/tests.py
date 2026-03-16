from django.test import Client, TestCase

from decimal import Decimal

from apps.accounts.constants import ROLE_BURSAR, ROLE_FORM_TEACHER, ROLE_IT_MANAGER, ROLE_PRINCIPAL, ROLE_VP
from apps.accounts.models import Role, User
from apps.academics.models import AcademicClass, AcademicSession, FormTeacherAssignment, GradeScale, Subject, TeacherSubjectAssignment, Term
from apps.results.entry_flow import build_posted_score_bundle, row_component_state
from apps.results.models import ResultSheet, StudentSubjectScore
from apps.dashboard.models import PrincipalSignature, SchoolProfile
from apps.results.utils import form_teacher_classes_for_user, teacher_assignments_for_user
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
                "promotion_policy_note": "Promotion requires both academics and conduct review.",
                "auto_comment_guidance": "Keep comments concise.",
                "teacher_comment_guidance": "Sound warm but direct.",
                "dean_comment_guidance": "Focus on intervention and academic compliance.",
                "principal_comment_guidance": "Keep it governance-aware.",
                "doctor_remark_guidance": "Keep health remarks brief.",
                "require_result_access_pin": "on",
            },
            follow=False,
        )
        self.assertEqual(save_profile.status_code, 302)
        profile = SchoolProfile.load()
        self.assertTrue(profile.require_result_access_pin)
        self.assertEqual(profile.contact_email, "office@ndgakuje.org")
        self.assertEqual(profile.teacher_comment_guidance, "Sound warm but direct.")
        self.assertEqual(profile.dean_comment_guidance, "Focus on intervention and academic compliance.")

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

    def test_vp_is_redirected_from_result_settings(self):
        client = Client(HTTP_HOST="vp.ndgakuje.org")
        client.force_login(self.vp_user)
        response = client.get("/results/settings/")
        self.assertEqual(response.status_code, 302)

    def test_vp_cannot_open_result_reports(self):
        client = Client(HTTP_HOST="vp.ndgakuje.org")
        client.force_login(self.vp_user)
        response = client.get("/results/report/performance/")
        self.assertEqual(response.status_code, 302)

    def test_it_can_manage_grade_scale_bands(self):
        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_user)

        response = client.post(
            "/results/settings/",
            {
                "action": "create_grade_scale",
                "grade": "E",
                "min_score": "35",
                "max_score": "39",
                "sort_order": "5",
            },
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(GradeScale.objects.filter(grade="E", min_score=35, max_score=39, is_default=True).exists())

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


class VPMixedRoleScopeTests(TestCase):
    PASSWORD = "Password123!"

    @classmethod
    def setUpTestData(cls):
        role_vp = Role.objects.get(code=ROLE_VP)
        role_form_teacher = Role.objects.get(code=ROLE_FORM_TEACHER)

        cls.vp_user = User.objects.create_user(
            username="vp-js1-scope",
            password=cls.PASSWORD,
            primary_role=role_vp,
            must_change_password=False,
        )
        cls.vp_user.secondary_roles.add(role_form_teacher)

        cls.session = AcademicSession.objects.create(name="2026/2027")
        cls.term = Term.objects.create(session=cls.session, name="FIRST")
        cls.js1 = AcademicClass.objects.create(code="JS1", display_name="JS1")
        cls.js2 = AcademicClass.objects.create(code="JS2", display_name="JS2")
        cls.math = Subject.objects.create(name="Mathematics", code="MTH")

        FormTeacherAssignment.objects.create(
            teacher=cls.vp_user,
            academic_class=cls.js1,
            session=cls.session,
            is_active=True,
        )
        TeacherSubjectAssignment.objects.create(
            teacher=cls.vp_user,
            academic_class=cls.js1,
            subject=cls.math,
            session=cls.session,
            term=cls.term,
            is_active=True,
        )

    def test_form_teacher_scope_stays_on_assigned_class_only(self):
        class_codes = list(
            form_teacher_classes_for_user(self.vp_user, session=self.session).values_list("academic_class__code", flat=True)
        )
        self.assertEqual(class_codes, ["JS1"])

    def test_teacher_assignment_scope_no_longer_expands_for_vp_role(self):
        assignment_codes = list(
            teacher_assignments_for_user(self.vp_user).values_list("academic_class__code", flat=True)
        )
        self.assertEqual(assignment_codes, ["JS1"])


class ResultEntryCBTPolicyTests(TestCase):
    PASSWORD = "Password123!"

    @classmethod
    def setUpTestData(cls):
        role_it = Role.objects.get(code=ROLE_IT_MANAGER)
        cls.actor = User.objects.create_user(
            username="result-cbt-policy-it",
            password=cls.PASSWORD,
            primary_role=role_it,
            must_change_password=False,
        )
        cls.student = User.objects.create_user(
            username="result-cbt-policy-student",
            password=cls.PASSWORD,
            must_change_password=False,
        )
        cls.session = AcademicSession.objects.create(name="2027/2028")
        cls.term = Term.objects.create(session=cls.session, name="FIRST")
        cls.academic_class = AcademicClass.objects.create(code="SS3", display_name="SS3")
        cls.subject = Subject.objects.create(name="Digital Technology", code="DIT")
        cls.sheet = ResultSheet.objects.create(
            academic_class=cls.academic_class,
            subject=cls.subject,
            session=cls.session,
            term=cls.term,
            created_by=cls.actor,
        )

    def test_exam_policy_keeps_objective_locked_but_allows_teacher_theory_input(self):
        score = StudentSubjectScore.objects.create(
            result_sheet=self.sheet,
            student=self.student,
            objective=Decimal("38.00"),
            theory=Decimal("18.00"),
            cbt_locked_fields=["objective"],
            cbt_component_breakdown={"objective_auto": "38.00"},
        )
        policies = {
            "ca1": {"enabled": False, "objective_max": "5.00", "theory_max": "5.00"},
            "ca23": {"enabled": False, "objective_max": "10.00", "theory_max": "10.00"},
            "ca4": {"enabled": False, "objective_max": "5.00", "theory_max": "5.00"},
            "exam": {"enabled": True, "objective_max": "40.00", "theory_max": "60.00"},
        }

        bundle = build_posted_score_bundle(
            current_score=score,
            post={f"objective_{self.student.id}": "0", f"theory_{self.student.id}": "31.50"},
            student_id=self.student.id,
            policies=policies,
            actor=self.actor,
        )
        cbt_state = row_component_state(score, policies)

        self.assertEqual(bundle["payload"].objective, Decimal("38.00"))
        self.assertEqual(bundle["payload"].theory, Decimal("31.50"))
        self.assertEqual(cbt_state["exam"]["theory"], "18.00")
        self.assertTrue(cbt_state["exam"]["locked"])

    def test_ca23_policy_keeps_objective_locked_but_allows_teacher_theory_input(self):
        score = StudentSubjectScore.objects.create(
            result_sheet=self.sheet,
            student=self.student,
            ca2=Decimal("9.50"),
            ca3=Decimal("8.00"),
            cbt_locked_fields=["ca2"],
            cbt_component_breakdown={"ca2_objective": "9.50", "ca3_theory": "8.00"},
        )
        policies = {
            "ca1": {"enabled": False, "objective_max": "5.00", "theory_max": "5.00"},
            "ca23": {"enabled": True, "objective_max": "10.00", "theory_max": "10.00"},
            "ca4": {"enabled": False, "objective_max": "5.00", "theory_max": "5.00"},
            "exam": {"enabled": False, "objective_max": "40.00", "theory_max": "20.00"},
        }

        bundle = build_posted_score_bundle(
            current_score=score,
            post={f"ca2_{self.student.id}": "0", f"ca3_{self.student.id}": "9.25"},
            student_id=self.student.id,
            policies=policies,
            actor=self.actor,
        )
        cbt_state = row_component_state(score, policies)

        self.assertEqual(bundle["payload"].ca2, Decimal("9.50"))
        self.assertEqual(bundle["payload"].ca3, Decimal("9.25"))
        self.assertEqual(cbt_state["ca23"]["theory"], "8.00")
        self.assertTrue(cbt_state["ca23"]["locked"])
