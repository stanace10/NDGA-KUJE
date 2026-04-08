from django.contrib import admin

from apps.dashboard.models import (
    LearningResource,
    LessonPlanDraft,
    PortalDocument,
    PrincipalSignature,
    PublicAdmissionWorkflowStatus,
    PublicSiteSubmission,
)


@admin.register(PrincipalSignature)
class PrincipalSignatureAdmin(admin.ModelAdmin):
    list_display = ("user", "updated_at")
    search_fields = ("user__username", "user__display_name")


@admin.register(LearningResource)
class LearningResourceAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "academic_class", "subject", "is_published", "due_date")
    list_filter = ("category", "is_published", "session", "term")
    search_fields = ("title", "description", "subject__name", "academic_class__code")


@admin.register(LessonPlanDraft)
class LessonPlanDraftAdmin(admin.ModelAdmin):
    list_display = ("topic", "subject", "academic_class", "teacher", "publish_to_learning_hub", "assignment_due_date")
    list_filter = ("publish_to_learning_hub", "session", "term")
    search_fields = ("topic", "subject__name", "academic_class__code", "teacher__username")


@admin.register(PortalDocument)
class PortalDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "student", "academic_class", "is_visible_to_student", "created_at")
    list_filter = ("category", "is_visible_to_student", "session", "term")
    search_fields = ("title", "student__username", "student__student_profile__student_number")


@admin.register(PublicSiteSubmission)
class PublicSiteSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "submission_type",
        "status",
        "admissions_status",
        "payment_status",
        "applicant_name",
        "contact_name",
        "contact_email",
        "intended_class",
        "generated_admission_number",
        "created_at",
    )
    list_filter = (
        "submission_type",
        "status",
        "admissions_status",
        "payment_status",
        "intended_class",
        "boarding_option",
    )
    search_fields = (
        "contact_name",
        "contact_email",
        "contact_phone",
        "applicant_name",
        "guardian_name",
        "guardian_phone",
        "subject",
        "generated_admission_number",
        "application_fee_reference",
    )
    actions = ("mark_admission_pending",)

    @admin.action(description="Mark selected admissions as pending review")
    def mark_admission_pending(self, request, queryset):
        queryset.filter(submission_type="ADMISSION").update(
            admissions_status=PublicAdmissionWorkflowStatus.PENDING
        )
