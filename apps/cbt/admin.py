from django.contrib import admin

from apps.cbt.models import (
    CorrectAnswer,
    Exam,
    ExamAttempt,
    ExamAttemptAnswer,
    ExamBlueprint,
    ExamDocumentImport,
    ExamQuestion,
    ExamSimulation,
    ExamReviewAction,
    Option,
    Question,
    QuestionBank,
    SimulationAttemptRecord,
    SimulationWrapper,
)


@admin.register(QuestionBank)
class QuestionBankAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "owner",
        "subject",
        "academic_class",
        "session",
        "term",
        "is_active",
    )
    search_fields = ("name", "owner__username", "subject__name", "academic_class__code")
    list_filter = ("is_active", "subject", "session", "term")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "subject",
        "question_type",
        "difficulty",
        "created_by",
        "is_active",
        "updated_at",
    )
    search_fields = ("stem", "topic", "subject__name", "created_by__username")
    list_filter = ("question_type", "difficulty", "source_type", "is_active")


@admin.register(Option)
class OptionAdmin(admin.ModelAdmin):
    list_display = ("question", "label", "sort_order")
    search_fields = ("question__stem", "option_text")


@admin.register(CorrectAnswer)
class CorrectAnswerAdmin(admin.ModelAdmin):
    list_display = ("question", "is_finalized")
    filter_horizontal = ("correct_options",)


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "exam_type",
        "status",
        "subject",
        "academic_class",
        "session",
        "term",
        "created_by",
    )
    search_fields = ("title", "subject__name", "academic_class__code", "created_by__username")
    list_filter = ("exam_type", "status", "session", "term", "subject")


@admin.register(ExamBlueprint)
class ExamBlueprintAdmin(admin.ModelAdmin):
    list_display = ("exam", "duration_minutes", "max_attempts", "shuffle_questions", "shuffle_options")


@admin.register(ExamQuestion)
class ExamQuestionAdmin(admin.ModelAdmin):
    list_display = ("exam", "question", "sort_order", "marks")
    search_fields = ("exam__title", "question__stem")
    list_filter = ("exam__status",)


@admin.register(SimulationWrapper)
class SimulationWrapperAdmin(admin.ModelAdmin):
    list_display = (
        "tool_name",
        "tool_category",
        "score_mode",
        "max_score",
        "status",
        "is_active",
        "updated_at",
    )
    search_fields = ("tool_name", "tool_type", "description")
    list_filter = ("tool_category", "score_mode", "status", "is_active")


@admin.register(ExamSimulation)
class ExamSimulationAdmin(admin.ModelAdmin):
    list_display = (
        "exam",
        "simulation_wrapper",
        "sort_order",
        "writeback_target",
        "is_required",
    )
    search_fields = ("exam__title", "simulation_wrapper__tool_name")
    list_filter = ("writeback_target", "is_required")


@admin.register(ExamReviewAction)
class ExamReviewActionAdmin(admin.ModelAdmin):
    list_display = ("exam", "actor", "from_status", "to_status", "action", "created_at")
    list_filter = ("from_status", "to_status", "action")
    search_fields = ("exam__title", "actor__username", "comment")


@admin.register(ExamDocumentImport)
class ExamDocumentImportAdmin(admin.ModelAdmin):
    list_display = ("source_filename", "uploaded_by", "extraction_status", "created_at")
    list_filter = ("extraction_status",)
    search_fields = ("source_filename", "uploaded_by__username")


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "exam",
        "student",
        "attempt_number",
        "status",
        "is_locked",
        "objective_score",
        "theory_score",
        "writeback_completed",
        "updated_at",
    )
    search_fields = ("exam__title", "student__username")
    list_filter = ("status", "is_locked", "writeback_completed")


@admin.register(ExamAttemptAnswer)
class ExamAttemptAnswerAdmin(admin.ModelAdmin):
    list_display = (
        "attempt",
        "exam_question",
        "is_flagged",
        "is_correct",
        "auto_score",
        "teacher_score",
    )
    search_fields = ("attempt__student__username", "exam_question__question__stem")
    list_filter = ("is_flagged", "is_correct")


@admin.register(SimulationAttemptRecord)
class SimulationAttemptRecordAdmin(admin.ModelAdmin):
    list_display = (
        "attempt",
        "exam_simulation",
        "status",
        "final_score",
        "imported_target",
        "imported_at",
    )
    search_fields = (
        "attempt__student__username",
        "attempt__exam__title",
        "exam_simulation__simulation_wrapper__tool_name",
    )
    list_filter = (
        "status",
        "imported_target",
        "exam_simulation__simulation_wrapper__score_mode",
        "exam_simulation__simulation_wrapper__status",
    )
