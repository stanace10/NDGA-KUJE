from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.academics.models import AcademicClass, AcademicSession
from apps.accounts.constants import ROLE_STUDENT
from apps.accounts.models import Role
from core.models import TimeStampedModel, UUIDPrimaryKeyModel


class ElectionStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    OPEN = "OPEN", "Open"
    CLOSED = "CLOSED", "Closed"
    ARCHIVED = "ARCHIVED", "Archived"


class Election(TimeStampedModel):
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="elections",
    )
    status = models.CharField(
        max_length=16,
        choices=ElectionStatus.choices,
        default=ElectionStatus.DRAFT,
    )
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="opened_elections",
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_elections",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_elections",
    )
    allow_staff_admin_voting = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-updated_at",)
        indexes = [
            models.Index(fields=("status", "updated_at")),
            models.Index(fields=("session", "status")),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("title", "session"),
                name="unique_election_title_per_session",
            )
        ]

    def clean(self):
        if self.ends_at and self.starts_at and self.ends_at <= self.starts_at:
            raise ValidationError("Election end time must be after start time.")

    def __str__(self):
        return self.title


class Position(TimeStampedModel):
    election = models.ForeignKey(
        Election,
        on_delete=models.CASCADE,
        related_name="positions",
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("sort_order", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("election", "name"),
                name="unique_position_name_per_election",
            ),
            models.UniqueConstraint(
                fields=("election", "sort_order"),
                name="unique_position_order_per_election",
            ),
        ]

    def __str__(self):
        return f"{self.election.title} - {self.name}"


class Candidate(TimeStampedModel):
    position = models.ForeignKey(
        Position,
        on_delete=models.CASCADE,
        related_name="candidates",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="election_candidate_entries",
    )
    display_name = models.CharField(max_length=150, blank=True)
    manifesto = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("position__sort_order", "user__username")
        constraints = [
            models.UniqueConstraint(
                fields=("position", "user"),
                name="unique_candidate_user_per_position",
            )
        ]

    def clean(self):
        if not hasattr(self.user, "student_profile") and not hasattr(
            self.user, "staff_profile"
        ):
            raise ValidationError(
                "Candidate must be linked to an existing student or staff profile."
            )
        if self.user.has_role(ROLE_STUDENT) is False and not hasattr(
            self.user, "staff_profile"
        ):
            raise ValidationError("Candidate user is not a recognized school member.")

    def __str__(self):
        return self.display_name or self.user.get_full_name() or self.user.username


class VoterGroup(TimeStampedModel):
    election = models.ForeignKey(
        Election,
        on_delete=models.CASCADE,
        related_name="voter_groups",
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    include_all_students = models.BooleanField(default=False)
    include_all_staff = models.BooleanField(default=False)
    roles = models.ManyToManyField(Role, blank=True, related_name="election_voter_groups")
    academic_classes = models.ManyToManyField(
        AcademicClass,
        blank=True,
        related_name="election_voter_groups",
    )
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="election_voter_groups",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=("election", "name"),
                name="unique_voter_group_name_per_election",
            )
        ]

    def __str__(self):
        return f"{self.election.title} - {self.name}"


class Vote(TimeStampedModel):
    election = models.ForeignKey(
        Election,
        on_delete=models.CASCADE,
        related_name="votes",
    )
    position = models.ForeignKey(
        Position,
        on_delete=models.CASCADE,
        related_name="votes",
    )
    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name="votes",
    )
    voter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="election_votes",
    )
    submission_token = models.CharField(max_length=96, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("election", "position", "voter"),
                name="unique_vote_per_voter_position_in_election",
            )
        ]
        indexes = [
            models.Index(fields=("election", "position")),
            models.Index(fields=("election", "voter")),
        ]

    def clean(self):
        if self.position_id and self.election_id and self.position.election_id != self.election_id:
            raise ValidationError("Vote position must belong to selected election.")
        if self.candidate_id and self.position_id and self.candidate.position_id != self.position_id:
            raise ValidationError("Vote candidate must belong to selected position.")
        if self.candidate_id and self.election_id:
            if self.candidate.position.election_id != self.election_id:
                raise ValidationError("Vote candidate must belong to selected election.")

    def __str__(self):
        return f"{self.election.title}: {self.voter.username} -> {self.position.name}"


class VoteAudit(TimeStampedModel):
    vote = models.OneToOneField(
        Vote,
        on_delete=models.CASCADE,
        related_name="audit",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    device = models.CharField(max_length=255, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("ip_address", "created_at"))]

    def __str__(self):
        return f"VoteAudit({self.vote_id})"


class ElectionResultArtifact(UUIDPrimaryKeyModel, TimeStampedModel):
    election = models.ForeignKey(
        Election,
        on_delete=models.CASCADE,
        related_name="result_artifacts",
    )
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_election_result_artifacts",
    )
    payload_hash = models.CharField(max_length=64)
    published_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("election", "created_at")),
            models.Index(fields=("payload_hash",)),
        ]

    def __str__(self):
        return f"ElectionResultArtifact({self.election.title})"
