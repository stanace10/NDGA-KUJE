from django.contrib import admin

from apps.finance.models import (
    Expense,
    FinanceReminderDispatch,
    InventoryAsset,
    InventoryAssetMovement,
    Payment,
    PaymentGatewayTransaction,
    Receipt,
    SalaryRecord,
    StudentCharge,
)


@admin.register(StudentCharge)
class StudentChargeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "item_name",
        "target_type",
        "student",
        "academic_class",
        "amount",
        "session",
        "term",
        "is_active",
    )
    list_filter = ("target_type", "session", "term", "is_active")
    search_fields = ("item_name", "student__username", "academic_class__code")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "student",
        "amount",
        "payment_method",
        "payment_date",
        "session",
        "term",
        "is_void",
    )
    list_filter = ("payment_method", "session", "term", "is_void")
    search_fields = ("student__username", "gateway_reference")


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ("id", "receipt_number", "payment", "issued_at", "generated_by")
    search_fields = ("receipt_number", "payment__student__username", "payload_hash")


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "category", "amount", "expense_date", "is_active")
    list_filter = ("category", "is_active", "expense_date")
    search_fields = ("title", "description")


@admin.register(SalaryRecord)
class SalaryRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "staff", "month", "amount", "status", "is_active")
    list_filter = ("status", "is_active", "month")
    search_fields = ("staff__username", "payment_reference")


@admin.register(PaymentGatewayTransaction)
class PaymentGatewayTransactionAdmin(admin.ModelAdmin):
    list_display = ("reference", "student", "amount", "provider", "status", "created_at")
    list_filter = ("provider", "status", "created_at")
    search_fields = ("reference", "gateway_reference", "student__username")


@admin.register(FinanceReminderDispatch)
class FinanceReminderDispatchAdmin(admin.ModelAdmin):
    list_display = ("student", "session", "term", "reminder_date", "reminder_type", "status")
    list_filter = ("reminder_type", "status", "reminder_date")
    search_fields = ("student__username", "student__student_profile__student_number")


@admin.register(InventoryAsset)
class InventoryAssetAdmin(admin.ModelAdmin):
    list_display = ("asset_code", "name", "category", "status", "quantity_available", "quantity_total", "is_active")
    list_filter = ("category", "status", "is_active")
    search_fields = ("asset_code", "name", "location")


@admin.register(InventoryAssetMovement)
class InventoryAssetMovementAdmin(admin.ModelAdmin):
    list_display = ("asset", "movement_type", "quantity", "recorded_by", "created_at")
    list_filter = ("movement_type", "created_at")
    search_fields = ("asset__asset_code", "asset__name", "reference")
