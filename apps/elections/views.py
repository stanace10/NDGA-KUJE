from __future__ import annotations

import secrets
from pathlib import Path

from django.contrib import messages
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.constants import (
    PORTAL_ROLE_ACCESS,
    ROLE_IT_MANAGER,
)
from apps.academics.models import StudentClassEnrollment
from apps.audit.models import AuditCategory, AuditStatus
from apps.audit.services import log_event
from apps.elections.forms import (
    BulkCandidateImportForm,
    CandidateCreateForm,
    ElectionCreateForm,
    PrefectRosterImportForm,
    PositionCreateForm,
    PositionVoteForm,
    VoterResetForm,
    VoterGroupCreateForm,
)
from apps.elections.models import (
    Candidate,
    Election,
    ElectionResultArtifact,
    ElectionStatus,
    Position,
    Vote,
    VoteAudit,
    VoterGroup,
)
from apps.elections.services import (
    auto_close_due_elections,
    build_lan_readiness_payload,
    broadcast_election_analytics,
    build_election_analytics_payload,
    can_view_live_analytics,
    close_election,
    ensure_default_voter_groups,
    election_summary_payload,
    generate_election_result_pdf,
    import_candidate_entries,
    import_prefect_screening_markdown,
    is_user_eligible_voter,
    open_election,
    remaining_positions_for_voter,
    submit_vote_bundle,
)
from apps.sync.models import SyncOperationType, SyncQueue
from apps.tenancy.utils import build_portal_url, current_portal_key


ELECTION_PORTAL_ROLES = PORTAL_ROLE_ACCESS["election"]


def _election_voting_window_error(election):
    current_time = timezone.localtime(timezone.now())
    if election.starts_at and current_time < timezone.localtime(election.starts_at):
        return f"Voting opens at {timezone.localtime(election.starts_at).strftime('%d %b %Y %H:%M')}."
    if election.ends_at and current_time > timezone.localtime(election.ends_at):
        return f"Voting closed at {timezone.localtime(election.ends_at).strftime('%d %b %Y %H:%M')}."
    return ""


def _user_mini_bio(*, user, session_id=None):
    student_profile = getattr(user, "student_profile", None)
    staff_profile = getattr(user, "staff_profile", None)

    voter_identifier = user.username
    voter_photo_url = ""
    voter_class_code = ""
    voter_role = user.primary_role.name if user.primary_role else "School Member"

    if student_profile:
        voter_identifier = student_profile.student_number or voter_identifier
        voter_role = "Student"
        if student_profile.profile_photo:
            voter_photo_url = student_profile.profile_photo.url
        enrollment_qs = StudentClassEnrollment.objects.select_related("academic_class").filter(
            student=user,
            is_active=True,
        )
        if session_id:
            enrollment_qs = enrollment_qs.filter(session_id=session_id)
        latest_enrollment = enrollment_qs.order_by("-updated_at", "-id").first()
        if latest_enrollment and latest_enrollment.academic_class:
            voter_class_code = latest_enrollment.academic_class.code
    elif staff_profile:
        voter_identifier = staff_profile.staff_id or voter_identifier
        if staff_profile.profile_photo:
            voter_photo_url = staff_profile.profile_photo.url

    return {
        "voter_name": user.get_full_name() or user.display_name or user.username,
        "voter_identifier": voter_identifier,
        "voter_role": voter_role,
        "voter_class_code": voter_class_code,
        "voter_photo_url": voter_photo_url,
    }


class ElectionPortalAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    allowed_portal_keys = {"election"}
    target_portal_key = "election"

    def dispatch(self, request, *args, **kwargs):
        portal_key = current_portal_key(request)
        if portal_key not in self.allowed_portal_keys:
            target = build_portal_url(
                request,
                self.target_portal_key,
                request.path,
                query=request.GET,
            )
            return redirect(target)
        return super().dispatch(request, *args, **kwargs)

    def test_func(self):
        return bool(self.request.user.get_all_role_codes() & ELECTION_PORTAL_ROLES)


class ElectionITAccessMixin(ElectionPortalAccessMixin):
    allowed_portal_keys = {"election"}
    target_portal_key = "election"

    def test_func(self):
        return self.request.user.has_role(ROLE_IT_MANAGER)


class ElectionAnalyticsAccessMixin(ElectionPortalAccessMixin):
    allowed_portal_keys = {"election"}
    target_portal_key = "election"

    def test_func(self):
        return can_view_live_analytics(self.request.user)


class ElectionHomeView(ElectionPortalAccessMixin, TemplateView):
    allowed_portal_keys = {"election"}
    template_name = "elections/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        auto_close_due_elections()
        user = self.request.user
        context.update(_user_mini_bio(user=user))
        open_qs = Election.objects.filter(status=ElectionStatus.OPEN, is_active=True).order_by("-updated_at")
        rows = []
        for election in open_qs:
            if not is_user_eligible_voter(election=election, user=user):
                continue
            position_count = election.positions.filter(is_active=True).count()
            voted_count = Vote.objects.filter(election=election, voter=user).count()
            rows.append(
                {
                    "election": election,
                    "position_count": position_count,
                    "voted_count": voted_count,
                    "is_completed": position_count > 0 and voted_count >= position_count,
                }
            )
        show_management = user.has_role(ROLE_IT_MANAGER)
        show_analytics = can_view_live_analytics(user)
        monitor_rows = []
        if show_management or show_analytics:
            for election in open_qs:
                monitor_rows.append(
                    {
                        "election": election,
                        "analytics": build_election_analytics_payload(election),
                        "position_count": election.positions.filter(is_active=True).count(),
                    }
                )
        context["open_elections"] = rows
        context["monitor_elections"] = monitor_rows
        context["show_management"] = show_management
        context["show_analytics"] = show_analytics
        context["show_closed_elections"] = show_analytics
        context["recent_closed"] = (
            Election.objects.filter(
                status=ElectionStatus.CLOSED,
                is_active=True,
            ).order_by("-closed_at")[:10]
            if show_analytics
            else []
        )
        return context


class ElectionITManagementView(ElectionITAccessMixin, TemplateView):
    template_name = "elections/it_manage_list.html"

    def _form(self, data=None):
        return ElectionCreateForm(data=data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        auto_close_due_elections()
        context["form"] = kwargs.get("form") or self._form()
        context["elections"] = Election.objects.select_related("session").order_by("-updated_at")
        return context

    def post(self, request, *args, **kwargs):
        form = self._form(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        election = form.save(commit=False)
        election.created_by = request.user
        election.save()
        messages.success(request, "Election created.")
        log_event(
            category=AuditCategory.ELECTION,
            event_type="ELECTION_CREATED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={"election_id": str(election.id)},
        )
        return redirect("elections:it-manage-detail", election_id=election.id)


class ElectionITManagementDetailView(ElectionITAccessMixin, TemplateView):
    template_name = "elections/it_manage_detail.html"

    def dispatch(self, request, *args, **kwargs):
        auto_close_due_elections(actor=request.user, request=request)
        self.election = get_object_or_404(Election, pk=kwargs["election_id"], is_active=True)
        return super().dispatch(request, *args, **kwargs)

    def _position_form(self, data=None):
        return PositionCreateForm(election=self.election, data=data)

    def _candidate_form(self, data=None):
        return CandidateCreateForm(election=self.election, data=data)

    def _voter_group_form(self, data=None):
        return VoterGroupCreateForm(election=self.election, data=data)

    def _bulk_candidate_form(self, data=None):
        return BulkCandidateImportForm(data=data)

    def _voter_reset_form(self, data=None):
        return VoterResetForm(election=self.election, data=data)

    def _prefect_roster_form(self, data=None):
        return PrefectRosterImportForm(data=data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["election"] = self.election
        context["position_form"] = kwargs.get("position_form") or self._position_form()
        context["candidate_form"] = kwargs.get("candidate_form") or self._candidate_form()
        context["bulk_candidate_form"] = kwargs.get("bulk_candidate_form") or self._bulk_candidate_form()
        context["prefect_roster_form"] = kwargs.get("prefect_roster_form") or self._prefect_roster_form()
        context["voter_group_form"] = kwargs.get("voter_group_form") or self._voter_group_form()
        context["voter_reset_form"] = kwargs.get("voter_reset_form") or self._voter_reset_form()
        context["positions"] = self.election.positions.prefetch_related("candidates__user").order_by(
            "sort_order",
            "name",
        )
        context["voter_groups"] = self.election.voter_groups.prefetch_related(
            "roles",
            "academic_classes",
            "users",
        ).order_by("name")
        context["analytics"] = build_election_analytics_payload(self.election)
        context["lan_readiness"] = build_lan_readiness_payload(election=self.election)
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()

        if action == "create_position":
            form = self._position_form(request.POST)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(position_form=form))
            row = form.save()
            messages.success(request, "Position added.")
            log_event(
                category=AuditCategory.ELECTION,
                event_type="ELECTION_POSITION_CREATED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={"election_id": str(self.election.id), "position_id": str(row.id)},
            )
            return redirect("elections:it-manage-detail", election_id=self.election.id)

        if action == "create_candidate":
            form = self._candidate_form(request.POST)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(candidate_form=form))
            row = form.save()
            messages.success(request, "Candidate added.")
            log_event(
                category=AuditCategory.ELECTION,
                event_type="ELECTION_CANDIDATE_CREATED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={
                    "election_id": str(self.election.id),
                    "position_id": str(row.position_id),
                    "candidate_id": str(row.id),
                    "user_id": str(row.user_id),
                },
            )
            return redirect("elections:it-manage-detail", election_id=self.election.id)

        if action == "create_voter_group":
            form = self._voter_group_form(request.POST)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(voter_group_form=form))
            row = form.save()
            messages.success(request, "Voter group saved.")
            log_event(
                category=AuditCategory.ELECTION,
                event_type="ELECTION_VOTER_GROUP_CREATED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={"election_id": str(self.election.id), "voter_group_id": str(row.id)},
            )
            return redirect("elections:it-manage-detail", election_id=self.election.id)

        if action == "quick_setup_voter_groups":
            results = ensure_default_voter_groups(election=self.election)
            created_count = sum(1 for row in results if row["created"])
            updated_count = sum(1 for row in results if row["updated"])
            log_event(
                category=AuditCategory.ELECTION,
                event_type="ELECTION_DEFAULT_VOTER_GROUPS_PREPARED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={
                    "election_id": str(self.election.id),
                    "created_count": created_count,
                    "updated_count": updated_count,
                },
            )
            messages.success(
                request,
                f"Student/staff voter groups prepared. Created {created_count}, updated {updated_count}.",
            )
            return redirect("elections:it-manage-detail", election_id=self.election.id)

        if action == "bulk_import_candidates":
            form = self._bulk_candidate_form(request.POST)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(bulk_candidate_form=form))
            try:
                result = import_candidate_entries(
                    election=self.election,
                    raw_entries=form.cleaned_data["entries"],
                    is_active=form.cleaned_data.get("is_active", True),
                    update_existing=form.cleaned_data.get("update_existing", True),
                )
            except ValidationError as exc:
                form.add_error("entries", "; ".join(exc.messages))
                return self.render_to_response(self.get_context_data(bulk_candidate_form=form))
            log_event(
                category=AuditCategory.ELECTION,
                event_type="ELECTION_CANDIDATE_BULK_IMPORTED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={
                    "election_id": str(self.election.id),
                    "created_count": result["created_count"],
                    "updated_count": result["updated_count"],
                    "skipped_count": result["skipped_count"],
                },
            )
            messages.success(
                request,
                "Bulk candidate import complete. "
                f"Created {result['created_count']}, updated {result['updated_count']}, skipped {result['skipped_count']}.",
            )
            return redirect("elections:it-manage-detail", election_id=self.election.id)

        if action == "import_prefect_roster":
            form = self._prefect_roster_form(request.POST)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(prefect_roster_form=form))
            try:
                root_dir = Path(settings.ROOT_DIR).resolve()
                source_path = (root_dir / form.cleaned_data["source_path"]).resolve()
                if root_dir not in source_path.parents and source_path != root_dir:
                    raise ValidationError("Prefect roster file must stay inside this workspace.")
                raw_text = source_path.read_text(encoding="utf-8")
                result = import_prefect_screening_markdown(
                    election=self.election,
                    raw_text=raw_text,
                    is_active=form.cleaned_data.get("is_active", True),
                    update_existing=form.cleaned_data.get("update_existing", True),
                    update_election_meta=form.cleaned_data.get("update_election_meta", True),
                    prepare_voter_groups=form.cleaned_data.get("prepare_voter_groups", True),
                )
            except FileNotFoundError:
                form.add_error("source_path", "Prefect roster file was not found.")
                return self.render_to_response(self.get_context_data(prefect_roster_form=form))
            except ValidationError as exc:
                form.add_error("source_path", "; ".join(exc.messages))
                return self.render_to_response(self.get_context_data(prefect_roster_form=form))
            log_event(
                category=AuditCategory.ELECTION,
                event_type="ELECTION_PREFECT_ROSTER_IMPORTED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={
                    "election_id": str(self.election.id),
                    "created_positions": result["created_positions"],
                    "updated_positions": result["updated_positions"],
                    "created_candidates": result["candidate_result"]["created_count"],
                    "updated_candidates": result["candidate_result"]["updated_count"],
                    "skipped_candidates": result["candidate_result"]["skipped_count"],
                },
            )
            parsed = result["parsed"]
            if parsed["starts_at"] and parsed["ends_at"]:
                schedule_label = (
                    f" Schedule set for {parsed['starts_at'].strftime('%d %b %Y %H:%M')} "
                    f"to {parsed['ends_at'].strftime('%H:%M')}."
                )
            else:
                schedule_label = ""
            messages.success(
                request,
                "Prefect roster imported. "
                f"Positions created {result['created_positions']}, updated {result['updated_positions']}. "
                f"Candidates created {result['candidate_result']['created_count']}, updated {result['candidate_result']['updated_count']}, "
                f"skipped {result['candidate_result']['skipped_count']}."
                f"{schedule_label}"
            )
            return redirect("elections:it-manage-detail", election_id=self.election.id)

        if action == "open":
            try:
                open_election(election=self.election, actor=request.user, request=request)
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
            else:
                messages.success(request, "Election opened for voting.")
            return redirect("elections:it-manage-detail", election_id=self.election.id)

        if action == "close":
            close_election(election=self.election, actor=request.user, request=request)
            messages.success(request, "Election closed.")
            return redirect("elections:it-manage-detail", election_id=self.election.id)

        if action == "toggle_staff_admin_voting":
            allow_staff_admin = request.POST.get("allow_staff_admin_voting") == "1"
            self.election.allow_staff_admin_voting = allow_staff_admin
            self.election.save(update_fields=["allow_staff_admin_voting", "updated_at"])
            log_event(
                category=AuditCategory.ELECTION,
                event_type="ELECTION_STAFF_ADMIN_VOTING_TOGGLED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={
                    "election_id": str(self.election.id),
                    "allow_staff_admin_voting": allow_staff_admin,
                },
            )
            if allow_staff_admin:
                messages.success(request, "Staff/Admin voting enabled for this election.")
            else:
                messages.success(request, "Staff/Admin voting disabled. Only students can vote now.")
            return redirect("elections:it-manage-detail", election_id=self.election.id)

        if action == "reset_voter_votes":
            form = self._voter_reset_form(request.POST)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(voter_reset_form=form))
            voter = form.cleaned_data["voter"]
            voter_label = voter.get_full_name() or voter.display_name or voter.username
            vote_ids = list(
                Vote.objects.filter(
                    election=self.election,
                    voter=voter,
                ).values_list("id", flat=True)
            )
            if not vote_ids:
                messages.info(request, "No saved votes found for that voter in this election.")
                return redirect("elections:it-manage-detail", election_id=self.election.id)
            removed_count = len(vote_ids)
            removed_position_ids = list(
                Vote.objects.filter(id__in=vote_ids).values_list("position_id", flat=True)
            )
            VoteAudit.objects.filter(vote_id__in=vote_ids).delete()
            Vote.objects.filter(id__in=vote_ids).delete()
            conflict_keys = [
                f"{self.election.id}:{position_id}:{voter.id}"
                for position_id in removed_position_ids
            ]
            if conflict_keys:
                SyncQueue.objects.filter(
                    operation_type=SyncOperationType.ELECTION_VOTE_SUBMISSION,
                    conflict_key__in=conflict_keys,
                ).delete()
            broadcast_election_analytics(self.election)
            log_event(
                category=AuditCategory.ELECTION,
                event_type="ELECTION_VOTER_VOTES_RESET",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={
                    "election_id": str(self.election.id),
                    "voter_id": str(voter.id),
                    "removed_votes": removed_count,
                },
            )
            messages.success(
                request,
                f"{voter_label} votes were reset for this election. Voter can now re-vote.",
            )
            return redirect("elections:it-manage-detail", election_id=self.election.id)

        if action == "remove_candidate":
            candidate = get_object_or_404(
                Candidate,
                pk=request.POST.get("candidate_id"),
                position__election=self.election,
            )
            candidate.is_active = False
            candidate.save(update_fields=["is_active", "updated_at"])
            log_event(
                category=AuditCategory.ELECTION,
                event_type="ELECTION_CANDIDATE_DEACTIVATED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={
                    "election_id": str(self.election.id),
                    "candidate_id": str(candidate.id),
                },
            )
            messages.success(request, "Candidate deactivated.")
            return redirect("elections:it-manage-detail", election_id=self.election.id)

        if action == "remove_position":
            position = get_object_or_404(
                Position,
                pk=request.POST.get("position_id"),
                election=self.election,
            )
            position.is_active = False
            position.save(update_fields=["is_active", "updated_at"])
            log_event(
                category=AuditCategory.ELECTION,
                event_type="ELECTION_POSITION_DEACTIVATED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={
                    "election_id": str(self.election.id),
                    "position_id": str(position.id),
                },
            )
            messages.success(request, "Position deactivated.")
            return redirect("elections:it-manage-detail", election_id=self.election.id)

        if action == "remove_voter_group":
            voter_group = get_object_or_404(
                VoterGroup,
                pk=request.POST.get("voter_group_id"),
                election=self.election,
            )
            voter_group.is_active = False
            voter_group.save(update_fields=["is_active", "updated_at"])
            log_event(
                category=AuditCategory.ELECTION,
                event_type="ELECTION_VOTER_GROUP_DEACTIVATED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={
                    "election_id": str(self.election.id),
                    "voter_group_id": str(voter_group.id),
                },
            )
            messages.success(request, "Voter group deactivated.")
            return redirect("elections:it-manage-detail", election_id=self.election.id)

        messages.error(request, "Invalid election management action.")
        return redirect("elections:it-manage-detail", election_id=self.election.id)


class ElectionVoteStartView(ElectionPortalAccessMixin, View):
    def get(self, request, *args, **kwargs):
        auto_close_due_elections(actor=request.user, request=request)
        election = get_object_or_404(Election, pk=kwargs["election_id"], is_active=True)
        if election.status != ElectionStatus.OPEN:
            messages.error(request, "Election is not open.")
            return redirect("elections:home")
        schedule_error = _election_voting_window_error(election)
        if schedule_error:
            messages.error(request, schedule_error)
            return redirect("elections:home")
        if not is_user_eligible_voter(election=election, user=request.user):
            messages.error(request, "You are not eligible to vote in this election.")
            return redirect("elections:home")
        remaining = remaining_positions_for_voter(election=election, user=request.user)
        if not remaining:
            messages.info(request, "You have already voted for all positions in this election.")
            return redirect("elections:home")
        first_position = remaining[0]
        return redirect(
            "elections:vote-position",
            election_id=election.id,
            position_id=first_position.id,
        )


class ElectionVotePositionView(ElectionPortalAccessMixin, TemplateView):
    template_name = "elections/vote_position.html"

    def dispatch(self, request, *args, **kwargs):
        auto_close_due_elections(actor=request.user, request=request)
        self.election = get_object_or_404(Election, pk=kwargs["election_id"], is_active=True)
        self.position = get_object_or_404(
            Position,
            pk=kwargs["position_id"],
            election=self.election,
            is_active=True,
        )
        if self.election.status != ElectionStatus.OPEN:
            messages.error(request, "Election is not open.")
            return redirect("elections:home")
        schedule_error = _election_voting_window_error(self.election)
        if schedule_error:
            messages.error(request, schedule_error)
            return redirect("elections:home")
        if not is_user_eligible_voter(election=self.election, user=request.user):
            messages.error(request, "You are not eligible to vote in this election.")
            return redirect("elections:home")
        if Vote.objects.filter(
            election=self.election,
            position=self.position,
            voter=request.user,
        ).exists():
            next_position = self._next_unvoted_position()
            if next_position:
                messages.info(
                    request,
                    f"Vote already saved for {self.position.name}. You cannot change it.",
                )
                return redirect(
                    "elections:vote-position",
                    election_id=self.election.id,
                    position_id=next_position.id,
                )
            messages.info(request, "Vote already saved for this position. Changes are blocked.")
            return redirect("elections:home")
        return super().dispatch(request, *args, **kwargs)

    def _remaining_positions(self):
        return remaining_positions_for_voter(election=self.election, user=self.request.user)

    def _next_unvoted_position(self):
        remaining = self._remaining_positions()
        for row in remaining:
            if row.id != self.position.id:
                return row
        return remaining[0] if remaining else None

    def _position_index(self):
        positions = list(self.election.positions.filter(is_active=True).order_by("sort_order", "name"))
        position_ids = [row.id for row in positions]
        if self.position.id not in position_ids:
            return 1, max(len(position_ids), 1)
        return position_ids.index(self.position.id) + 1, len(position_ids)

    def _form(self, data=None):
        return PositionVoteForm(position=self.position, data=data)

    def _voter_meta(self):
        return _user_mini_bio(
            user=self.request.user,
            session_id=self.election.session_id,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        index, total = self._position_index()
        context["election"] = self.election
        context["position"] = self.position
        context["form"] = kwargs.get("form") or self._form()
        context["step_index"] = index
        context["step_total"] = total
        context["remaining_count"] = len(self._remaining_positions())
        context.update(self._voter_meta())
        return context

    def post(self, request, *args, **kwargs):
        form = self._form(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        candidate = form.cleaned_data["candidate"]
        submission_token = secrets.token_hex(10)
        try:
            submit_vote_bundle(
                election=self.election,
                voter=request.user,
                choices_map={self.position.id: candidate.id},
                request=request,
                submission_token=submission_token,
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("elections:home")

        next_position = self._next_unvoted_position()
        if next_position:
            messages.success(request, f"Vote saved for {self.position.name}.")
            return redirect(
                "elections:vote-position",
                election_id=self.election.id,
                position_id=next_position.id,
            )
        messages.success(request, "All votes saved successfully. Voting is complete.")
        return redirect("accounts:logout")


class ElectionVoteConfirmView(ElectionPortalAccessMixin, View):
    def get(self, request, *args, **kwargs):
        messages.info(
            request,
            "Voting now auto-saves per position. Continue from Election Home.",
        )
        return redirect("elections:home")

    def post(self, request, *args, **kwargs):
        return self.get(request, *args, **kwargs)


class ElectionAnalyticsView(ElectionAnalyticsAccessMixin, TemplateView):
    template_name = "elections/analytics.html"

    def dispatch(self, request, *args, **kwargs):
        auto_close_due_elections(actor=request.user, request=request)
        self.election = get_object_or_404(Election, pk=kwargs["election_id"], is_active=True)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["election"] = self.election
        context["analytics"] = build_election_analytics_payload(self.election)
        context["ws_path"] = f"/ws/elections/{self.election.id}/analytics/"
        return context


class ElectionResultPDFView(ElectionAnalyticsAccessMixin, View):
    def get(self, request, *args, **kwargs):
        auto_close_due_elections(actor=request.user, request=request)
        election = get_object_or_404(Election, pk=kwargs["election_id"], is_active=True)
        if election.status != ElectionStatus.CLOSED:
            messages.error(request, "Election must be closed before exporting summary PDF.")
            return redirect("elections:analytics", election_id=election.id)
        try:
            pdf_bytes, artifact = generate_election_result_pdf(
                request=request,
                election=election,
                generated_by=request.user,
            )
        except RuntimeError:
            messages.error(
                request,
                "PDF engine dependencies are missing on this machine. Install WeasyPrint runtime libs.",
            )
            return redirect("elections:analytics", election_id=election.id)
        filename = f"NDGA-Election-Result-{election.id}.pdf"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        log_event(
            category=AuditCategory.ELECTION,
            event_type="ELECTION_RESULT_PDF_DOWNLOAD",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={"election_id": str(election.id), "artifact_id": str(artifact.id)},
        )
        return response


class ElectionResultVerificationView(TemplateView):
    template_name = "elections/verify.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        artifact = get_object_or_404(
            ElectionResultArtifact.objects.select_related("election", "generated_by"),
            pk=kwargs["artifact_id"],
        )
        incoming_hash = (self.request.GET.get("hash") or "").strip().lower()
        stored_hash = artifact.payload_hash.lower()
        hash_matches = bool(incoming_hash) and incoming_hash == stored_hash
        context["artifact"] = artifact
        context["incoming_hash"] = incoming_hash
        context["hash_matches"] = hash_matches
        context["verification_state"] = "VALID" if hash_matches else "CHECK_REQUIRED"
        context["payload"] = election_summary_payload(artifact.election)
        return context
