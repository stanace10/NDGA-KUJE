from django.core.exceptions import ValidationError
from django.test import Client, RequestFactory, TestCase
from django.utils import timezone

from decimal import Decimal
from unittest.mock import patch

from apps.accounts.constants import ROLE_BURSAR, ROLE_DEAN, ROLE_FORM_TEACHER, ROLE_IT_MANAGER, ROLE_PRINCIPAL, ROLE_SUBJECT_TEACHER, ROLE_VP
from apps.accounts.models import Role, User
from apps.academics.models import AcademicClass, AcademicSession, FormTeacherAssignment, GradeScale, StudentClassEnrollment, Subject, TeacherSubjectAssignment, Term
from apps.audit.models import AuditEvent
from apps.results.entry_flow import build_posted_score_bundle, read_sheet_policies_from_post, row_component_state
from apps.results.insights import build_advanced_result_comment_bundle
from apps.results.models import (
    ClassCompilationStatus,
    ClassResultCompilation,
    ClassResultStudentRecord,
    ResultSheet,
    ResultSheetStatus,
    StudentResultManagementStatus,
    StudentSubjectScore,
)
from apps.results.views import (
    _component_window_state,
    _log_score_change,
    _publish_allowed_for_actor,
    _score_snapshot,
    _send_dean_approved_sheet_to_form_teachers,
    _vp_approval_allowed,
)
from apps.results.workflow import mark_compilation_approved_by_vp
from apps.dashboard.models import PrincipalSignature, SchoolProfile
from apps.results.utils import form_teacher_classes_for_user, teacher_assignments_for_user
from apps.setup_wizard.models import AcademicOperationWindow, SetupStateCode, SystemSetupState


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

    def test_vp_can_open_result_reports(self):
        client = Client(HTTP_HOST="vp.ndgakuje.org")
        client.force_login(self.vp_user)
        response = client.get("/results/report/performance/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Performance Analysis")

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


class AdvancedResultSuggestionTests(TestCase):
    @patch("apps.results.insights.ai_json_response")
    def test_configured_ai_suggestions_are_validated_and_returned(self, mocked_ai):
        mocked_ai.return_value = {
            "_ai_provider": "openai",
            "teacher_suggestions": [
                "Ada worked consistently this term and should strengthen Mathematics through regular guided practice.",
                "Ada showed good discipline and can improve further by maintaining steady attendance and revision.",
                "Ada is making progress; focused support in Mathematics will help her build confidence next term.",
            ],
            "principal_suggestions": [
                "A commendable effort. Continue working consistently.",
                "Good progress has been made; greater attention to weaker areas is encouraged.",
                "Keep building on this term's progress with discipline and regular study.",
            ],
        }
        payload = build_advanced_result_comment_bundle(
            student_name="Ada",
            average_score=Decimal("62.50"),
            attendance_percentage=Decimal("88.00"),
            fail_count=1,
            weak_subjects=["Mathematics"],
            behavior_breakdown={"discipline": 4, "punctuality": 3},
        )
        self.assertEqual(payload["ai_provider"], "openai")
        self.assertEqual(len(payload["teacher_suggestions"]), 3)
        self.assertIn("Mathematics", payload["teacher_comment"])

    @patch("apps.results.insights.ai_json_response", return_value=None)
    def test_ai_failure_uses_deterministic_fallback(self, _mocked_ai):
        payload = build_advanced_result_comment_bundle(
            student_name="Ada",
            average_score=Decimal("62.50"),
            attendance_percentage=Decimal("88.00"),
            fail_count=1,
            weak_subjects=["Mathematics"],
        )
        self.assertEqual(payload["ai_provider"], "deterministic-fallback")
        self.assertEqual(len(payload["teacher_suggestions"]), 3)

    def test_dean_approved_sheet_is_sent_to_form_teacher_queue_automatically(self):
        form_teacher = User.objects.create_user(
            username="auto-form-teacher",
            password="Password123!",
            primary_role=Role.objects.get(code=ROLE_FORM_TEACHER),
            must_change_password=False,
        )
        subject_teacher = User.objects.create_user(
            username="auto-subject-teacher",
            password="Password123!",
            primary_role=Role.objects.get(code=ROLE_SUBJECT_TEACHER),
            must_change_password=False,
        )
        session = AcademicSession.objects.create(name="2040/2041")
        term = Term.objects.create(session=session, name="FIRST")
        base_class = AcademicClass.objects.create(code="AUTO1", display_name="Auto One")
        arm_class = AcademicClass.objects.create(
            code="AUTO1A",
            display_name="Auto One A",
            base_class=base_class,
            arm_name="A",
        )
        subject = Subject.objects.create(name="Automatic Flow Subject", code="AFS")
        TeacherSubjectAssignment.objects.create(
            teacher=subject_teacher,
            academic_class=base_class,
            subject=subject,
            session=session,
            term=term,
            is_active=True,
        )
        FormTeacherAssignment.objects.create(
            teacher=form_teacher,
            academic_class=arm_class,
            session=session,
            is_active=True,
        )
        sheet = ResultSheet.objects.create(
            academic_class=base_class,
            subject=subject,
            session=session,
            term=term,
            created_by=subject_teacher,
            status=ResultSheetStatus.APPROVED_BY_DEAN,
        )
        _send_dean_approved_sheet_to_form_teachers(sheet)
        compilation = ClassResultCompilation.objects.get(
            academic_class=arm_class,
            session=session,
            term=term,
        )
        self.assertEqual(compilation.form_teacher, form_teacher)
        self.assertEqual(compilation.status, ClassCompilationStatus.DRAFT)


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


class ResultFinalPublicationFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vp = User.objects.create_user(
            username="vp-final-flow",
            password="Password123!",
            primary_role=Role.objects.get(code=ROLE_VP),
            must_change_password=False,
        )
        cls.it = User.objects.create_user(
            username="it-final-flow",
            password="Password123!",
            primary_role=Role.objects.get(code=ROLE_IT_MANAGER),
            must_change_password=False,
        )
        cls.session = AcademicSession.objects.create(name="2031/2032")
        cls.term = Term.objects.create(session=cls.session, name="THIRD")
        cls.academic_class = AcademicClass.objects.create(code="FLOW1", display_name="Flow One")
        cls.compilation = ClassResultCompilation.objects.create(
            academic_class=cls.academic_class,
            session=cls.session,
            term=cls.term,
            status=ClassCompilationStatus.SUBMITTED_TO_VP,
        )
        cls.students = []
        for index in range(2):
            student = User.objects.create_user(
                username=f"flow-student-{index}",
                password="Password123!",
                must_change_password=False,
            )
            StudentClassEnrollment.objects.create(
                student=student,
                academic_class=cls.academic_class,
                session=cls.session,
                is_active=True,
            )
            cls.students.append(student)

    def test_vp_approval_requires_every_principal_comment_then_it_publishes(self):
        for student in self.students:
            ClassResultStudentRecord.objects.create(
                compilation=self.compilation,
                student=student,
                teacher_comment="Form teacher comment",
                form_teacher_completed_at=timezone.now(),
                management_status=StudentResultManagementStatus.REVIEWED,
            )

        self.assertFalse(_vp_approval_allowed(actor=self.vp, compilation=self.compilation))
        self.compilation.student_records.update(principal_comment="Principal comment")
        self.assertTrue(_vp_approval_allowed(actor=self.vp, compilation=self.compilation))

        mark_compilation_approved_by_vp(self.compilation, self.vp, comment="Ready")
        self.compilation.refresh_from_db()
        self.assertEqual(self.compilation.status, ClassCompilationStatus.APPROVED_BY_VP)
        self.assertFalse(_publish_allowed_for_actor(actor=self.vp, compilation=self.compilation))
        self.assertTrue(_publish_allowed_for_actor(actor=self.it, compilation=self.compilation))

    def test_it_can_bypass_unfinished_stages_but_vp_cannot_publish(self):
        self.compilation.status = ClassCompilationStatus.DRAFT
        self.compilation.save(update_fields=["status", "updated_at"])

        self.assertFalse(_publish_allowed_for_actor(actor=self.vp, compilation=self.compilation))
        self.assertTrue(_publish_allowed_for_actor(actor=self.it, compilation=self.compilation))


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
            objective=Decimal("19.00"),
            theory=Decimal("18.00"),
            cbt_locked_fields=["objective"],
            cbt_component_breakdown={"objective_auto": "19.00"},
        )
        policies = {
            "ca1": {"enabled": False, "objective_max": "5.00", "theory_max": "5.00"},
            "ca23": {"enabled": False, "objective_max": "10.00", "theory_max": "10.00"},
            "ca4": {"enabled": False, "objective_max": "5.00", "theory_max": "5.00"},
            "exam": {"enabled": True, "objective_max": "20.00", "theory_max": "30.00"},
        }

        bundle = build_posted_score_bundle(
            current_score=score,
            post={f"objective_{self.student.id}": "0", f"theory_{self.student.id}": "29.50"},
            student_id=self.student.id,
            policies=policies,
            actor=self.actor,
        )
        cbt_state = row_component_state(score, policies)

        self.assertEqual(bundle["payload"].objective, Decimal("19.00"))
        self.assertEqual(bundle["payload"].theory, Decimal("29.50"))
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

    def test_ca1_split_rejects_theory_above_policy_max(self):
        score = StudentSubjectScore.objects.create(
            result_sheet=self.sheet,
            student=self.student,
            ca1=Decimal("4.00"),
            cbt_locked_fields=["ca1"],
            cbt_component_breakdown={"ca1_objective": "4.00"},
        )
        policies = {
            "ca1": {"enabled": True, "objective_max": "5.00", "theory_max": "5.00"},
            "ca23": {"enabled": False, "objective_max": "10.00", "theory_max": "10.00"},
            "ca4": {"enabled": False, "objective_max": "5.00", "theory_max": "5.00"},
            "exam": {"enabled": False, "objective_max": "40.00", "theory_max": "20.00"},
        }

        with self.assertRaises(ValidationError) as ctx:
            build_posted_score_bundle(
                current_score=score,
                post={f"ca1_theory_{self.student.id}": "6.00"},
                student_id=self.student.id,
                policies=policies,
                actor=self.actor,
            )

        self.assertIn("ca1_theory", ctx.exception.message_dict)

    def test_ca23_split_rejects_theory_above_ten(self):
        score = StudentSubjectScore.objects.create(
            result_sheet=self.sheet,
            student=self.student,
            ca2=Decimal("9.50"),
            cbt_locked_fields=["ca2"],
            cbt_component_breakdown={"ca2_objective": "9.50"},
        )
        policies = {
            "ca1": {"enabled": False, "objective_max": "5.00", "theory_max": "5.00"},
            "ca23": {"enabled": True, "objective_max": "10.00", "theory_max": "10.00"},
            "ca4": {"enabled": False, "objective_max": "5.00", "theory_max": "5.00"},
            "exam": {"enabled": False, "objective_max": "40.00", "theory_max": "20.00"},
        }

        with self.assertRaises(ValidationError) as ctx:
            build_posted_score_bundle(
                current_score=score,
                post={f"ca3_{self.student.id}": "10.50"},
                student_id=self.student.id,
                policies=policies,
                actor=self.actor,
            )

        self.assertIn("ca23_theory", ctx.exception.message_dict)

    def test_exam_policy_without_cbt_import_allows_manual_objective_input_over_twenty(self):
        score = StudentSubjectScore.objects.create(
            result_sheet=self.sheet,
            student=self.student,
            objective=Decimal("0.00"),
            theory=Decimal("0.00"),
        )
        policies = {
            "ca1": {"enabled": False, "objective_max": "5.00", "theory_max": "5.00"},
            "ca23": {"enabled": False, "objective_max": "10.00", "theory_max": "10.00"},
            "ca4": {"enabled": False, "objective_max": "5.00", "theory_max": "5.00"},
            "exam": {"enabled": True, "objective_max": "20.00", "theory_max": "30.00"},
        }

        bundle = build_posted_score_bundle(
            current_score=score,
            post={f"objective_{self.student.id}": "20.00", f"theory_{self.student.id}": "30.00"},
            student_id=self.student.id,
            policies=policies,
            actor=self.actor,
        )
        cbt_state = row_component_state(score, policies)

        self.assertEqual(bundle["payload"].objective, Decimal("20.00"))
        self.assertEqual(bundle["payload"].theory, Decimal("30.00"))
        self.assertEqual(bundle["payload"].total_exam, Decimal("50.00"))
        self.assertEqual(bundle["breakdown_updates"]["objective_display_raw"], Decimal("20.00"))
        self.assertFalse(cbt_state["exam"]["locked"])

    def test_ca23_policy_without_cbt_import_allows_manual_ca2_input(self):
        score = StudentSubjectScore.objects.create(
            result_sheet=self.sheet,
            student=self.student,
            ca2=Decimal("0.00"),
            ca3=Decimal("0.00"),
        )
        policies = {
            "ca1": {"enabled": False, "objective_max": "5.00", "theory_max": "5.00"},
            "ca23": {"enabled": True, "objective_max": "10.00", "theory_max": "10.00"},
            "ca4": {"enabled": False, "objective_max": "5.00", "theory_max": "5.00"},
            "exam": {"enabled": False, "objective_max": "40.00", "theory_max": "20.00"},
        }

        bundle = build_posted_score_bundle(
            current_score=score,
            post={f"ca2_{self.student.id}": "7.50", f"ca3_{self.student.id}": "8.25"},
            student_id=self.student.id,
            policies=policies,
            actor=self.actor,
        )
        cbt_state = row_component_state(score, policies)

        self.assertEqual(bundle["payload"].ca2, Decimal("7.50"))
        self.assertEqual(bundle["payload"].ca3, Decimal("8.25"))
        self.assertEqual(bundle["breakdown_updates"]["ca2_objective"], Decimal("0.00"))
        self.assertFalse(cbt_state["ca23"]["locked"])

    def test_ca1_policy_without_cbt_import_allows_full_manual_score(self):
        score = StudentSubjectScore.objects.create(
            result_sheet=self.sheet,
            student=self.student,
            ca1=Decimal("0.00"),
        )
        policies = {
            "ca1": {"enabled": True, "objective_max": "5.00", "theory_max": "5.00"},
            "ca23": {"enabled": False, "objective_max": "10.00", "theory_max": "10.00"},
            "ca4": {"enabled": False, "objective_max": "5.00", "theory_max": "5.00"},
            "exam": {"enabled": False, "objective_max": "40.00", "theory_max": "20.00"},
        }

        bundle = build_posted_score_bundle(
            current_score=score,
            post={f"ca1_{self.student.id}": "8.50"},
            student_id=self.student.id,
            policies=policies,
            actor=self.actor,
        )
        cbt_state = row_component_state(score, policies)

        self.assertEqual(bundle["payload"].ca1, Decimal("8.50"))
        self.assertEqual(bundle["breakdown_updates"]["ca1_objective"], Decimal("0.00"))
        self.assertEqual(bundle["breakdown_updates"]["ca1_theory"], Decimal("0.00"))
        self.assertFalse(cbt_state["ca1"]["locked"])

    def test_score_change_audit_log_tracks_before_and_after_values(self):
        score = StudentSubjectScore.objects.create(
            result_sheet=self.sheet,
            student=self.student,
            ca1=Decimal("8.00"),
            objective=Decimal("12.00"),
            theory=Decimal("16.00"),
        )
        before_snapshot = _score_snapshot(score)
        score.theory = Decimal("19.50")
        score.save(update_fields=["theory", "updated_at"])

        request = RequestFactory().post("/results/entry/")
        _log_score_change(
            actor=self.actor,
            request=request,
            score=score,
            sheet=self.sheet,
            before_snapshot=before_snapshot,
        )

        audit_event = AuditEvent.objects.filter(event_type="RESULTS_EDIT").latest("id")
        self.assertEqual(audit_event.metadata["before"]["theory"], "16.00")
        self.assertEqual(audit_event.metadata["after"]["theory"], "19.50")
        self.assertIn("theory", audit_event.metadata["changed_fields"])


class AcademicWindowResultFlowTests(TestCase):
    PASSWORD = "Password123!"

    @classmethod
    def setUpTestData(cls):
        cls.role_teacher = Role.objects.get(code=ROLE_SUBJECT_TEACHER)
        cls.role_dean = Role.objects.get(code=ROLE_DEAN)
        cls.role_it = Role.objects.get(code=ROLE_IT_MANAGER)

        cls.teacher_user = User.objects.create_user(
            username="teacher-result-window",
            password=cls.PASSWORD,
            primary_role=cls.role_teacher,
            must_change_password=False,
        )
        cls.dean_user = User.objects.create_user(
            username="dean-result-window",
            password=cls.PASSWORD,
            primary_role=cls.role_dean,
            must_change_password=False,
        )
        cls.it_user = User.objects.create_user(
            username="it-result-window",
            password=cls.PASSWORD,
            primary_role=cls.role_it,
            must_change_password=False,
        )
        cls.student_user = User.objects.create_user(
            username="student-result-window",
            password=cls.PASSWORD,
            primary_role=cls.role_teacher,
            must_change_password=False,
        )

        cls.session = AcademicSession.objects.create(name="2027/2028")
        cls.term = Term.objects.create(session=cls.session, name="FIRST")
        cls.academic_class = AcademicClass.objects.create(code="JSS2A", display_name="JSS2A")
        cls.subject = Subject.objects.create(name="English Language", code="ENG")
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

        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = cls.session
        setup_state.current_term = cls.term
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

    def _close_result_window(self):
        AcademicOperationWindow.objects.update_or_create(
            window_type=AcademicOperationWindow.WindowType.RESULTS,
            defaults={
                "is_enabled": True,
                "start_at": None,
                "end_at": None,
            },
        )

    def _open_result_window(self):
        now = timezone.now()
        AcademicOperationWindow.objects.update_or_create(
            window_type=AcademicOperationWindow.WindowType.RESULTS,
            defaults={
                "is_enabled": True,
                "start_at": now - timezone.timedelta(minutes=5),
                "end_at": now + timezone.timedelta(days=7),
            },
        )

    def test_closed_result_window_blocks_staff_submission_to_dean(self):
        self._close_result_window()
        client = Client(HTTP_HOST="staff.ndgakuje.org")
        client.force_login(self.teacher_user)

        response = client.post(
            f"/results/grade-entry/class/{self.academic_class.id}/",
            {"assignment_id": str(self.assignment.id)},
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            ResultSheet.objects.filter(
                academic_class=self.academic_class,
                subject=self.subject,
                session=self.session,
                term=self.term,
            ).exists()
        )

    def test_previous_term_filter_is_view_only_for_staff_submission(self):
        self._open_result_window()
        previous_term = Term.objects.create(session=self.session, name="SECOND")
        current_term = Term.objects.create(session=self.session, name="THIRD")
        previous_assignment = TeacherSubjectAssignment.objects.create(
            teacher=self.teacher_user,
            subject=self.subject,
            academic_class=self.academic_class,
            session=self.session,
            term=previous_term,
            is_active=True,
        )
        setup_state = SystemSetupState.get_solo()
        setup_state.current_term = current_term
        setup_state.save(update_fields=["current_term", "updated_at"])

        client = Client(HTTP_HOST="staff.ndgakuje.org")
        client.force_login(self.teacher_user)
        response = client.post(
            f"/results/grade-entry/class/{self.academic_class.id}/?session_id={self.session.id}&term_id={previous_term.id}",
            {"assignment_id": str(previous_assignment.id)},
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            ResultSheet.objects.filter(
                academic_class=self.academic_class,
                subject=self.subject,
                session=self.session,
                term=previous_term,
            ).exists()
        )

    def test_closed_result_window_blocks_dean_bulk_review(self):
        self._close_result_window()
        sheet = ResultSheet.objects.create(
            academic_class=self.academic_class,
            subject=self.subject,
            session=self.session,
            term=self.term,
            created_by=self.teacher_user,
            status=ResultSheetStatus.SUBMITTED_TO_DEAN,
        )
        client = Client(HTTP_HOST="dean.ndgakuje.org")
        client.force_login(self.dean_user)

        response = client.post(
            "/results/dean/review/results/",
            {"bulk_action": "approve_selected", "sheet_ids": [str(sheet.id)]},
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        sheet.refresh_from_db()
        self.assertEqual(sheet.status, ResultSheetStatus.SUBMITTED_TO_DEAN)

    def test_it_manager_can_open_academic_setup_page(self):
        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_user)

        response = client.get("/portal/it/academic-setup/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Academic Setup")

    def test_subject_specific_emergency_window_opens_only_selected_sheet_component(self):
        now = timezone.now()
        AcademicOperationWindow.objects.update_or_create(
            window_type=AcademicOperationWindow.WindowType.RESULT_CA23,
            defaults={
                "is_enabled": False,
                "start_at": None,
                "end_at": None,
            },
        )
        sheet = ResultSheet.objects.create(
            academic_class=self.academic_class,
            subject=self.subject,
            session=self.session,
            term=self.term,
            created_by=self.teacher_user,
            cbt_component_policies={
                "emergency_entry_windows": {
                    "ca23": {
                        "is_enabled": True,
                        "start_at": (now - timezone.timedelta(minutes=5)).isoformat(),
                        "end_at": (now + timezone.timedelta(minutes=30)).isoformat(),
                    }
                }
            },
        )
        other_subject = Subject.objects.create(name="Mathematics", code="MTH-WINDOW")
        other_sheet = ResultSheet.objects.create(
            academic_class=self.academic_class,
            subject=other_subject,
            session=self.session,
            term=self.term,
            created_by=self.teacher_user,
        )

        selected_state = _component_window_state("ca23", self.teacher_user, sheet)
        other_state = _component_window_state("ca23", self.teacher_user, other_sheet)

        self.assertTrue(selected_state["is_open"])
        self.assertTrue(selected_state["is_subject_override"])
        self.assertFalse(other_state["is_open"])

    def test_policy_edit_preserves_subject_specific_emergency_deadline(self):
        now = timezone.now()
        emergency_windows = {
            "ca1": {
                "is_enabled": True,
                "start_at": now.isoformat(),
                "end_at": (now + timezone.timedelta(hours=1)).isoformat(),
            }
        }
        sheet = ResultSheet.objects.create(
            academic_class=self.academic_class,
            subject=self.subject,
            session=self.session,
            term=self.term,
            created_by=self.teacher_user,
            cbt_component_policies={"emergency_entry_windows": emergency_windows},
        )

        policies, _warnings, _changed = read_sheet_policies_from_post(
            sheet,
            {
                "policy_ca1_enabled": "on",
                "policy_ca1_objective_max": "5",
                "policy_ca1_theory_max": "5",
            },
            [],
        )

        self.assertEqual(policies["emergency_entry_windows"], emergency_windows)
