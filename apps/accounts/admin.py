from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.accounts.models import Role, StaffProfile, StudentProfile, User


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_system")
    search_fields = ("code", "name")


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "primary_role", "is_active", "is_staff")
    list_filter = ("primary_role", "is_active", "is_staff")
    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "NDGA Access",
            {
                "fields": (
                    "primary_role",
                    "secondary_roles",
                    "password_changed_count",
                    "must_change_password",
                    "login_code_hash",
                    "login_code_expires_at",
                )
            },
        ),
    )
    readonly_fields = ("login_code_hash",)


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("staff_id", "user", "phone_number")
    search_fields = ("staff_id", "user__username", "user__first_name", "user__last_name")


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("student_number", "user", "admission_date")
    search_fields = (
        "student_number",
        "user__username",
        "user__first_name",
        "user__last_name",
    )
