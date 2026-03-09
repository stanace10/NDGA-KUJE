from django.contrib import admin

from apps.dashboard.models import LearningResource, LessonPlanDraft, PortalDocument, PrincipalSignature


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
