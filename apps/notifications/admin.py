from django.contrib import admin

from apps.notifications.models import BirthdayContact, BirthdayDispatch, Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("created_at", "recipient", "category", "title", "read_at")
    search_fields = ("recipient__username", "title", "message")
    list_filter = ("category", "read_at")


@admin.register(BirthdayContact)
class BirthdayContactAdmin(admin.ModelAdmin):
    list_display = ("full_name", "contact_type", "birth_month", "birth_day", "email", "phone", "is_active")
    list_filter = ("contact_type", "birth_month", "is_active")
    search_fields = ("full_name", "email", "phone", "student_name", "student_admission_no")
    ordering = ("birth_month", "birth_day", "full_name")


@admin.register(BirthdayDispatch)
class BirthdayDispatchAdmin(admin.ModelAdmin):
    list_display = ("contact", "birthday_year", "status", "sent_email", "sent_whatsapp", "dispatched_at")
    list_filter = ("birthday_year", "status", "sent_email", "sent_whatsapp", "dispatched_at")
    search_fields = ("contact__full_name", "recipient", "message_subject")
    ordering = ("-created_at",)
