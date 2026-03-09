from django.contrib import admin

from apps.elections.models import (
    Candidate,
    Election,
    ElectionResultArtifact,
    Position,
    Vote,
    VoteAudit,
    VoterGroup,
)


class CandidateInline(admin.TabularInline):
    model = Candidate
    extra = 0


class PositionInline(admin.TabularInline):
    model = Position
    extra = 0


@admin.register(Election)
class ElectionAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "session", "status", "starts_at", "ends_at", "updated_at")
    list_filter = ("status", "session")
    search_fields = ("title", "description")
    inlines = [PositionInline]


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "election", "sort_order", "is_active")
    list_filter = ("election", "is_active")
    search_fields = ("name", "election__title")
    inlines = [CandidateInline]


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ("id", "position", "user", "display_name", "is_active")
    list_filter = ("is_active", "position__election")
    search_fields = ("display_name", "user__username", "position__name")


@admin.register(VoterGroup)
class VoterGroupAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "election", "include_all_students", "include_all_staff", "is_active")
    list_filter = ("is_active", "include_all_students", "include_all_staff", "election")
    search_fields = ("name", "description", "election__title")
    filter_horizontal = ("roles", "academic_classes", "users")


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ("id", "election", "position", "candidate", "voter", "created_at")
    list_filter = ("election", "position")
    search_fields = ("voter__username", "candidate__display_name", "candidate__user__username")


@admin.register(VoteAudit)
class VoteAuditAdmin(admin.ModelAdmin):
    list_display = ("id", "vote", "ip_address", "device", "created_at")
    list_filter = ("created_at",)
    search_fields = ("ip_address", "device", "user_agent")


@admin.register(ElectionResultArtifact)
class ElectionResultArtifactAdmin(admin.ModelAdmin):
    list_display = ("id", "election", "generated_by", "published_at", "created_at")
    list_filter = ("election",)
    search_fields = ("payload_hash", "election__title")
