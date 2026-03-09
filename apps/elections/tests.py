from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings

from apps.accounts.constants import ROLE_DEAN, ROLE_IT_MANAGER, ROLE_PRINCIPAL, ROLE_STUDENT
from apps.accounts.models import Role, StaffProfile, StudentProfile, User
from apps.academics.models import (
    AcademicClass,
    AcademicSession,
    StudentClassEnrollment,
    Term,
)
from apps.elections.models import (
    Candidate,
    Election,
    ElectionStatus,
    Position,
    Vote,
    VoteAudit,
    VoterGroup,
)
from apps.elections.services import (
    build_election_analytics_payload,
    close_election,
    is_user_eligible_voter,
    open_election,
    submit_vote_bundle,
)
from apps.notifications.models import Notification, NotificationCategory
from apps.setup_wizard.models import SetupStateCode, SystemSetupState
from apps.sync.models import SyncOperationType, SyncQueue
from apps.sync.services import queue_vote_submission_sync


@override_settings(
    FEATURE_FLAGS={
        **settings.FEATURE_FLAGS,
        "ELECTION_ENABLED": True,
    }
)
class StageFifteenElectionTests(TestCase):
    PASSWORD = "Password123!"

    @classmethod
    def setUpTestData(cls):
        role_it = Role.objects.get(code=ROLE_IT_MANAGER)
        role_principal = Role.objects.get(code=ROLE_PRINCIPAL)
        role_dean = Role.objects.get(code=ROLE_DEAN)
        role_student = Role.objects.get(code=ROLE_STUDENT)

        cls.it_user = User.objects.create_user(
            username="it-election",
            password=cls.PASSWORD,
            primary_role=role_it,
            must_change_password=False,
        )
        cls.principal_user = User.objects.create_user(
            username="principal-election",
            password=cls.PASSWORD,
            primary_role=role_principal,
            must_change_password=False,
        )
        cls.student_voter = User.objects.create_user(
            username="student-voter-election",
            password=cls.PASSWORD,
            primary_role=role_student,
            must_change_password=False,
            email="parent1@example.com",
        )
        cls.student_voter_two = User.objects.create_user(
            username="student-voter-two-election",
            password=cls.PASSWORD,
            primary_role=role_student,
            must_change_password=False,
            email="parent2@example.com",
        )
        cls.student_candidate_a = User.objects.create_user(
            username="student-candidate-a",
            password=cls.PASSWORD,
            primary_role=role_student,
            must_change_password=False,
        )
        cls.student_candidate_b = User.objects.create_user(
            username="student-candidate-b",
            password=cls.PASSWORD,
            primary_role=role_student,
            must_change_password=False,
        )
        cls.student_outside = User.objects.create_user(
            username="student-outside-election",
            password=cls.PASSWORD,
            primary_role=role_student,
            must_change_password=False,
        )
        cls.staff_voter = User.objects.create_user(
            username="staff-voter-election",
            password=cls.PASSWORD,
            primary_role=role_dean,
            must_change_password=False,
        )

        for user, number in [
            (cls.student_voter, "NDGAK/20/101"),
            (cls.student_voter_two, "NDGAK/20/102"),
            (cls.student_candidate_a, "NDGAK/20/103"),
            (cls.student_candidate_b, "NDGAK/20/104"),
            (cls.student_outside, "NDGAK/20/105"),
        ]:
            StudentProfile.objects.create(
                user=user,
                student_number=number,
                guardian_email=f"{user.username}@guardian.test",
            )
        StaffProfile.objects.create(
            user=cls.staff_voter,
            staff_id="TMP-STF-900",
            designation="Dean",
        )

        cls.session = AcademicSession.objects.create(name="2025/2026")
        cls.term = Term.objects.create(session=cls.session, name="SECOND")
        cls.class_science = AcademicClass.objects.create(code="SS2SCI", display_name="SS2 Science")
        cls.class_arts = AcademicClass.objects.create(code="SS2ART", display_name="SS2 Arts")

        StudentClassEnrollment.objects.create(
            student=cls.student_voter,
            academic_class=cls.class_science,
            session=cls.session,
            is_active=True,
        )
        StudentClassEnrollment.objects.create(
            student=cls.student_voter_two,
            academic_class=cls.class_science,
            session=cls.session,
            is_active=True,
        )
        StudentClassEnrollment.objects.create(
            student=cls.student_candidate_a,
            academic_class=cls.class_science,
            session=cls.session,
            is_active=True,
        )
        StudentClassEnrollment.objects.create(
            student=cls.student_candidate_b,
            academic_class=cls.class_science,
            session=cls.session,
            is_active=True,
        )
        StudentClassEnrollment.objects.create(
            student=cls.student_outside,
            academic_class=cls.class_arts,
            session=cls.session,
            is_active=True,
        )

        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = cls.session
        setup_state.current_term = cls.term
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

    def login_client(self, *, host, username, audience="election"):
        client = Client(HTTP_HOST=host)
        response = client.post(
            f"/auth/login/?audience={audience}",
            {"username": username, "password": self.PASSWORD},
        )
        self.assertEqual(response.status_code, 302)
        return client

    def create_open_election(self, *, with_second_position=False):
        election = Election.objects.create(
            title=f"Student Council {Election.objects.count() + 1}",
            description="Stage 15 automated test election",
            session=self.session,
            created_by=self.it_user,
            status=ElectionStatus.DRAFT,
        )
        head_girl = Position.objects.create(
            election=election,
            name="Head Girl",
            sort_order=1,
            is_active=True,
        )
        sports = None
        if with_second_position:
            sports = Position.objects.create(
                election=election,
                name="Sports Prefect",
                sort_order=2,
                is_active=True,
            )

        candidate_a = Candidate.objects.create(
            position=head_girl,
            user=self.student_candidate_a,
            display_name="Candidate A",
            is_active=True,
        )
        candidate_b = Candidate.objects.create(
            position=head_girl,
            user=self.student_candidate_b,
            display_name="Candidate B",
            is_active=True,
        )
        candidate_sports = None
        if sports:
            candidate_sports = Candidate.objects.create(
                position=sports,
                user=self.student_candidate_b,
                display_name="Candidate B",
                is_active=True,
            )

        group = VoterGroup.objects.create(
            election=election,
            name="All Students",
            include_all_students=True,
            is_active=True,
        )
        self.assertTrue(group.is_active)

        open_election(election=election, actor=self.it_user)
        election.refresh_from_db()
        self.assertEqual(election.status, ElectionStatus.OPEN)
        return election, head_girl, sports, candidate_a, candidate_b, candidate_sports

    def test_voter_group_class_filter_controls_eligibility(self):
        election = Election.objects.create(
            title="Class Filter Election",
            session=self.session,
            created_by=self.it_user,
            status=ElectionStatus.DRAFT,
        )
        position = Position.objects.create(
            election=election,
            name="Head Girl",
            sort_order=1,
            is_active=True,
        )
        Candidate.objects.create(
            position=position,
            user=self.student_candidate_a,
            display_name="Candidate A",
            is_active=True,
        )
        group = VoterGroup.objects.create(
            election=election,
            name="Science Only",
            include_all_students=False,
            is_active=True,
        )
        group.academic_classes.add(self.class_science)
        open_election(election=election, actor=self.it_user)

        self.assertTrue(is_user_eligible_voter(election=election, user=self.student_voter))
        self.assertFalse(is_user_eligible_voter(election=election, user=self.student_outside))

    def test_staff_admin_voting_toggle_controls_staff_eligibility(self):
        election = Election.objects.create(
            title="Staff Toggle Election",
            session=self.session,
            created_by=self.it_user,
            status=ElectionStatus.DRAFT,
            allow_staff_admin_voting=False,
        )
        position = Position.objects.create(
            election=election,
            name="Head Girl",
            sort_order=1,
            is_active=True,
        )
        Candidate.objects.create(
            position=position,
            user=self.student_candidate_a,
            display_name="Candidate A",
            is_active=True,
        )
        VoterGroup.objects.create(
            election=election,
            name="Mixed Group",
            include_all_students=True,
            include_all_staff=True,
            is_active=True,
        )
        open_election(election=election, actor=self.it_user)

        self.assertTrue(is_user_eligible_voter(election=election, user=self.student_voter))
        self.assertFalse(is_user_eligible_voter(election=election, user=self.staff_voter))

        election.allow_staff_admin_voting = True
        election.save(update_fields=["allow_staff_admin_voting", "updated_at"])
        self.assertTrue(is_user_eligible_voter(election=election, user=self.staff_voter))

    def test_submit_vote_bundle_enforces_one_vote_per_user_per_position(self):
        election, position, _, candidate_a, _, _ = self.create_open_election(with_second_position=False)

        created = submit_vote_bundle(
            election=election,
            voter=self.student_voter,
            choices_map={position.id: candidate_a.id},
        )
        self.assertEqual(len(created), 1)
        self.assertEqual(
            Vote.objects.filter(
                election=election,
                position=position,
                voter=self.student_voter,
            ).count(),
            1,
        )

        with self.assertRaises(ValidationError):
            submit_vote_bundle(
                election=election,
                voter=self.student_voter,
                choices_map={position.id: candidate_a.id},
            )

        self.assertEqual(
            SyncQueue.objects.filter(operation_type=SyncOperationType.ELECTION_VOTE_SUBMISSION).count(),
            1,
        )

    def test_vote_submission_flow_is_sequential_and_final(self):
        (
            election,
            first_position,
            second_position,
            candidate_a,
            _candidate_b,
            candidate_sports,
        ) = self.create_open_election(with_second_position=True)
        self.assertIsNotNone(second_position)
        self.assertIsNotNone(candidate_sports)

        student_client = self.login_client(
            host="election.ndgakuje.org",
            username=self.student_voter.username,
            audience="election",
        )

        start_response = student_client.get(f"/elections/vote/{election.id}/start/")
        self.assertEqual(start_response.status_code, 302)
        self.assertIn(
            f"/elections/vote/{election.id}/position/{first_position.id}/",
            start_response.url,
        )

        first_position_page = student_client.get(
            f"/elections/vote/{election.id}/position/{first_position.id}/"
        )
        self.assertEqual(first_position_page.status_code, 200)
        self.assertContains(first_position_page, first_position.name)

        first_vote_response = student_client.post(
            f"/elections/vote/{election.id}/position/{first_position.id}/",
            {"candidate": str(candidate_a.id)},
        )
        self.assertEqual(first_vote_response.status_code, 302)
        self.assertIn(
            f"/elections/vote/{election.id}/position/{second_position.id}/",
            first_vote_response.url,
        )

        second_vote_response = student_client.post(
            f"/elections/vote/{election.id}/position/{second_position.id}/",
            {"candidate": str(candidate_sports.id)},
        )
        self.assertEqual(second_vote_response.status_code, 302)
        self.assertIn("/elections/", second_vote_response.url)
        self.assertEqual(
            Vote.objects.filter(election=election, voter=self.student_voter).count(),
            2,
        )

        revisit_first_position = student_client.get(
            f"/elections/vote/{election.id}/position/{first_position.id}/"
        )
        self.assertEqual(revisit_first_position.status_code, 302)
        self.assertIn("/elections/", revisit_first_position.url)

        current_vote = Vote.objects.get(
            election=election,
            position=first_position,
            voter=self.student_voter,
        )
        self.assertEqual(current_vote.candidate_id, candidate_a.id)

        second_start = student_client.get(f"/elections/vote/{election.id}/start/")
        self.assertEqual(second_start.status_code, 302)
        self.assertIn("/elections/", second_start.url)
        self.assertEqual(
            Vote.objects.filter(
                election=election,
                position=first_position,
                voter=self.student_voter,
            ).count(),
            1,
        )

    def test_it_manager_can_reset_voter_votes_for_revote(self):
        election, position, _, candidate_a, candidate_b, _ = self.create_open_election(
            with_second_position=False
        )

        student_client = self.login_client(
            host="election.ndgakuje.org",
            username=self.student_voter.username,
            audience="election",
        )
        first_vote_response = student_client.post(
            f"/elections/vote/{election.id}/position/{position.id}/",
            {"candidate": str(candidate_a.id)},
        )
        self.assertEqual(first_vote_response.status_code, 302)
        self.assertEqual(
            Vote.objects.filter(election=election, voter=self.student_voter).count(),
            1,
        )
        self.assertEqual(
            VoteAudit.objects.filter(vote__election=election, vote__voter=self.student_voter).count(),
            1,
        )

        it_client = self.login_client(
            host="election.ndgakuje.org",
            username=self.it_user.username,
            audience="election",
        )
        reset_response = it_client.post(
            f"/elections/it/manage/{election.id}/",
            {
                "action": "reset_voter_votes",
                "voter": str(self.student_voter.id),
            },
        )
        self.assertEqual(reset_response.status_code, 302)
        self.assertIn(f"/elections/it/manage/{election.id}/", reset_response.url)
        self.assertEqual(
            Vote.objects.filter(election=election, voter=self.student_voter).count(),
            0,
        )
        self.assertEqual(
            VoteAudit.objects.filter(vote__election=election, vote__voter=self.student_voter).count(),
            0,
        )

        second_start = student_client.get(f"/elections/vote/{election.id}/start/")
        self.assertEqual(second_start.status_code, 302)
        self.assertIn(f"/elections/vote/{election.id}/position/{position.id}/", second_start.url)

        second_vote_response = student_client.post(second_start.url, {"candidate": str(candidate_b.id)})
        self.assertEqual(second_vote_response.status_code, 302)
        self.assertIn("/elections/", second_vote_response.url)
        self.assertEqual(
            Vote.objects.filter(election=election, position=position, voter=self.student_voter).count(),
            1,
        )
        updated_vote = Vote.objects.get(
            election=election,
            position=position,
            voter=self.student_voter,
        )
        self.assertEqual(updated_vote.candidate_id, candidate_b.id)

    def test_opening_election_creates_announcement_notifications(self):
        election, _, _, _, _, _ = self.create_open_election(with_second_position=False)
        self.assertTrue(
            Notification.objects.filter(
                category=NotificationCategory.ELECTION,
                title__icontains=election.title,
            ).exists()
        )

    def test_live_analytics_page_renders_for_it_and_principal(self):
        election, position, _, candidate_a, _, _ = self.create_open_election(with_second_position=False)
        submit_vote_bundle(
            election=election,
            voter=self.student_voter,
            choices_map={position.id: candidate_a.id},
        )

        it_client = self.login_client(
            host="election.ndgakuje.org",
            username=self.it_user.username,
            audience="election",
        )
        response = it_client.get(f"/elections/analytics/{election.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Live Election Analytics")
        self.assertContains(response, f"/ws/elections/{election.id}/analytics/")

        principal_client = self.login_client(
            host="election.ndgakuje.org",
            username=self.principal_user.username,
            audience="election",
        )
        response_principal = principal_client.get(f"/elections/analytics/{election.id}/")
        self.assertEqual(response_principal.status_code, 200)

    def test_analytics_payload_and_sync_idempotency_rule(self):
        election, position, _, candidate_a, candidate_b, _ = self.create_open_election(with_second_position=False)
        submit_vote_bundle(
            election=election,
            voter=self.student_voter,
            choices_map={position.id: candidate_a.id},
        )
        submit_vote_bundle(
            election=election,
            voter=self.student_voter_two,
            choices_map={position.id: candidate_b.id},
        )
        payload = build_election_analytics_payload(election)
        self.assertEqual(payload["votes_cast"], 2)
        self.assertGreaterEqual(payload["eligible_voters"], 2)
        self.assertEqual(len(payload["positions"]), 1)
        self.assertEqual(payload["positions"][0]["position_name"], "Head Girl")
        self.assertEqual(len(payload["positions"][0]["candidate_rows"]), 2)

        queue_vote_submission_sync(
            election_id=str(election.id),
            position_id=str(position.id),
            voter_id=str(self.student_outside.id),
            payload={"vote_id": "manual-sync-a"},
            idempotency_key="stage15-manual-sync-a",
        )
        with self.assertRaises(ValidationError):
            queue_vote_submission_sync(
                election_id=str(election.id),
                position_id=str(position.id),
                voter_id=str(self.student_outside.id),
                payload={"vote_id": "manual-sync-b"},
                idempotency_key="stage15-manual-sync-b",
            )

    def test_closed_election_pdf_and_qr_verify_endpoint(self):
        election, position, _, candidate_a, _, _ = self.create_open_election(with_second_position=False)
        submit_vote_bundle(
            election=election,
            voter=self.student_voter,
            choices_map={position.id: candidate_a.id},
        )
        close_election(election=election, actor=self.it_user)
        election.refresh_from_db()
        self.assertEqual(election.status, ElectionStatus.CLOSED)

        principal_client = self.login_client(
            host="election.ndgakuje.org",
            username=self.principal_user.username,
            audience="election",
        )
        pdf_response = principal_client.get(f"/elections/results/{election.id}/pdf/")
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")

        artifact = election.result_artifacts.latest("created_at")
        verify_client = Client(HTTP_HOST="ndgakuje.org")
        verify_response = verify_client.get(
            f"/elections/verify/{artifact.id}/?hash={artifact.payload_hash}"
        )
        self.assertEqual(verify_response.status_code, 200)
        self.assertContains(verify_response, "Valid PDF")
