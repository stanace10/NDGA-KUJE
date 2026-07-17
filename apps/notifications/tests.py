import json
from unittest.mock import patch

from django.test import Client, TestCase, override_settings

from apps.accounts.constants import ROLE_BURSAR, ROLE_STUDENT, ROLE_SUBJECT_TEACHER, ROLE_VP
from apps.accounts.models import Role, StudentProfile, User
from apps.academics.models import AcademicClass, AcademicSession, ClassSubject, StudentClassEnrollment, StudentSubjectEnrollment, Subject, Term
from apps.audit.models import AuditEvent
from apps.notifications.models import (
    EmailReplyMessage,
    EmailReplyMessageDirection,
    EmailReplyThread,
    EmailThreadScope,
    Notification,
    NotificationCategory,
)
from apps.notifications.services import (
    notify_assignment_deadline,
    notify_election_announcement,
    notify_payment_receipt,
    send_email_event,
    send_whatsapp_event,
)
from apps.notifications.whatsapp_adapters import WhatsAppSendResult
from apps.results.models import (
    ClassCompilationStatus,
    ClassResultCompilation,
    ClassResultStudentRecord,
    ResultSheet,
    ResultSheetStatus,
)
from apps.setup_wizard.models import SetupStateCode, SystemSetupState


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    NOTIFICATIONS_EMAIL_PROVIDER="console",
)
class NotificationWorkflowTests(TestCase):
    PASSWORD = "Password123!"

    @classmethod
    def setUpTestData(cls):
        student_role = Role.objects.get(code=ROLE_STUDENT)
        vp_role = Role.objects.get(code=ROLE_VP)
        subject_role = Role.objects.get(code=ROLE_SUBJECT_TEACHER)
        bursar_role = Role.objects.get(code=ROLE_BURSAR)

        cls.student = User.objects.create_user(
            username="student-notify",
            password=cls.PASSWORD,
            primary_role=student_role,
            email="student-notify@example.com",
            must_change_password=False,
        )
        cls.vp_user = User.objects.create_user(
            username="vp-notify",
            password=cls.PASSWORD,
            primary_role=vp_role,
            must_change_password=False,
        )
        cls.subject_teacher = User.objects.create_user(
            username="subject-notify",
            password=cls.PASSWORD,
            primary_role=subject_role,
            must_change_password=False,
        )
        cls.bursar_user = User.objects.create_user(
            username="bursar-notify",
            password=cls.PASSWORD,
            primary_role=bursar_role,
            must_change_password=False,
        )

        cls.session = AcademicSession.objects.create(name="2025/2026")
        cls.term = Term.objects.create(session=cls.session, name="FIRST")
        cls.academic_class = AcademicClass.objects.create(code="SS2A", display_name="SS2A")
        cls.subject = Subject.objects.create(name="Chemistry", code="CHEM")
        ClassSubject.objects.create(academic_class=cls.academic_class, subject=cls.subject)

        cls.compilation = ClassResultCompilation.objects.create(
            academic_class=cls.academic_class,
            session=cls.session,
            term=cls.term,
            status=ClassCompilationStatus.SUBMITTED_TO_VP,
        )
        ClassResultStudentRecord.objects.create(
            compilation=cls.compilation,
            student=cls.student,
            attendance_percentage=90,
            behavior_rating=4,
            teacher_comment="Good work.",
        )
        ResultSheet.objects.create(
            academic_class=cls.academic_class,
            subject=cls.subject,
            session=cls.session,
            term=cls.term,
            status=ResultSheetStatus.SUBMITTED_TO_VP,
            created_by=cls.subject_teacher,
        )

        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = cls.session
        setup_state.current_term = cls.term
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

    def _client(self, host, user):
        client = Client(HTTP_HOST=host)
        client.force_login(user)
        return client

    def test_vp_publish_creates_results_notification_and_email_audit(self):
        client = self._client("vp.ndgakuje.org", self.vp_user)
        response = client.post(
            f"/results/vp/review/{self.compilation.id}/",
            {"action": "publish"},
        )
        self.assertEqual(response.status_code, 302)

        notification = Notification.objects.get(recipient=self.student)
        self.assertEqual(notification.category, NotificationCategory.RESULTS)
        self.assertIn("Result Published", notification.title)
        self.assertEqual(notification.action_url, "/pdfs/student/reports/")

        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="EMAIL_EVENT",
                status="SUCCESS",
                metadata__event="RESULT_PUBLISHED",
                metadata__compilation_id=str(self.compilation.id),
            ).exists()
        )

    def test_notification_center_can_mark_single_and_all_read(self):
        Notification.objects.create(
            recipient=self.student,
            category=NotificationCategory.SYSTEM,
            title="System Notice",
            message="Test message.",
        )
        Notification.objects.create(
            recipient=self.student,
            category=NotificationCategory.PAYMENT,
            title="Receipt Ready",
            message="Receipt generated.",
        )
        client = self._client("student.ndgakuje.org", self.student)
        center = client.get("/notifications/center/")
        self.assertEqual(center.status_code, 200)
        self.assertContains(center, "System Notice")

        first = Notification.objects.filter(recipient=self.student).first()
        read_response = client.post(f"/notifications/read/{first.id}/")
        self.assertEqual(read_response.status_code, 302)
        first.refresh_from_db()
        self.assertIsNotNone(first.read_at)

        all_response = client.post("/notifications/read-all/")
        self.assertEqual(all_response.status_code, 302)
        self.assertEqual(
            Notification.objects.filter(recipient=self.student, read_at__isnull=True).count(),
            0,
        )

    def test_payment_and_election_services_create_notifications(self):
        notify_payment_receipt(
            student=self.student,
            receipt_number="RCP-0091",
            amount="120000.00",
            actor=self.vp_user,
            message="Payment confirmed for school fees.",
        )
        notify_election_announcement(
            recipients=[self.student],
            title="Election Opening",
            message="Voting opens at 9:00 AM.",
            actor=self.vp_user,
            action_url="/portal/election/",
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.student,
                category=NotificationCategory.PAYMENT,
                title="Payment Receipt Issued",
            ).exists()
        )
        payment_notice = Notification.objects.filter(
            recipient=self.student,
            category=NotificationCategory.PAYMENT,
            title="Payment Receipt Issued",
        ).latest("created_at")
        self.assertEqual(payment_notice.action_url, "/portal/student/finance/")
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.student,
                category=NotificationCategory.ELECTION,
                title="Election Opening",
            ).exists()
        )

    def test_staff_notification_center_hides_payment_category(self):
        Notification.objects.create(
            recipient=self.subject_teacher,
            category=NotificationCategory.SYSTEM,
            title="Staff System Notice",
            message="System-wide update.",
        )
        Notification.objects.create(
            recipient=self.subject_teacher,
            category=NotificationCategory.PAYMENT,
            title="Payment Receipt Issued",
            message="Should stay hidden for staff teaching roles.",
        )

        staff_client = self._client("staff.ndgakuje.org", self.subject_teacher)
        center = staff_client.get("/notifications/center/")
        self.assertEqual(center.status_code, 200)
        self.assertContains(center, "Staff System Notice")
        self.assertNotContains(center, "Payment Receipt Issued")

        read_all = staff_client.post("/notifications/read-all/")
        self.assertEqual(read_all.status_code, 302)
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.subject_teacher,
                category=NotificationCategory.SYSTEM,
                read_at__isnull=True,
            ).count(),
            0,
        )
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.subject_teacher,
                category=NotificationCategory.PAYMENT,
                read_at__isnull=True,
            ).count(),
            1,
        )

        Notification.objects.create(
            recipient=self.bursar_user,
            category=NotificationCategory.PAYMENT,
            title="Bursar Payment Notice",
            message="Visible to bursar role.",
        )
        bursar_client = self._client("bursar.ndgakuje.org", self.bursar_user)
        bursar_center = bursar_client.get("/notifications/center/")
        self.assertEqual(bursar_center.status_code, 200)
        self.assertContains(bursar_center, "Bursar Payment Notice")

    def test_payment_notification_detail_resolves_legacy_dashboard_link(self):
        notice = Notification.objects.create(
            recipient=self.student,
            category=NotificationCategory.PAYMENT,
            title="Legacy Payment",
            message="Open payment page.",
            action_url="/portal/student/",
        )
        client = self._client("student.ndgakuje.org", self.student)
        response = client.get(f"/notifications/detail/{notice.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/portal/student/finance/")

    @override_settings(
        NOTIFICATIONS_EMAIL_REPLY_ENABLED=True,
        NOTIFICATIONS_REPLY_DOMAIN="reply.ndgakuje.org",
    )
    def test_send_email_event_with_replies_creates_thread_and_outbound_message(self):
        result = send_email_event(
            to_emails=["parent.one@example.com"],
            subject="Admission Update",
            body_text="Please review the attached school notice.",
            actor=self.vp_user,
            enable_replies=True,
            reply_thread_scope=EmailThreadScope.GENERAL,
            metadata={"event": "TEST_REPLY_THREAD"},
        )

        self.assertTrue(result.success)
        thread = EmailReplyThread.objects.get(recipient_email="parent.one@example.com")
        self.assertEqual(thread.scope, EmailThreadScope.GENERAL)
        self.assertTrue(thread.reply_to_email.endswith("@reply.ndgakuje.org"))
        self.assertTrue(
            EmailReplyMessage.objects.filter(
                thread=thread,
                direction=EmailReplyMessageDirection.OUTBOUND,
                subject="Admission Update",
            ).exists()
        )

    @override_settings(
        NOTIFICATIONS_EMAIL_REPLY_ENABLED=True,
        NOTIFICATIONS_REPLY_DOMAIN="reply.ndgakuje.org",
        BREVO_INBOUND_WEBHOOK_BEARER_TOKEN="reply-token",
    )
    def test_brevo_inbound_webhook_ingests_parent_reply(self):
        thread = EmailReplyThread.objects.create(
            thread_key="replyabc123",
            scope=EmailThreadScope.GENERAL,
            subject="Principal Memo",
            recipient_email="guardian@example.com",
            recipient_label="Guardian",
            reply_to_email="thread-replyabc123@reply.ndgakuje.org",
            created_by=self.vp_user,
        )
        EmailReplyMessage.objects.create(
            thread=thread,
            direction=EmailReplyMessageDirection.OUTBOUND,
            provider="console",
            external_message_id="msg-001",
            sender_email="office@ndgakuje.org",
            recipient_email="guardian@example.com",
            subject="Principal Memo",
            body_text="Initial memo",
            created_by=self.vp_user,
        )

        client = Client(HTTP_HOST="ndgakuje.org")
        response = client.post(
            "/notifications/webhooks/brevo/inbound/",
            data=json.dumps(
                {
                    "items": [
                        {
                            "MessageId": "reply-001",
                            "InReplyTo": "msg-001",
                            "Subject": "Re: Principal Memo",
                            "RawTextBody": "Thank you, we have received the memo.",
                            "ExtractedMarkdownMessage": "Thank you, we have received the memo.",
                            "SentAtDate": "Fri, 17 Apr 2026 10:20:00 +0100",
                            "From": {"Address": "guardian@example.com", "Name": "Guardian"},
                            "To": [{"Address": "thread-replyabc123@reply.ndgakuje.org", "Name": "NDGA"}],
                            "Attachments": [],
                            "Headers": {},
                        }
                    ]
                }
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer reply-token",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ingested"], 1)
        thread.refresh_from_db()
        self.assertIsNotNone(thread.last_inbound_at)
        self.assertTrue(
            EmailReplyMessage.objects.filter(
                thread=thread,
                direction=EmailReplyMessageDirection.INBOUND,
                external_message_id="reply-001",
                sender_email="guardian@example.com",
            ).exists()
        )

    @override_settings(
        NOTIFICATIONS_EMAIL_REPLY_ENABLED=True,
        NOTIFICATIONS_REPLY_DOMAIN="reply.ndgakuje.org",
    )
    def test_bursar_can_open_finance_reply_thread(self):
        thread = EmailReplyThread.objects.create(
            thread_key="finance123",
            scope=EmailThreadScope.FINANCE,
            subject="Finance Notice",
            recipient_email="finance.parent@example.com",
            recipient_label="Finance Parent",
            reply_to_email="thread-finance123@reply.ndgakuje.org",
            created_by=self.bursar_user,
        )
        EmailReplyMessage.objects.create(
            thread=thread,
            direction=EmailReplyMessageDirection.OUTBOUND,
            provider="console",
            sender_email="office@ndgakuje.org",
            recipient_email="finance.parent@example.com",
            subject="Finance Notice",
            body_text="School fees reminder.",
            created_by=self.bursar_user,
        )

        client = self._client("bursar.ndgakuje.org", self.bursar_user)
        response = client.get(f"/notifications/replies/{thread.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Finance Notice")
        self.assertContains(response, "Finance Parent")

    @override_settings(
        WHATSAPP_PROVIDER="meta_cloud",
        WHATSAPP_ACCESS_TOKEN="token",
        WHATSAPP_PHONE_NUMBER_ID="123456",
    )
    @patch("apps.notifications.whatsapp_adapters.MetaWhatsAppCloudProvider.send")
    def test_send_whatsapp_event_logs_success(self, mocked_send):
        mocked_send.return_value = WhatsAppSendResult(
            success=True,
            provider="meta_cloud",
            detail="status=200",
            message_id="wamid-001",
        )
        result = send_whatsapp_event(
            to_numbers=["08011111111"],
            body_text="Leadership message",
            actor=self.vp_user,
        )
        self.assertTrue(result.success)
        self.assertEqual(result.sent_count, 1)
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="WHATSAPP_EVENT",
                status="SUCCESS",
                metadata__sent_count=1,
            ).exists()
        )


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    NOTIFICATIONS_EMAIL_PROVIDER="console",
)
class AssignmentDeadlineNotificationScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        student_role = Role.objects.get(code=ROLE_STUDENT)
        subject_role = Role.objects.get(code=ROLE_SUBJECT_TEACHER)

        cls.teacher = User.objects.create_user(
            username="assignment-teacher",
            password="Password123!",
            primary_role=subject_role,
            must_change_password=False,
        )
        cls.current_student = User.objects.create_user(
            username="assignment-current",
            password="Password123!",
            primary_role=student_role,
            email="current.student@example.com",
            must_change_password=False,
        )
        cls.other_session_student = User.objects.create_user(
            username="assignment-other",
            password="Password123!",
            primary_role=student_role,
            email="other.student@example.com",
            must_change_password=False,
        )
        StudentProfile.objects.create(
            user=cls.current_student,
            student_number="NDGAK/27/101",
            guardian_email="current.parent@example.com",
        )
        StudentProfile.objects.create(
            user=cls.other_session_student,
            student_number="NDGAK/28/101",
            guardian_email="other.parent@example.com",
        )

        cls.session = AcademicSession.objects.create(name="2027/2028")
        cls.other_session = AcademicSession.objects.create(name="2028/2029")
        cls.term = Term.objects.create(session=cls.session, name="FIRST")
        cls.other_term = Term.objects.create(session=cls.other_session, name="FIRST")
        cls.academic_class = AcademicClass.objects.create(code="JS3-NOTIFY", display_name="JS3 Notify")
        cls.subject = Subject.objects.create(name="Civic Education Notify", code="CIV-NOTIFY")
        ClassSubject.objects.create(academic_class=cls.academic_class, subject=cls.subject)

        StudentClassEnrollment.objects.create(
            student=cls.current_student,
            academic_class=cls.academic_class,
            session=cls.session,
            is_active=True,
        )
        StudentClassEnrollment.objects.create(
            student=cls.other_session_student,
            academic_class=cls.academic_class,
            session=cls.other_session,
            is_active=True,
        )
        StudentSubjectEnrollment.objects.create(
            student=cls.current_student,
            subject=cls.subject,
            session=cls.session,
            is_active=True,
        )
        StudentSubjectEnrollment.objects.create(
            student=cls.other_session_student,
            subject=cls.subject,
            session=cls.other_session,
            is_active=True,
        )

    def test_assignment_deadline_notifies_only_students_in_selected_session(self):
        notify_assignment_deadline(
            academic_class=self.academic_class,
            subject=self.subject,
            topic="Essay Writing",
            due_date=None,
            session=self.session,
            actor=self.teacher,
        )

        self.assertTrue(
            Notification.objects.filter(
                recipient=self.current_student,
                title__icontains="Assignment Deadline",
            ).exists()
        )
        self.assertFalse(
            Notification.objects.filter(
                recipient=self.other_session_student,
                title__icontains="Assignment Deadline",
            ).exists()
        )
