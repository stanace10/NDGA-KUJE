from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from apps.academics.models import AcademicClass, AcademicSession, Term
from apps.accounts.constants import ROLE_STUDENT
from apps.accounts.models import User
from core.models import TimeStampedModel, UUIDPrimaryKeyModel


class ChargeTargetType(models.TextChoices):
    STUDENT = "STUDENT", "Student"
    CLASS = "CLASS", "Class"


class PaymentMethod(models.TextChoices):
    CASH = "CASH", "Cash"
    TRANSFER = "TRANSFER", "Bank Transfer"
    POS = "POS", "POS"
    GATEWAY = "GATEWAY", "Gateway"
    OTHER = "OTHER", "Other"


class ExpenseCategory(models.TextChoices):
    UTILITIES = "UTILITIES", "Utilities"
    FACILITIES = "FACILITIES", "Facilities"
    OPERATIONS = "OPERATIONS", "Operations"
    ACADEMICS = "ACADEMICS", "Academics"
    TRANSPORT = "TRANSPORT", "Transport"
    OTHER = "OTHER", "Other"


class SalaryStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PAID = "PAID", "Paid"
    HOLD = "HOLD", "On Hold"


class PaymentGatewayProvider(models.TextChoices):
    PAYSTACK = "PAYSTACK", "Paystack"
    REMITTA = "REMITTA", "Remitta"
    FLUTTERWAVE = "FLUTTERWAVE", "Flutterwave"


class PaymentGatewayStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    INITIALIZED = "INITIALIZED", "Initialized"
    PAID = "PAID", "Paid"
    FAILED = "FAILED", "Failed"
    CANCELLED = "CANCELLED", "Cancelled"


class FinanceDataAuthority(models.TextChoices):
    LAN = "LAN", "LAN"
    CLOUD = "CLOUD", "Cloud"


class FinanceReconciliationStatus(models.TextChoices):
    IMPORTED = "IMPORTED", "Imported"
    DUPLICATE = "DUPLICATE", "Duplicate"
    CONFLICT = "CONFLICT", "Conflict"
    SKIPPED = "SKIPPED", "Skipped"


class ReminderType(models.TextChoices):
    UPCOMING = "UPCOMING", "Upcoming Due"
    OVERDUE = "OVERDUE", "Overdue"


class ReminderStatus(models.TextChoices):
    SENT = "SENT", "Sent"
    SKIPPED = "SKIPPED", "Skipped"
    FAILED = "FAILED", "Failed"


class AssetCategory(models.TextChoices):
    ICT = "ICT", "ICT"
    LAB = "LAB", "Lab"
    FURNITURE = "FURNITURE", "Furniture"
    SPORTS = "SPORTS", "Sports"
    TRANSPORT = "TRANSPORT", "Transport"
    FACILITY = "FACILITY", "Facility"
    OTHER = "OTHER", "Other"


class AssetStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    MAINTENANCE = "MAINTENANCE", "Maintenance"
    RETIRED = "RETIRED", "Retired"


class AssetMovementType(models.TextChoices):
    STOCK_IN = "STOCK_IN", "Stock In"
    ISSUE_OUT = "ISSUE_OUT", "Issue Out"
    RETURN_IN = "RETURN_IN", "Return In"
    WRITE_OFF = "WRITE_OFF", "Write Off"


class FinanceInstitutionProfile(TimeStampedModel):
    singleton_key = models.CharField(max_length=16, default="PRIMARY", unique=True, editable=False)
    school_bank_name = models.CharField(max_length=140, blank=True)
    school_account_name = models.CharField(max_length=160, blank=True)
    school_account_number = models.CharField(max_length=64, blank=True)
    application_form_fee_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    application_form_fee_note = models.CharField(max_length=220, blank=True)
    transcript_fee_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    transcript_fee_note = models.CharField(max_length=220, blank=True)
    include_bank_details_in_messages = models.BooleanField(default=False)
    show_on_receipt_pdf = models.BooleanField(default=False)
    show_on_result_pdf = models.BooleanField(default=False)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_finance_profiles",
    )

    class Meta:
        verbose_name = "Finance Institution Profile"
        verbose_name_plural = "Finance Institution Profile"

    def clean(self):
        self.singleton_key = "PRIMARY"
        self.school_bank_name = (self.school_bank_name or "").strip()
        self.school_account_name = (self.school_account_name or "").strip()
        self.school_account_number = (self.school_account_number or "").strip()
        self.application_form_fee_note = (self.application_form_fee_note or "").strip()
        self.transcript_fee_note = (self.transcript_fee_note or "").strip()

    @classmethod
    def load(cls):
        profile = cls.objects.first()
        if profile:
            return profile
        return cls.objects.create()

    def __str__(self):
        return "Finance Institution Profile"


class StudentCharge(TimeStampedModel):
    item_name = models.CharField(max_length=140)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField(null=True, blank=True)
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name="finance_student_charges",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finance_student_charges",
    )
    target_type = models.CharField(
        max_length=12,
        choices=ChargeTargetType.choices,
        default=ChargeTargetType.STUDENT,
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="finance_charges",
    )
    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="finance_charges",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_finance_charges",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("session", "target_type", "is_active")),
            models.Index(fields=("student", "is_active")),
            models.Index(fields=("academic_class", "is_active")),
        ]

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Charge amount must be greater than zero.")
        if self.term_id and self.term.session_id != self.session_id:
            raise ValidationError("Selected term does not belong to selected session.")
        if self.target_type == ChargeTargetType.STUDENT:
            if not self.student_id:
                raise ValidationError("Student target requires selecting a student.")
            if self.academic_class_id:
                raise ValidationError("Class must be empty for student-target charge.")
            if not self.student.has_role(ROLE_STUDENT):
                raise ValidationError("Selected user is not a student.")
        if self.target_type == ChargeTargetType.CLASS:
            if not self.academic_class_id:
                raise ValidationError("Class target requires selecting a class.")
            if self.student_id:
                raise ValidationError("Student must be empty for class-target charge.")

    def __str__(self):
        target = self.student.username if self.student_id else (self.academic_class.code if self.academic_class_id else "-")
        return f"{self.item_name} [{target}] {self.amount}"


class Payment(TimeStampedModel):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="finance_payments",
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name="finance_payments",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finance_payments",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(
        max_length=16,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    gateway_reference = models.CharField(max_length=120, blank=True)
    note = models.TextField(blank=True)
    payment_date = models.DateField(default=timezone.localdate)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_finance_payments",
    )
    is_void = models.BooleanField(default=False)
    source_authority = models.CharField(
        max_length=16,
        choices=FinanceDataAuthority.choices,
        default=FinanceDataAuthority.LAN,
    )
    source_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-payment_date", "-created_at")
        indexes = [
            models.Index(fields=("student", "session", "payment_date")),
            models.Index(fields=("is_void", "payment_date")),
            models.Index(fields=("source_authority", "source_updated_at")),
        ]

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Payment amount must be greater than zero.")
        if self.term_id and self.term.session_id != self.session_id:
            raise ValidationError("Selected term does not belong to selected session.")
        if not self.student.has_role(ROLE_STUDENT):
            raise ValidationError("Selected payer must be a student account.")

    def __str__(self):
        return f"{self.student.username} {self.amount} ({self.payment_method})"

    def save(self, *args, **kwargs):
        """
        Lock core payment fields after receipt issuance.

        A receipt is an auditable financial artifact. After a receipt exists,
        only non-financial flags like `is_void` may change.
        """
        if self.pk:
            update_fields = kwargs.get("update_fields")
            tracked_fields = (
                "student_id",
                "session_id",
                "term_id",
                "amount",
                "payment_method",
                "gateway_reference",
                "note",
                "payment_date",
                "received_by_id",
            )
            if update_fields is not None:
                update_field_set = set(update_fields)
                tracked_fields = tuple(
                    field
                    for field in tracked_fields
                    if field in update_field_set or field.removesuffix("_id") in update_field_set
                )
            if tracked_fields and Receipt.objects.filter(payment_id=self.pk).exists():
                original = (
                    Payment.objects.filter(pk=self.pk)
                    .values(*tracked_fields)
                    .first()
                )
                if original:
                    changed_fields = [
                        field.removesuffix("_id")
                        for field in tracked_fields
                        if getattr(self, field) != original.get(field)
                    ]
                    if changed_fields:
                        raise ValidationError(
                            "Cannot edit payment fields after receipt issuance. "
                            "Void the payment and create a new record instead."
                        )
        super().save(*args, **kwargs)


class Receipt(UUIDPrimaryKeyModel, TimeStampedModel):
    payment = models.OneToOneField(
        Payment,
        on_delete=models.CASCADE,
        related_name="receipt",
    )
    receipt_number = models.CharField(max_length=40, unique=True)
    payload_hash = models.CharField(max_length=64)
    issued_at = models.DateTimeField(default=timezone.now)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_finance_receipts",
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-issued_at",)
        indexes = [
            models.Index(fields=("receipt_number",)),
            models.Index(fields=("payload_hash",)),
        ]

    def __str__(self):
        return self.receipt_number


class Expense(TimeStampedModel):
    category = models.CharField(
        max_length=24,
        choices=ExpenseCategory.choices,
        default=ExpenseCategory.OPERATIONS,
    )
    title = models.CharField(max_length=160)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    expense_date = models.DateField(default=timezone.localdate)
    description = models.TextField(blank=True)
    receipt_attachment = models.FileField(
        upload_to="finance/expenses/",
        blank=True,
        null=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_finance_expenses",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-expense_date", "-created_at")
        indexes = [
            models.Index(fields=("expense_date", "category")),
            models.Index(fields=("is_active", "expense_date")),
        ]

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Expense amount must be greater than zero.")

    def __str__(self):
        return f"{self.title} - {self.amount}"


class SalaryRecord(TimeStampedModel):
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="finance_salary_records",
    )
    month = models.DateField(help_text="Use first day of the salary month.")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=12,
        choices=SalaryStatus.choices,
        default=SalaryStatus.PENDING,
    )
    payment_reference = models.CharField(max_length=140, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_finance_salaries",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-month", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("staff", "month"),
                name="unique_staff_salary_month",
            ),
            models.CheckConstraint(
                check=Q(amount__gt=0),
                name="salary_amount_gt_zero",
            ),
        ]
        indexes = [
            models.Index(fields=("month", "status")),
            models.Index(fields=("is_active", "month")),
        ]

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Salary amount must be greater than zero.")
        if self.staff.has_role(ROLE_STUDENT):
            raise ValidationError("Salary record cannot be assigned to student accounts.")

    def save(self, *args, **kwargs):
        if self.status == SalaryStatus.PAID and self.paid_at is None:
            self.paid_at = timezone.now()
        if self.status != SalaryStatus.PAID:
            self.paid_at = None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.staff.username} {self.month:%Y-%m} {self.amount}"


class PaymentGatewayTransaction(TimeStampedModel):
    reference = models.CharField(max_length=80, unique=True)
    provider = models.CharField(
        max_length=16,
        choices=PaymentGatewayProvider.choices,
        default=PaymentGatewayProvider.PAYSTACK,
    )
    status = models.CharField(
        max_length=16,
        choices=PaymentGatewayStatus.choices,
        default=PaymentGatewayStatus.PENDING,
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="finance_gateway_transactions",
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name="finance_gateway_transactions",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finance_gateway_transactions",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    callback_url = models.CharField(max_length=320, blank=True)
    authorization_url = models.CharField(max_length=500, blank=True)
    gateway_reference = models.CharField(max_length=180, blank=True)
    initialized_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="initiated_gateway_transactions",
    )
    payment = models.OneToOneField(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gateway_transaction",
    )
    source_authority = models.CharField(
        max_length=16,
        choices=FinanceDataAuthority.choices,
        default=FinanceDataAuthority.LAN,
    )
    source_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("status", "created_at")),
            models.Index(fields=("student", "session", "status")),
            models.Index(fields=("provider", "reference")),
            models.Index(fields=("source_authority", "source_updated_at")),
        ]

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Gateway transaction amount must be greater than zero.")
        if self.term_id and self.term.session_id != self.session_id:
            raise ValidationError("Selected term does not belong to selected session.")
        if not self.student.has_role(ROLE_STUDENT):
            raise ValidationError("Gateway transaction student must be a student account.")

    def __str__(self):
        return f"{self.reference} [{self.status}]"


class TranscriptRequestPaymentStatus(models.TextChoices):
    UNPAID = "UNPAID", "Unpaid"
    INITIALIZED = "INITIALIZED", "Payment Initialized"
    PAID = "PAID", "Paid"


class TranscriptRequestApprovalStatus(models.TextChoices):
    PENDING = "PENDING", "Pending Review"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class TranscriptRequest(TimeStampedModel):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transcript_requests",
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transcript_requests",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_transcript_requests",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_status = models.CharField(
        max_length=16,
        choices=TranscriptRequestPaymentStatus.choices,
        default=TranscriptRequestPaymentStatus.UNPAID,
    )
    approval_status = models.CharField(
        max_length=16,
        choices=TranscriptRequestApprovalStatus.choices,
        default=TranscriptRequestApprovalStatus.PENDING,
    )
    gateway_transaction = models.OneToOneField(
        PaymentGatewayTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transcript_request",
    )
    payment = models.OneToOneField(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transcript_request",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_transcript_requests",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)
    response_message = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("student", "payment_status", "approval_status")),
        ]

    def clean(self):
        if not self.student.has_role(ROLE_STUDENT):
            raise ValidationError("Transcript requests can only be created for student accounts.")
        self.note = (self.note or "").strip()
        self.response_message = (self.response_message or "").strip()

    @property
    def is_access_granted(self):
        return (
            self.payment_status == TranscriptRequestPaymentStatus.PAID
            and self.approval_status == TranscriptRequestApprovalStatus.APPROVED
        )

    def __str__(self):
        return f"Transcript request for {self.student.username}"


class FinanceDeltaSyncCursor(TimeStampedModel):
    cursor_name = models.CharField(max_length=40, unique=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_reference = models.CharField(max_length=120, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("cursor_name",)

    def __str__(self):
        return self.cursor_name


class FinanceReconciliationEvent(TimeStampedModel):
    direction = models.CharField(max_length=24, default="CLOUD_TO_LAN")
    status = models.CharField(
        max_length=16,
        choices=FinanceReconciliationStatus.choices,
        default=FinanceReconciliationStatus.IMPORTED,
    )
    reference = models.CharField(max_length=120)
    gateway_reference = models.CharField(max_length=180, blank=True)
    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reconciliation_events",
    )
    gateway_transaction = models.ForeignKey(
        PaymentGatewayTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reconciliation_events",
    )
    notes = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_finance_reconciliation_events",
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("status", "created_at")),
            models.Index(fields=("reference",)),
        ]

    def __str__(self):
        return f"{self.reference} [{self.status}]"


class FinanceReminderDispatch(TimeStampedModel):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="finance_reminder_dispatches",
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name="finance_reminder_dispatches",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finance_reminder_dispatches",
    )
    reminder_date = models.DateField(default=timezone.localdate)
    reminder_type = models.CharField(max_length=16, choices=ReminderType.choices)
    status = models.CharField(
        max_length=16,
        choices=ReminderStatus.choices,
        default=ReminderStatus.SENT,
    )
    due_date = models.DateField(null=True, blank=True)
    outstanding_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    charge_ids = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finance_reminders_sent",
    )

    class Meta:
        ordering = ("-reminder_date", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("student", "session", "term", "reminder_date", "reminder_type"),
                name="unique_finance_reminder_per_student_day",
            )
        ]
        indexes = [
            models.Index(fields=("reminder_date", "reminder_type", "status")),
            models.Index(fields=("student", "session", "reminder_date")),
        ]

    def clean(self):
        if not self.student.has_role(ROLE_STUDENT):
            raise ValidationError("Reminder recipient must be a student account.")
        if self.term_id and self.term.session_id != self.session_id:
            raise ValidationError("Selected term does not belong to selected session.")

    def __str__(self):
        return f"{self.student.username} {self.reminder_type} {self.reminder_date}"


class InventoryAsset(TimeStampedModel):
    asset_code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=160)
    category = models.CharField(
        max_length=24,
        choices=AssetCategory.choices,
        default=AssetCategory.OTHER,
    )
    status = models.CharField(
        max_length=16,
        choices=AssetStatus.choices,
        default=AssetStatus.ACTIVE,
    )
    location = models.CharField(max_length=140, blank=True)
    description = models.TextField(blank=True)
    quantity_total = models.PositiveIntegerField(default=1)
    quantity_available = models.PositiveIntegerField(default=1)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    purchase_date = models.DateField(null=True, blank=True)
    acquisition_reference = models.CharField(max_length=140, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_inventory_assets",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("asset_code",)
        indexes = [
            models.Index(fields=("category", "status", "is_active")),
            models.Index(fields=("asset_code",)),
        ]

    def clean(self):
        if self.quantity_total < 0:
            raise ValidationError("Asset total quantity cannot be negative.")
        if self.quantity_available < 0:
            raise ValidationError("Asset available quantity cannot be negative.")
        if self.quantity_available > self.quantity_total:
            raise ValidationError("Asset available quantity cannot exceed total quantity.")
        if self.unit_cost < 0:
            raise ValidationError("Asset unit cost cannot be negative.")

    @property
    def total_value(self):
        return self.unit_cost * self.quantity_total

    def __str__(self):
        return f"{self.asset_code} - {self.name}"


class InventoryAssetMovement(TimeStampedModel):
    asset = models.ForeignKey(
        InventoryAsset,
        on_delete=models.CASCADE,
        related_name="movements",
    )
    movement_type = models.CharField(max_length=16, choices=AssetMovementType.choices)
    quantity = models.PositiveIntegerField()
    note = models.TextField(blank=True)
    reference = models.CharField(max_length=140, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_inventory_movements",
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("movement_type", "created_at")),
            models.Index(fields=("asset", "created_at")),
        ]

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError("Movement quantity must be greater than zero.")

    def _apply_asset_change(self):
        asset = self.asset
        qty = int(self.quantity)

        if self.movement_type == AssetMovementType.STOCK_IN:
            asset.quantity_total += qty
            asset.quantity_available += qty
        elif self.movement_type == AssetMovementType.ISSUE_OUT:
            if asset.quantity_available < qty:
                raise ValidationError("Cannot issue more items than currently available.")
            asset.quantity_available -= qty
        elif self.movement_type == AssetMovementType.RETURN_IN:
            if asset.quantity_available + qty > asset.quantity_total:
                raise ValidationError("Return quantity exceeds total tracked stock.")
            asset.quantity_available += qty
        elif self.movement_type == AssetMovementType.WRITE_OFF:
            if asset.quantity_available < qty:
                raise ValidationError("Cannot write off more than available stock.")
            if asset.quantity_total < qty:
                raise ValidationError("Cannot write off more than total stock.")
            asset.quantity_available -= qty
            asset.quantity_total -= qty
        from apps.sync.model_sync import suppress_model_sync_capture

        with suppress_model_sync_capture():
            asset.save(update_fields=["quantity_total", "quantity_available", "updated_at"])

    def save(self, *args, **kwargs):
        is_create = self._state.adding
        if not is_create:
            super().save(*args, **kwargs)
            return
        with transaction.atomic():
            self._apply_asset_change()
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.asset.asset_code} {self.movement_type} {self.quantity}"
