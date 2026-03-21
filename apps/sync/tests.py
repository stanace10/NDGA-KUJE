import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.utils import ProgrammingError
from django.test import Client, TestCase, override_settings

from apps.accounts.constants import ROLE_IT_MANAGER, ROLE_STUDENT, ROLE_SUBJECT_TEACHER
from apps.accounts.models import Role, StudentProfile, User
from apps.academics.models import (
    AcademicClass,
    AcademicSession,
    ClassSubject,
    StudentClassEnrollment,
    StudentSubjectEnrollment,
    Subject,
    Term,
)
from apps.elections.models import Election, ElectionStatus, VoterGroup
from apps.setup_wizard.models import SetupStateCode, SystemSetupState
from apps.sync.models import (
    SyncContentChange,
    SyncContentObjectType,
    SyncContentStream,
    SyncConflictRule,
    SyncModelBinding,
    SyncOperationType,
    SyncPullCursor,
    SyncQueue,
    SyncQueueEvent,
    SyncQueueStatus,
    SyncTransferBatch,
)
from apps.sync.inbound_sync import ingest_remote_outbox_event
from apps.sync.services import (
    export_sync_queue_snapshot,
    get_runtime_status,
    import_sync_queue_snapshot,
    process_queue_row,
    pull_remote_outbox_updates,
    ready_queue_queryset,
    queue_student_registration_sync,
    queue_sync_operation,
    queue_vote_submission_sync,
)
from apps.sync.content_sync import register_cbt_content_change
from apps.sync.model_sync import apply_generic_model_payload
from apps.sync.models import SyncContentOperation


SYNC_TEST_HOST_SETTINGS = {
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


@override_settings(**SYNC_TEST_HOST_SETTINGS)
class SyncServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.role_it = Role.objects.get(code=ROLE_IT_MANAGER)
        cls.it_user = User.objects.create_user(
            username="sync-it",
            password="Password123!",
            primary_role=cls.role_it,
            must_change_password=False,
        )
        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.save(update_fields=["state", "updated_at"])

    def setUp(self):
        SyncQueue.objects.all().delete()
        SyncContentChange.objects.all().delete()
        SyncPullCursor.objects.all().delete()
        SyncTransferBatch.objects.all().delete()
        SyncModelBinding.objects.all().delete()

    def test_idempotency_key_prevents_duplicate_queue_rows(self):
        payload = {"attempt_id": "101", "status": "SUBMITTED"}
        first, created_first = queue_sync_operation(
            operation_type=SyncOperationType.CBT_EXAM_ATTEMPT,
            payload=payload,
            object_ref="attempt:101",
            idempotency_key="attempt-101-submitted",
        )
        second, created_second = queue_sync_operation(
            operation_type=SyncOperationType.CBT_EXAM_ATTEMPT,
            payload=payload,
            object_ref="attempt:101",
            idempotency_key="attempt-101-submitted",
        )
        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first.id, second.id)
        self.assertEqual(SyncQueue.objects.count(), 1)

    def test_vote_submission_uses_strict_unique_conflict_rule(self):
        queue_vote_submission_sync(
            election_id="e1",
            position_id="p1",
            voter_id="u1",
            payload={"candidate_id": "c1"},
            idempotency_key="vote-e1-p1-u1-c1",
        )
        with self.assertRaises(ValidationError):
            queue_vote_submission_sync(
                election_id="e1",
                position_id="p1",
                voter_id="u1",
                payload={"candidate_id": "c2"},
                idempotency_key="vote-e1-p1-u1-c2",
            )
        vote_row = SyncQueue.objects.get()
        self.assertEqual(vote_row.conflict_rule, SyncConflictRule.STRICT_UNIQUE)
        self.assertEqual(vote_row.conflict_key, "e1:p1:u1")

    def test_process_queue_without_cloud_endpoint_moves_to_retry(self):
        row, _ = queue_sync_operation(
            operation_type=SyncOperationType.CBT_EXAM_ATTEMPT,
            payload={"attempt_id": "200"},
            object_ref="attempt:200",
            idempotency_key="attempt-200",
            max_retries=1,
        )
        first = process_queue_row(row)
        row.refresh_from_db()
        self.assertTrue(first["processed"])
        self.assertEqual(row.status, SyncQueueStatus.RETRY)
        self.assertEqual(row.retry_count, 1)
        self.assertIsNotNone(row.next_retry_at)

        row.next_retry_at = None
        row.save(update_fields=["next_retry_at", "updated_at"])
        second = process_queue_row(row)
        row.refresh_from_db()
        self.assertTrue(second["processed"])
        self.assertEqual(row.status, SyncQueueStatus.FAILED)
        self.assertEqual(row.retry_count, 2)

    def test_export_and_import_snapshot_round_trip(self):
        queue_sync_operation(
            operation_type=SyncOperationType.CBT_EXAM_ATTEMPT,
            payload={"attempt_id": "301"},
            object_ref="attempt:301",
            idempotency_key="attempt-301",
        )
        queue_sync_operation(
            operation_type=SyncOperationType.CBT_SIMULATION_ATTEMPT,
            payload={"record_id": "401"},
            object_ref="simulation_record:401",
            idempotency_key="simulation-401",
        )
        exported = export_sync_queue_snapshot(actor=self.it_user)
        self.assertIn("queue", exported["json_text"])
        self.assertEqual(exported["item_count"], 2)

        SyncQueue.objects.all().delete()
        summary = import_sync_queue_snapshot(
            raw_json=exported["json_text"],
            actor=self.it_user,
        )
        self.assertEqual(summary["imported"], 2)
        self.assertEqual(SyncQueue.objects.count(), 2)

    @override_settings(
        FEATURE_FLAGS={**settings.FEATURE_FLAGS, "OFFLINE_MODE_ENABLED": True},
        SYNC_CLOUD_ENDPOINT="",
    )
    def test_runtime_status_switches_local_and_pending(self):
        status = get_runtime_status()
        self.assertEqual(status["code"], "LOCAL_MODE")
        queue_sync_operation(
            operation_type=SyncOperationType.CBT_EXAM_ATTEMPT,
            payload={"attempt_id": "777"},
            object_ref="attempt:777",
            idempotency_key="attempt-777",
        )
        status_pending = get_runtime_status()
        self.assertEqual(status_pending["code"], "SYNC_PENDING")
        self.assertEqual(status_pending["pending_count"], 1)

    def test_register_cbt_content_change_gracefully_handles_missing_table(self):
        fake_instance = SimpleNamespace(pk=55)
        with patch("apps.sync.content_sync._serialize_cbt_instance") as serializer, patch(
            "apps.sync.content_sync.SyncContentChange.objects.create",
            side_effect=ProgrammingError('relation "sync_synccontentchange" does not exist'),
        ):
            serializer.return_value = ("EXAM", {"id": 55, "title": "Physics"})
            result = register_cbt_content_change(
                instance=fake_instance,
                operation=SyncContentOperation.UPSERT,
            )
        self.assertIsNone(result)

    def test_ready_queue_prioritizes_dependency_rows_before_cbt_content(self):
        model_row, _ = queue_sync_operation(
            operation_type=SyncOperationType.MODEL_RECORD_UPSERT,
            payload={"model": "academics.academicsession", "identity": {"source_node_id": "lan", "source_pk": "1", "lookup": {"name": "2025/2026"}}},
            object_ref="academics.academicsession:lan:1",
            idempotency_key="model-first",
        )
        content_row, _ = queue_sync_operation(
            operation_type=SyncOperationType.CBT_CONTENT_CHANGE,
            payload={"id": 1, "stream": "CBT_CONTENT", "object_type": "EXAM", "operation": "UPSERT", "object_pk": "1", "payload": {}, "created_at": ""},
            object_ref="cbt-change:1",
            idempotency_key="content-second",
        )

        ordered_ids = list(ready_queue_queryset().values_list("id", flat=True)[:2])

        self.assertEqual(ordered_ids, [model_row.id, content_row.id])

    def test_dependency_503_stays_in_retry_without_consuming_max_retries(self):
        row, _ = queue_sync_operation(
            operation_type=SyncOperationType.CBT_CONTENT_CHANGE,
            payload={"id": 1},
            object_ref="cbt-change:1",
            idempotency_key="dependency-503-row",
            max_retries=1,
        )
        row.retry_count = 1
        row.save(update_fields=["retry_count", "updated_at"])

        with patch("apps.sync.services._dispatch_to_cloud") as dispatch:
            dispatch.return_value = {
                "ok": False,
                "deferred": False,
                "status_code": 503,
                "payload": {"ok": False, "detail": "Dependency unavailable. Retry later."},
                "error": "Dependency unavailable. Retry later.",
                "remote_reference": "",
            }
            result = process_queue_row(row)

        row.refresh_from_db()
        self.assertTrue(result["processed"])
        self.assertEqual(row.status, SyncQueueStatus.RETRY)
        self.assertEqual(row.retry_count, 1)
        self.assertIsNotNone(row.next_retry_at)

    def test_queue_student_registration_sync_serializes_profile_and_enrollment(self):
        role_student = Role.objects.get(code=ROLE_STUDENT)
        student = User.objects.create_user(
            username="sync-student@ndgakuje.org",
            password="Password123!",
            primary_role=role_student,
            must_change_password=False,
            email="guardian@example.com",
            first_name="Sync",
            last_name="Student",
        )
        StudentProfile.objects.create(
            user=student,
            student_number="NDGAK/26/900",
            guardian_email="guardian@example.com",
        )
        session = AcademicSession.objects.create(name="2025/2026")
        academic_class = AcademicClass.objects.create(code="JS1A", display_name="JS1A")
        subject = Subject.objects.create(name="Mathematics", code="MTH")
        ClassSubject.objects.create(academic_class=academic_class, subject=subject, is_active=True)
        StudentClassEnrollment.objects.create(
            student=student,
            academic_class=academic_class,
            session=session,
            is_active=True,
        )
        StudentSubjectEnrollment.objects.create(
            student=student,
            subject=subject,
            session=session,
            is_active=True,
        )

        row, created = queue_student_registration_sync(user=student, raw_password="admin")

        self.assertTrue(created)
        self.assertEqual(row.operation_type, SyncOperationType.STUDENT_REGISTRATION_UPSERT)
        self.assertEqual(row.payload["student_number"], "NDGAK/26/900")
        self.assertEqual(row.payload["current_class_code"], "JS1A")
        self.assertEqual(row.payload["subject_codes"], ["MTH"])
        self.assertEqual(row.payload["temporary_password"], "admin")

    def test_register_cbt_content_change_also_queues_outbox_row(self):
        fake_instance = SimpleNamespace(pk=77)
        with patch("apps.sync.content_sync._serialize_cbt_instance") as serializer:
            serializer.return_value = ("EXAM", {"id": 77, "title": "Physics"})
            register_cbt_content_change(instance=fake_instance, operation=SyncContentOperation.UPSERT)

        row = SyncQueue.objects.get(operation_type=SyncOperationType.CBT_CONTENT_CHANGE)
        self.assertEqual(row.payload["object_pk"], "77")
        self.assertEqual(row.payload["payload"]["title"], "Physics")


    def test_queue_timeline_events_track_status_changes(self):
        row, created = queue_sync_operation(
            operation_type=SyncOperationType.CBT_EXAM_ATTEMPT,
            payload={"attempt_id": "909"},
            object_ref="attempt:909",
            idempotency_key="attempt-909",
        )
        self.assertTrue(created)
        queued_event = SyncQueueEvent.objects.get(queue_row=row, event_type="QUEUED")
        self.assertEqual(queued_event.to_status, SyncQueueStatus.PENDING)

        process_queue_row(row)
        row.refresh_from_db()
        transition_event = SyncQueueEvent.objects.filter(
            queue_row=row,
            event_type="STATUS_TRANSITION",
        ).latest("id")
        self.assertEqual(transition_event.from_status, SyncQueueStatus.PENDING)
        self.assertEqual(transition_event.to_status, row.status)
        self.assertIn(row.status, {SyncQueueStatus.RETRY, SyncQueueStatus.FAILED})


@override_settings(**SYNC_TEST_HOST_SETTINGS)
class SyncDashboardAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.role_it = Role.objects.get(code=ROLE_IT_MANAGER)
        cls.role_teacher = Role.objects.get(code=ROLE_SUBJECT_TEACHER)
        cls.role_student = Role.objects.get(code=ROLE_STUDENT)

        cls.it_user = User.objects.create_user(
            username="sync-dashboard-it",
            password="Password123!",
            primary_role=cls.role_it,
            must_change_password=False,
            email="sync-dashboard-it@ndgakuje.org",
        )
        cls.teacher_user = User.objects.create_user(
            username="sync-dashboard-teacher",
            password="Password123!",
            primary_role=cls.role_teacher,
            must_change_password=False,
        )
        cls.student_user = User.objects.create_user(
            username="sync-dashboard-student",
            password="Password123!",
            primary_role=cls.role_student,
            must_change_password=False,
        )
        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.save(update_fields=["state", "updated_at"])

    def setUp(self):
        SyncQueue.objects.all().delete()

    def _login_staff(self, username, host="staff.ndgakuje.org"):
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

    def test_it_can_access_sync_dashboard(self):
        client = self._login_staff(self.it_user.username, host="it.ndgakuje.org")
        response = client.get("/sync/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sync Queue Dashboard")

    def test_teacher_is_redirected_from_sync_dashboard(self):
        client = self._login_staff(self.teacher_user.username, host="staff.ndgakuje.org")
        response = client.get("/sync/dashboard/")
        self.assertEqual(response.status_code, 302)

    def test_sync_import_rejects_executable_signature_payload(self):
        client = self._login_staff(self.it_user.username, host="it.ndgakuje.org")
        bad_json = SimpleUploadedFile(
            "snapshot.json",
            b"MZ\x90\x00\x03\x00\x00\x00",
            content_type="application/json",
        )
        response = client.post(
            "/sync/dashboard/",
            {"action": "import", "snapshot_file": bad_json},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Executable file signatures are blocked")


@override_settings(**SYNC_TEST_HOST_SETTINGS)
class SyncAPIEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.save(update_fields=["state", "updated_at"])
        SyncContentChange.objects.create(
            stream=SyncContentStream.CBT_CONTENT,
            object_type=SyncContentObjectType.EXAM,
            operation="UPSERT",
            object_pk="1",
            payload={"id": 1, "title": "Test Exam"},
            source_node_id="cloud-node",
        )

    def setUp(self):
        SyncQueue.objects.all().delete()
        SyncPullCursor.objects.all().delete()
        SyncModelBinding.objects.all().delete()

    @override_settings(SYNC_ENDPOINT_AUTH_TOKEN="sync-token")
    def test_content_feed_requires_bearer_token(self):
        client = Client(HTTP_HOST="it.ndgakuje.org")
        denied = client.get("/sync/api/content/cbt/")
        self.assertEqual(denied.status_code, 401)

        allowed = client.get(
            "/sync/api/content/cbt/",
            HTTP_AUTHORIZATION="Bearer sync-token",
        )
        self.assertEqual(allowed.status_code, 200)
        payload = allowed.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["changes"][0]["object_type"], SyncContentObjectType.EXAM)

    @override_settings(SYNC_ENDPOINT_AUTH_TOKEN="sync-token")
    def test_outbox_ingest_rejects_invalid_json(self):
        client = Client(HTTP_HOST="it.ndgakuje.org")
        response = client.post(
            "/sync/api/outbox/",
            data="not-json",
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer sync-token",
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(SYNC_ENDPOINT_AUTH_TOKEN="sync-token")
    def test_sync_api_status_exposes_queue_and_ops_summary(self):
        queue_sync_operation(
            operation_type=SyncOperationType.MODEL_RECORD_UPSERT,
            payload={"model": "academics.academicsession", "fields": {"name": "2026/2027"}},
            object_ref="academics.academicsession:1",
            idempotency_key="status-summary-row",
        )
        client = Client(HTTP_HOST="it.ndgakuje.org")
        response = client.get(
            "/sync/api/",
            HTTP_AUTHORIZATION="Bearer sync-token",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status_counts"]["PENDING"], 1)
        self.assertIn("ops_snapshot", payload)
        self.assertIn("celery", payload["ops_snapshot"])
        self.assertIn("cbt", payload["ops_snapshot"])

    def test_ops_metrics_endpoint_exposes_prometheus_text(self):
        queue_sync_operation(
            operation_type=SyncOperationType.MODEL_RECORD_UPSERT,
            payload={"model": "academics.academicsession", "fields": {"name": "2026/2027"}},
            object_ref="academics.academicsession:2",
            idempotency_key="metrics-row",
        )
        client = Client(HTTP_HOST="it.ndgakuje.org")
        response = client.get("/ops/metrics/")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("ndga_ready", body)
        self.assertIn('ndga_sync_queue_items{status="pending"}', body)

    @override_settings(SYNC_ENDPOINT_AUTH_TOKEN="sync-token")
    def test_outbox_ingest_applies_student_registration_payload(self):
        AcademicSession.objects.create(name="2025/2026")
        academic_class = AcademicClass.objects.create(code="JS2A", display_name="JS2A")
        subject = Subject.objects.create(name="English", code="ENG")
        ClassSubject.objects.create(academic_class=academic_class, subject=subject, is_active=True)

        client = Client(HTTP_HOST="it.ndgakuje.org")
        response = client.post(
            "/sync/api/outbox/",
            data=json.dumps({
                "idempotency_key": "student-sync-1",
                "operation_type": SyncOperationType.STUDENT_REGISTRATION_UPSERT,
                "payload": {
                    "student_number": "NDGAK/26/901",
                    "username": "ndgak-26-901@ndgakuje.org",
                    "temporary_password": "admin",
                    "email": "guardian@example.com",
                    "first_name": "Remote",
                    "last_name": "Student",
                    "guardian_email": "guardian@example.com",
                    "current_session_name": "2025/2026",
                    "current_class_code": "JS2A",
                    "subject_codes": ["ENG"],
                },
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer sync-token",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(StudentProfile.objects.filter(student_number="NDGAK/26/901").exists())
        synced_user = User.objects.get(username="ndgak-26-901@ndgakuje.org")
        self.assertTrue(StudentClassEnrollment.objects.filter(student=synced_user, academic_class=academic_class).exists())


    @override_settings(SYNC_ENDPOINT_AUTH_TOKEN="sync-token")
    def test_outbox_feed_filters_by_origin_node(self):
        queue_sync_operation(
            operation_type=SyncOperationType.MODEL_RECORD_UPSERT,
            payload={"model": "academics.academicsession", "identity": {"source_node_id": "cloud-node", "source_pk": "1"}},
            object_ref="academics.academicsession:cloud-node:1",
            idempotency_key="feed-cloud-row",
            local_node_id="cloud-node",
        )
        queue_sync_operation(
            operation_type=SyncOperationType.MODEL_RECORD_UPSERT,
            payload={"model": "academics.academicsession", "identity": {"source_node_id": "other-node", "source_pk": "2"}},
            object_ref="academics.academicsession:other-node:2",
            idempotency_key="feed-other-row",
            local_node_id="other-node",
        )

        client = Client(HTTP_HOST="it.ndgakuje.org")
        response = client.get(
            "/sync/api/outbox/feed/?exclude_origin_node_id=cloud-node",
            HTTP_AUTHORIZATION="Bearer sync-token",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["events"][0]["idempotency_key"], "feed-other-row")


    @override_settings(
        SYNC_ENDPOINT_AUTH_TOKEN="sync-token",
        SYNC_NODE_ROLE="LAN",
        SYNC_ENFORCE_ACTIVE_SESSION_AUTHORITY=True,
    )
    def test_outbox_ingest_retries_remote_vote_when_lan_election_is_open(self):
        session = AcademicSession.objects.create(name="2026/2027")
        election = Election.objects.create(
            title="LAN Election",
            session=session,
            status=ElectionStatus.OPEN,
        )

        client = Client(HTTP_HOST="it.ndgakuje.org")
        response = client.post(
            "/sync/api/outbox/",
            data=json.dumps({
                "idempotency_key": "remote-vote-open-lan",
                "operation_type": SyncOperationType.ELECTION_VOTE_SUBMISSION,
                "object_ref": f"vote:{election.id}:11:12",
                "conflict_key": f"{election.id}:11:12",
                "local_node_id": "cloud-node",
                "payload": {
                    "candidate_id": "99",
                    "submitted_at": "2026-03-08T08:30:00+00:00",
                },
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer sync-token",
        )
        self.assertEqual(response.status_code, 503)
        row = SyncQueue.objects.get(idempotency_key="remote-vote-open-lan")
        self.assertEqual(row.status, SyncQueueStatus.RETRY)



@override_settings(**SYNC_TEST_HOST_SETTINGS)
class GenericModelSyncTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.role_it = Role.objects.get(code=ROLE_IT_MANAGER)
        cls.role_student = Role.objects.get(code=ROLE_STUDENT)
        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.save(update_fields=["state", "updated_at"])

    def setUp(self):
        SyncQueue.objects.all().delete()
        SyncModelBinding.objects.all().delete()
        SyncPullCursor.objects.all().delete()

    def test_generic_post_save_and_delete_capture_queue_rows(self):
        SyncQueue.objects.all().delete()

        with self.captureOnCommitCallbacks(execute=True):
            session = AcademicSession.objects.create(name="2026/2027")

        upsert_row = SyncQueue.objects.get(operation_type=SyncOperationType.MODEL_RECORD_UPSERT)
        self.assertEqual(upsert_row.payload["model"], "academics.academicsession")
        self.assertEqual(upsert_row.payload["fields"]["name"], "2026/2027")

        session_pk = session.pk
        SyncQueue.objects.all().delete()
        with self.captureOnCommitCallbacks(execute=True):
            session.delete()

        delete_row = SyncQueue.objects.get(operation_type=SyncOperationType.MODEL_RECORD_DELETE)
        self.assertEqual(delete_row.payload["model"], "academics.academicsession")
        self.assertEqual(delete_row.payload["identity"]["source_pk"], str(session_pk))

    def test_generic_m2m_capture_updates_user_secondary_roles(self):
        user = User.objects.create_user(
            username="generic-m2m-user",
            password="Password123!",
            primary_role=self.role_student,
            must_change_password=False,
        )
        SyncQueue.objects.all().delete()

        with self.captureOnCommitCallbacks(execute=True):
            user.secondary_roles.add(self.role_it)

        row = SyncQueue.objects.get(operation_type=SyncOperationType.MODEL_RECORD_UPSERT)
        self.assertEqual(row.payload["model"], "accounts.user")
        secondary_role_codes = sorted(
            role_payload["lookup"]["code"]
            for role_payload in row.payload["m2m"]["secondary_roles"]
        )
        self.assertEqual(secondary_role_codes, [ROLE_IT_MANAGER])

    def test_apply_generic_model_payload_allows_nullable_foreign_key(self):
        payload = {
            "model": "accounts.user",
            "identity": {
                "model": "accounts.user",
                "source_node_id": "cloud-node",
                "source_pk": "user-null-role",
                "lookup": {"username": "nullable-role-user"},
            },
            "fields": {
                "username": "nullable-role-user",
                "password": "!",
                "first_name": "Null",
                "last_name": "Role",
                "email": "",
                "display_name": "",
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
                "must_change_password": False,
                "password_changed_count": 0,
                "two_factor_enabled": False,
                "two_factor_email": "",
                "login_code_hash": "",
                "login_code_expires_at": None,
                "last_login": None,
                "primary_role": None,
                "date_joined": "2026-03-11T22:27:26.858076+00:00",
                "permission_scopes": [],
            },
            "m2m": {"secondary_roles": []},
            "created_at": "",
            "updated_at": "",
        }

        result = apply_generic_model_payload(
            payload=payload,
            operation_type=SyncOperationType.MODEL_RECORD_UPSERT,
        )

        synced_user = User.objects.get(username="nullable-role-user")
        self.assertIsNone(synced_user.primary_role)
        self.assertIn("accounts.user", result["reference"])

    def test_apply_generic_model_payload_materializes_missing_result_sheet_dependency(self):
        from apps.results.models import ResultSheet, StudentSubjectScore

        session = AcademicSession.objects.create(name="2025/2026")
        term = Term.objects.create(session=session, name="SECOND")
        academic_class = AcademicClass.objects.create(code="JS3", display_name="JS3")
        subject = Subject.objects.create(name="Social Studies", code="SST")
        student = User.objects.create_user(
            username="ndgak-23-260@ndgakuje.org",
            password="Password123!",
            primary_role=self.role_student,
            must_change_password=False,
        )

        payload = {
            "model": "results.studentsubjectscore",
            "identity": {
                "model": "results.studentsubjectscore",
                "source_node_id": "ndga-lan-node",
                "source_pk": "82",
                "lookup": {
                    "student": {
                        "model": "accounts.user",
                        "source_node_id": "ndga-lan-node",
                        "source_pk": "99",
                        "lookup": {"username": student.username},
                    },
                    "result_sheet": {
                        "model": "results.resultsheet",
                        "source_node_id": "ndga-lan-node",
                        "source_pk": "4",
                        "lookup": {
                            "academic_class": {
                                "model": "academics.academicclass",
                                "source_node_id": "ndga-lan-node",
                                "source_pk": "7",
                                "lookup": {"code": academic_class.code},
                            },
                            "subject": {
                                "model": "academics.subject",
                                "source_node_id": "ndga-lan-node",
                                "source_pk": "28",
                                "lookup": {"code": subject.code},
                            },
                            "session": {
                                "model": "academics.academicsession",
                                "source_node_id": "ndga-lan-node",
                                "source_pk": "1",
                                "lookup": {"name": session.name},
                            },
                            "term": {
                                "model": "academics.term",
                                "source_node_id": "ndga-lan-node",
                                "source_pk": "1",
                                "lookup": {
                                    "name": term.name,
                                    "session": {
                                        "model": "academics.academicsession",
                                        "source_node_id": "ndga-lan-node",
                                        "source_pk": "1",
                                        "lookup": {"name": session.name},
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "fields": {
                "result_sheet": {
                    "model": "results.resultsheet",
                    "source_node_id": "ndga-lan-node",
                    "source_pk": "4",
                    "lookup": {
                        "academic_class": {
                            "model": "academics.academicclass",
                            "source_node_id": "ndga-lan-node",
                            "source_pk": "7",
                            "lookup": {"code": academic_class.code},
                        },
                        "subject": {
                            "model": "academics.subject",
                            "source_node_id": "ndga-lan-node",
                            "source_pk": "28",
                            "lookup": {"code": subject.code},
                        },
                        "session": {
                            "model": "academics.academicsession",
                            "source_node_id": "ndga-lan-node",
                            "source_pk": "1",
                            "lookup": {"name": session.name},
                        },
                        "term": {
                            "model": "academics.term",
                            "source_node_id": "ndga-lan-node",
                            "source_pk": "1",
                            "lookup": {
                                "name": term.name,
                                "session": {
                                    "model": "academics.academicsession",
                                    "source_node_id": "ndga-lan-node",
                                    "source_pk": "1",
                                    "lookup": {"name": session.name},
                                },
                            },
                        },
                    },
                },
                "student": {
                    "model": "accounts.user",
                    "source_node_id": "ndga-lan-node",
                    "source_pk": "99",
                    "lookup": {"username": student.username},
                },
                "ca1": "0.00",
                "ca2": "10.00",
                "ca3": "0.00",
                "ca4": "0.00",
                "objective": "0.00",
                "theory": "0.00",
                "total_ca": "10.00",
                "total_exam": "0.00",
                "grand_total": "10.00",
                "grade": "F",
                "has_override": False,
                "override_reason": "",
                "cbt_locked_fields": ["ca2"],
                "cbt_component_breakdown": {"ca2_objective": "10.00"},
                "override_by": None,
                "override_at": None,
            },
            "m2m": {},
            "created_at": "2026-03-12T11:12:57.723517+00:00",
            "updated_at": "2026-03-13T11:39:56.342828+00:00",
        }

        result = apply_generic_model_payload(
            payload=payload,
            operation_type=SyncOperationType.MODEL_RECORD_UPSERT,
        )

        result_sheet = ResultSheet.objects.get(
            academic_class=academic_class,
            subject=subject,
            session=session,
            term=term,
        )
        score = StudentSubjectScore.objects.get(result_sheet=result_sheet, student=student)
        self.assertEqual(score.ca2, Decimal("10.00"))
        self.assertEqual(score.grade, "F")
        self.assertIn("results.studentsubjectscore", result["reference"])

    @override_settings(SYNC_NODE_ROLE="CLOUD", SYNC_LOCAL_NODE_ID="ndga-cloud-node")
    def test_cloud_preserves_manual_result_fields_when_lan_pushes_cbt_score(self):
        from apps.results.models import ResultSheet, StudentSubjectScore

        session = AcademicSession.objects.create(name="2025/2026")
        term = Term.objects.create(session=session, name="SECOND")
        academic_class = AcademicClass.objects.create(code="SS2", display_name="SS2")
        subject = Subject.objects.create(name="Chemistry", code="CHM")
        student = User.objects.create_user(
            username="result-merge-cloud-student",
            password="Password123!",
            primary_role=self.role_student,
            must_change_password=False,
        )
        result_sheet = ResultSheet.objects.create(
            academic_class=academic_class,
            subject=subject,
            session=session,
            term=term,
        )
        score = StudentSubjectScore.objects.create(
            result_sheet=result_sheet,
            student=student,
            ca2=Decimal("0.00"),
            ca3=Decimal("8.00"),
            objective=Decimal("0.00"),
            theory=Decimal("31.50"),
            cbt_component_breakdown={"ca3_theory": "8.00"},
        )

        payload = {
            "model": "results.studentsubjectscore",
            "identity": {
                "model": "results.studentsubjectscore",
                "source_node_id": "ndga-lan-node",
                "source_pk": "score-merge-1",
                "lookup": {
                    "student": {
                        "model": "accounts.user",
                        "source_node_id": "ndga-lan-node",
                        "source_pk": "student-1",
                        "lookup": {"username": student.username},
                    },
                    "result_sheet": {
                        "model": "results.resultsheet",
                        "source_node_id": "ndga-lan-node",
                        "source_pk": "sheet-1",
                        "lookup": {
                            "academic_class": {
                                "model": "academics.academicclass",
                                "source_node_id": "ndga-lan-node",
                                "source_pk": "class-1",
                                "lookup": {"code": academic_class.code},
                            },
                            "subject": {
                                "model": "academics.subject",
                                "source_node_id": "ndga-lan-node",
                                "source_pk": "subject-1",
                                "lookup": {"code": subject.code},
                            },
                            "session": {
                                "model": "academics.academicsession",
                                "source_node_id": "ndga-lan-node",
                                "source_pk": "session-1",
                                "lookup": {"name": session.name},
                            },
                            "term": {
                                "model": "academics.term",
                                "source_node_id": "ndga-lan-node",
                                "source_pk": "term-1",
                                "lookup": {
                                    "name": term.name,
                                    "session": {
                                        "model": "academics.academicsession",
                                        "source_node_id": "ndga-lan-node",
                                        "source_pk": "session-1",
                                        "lookup": {"name": session.name},
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "fields": {
                "result_sheet": {
                    "model": "results.resultsheet",
                    "source_node_id": "ndga-lan-node",
                    "source_pk": "sheet-1",
                    "lookup": {
                        "academic_class": {
                            "model": "academics.academicclass",
                            "source_node_id": "ndga-lan-node",
                            "source_pk": "class-1",
                            "lookup": {"code": academic_class.code},
                        },
                        "subject": {
                            "model": "academics.subject",
                            "source_node_id": "ndga-lan-node",
                            "source_pk": "subject-1",
                            "lookup": {"code": subject.code},
                        },
                        "session": {
                            "model": "academics.academicsession",
                            "source_node_id": "ndga-lan-node",
                            "source_pk": "session-1",
                            "lookup": {"name": session.name},
                        },
                        "term": {
                            "model": "academics.term",
                            "source_node_id": "ndga-lan-node",
                            "source_pk": "term-1",
                            "lookup": {
                                "name": term.name,
                                "session": {
                                    "model": "academics.academicsession",
                                    "source_node_id": "ndga-lan-node",
                                    "source_pk": "session-1",
                                    "lookup": {"name": session.name},
                                },
                            },
                        },
                    },
                },
                "student": {
                    "model": "accounts.user",
                    "source_node_id": "ndga-lan-node",
                    "source_pk": "student-1",
                    "lookup": {"username": student.username},
                },
                "ca1": "0.00",
                "ca2": "9.50",
                "ca3": "0.00",
                "ca4": "0.00",
                "objective": "38.00",
                "theory": "0.00",
                "total_ca": "9.50",
                "total_exam": "38.00",
                "grand_total": "47.50",
                "grade": "F",
                "has_override": False,
                "override_reason": "",
                "cbt_locked_fields": ["ca2", "objective"],
                "cbt_component_breakdown": {
                    "ca2_objective": "9.50",
                    "objective_auto": "38.00",
                },
                "override_by": None,
                "override_at": None,
            },
            "m2m": {},
            "created_at": "",
            "updated_at": "",
        }

        apply_generic_model_payload(
            payload=payload,
            operation_type=SyncOperationType.MODEL_RECORD_UPSERT,
        )

        score.refresh_from_db()
        self.assertEqual(score.ca2, Decimal("9.50"))
        self.assertEqual(score.objective, Decimal("38.00"))
        self.assertEqual(score.ca3, Decimal("8.00"))
        self.assertEqual(score.theory, Decimal("31.50"))

    @override_settings(SYNC_NODE_ROLE="LAN", SYNC_LOCAL_NODE_ID="ndga-lan-node")
    def test_lan_preserves_cbt_score_fields_when_cloud_pushes_manual_theory(self):
        from apps.results.models import ResultSheet, StudentSubjectScore

        session = AcademicSession.objects.create(name="2025/2026")
        term = Term.objects.create(session=session, name="SECOND")
        academic_class = AcademicClass.objects.create(code="SS3", display_name="SS3")
        subject = Subject.objects.create(name="Biology", code="BIO")
        student = User.objects.create_user(
            username="result-merge-lan-student",
            password="Password123!",
            primary_role=self.role_student,
            must_change_password=False,
        )
        result_sheet = ResultSheet.objects.create(
            academic_class=academic_class,
            subject=subject,
            session=session,
            term=term,
        )
        score = StudentSubjectScore.objects.create(
            result_sheet=result_sheet,
            student=student,
            ca2=Decimal("9.50"),
            objective=Decimal("38.00"),
            cbt_locked_fields=["ca2", "objective"],
            cbt_component_breakdown={"ca2_objective": "9.50", "objective_auto": "38.00"},
        )

        payload = {
            "model": "results.studentsubjectscore",
            "identity": {
                "model": "results.studentsubjectscore",
                "source_node_id": "ndga-cloud-node",
                "source_pk": "score-cloud-1",
                "lookup": {
                    "student": {
                        "model": "accounts.user",
                        "source_node_id": "ndga-cloud-node",
                        "source_pk": "student-1",
                        "lookup": {"username": student.username},
                    },
                    "result_sheet": {
                        "model": "results.resultsheet",
                        "source_node_id": "ndga-cloud-node",
                        "source_pk": "sheet-1",
                        "lookup": {
                            "academic_class": {
                                "model": "academics.academicclass",
                                "source_node_id": "ndga-cloud-node",
                                "source_pk": "class-1",
                                "lookup": {"code": academic_class.code},
                            },
                            "subject": {
                                "model": "academics.subject",
                                "source_node_id": "ndga-cloud-node",
                                "source_pk": "subject-1",
                                "lookup": {"code": subject.code},
                            },
                            "session": {
                                "model": "academics.academicsession",
                                "source_node_id": "ndga-cloud-node",
                                "source_pk": "session-1",
                                "lookup": {"name": session.name},
                            },
                            "term": {
                                "model": "academics.term",
                                "source_node_id": "ndga-cloud-node",
                                "source_pk": "term-1",
                                "lookup": {
                                    "name": term.name,
                                    "session": {
                                        "model": "academics.academicsession",
                                        "source_node_id": "ndga-cloud-node",
                                        "source_pk": "session-1",
                                        "lookup": {"name": session.name},
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "fields": {
                "result_sheet": {
                    "model": "results.resultsheet",
                    "source_node_id": "ndga-cloud-node",
                    "source_pk": "sheet-1",
                    "lookup": {
                        "academic_class": {
                            "model": "academics.academicclass",
                            "source_node_id": "ndga-cloud-node",
                            "source_pk": "class-1",
                            "lookup": {"code": academic_class.code},
                        },
                        "subject": {
                            "model": "academics.subject",
                            "source_node_id": "ndga-cloud-node",
                            "source_pk": "subject-1",
                            "lookup": {"code": subject.code},
                        },
                        "session": {
                            "model": "academics.academicsession",
                            "source_node_id": "ndga-cloud-node",
                            "source_pk": "session-1",
                            "lookup": {"name": session.name},
                        },
                        "term": {
                            "model": "academics.term",
                            "source_node_id": "ndga-cloud-node",
                            "source_pk": "term-1",
                            "lookup": {
                                "name": term.name,
                                "session": {
                                    "model": "academics.academicsession",
                                    "source_node_id": "ndga-cloud-node",
                                    "source_pk": "session-1",
                                    "lookup": {"name": session.name},
                                },
                            },
                        },
                    },
                },
                "student": {
                    "model": "accounts.user",
                    "source_node_id": "ndga-cloud-node",
                    "source_pk": "student-1",
                    "lookup": {"username": student.username},
                },
                "ca1": "0.00",
                "ca2": "0.00",
                "ca3": "8.00",
                "ca4": "0.00",
                "objective": "0.00",
                "theory": "31.50",
                "total_ca": "8.00",
                "total_exam": "31.50",
                "grand_total": "39.50",
                "grade": "F",
                "has_override": False,
                "override_reason": "",
                "cbt_locked_fields": [],
                "cbt_component_breakdown": {"ca3_theory": "8.00"},
                "override_by": None,
                "override_at": None,
            },
            "m2m": {},
            "created_at": "",
            "updated_at": "",
        }

        apply_generic_model_payload(
            payload=payload,
            operation_type=SyncOperationType.MODEL_RECORD_UPSERT,
        )

        score.refresh_from_db()
        self.assertEqual(score.ca2, Decimal("9.50"))
        self.assertEqual(score.objective, Decimal("38.00"))
        self.assertEqual(score.ca3, Decimal("8.00"))
        self.assertEqual(score.theory, Decimal("31.50"))

    @override_settings(SYNC_NODE_ROLE="CLOUD", SYNC_LOCAL_NODE_ID="ndga-cloud-node")
    def test_cloud_preserves_manual_ca_fields_when_lan_pushes_only_cbt_components(self):
        from apps.results.models import ResultSheet, StudentSubjectScore

        session = AcademicSession.objects.create(name="2025/2026")
        term = Term.objects.create(session=session, name="SECOND")
        academic_class = AcademicClass.objects.create(code="SS2B", display_name="SS2B")
        subject = Subject.objects.create(name="Physics", code="PHY2")
        student = User.objects.create_user(
            username="result-merge-cloud-manual-student",
            password="Password123!",
            primary_role=self.role_student,
            must_change_password=False,
        )
        result_sheet = ResultSheet.objects.create(
            academic_class=academic_class,
            subject=subject,
            session=session,
            term=term,
        )
        score = StudentSubjectScore.objects.create(
            result_sheet=result_sheet,
            student=student,
            ca1=Decimal("7.50"),
            ca2=Decimal("0.00"),
            ca3=Decimal("8.00"),
            ca4=Decimal("4.50"),
            objective=Decimal("0.00"),
            theory=Decimal("31.50"),
        )

        payload = {
            "model": "results.studentsubjectscore",
            "identity": {
                "model": "results.studentsubjectscore",
                "source_node_id": "ndga-lan-node",
                "source_pk": "score-merge-2",
                "lookup": {
                    "student": {
                        "model": "accounts.user",
                        "source_node_id": "ndga-lan-node",
                        "source_pk": "student-2",
                        "lookup": {"username": student.username},
                    },
                    "result_sheet": {
                        "model": "results.resultsheet",
                        "source_node_id": "ndga-lan-node",
                        "source_pk": "sheet-2",
                        "lookup": {
                            "academic_class": {
                                "model": "academics.academicclass",
                                "source_node_id": "ndga-lan-node",
                                "source_pk": "class-2",
                                "lookup": {"code": academic_class.code},
                            },
                            "subject": {
                                "model": "academics.subject",
                                "source_node_id": "ndga-lan-node",
                                "source_pk": "subject-2",
                                "lookup": {"code": subject.code},
                            },
                            "session": {
                                "model": "academics.academicsession",
                                "source_node_id": "ndga-lan-node",
                                "source_pk": "session-2",
                                "lookup": {"name": session.name},
                            },
                            "term": {
                                "model": "academics.term",
                                "source_node_id": "ndga-lan-node",
                                "source_pk": "term-2",
                                "lookup": {
                                    "name": term.name,
                                    "session": {
                                        "model": "academics.academicsession",
                                        "source_node_id": "ndga-lan-node",
                                        "source_pk": "session-2",
                                        "lookup": {"name": session.name},
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "fields": {
                "result_sheet": {
                    "model": "results.resultsheet",
                    "source_node_id": "ndga-lan-node",
                    "source_pk": "sheet-2",
                    "lookup": {
                        "academic_class": {
                            "model": "academics.academicclass",
                            "source_node_id": "ndga-lan-node",
                            "source_pk": "class-2",
                            "lookup": {"code": academic_class.code},
                        },
                        "subject": {
                            "model": "academics.subject",
                            "source_node_id": "ndga-lan-node",
                            "source_pk": "subject-2",
                            "lookup": {"code": subject.code},
                        },
                        "session": {
                            "model": "academics.academicsession",
                            "source_node_id": "ndga-lan-node",
                            "source_pk": "session-2",
                            "lookup": {"name": session.name},
                        },
                        "term": {
                            "model": "academics.term",
                            "source_node_id": "ndga-lan-node",
                            "source_pk": "term-2",
                            "lookup": {
                                "name": term.name,
                                "session": {
                                    "model": "academics.academicsession",
                                    "source_node_id": "ndga-lan-node",
                                    "source_pk": "session-2",
                                    "lookup": {"name": session.name},
                                },
                            },
                        },
                    },
                },
                "student": {
                    "model": "accounts.user",
                    "source_node_id": "ndga-lan-node",
                    "source_pk": "student-2",
                    "lookup": {"username": student.username},
                },
                "ca1": "0.00",
                "ca2": "9.50",
                "ca3": "0.00",
                "ca4": "0.00",
                "objective": "38.00",
                "theory": "0.00",
                "total_ca": "9.50",
                "total_exam": "38.00",
                "grand_total": "47.50",
                "grade": "F",
                "has_override": False,
                "override_reason": "",
                "cbt_locked_fields": ["ca2", "objective"],
                "cbt_component_breakdown": {
                    "ca2_objective": "9.50",
                    "objective_auto": "38.00",
                },
                "override_by": None,
                "override_at": None,
            },
            "m2m": {},
            "created_at": "",
            "updated_at": "",
        }

        apply_generic_model_payload(
            payload=payload,
            operation_type=SyncOperationType.MODEL_RECORD_UPSERT,
        )

        score.refresh_from_db()
        self.assertEqual(score.ca1, Decimal("7.50"))
        self.assertEqual(score.ca2, Decimal("9.50"))
        self.assertEqual(score.ca3, Decimal("8.00"))
        self.assertEqual(score.ca4, Decimal("4.50"))
        self.assertEqual(score.objective, Decimal("38.00"))
        self.assertEqual(score.theory, Decimal("31.50"))

    @override_settings(SYNC_NODE_ROLE="LAN", SYNC_LOCAL_NODE_ID="ndga-lan-node")
    def test_lan_accepts_cloud_manual_ca_fields_when_no_local_cbt_lock_exists(self):
        from apps.results.models import ResultSheet, StudentSubjectScore

        session = AcademicSession.objects.create(name="2025/2026")
        term = Term.objects.create(session=session, name="SECOND")
        academic_class = AcademicClass.objects.create(code="SS3B", display_name="SS3B")
        subject = Subject.objects.create(name="Economics", code="ECO")
        student = User.objects.create_user(
            username="result-merge-lan-manual-student",
            password="Password123!",
            primary_role=self.role_student,
            must_change_password=False,
        )
        result_sheet = ResultSheet.objects.create(
            academic_class=academic_class,
            subject=subject,
            session=session,
            term=term,
        )
        score = StudentSubjectScore.objects.create(
            result_sheet=result_sheet,
            student=student,
            ca1=Decimal("0.00"),
            ca2=Decimal("0.00"),
            ca3=Decimal("0.00"),
            ca4=Decimal("0.00"),
            objective=Decimal("0.00"),
            theory=Decimal("0.00"),
        )

        payload = {
            "model": "results.studentsubjectscore",
            "identity": {
                "model": "results.studentsubjectscore",
                "source_node_id": "ndga-cloud-node",
                "source_pk": "score-cloud-2",
                "lookup": {
                    "student": {
                        "model": "accounts.user",
                        "source_node_id": "ndga-cloud-node",
                        "source_pk": "student-2",
                        "lookup": {"username": student.username},
                    },
                    "result_sheet": {
                        "model": "results.resultsheet",
                        "source_node_id": "ndga-cloud-node",
                        "source_pk": "sheet-2",
                        "lookup": {
                            "academic_class": {
                                "model": "academics.academicclass",
                                "source_node_id": "ndga-cloud-node",
                                "source_pk": "class-2",
                                "lookup": {"code": academic_class.code},
                            },
                            "subject": {
                                "model": "academics.subject",
                                "source_node_id": "ndga-cloud-node",
                                "source_pk": "subject-2",
                                "lookup": {"code": subject.code},
                            },
                            "session": {
                                "model": "academics.academicsession",
                                "source_node_id": "ndga-cloud-node",
                                "source_pk": "session-2",
                                "lookup": {"name": session.name},
                            },
                            "term": {
                                "model": "academics.term",
                                "source_node_id": "ndga-cloud-node",
                                "source_pk": "term-2",
                                "lookup": {
                                    "name": term.name,
                                    "session": {
                                        "model": "academics.academicsession",
                                        "source_node_id": "ndga-cloud-node",
                                        "source_pk": "session-2",
                                        "lookup": {"name": session.name},
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "fields": {
                "result_sheet": {
                    "model": "results.resultsheet",
                    "source_node_id": "ndga-cloud-node",
                    "source_pk": "sheet-2",
                    "lookup": {
                        "academic_class": {
                            "model": "academics.academicclass",
                            "source_node_id": "ndga-cloud-node",
                            "source_pk": "class-2",
                            "lookup": {"code": academic_class.code},
                        },
                        "subject": {
                            "model": "academics.subject",
                            "source_node_id": "ndga-cloud-node",
                            "source_pk": "subject-2",
                            "lookup": {"code": subject.code},
                        },
                        "session": {
                            "model": "academics.academicsession",
                            "source_node_id": "ndga-cloud-node",
                            "source_pk": "session-2",
                            "lookup": {"name": session.name},
                        },
                        "term": {
                            "model": "academics.term",
                            "source_node_id": "ndga-cloud-node",
                            "source_pk": "term-2",
                            "lookup": {
                                "name": term.name,
                                "session": {
                                    "model": "academics.academicsession",
                                    "source_node_id": "ndga-cloud-node",
                                    "source_pk": "session-2",
                                    "lookup": {"name": session.name},
                                },
                            },
                        },
                    },
                },
                "student": {
                    "model": "accounts.user",
                    "source_node_id": "ndga-cloud-node",
                    "source_pk": "student-2",
                    "lookup": {"username": student.username},
                },
                "ca1": "6.50",
                "ca2": "0.00",
                "ca3": "8.00",
                "ca4": "3.50",
                "objective": "0.00",
                "theory": "31.50",
                "total_ca": "18.00",
                "total_exam": "31.50",
                "grand_total": "49.50",
                "grade": "C",
                "has_override": False,
                "override_reason": "",
                "cbt_locked_fields": [],
                "cbt_component_breakdown": {"ca3_theory": "8.00"},
                "override_by": None,
                "override_at": None,
            },
            "m2m": {},
            "created_at": "",
            "updated_at": "",
        }

        apply_generic_model_payload(
            payload=payload,
            operation_type=SyncOperationType.MODEL_RECORD_UPSERT,
        )

        score.refresh_from_db()
        self.assertEqual(score.ca1, Decimal("6.50"))
        self.assertEqual(score.ca2, Decimal("0.00"))
        self.assertEqual(score.ca3, Decimal("8.00"))
        self.assertEqual(score.ca4, Decimal("3.50"))
        self.assertEqual(score.objective, Decimal("0.00"))
        self.assertEqual(score.theory, Decimal("31.50"))

    @override_settings(SYNC_NODE_ROLE="CLOUD", SYNC_LOCAL_NODE_ID="ndga-cloud-node")
    def test_cloud_preserves_result_sheet_status_when_lan_pushes_cbt_policy(self):
        from apps.results.models import ResultSheet, ResultSheetStatus

        session = AcademicSession.objects.create(name="2025/2026")
        term = Term.objects.create(session=session, name="SECOND")
        academic_class = AcademicClass.objects.create(code="SS1", display_name="SS1")
        subject = Subject.objects.create(name="Physics", code="PHY")
        result_sheet = ResultSheet.objects.create(
            academic_class=academic_class,
            subject=subject,
            session=session,
            term=term,
            status=ResultSheetStatus.SUBMITTED_TO_DEAN,
        )

        payload = {
            "model": "results.resultsheet",
            "identity": {
                "model": "results.resultsheet",
                "source_node_id": "ndga-lan-node",
                "source_pk": "sheet-policy-1",
                "lookup": {
                    "academic_class": {
                        "model": "academics.academicclass",
                        "source_node_id": "ndga-lan-node",
                        "source_pk": "class-1",
                        "lookup": {"code": academic_class.code},
                    },
                    "subject": {
                        "model": "academics.subject",
                        "source_node_id": "ndga-lan-node",
                        "source_pk": "subject-1",
                        "lookup": {"code": subject.code},
                    },
                    "session": {
                        "model": "academics.academicsession",
                        "source_node_id": "ndga-lan-node",
                        "source_pk": "session-1",
                        "lookup": {"name": session.name},
                    },
                    "term": {
                        "model": "academics.term",
                        "source_node_id": "ndga-lan-node",
                        "source_pk": "term-1",
                        "lookup": {
                            "name": term.name,
                            "session": {
                                "model": "academics.academicsession",
                                "source_node_id": "ndga-lan-node",
                                "source_pk": "session-1",
                                "lookup": {"name": session.name},
                            },
                        },
                    },
                },
            },
            "fields": {
                "academic_class": {
                    "model": "academics.academicclass",
                    "source_node_id": "ndga-lan-node",
                    "source_pk": "class-1",
                    "lookup": {"code": academic_class.code},
                },
                "subject": {
                    "model": "academics.subject",
                    "source_node_id": "ndga-lan-node",
                    "source_pk": "subject-1",
                    "lookup": {"code": subject.code},
                },
                "session": {
                    "model": "academics.academicsession",
                    "source_node_id": "ndga-lan-node",
                    "source_pk": "session-1",
                    "lookup": {"name": session.name},
                },
                "term": {
                    "model": "academics.term",
                    "source_node_id": "ndga-lan-node",
                    "source_pk": "term-1",
                    "lookup": {
                        "name": term.name,
                        "session": {
                            "model": "academics.academicsession",
                            "source_node_id": "ndga-lan-node",
                            "source_pk": "session-1",
                            "lookup": {"name": session.name},
                        },
                    },
                },
                "cbt_component_policies": {"exam": {"enabled": True, "objective_max": "40.00", "theory_max": "60.00"}},
                "status": ResultSheetStatus.DRAFT,
                "created_by": None,
            },
            "m2m": {},
            "created_at": "",
            "updated_at": "",
        }

        apply_generic_model_payload(
            payload=payload,
            operation_type=SyncOperationType.MODEL_RECORD_UPSERT,
        )

        result_sheet.refresh_from_db()
        self.assertEqual(result_sheet.status, ResultSheetStatus.SUBMITTED_TO_DEAN)
        self.assertTrue(result_sheet.cbt_component_policies.get("exam", {}).get("enabled"))

    @override_settings(
        SYNC_CLOUD_ENDPOINT="https://sync.example/sync/api",
        SYNC_PULL_ENABLED=True,
    )
    def test_pull_remote_outbox_updates_applies_generic_votergroup_payload(self):
        session = AcademicSession.objects.create(name="2025/2026")
        election = Election.objects.create(title="2026 Prefects", session=session)
        academic_class = AcademicClass.objects.create(code="SS1", display_name="SS1")
        user = User.objects.create_user(
            username="pull-voter-user",
            password="Password123!",
            primary_role=self.role_student,
            must_change_password=False,
        )
        SyncQueue.objects.all().delete()

        remote_event = {
            "id": 41,
            "idempotency_key": "remote-vgroup-1",
            "operation_type": SyncOperationType.MODEL_RECORD_UPSERT,
            "object_ref": "elections.votergroup:cloud-node:vgroup-1",
            "conflict_rule": SyncConflictRule.LAST_WRITE_WINS,
            "conflict_key": "elections.votergroup:cloud-node:vgroup-1",
            "local_node_id": "cloud-node",
            "payload": {
                "model": "elections.votergroup",
                "identity": {
                    "model": "elections.votergroup",
                    "source_node_id": "cloud-node",
                    "source_pk": "vgroup-1",
                    "lookup": {
                        "election": {
                            "model": "elections.election",
                            "source_node_id": "cloud-node",
                            "source_pk": "election-1",
                            "lookup": {
                                "title": election.title,
                                "session": {
                                    "model": "academics.academicsession",
                                    "source_node_id": "cloud-node",
                                    "source_pk": "session-1",
                                    "lookup": {"name": session.name},
                                },
                            },
                        },
                        "name": "Senior Voters",
                    },
                },
                "fields": {
                    "election": {
                        "model": "elections.election",
                        "source_node_id": "cloud-node",
                        "source_pk": "election-1",
                        "lookup": {
                            "title": election.title,
                            "session": {
                                "model": "academics.academicsession",
                                "source_node_id": "cloud-node",
                                "source_pk": "session-1",
                                "lookup": {"name": session.name},
                            },
                        },
                    },
                    "name": "Senior Voters",
                    "description": "Synced remote voter group",
                    "include_all_students": False,
                    "include_all_staff": False,
                    "is_active": True,
                },
                "m2m": {
                    "roles": [
                        {
                            "model": "accounts.role",
                            "source_node_id": "cloud-node",
                            "source_pk": "role-student",
                            "lookup": {"code": ROLE_STUDENT},
                        }
                    ],
                    "academic_classes": [
                        {
                            "model": "academics.academicclass",
                            "source_node_id": "cloud-node",
                            "source_pk": "class-ss1",
                            "lookup": {"code": academic_class.code},
                        }
                    ],
                    "users": [
                        {
                            "model": "accounts.user",
                            "source_node_id": "cloud-node",
                            "source_pk": "user-1",
                            "lookup": {"username": user.username},
                        }
                    ],
                },
                "created_at": "2026-03-08T07:30:00+00:00",
                "updated_at": "2026-03-08T07:35:00+00:00",
            },
        }

        with patch(
            "apps.sync.services._fetch_remote_outbox_feed",
            return_value={
                "ok": True,
                "status_code": 200,
                "payload": {
                    "events": [remote_event],
                    "has_more": False,
                    "next_after_id": 41,
                },
                "error": "",
            },
        ):
            summary = pull_remote_outbox_updates(limit=20, max_pages=1)

        self.assertTrue(summary["triggered"])
        self.assertEqual(summary["applied"], 1)
        voter_group = VoterGroup.objects.get(name="Senior Voters")
        self.assertEqual(voter_group.description, "Synced remote voter group")
        self.assertEqual(list(voter_group.roles.values_list("code", flat=True)), [ROLE_STUDENT])
        self.assertEqual(list(voter_group.academic_classes.values_list("code", flat=True)), [academic_class.code])
        self.assertEqual(list(voter_group.users.values_list("username", flat=True)), [user.username])
        self.assertTrue(
            SyncModelBinding.objects.filter(
                source_node_id="cloud-node",
                model_label="elections.votergroup",
                source_pk="vgroup-1",
                local_pk=str(voter_group.pk),
            ).exists()
        )
        cursor = SyncPullCursor.objects.get(stream=SyncContentStream.OUTBOX_EVENTS)
        self.assertEqual(cursor.last_remote_id, 41)


    @override_settings(
        SYNC_NODE_ROLE="LAN",
        SYNC_ENFORCE_ACTIVE_SESSION_AUTHORITY=True,
    )
    def test_generic_remote_election_config_retries_when_lan_election_is_open(self):
        session = AcademicSession.objects.create(name="2027/2028")
        election = Election.objects.create(
            title="Open LAN Election",
            session=session,
            status=ElectionStatus.OPEN,
        )

        payload = {
            "model": "elections.votergroup",
            "identity": {
                "model": "elections.votergroup",
                "source_node_id": "cloud-node",
                "source_pk": "vgroup-open",
                "lookup": {
                    "election": {
                        "model": "elections.election",
                        "source_node_id": "cloud-node",
                        "source_pk": "election-open",
                        "lookup": {
                            "title": election.title,
                            "session": {
                                "model": "academics.academicsession",
                                "source_node_id": "cloud-node",
                                "source_pk": "session-open",
                                "lookup": {"name": session.name},
                            },
                        },
                    },
                    "name": "Blocked Group",
                },
            },
            "fields": {
                "election": {
                    "model": "elections.election",
                    "source_node_id": "cloud-node",
                    "source_pk": "election-open",
                    "lookup": {
                        "title": election.title,
                        "session": {
                            "model": "academics.academicsession",
                            "source_node_id": "cloud-node",
                            "source_pk": "session-open",
                            "lookup": {"name": session.name},
                        },
                    },
                },
                "name": "Blocked Group",
                "description": "Should retry until LAN election closes",
                "include_all_students": False,
                "include_all_staff": False,
                "is_active": True,
            },
            "m2m": {"roles": [], "academic_classes": [], "users": []},
            "created_at": "2026-03-08T07:30:00+00:00",
            "updated_at": "2026-03-08T07:35:00+00:00",
        }

        with self.assertRaises(ValidationError):
            ingest_remote_outbox_event(
                envelope={
                    "idempotency_key": "generic-open-election-block",
                    "operation_type": SyncOperationType.MODEL_RECORD_UPSERT,
                    "object_ref": "elections.votergroup:cloud-node:vgroup-open",
                    "conflict_rule": SyncConflictRule.LAST_WRITE_WINS,
                    "conflict_key": "elections.votergroup:cloud-node:vgroup-open",
                    "local_node_id": "cloud-node",
                    "payload": payload,
                }
            )

        row = SyncQueue.objects.get(idempotency_key="generic-open-election-block")
        self.assertEqual(row.status, SyncQueueStatus.RETRY)
        self.assertFalse(VoterGroup.objects.filter(name="Blocked Group").exists())
