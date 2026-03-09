from django.contrib import admin

from apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("created_at", "recipient", "category", "title", "read_at")
    search_fields = ("recipient__username", "title", "message")
    list_filter = ("category", "read_at")
