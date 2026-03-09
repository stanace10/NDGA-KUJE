from django.contrib import admin

from apps.pdfs.models import PDFArtifact


@admin.register(PDFArtifact)
class PDFArtifactAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "document_type",
        "student",
        "session",
        "term",
        "payload_hash",
    )
    search_fields = ("student__username", "payload_hash", "source_label")
    list_filter = ("document_type", "session", "term")
