from django.contrib import admin

from apps.setup_wizard.models import AcademicOperationWindow, RuntimeFeatureFlags, SystemSetupState


@admin.register(SystemSetupState)
class SystemSetupStateAdmin(admin.ModelAdmin):
    list_display = ("state", "current_session", "current_term", "last_updated_by", "updated_at")


@admin.register(RuntimeFeatureFlags)
class RuntimeFeatureFlagsAdmin(admin.ModelAdmin):
    list_display = (
        "cbt_enabled",
        "election_enabled",
        "offline_mode_enabled",
        "lockdown_enabled",
        "last_updated_by",
        "updated_at",
    )


@admin.register(AcademicOperationWindow)
class AcademicOperationWindowAdmin(admin.ModelAdmin):
    list_display = ("window_type", "is_enabled", "start_at", "end_at", "last_updated_by", "updated_at")
    list_filter = ("window_type", "is_enabled")
