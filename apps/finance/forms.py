from __future__ import annotations

from django import forms
from django.db import models
from django.utils import timezone

from apps.academics.models import AcademicClass
from apps.accounts.constants import STAFF_ROLE_CODES
from apps.accounts.models import User
from apps.finance.models import (
    AssetMovementType,
    ChargeTargetType,
    FinanceInstitutionProfile,
    InventoryAsset,
    InventoryAssetMovement,
    PaymentGatewayProvider,
    Expense,
    Payment,
    SalaryRecord,
    StudentCharge,
)
from core.upload_scan import validate_receipt_upload


class _StyledFormMixin:
    base_input_class = (
        "w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm "
        "focus:border-ndga-navy/60 focus:ring-4 focus:ring-ndga-navy/10"
    )

    def apply_default_styles(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "h-4 w-4 rounded border-slate-300")
                continue
            if isinstance(widget, forms.SelectMultiple):
                widget.attrs.setdefault("class", f"{self.base_input_class} min-h-28")
                continue
            widget.attrs.setdefault("class", self.base_input_class)


class StudentChargeForm(_StyledFormMixin, forms.ModelForm):
    academic_class = forms.ModelChoiceField(
        queryset=AcademicClass.objects.order_by("code"),
        required=True,
    )

    class Meta:
        model = StudentCharge
        fields = [
            "item_name",
            "description",
            "amount",
            "academic_class",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_default_styles()

    def clean_item_name(self):
        return (self.cleaned_data.get("item_name") or "").strip()

    def clean(self):
        cleaned = super().clean()
        academic_class = cleaned.get("academic_class")
        if not academic_class:
            raise forms.ValidationError("Select class for termly fee structure.")
        cleaned["target_type"] = ChargeTargetType.CLASS
        cleaned["student"] = None
        self.instance.target_type = ChargeTargetType.CLASS
        self.instance.student = None
        self.instance.due_date = None
        return cleaned


class PaymentForm(_StyledFormMixin, forms.ModelForm):
    student = forms.ModelChoiceField(
        queryset=User.objects.filter(primary_role__code="STUDENT").order_by("username"),
        required=True,
    )

    class Meta:
        model = Payment
        fields = [
            "student",
            "amount",
            "payment_method",
            "gateway_reference",
            "payment_date",
            "note",
        ]
        widgets = {
            "payment_date": forms.DateInput(attrs={"type": "date"}),
            "note": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_default_styles()
        self.fields["payment_date"].initial = timezone.localdate()


class GatewayPaymentInitForm(_StyledFormMixin, forms.Form):
    student = forms.ModelChoiceField(
        queryset=User.objects.filter(primary_role__code="STUDENT", is_active=True).order_by("username"),
        required=True,
    )
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)
    provider = forms.ChoiceField(
        choices=PaymentGatewayProvider.choices,
        initial=PaymentGatewayProvider.PAYSTACK,
    )
    auto_email_link = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_default_styles()


class ExpenseForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            "category",
            "title",
            "amount",
            "expense_date",
            "description",
            "receipt_attachment",
            "is_active",
        ]
        widgets = {
            "expense_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_default_styles()
        self.fields["expense_date"].initial = timezone.localdate()

    def clean_receipt_attachment(self):
        upload = self.cleaned_data.get("receipt_attachment")
        if not upload:
            return upload
        return validate_receipt_upload(upload)


class SalaryRecordForm(_StyledFormMixin, forms.ModelForm):
    staff = forms.ModelChoiceField(
        queryset=User.objects.filter(primary_role__code__in=STAFF_ROLE_CODES).order_by("username"),
        required=True,
    )

    class Meta:
        model = SalaryRecord
        fields = [
            "staff",
            "month",
            "amount",
            "status",
            "payment_reference",
            "is_active",
        ]
        widgets = {
            "month": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_default_styles()
        today = timezone.localdate()
        self.fields["month"].initial = today.replace(day=1)

    def clean_month(self):
        value = self.cleaned_data["month"]
        return value.replace(day=1)


class InventoryAssetForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = InventoryAsset
        fields = [
            "asset_code",
            "name",
            "category",
            "status",
            "location",
            "description",
            "quantity_total",
            "quantity_available",
            "unit_cost",
            "purchase_date",
            "acquisition_reference",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "purchase_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_default_styles()

    def clean_asset_code(self):
        return (self.cleaned_data.get("asset_code") or "").strip().upper()

    def clean_name(self):
        return (self.cleaned_data.get("name") or "").strip()


class InventoryAssetMovementForm(_StyledFormMixin, forms.ModelForm):
    asset = forms.ModelChoiceField(
        queryset=InventoryAsset.objects.filter(is_active=True).order_by("asset_code"),
        required=True,
    )

    class Meta:
        model = InventoryAssetMovement
        fields = ["asset", "movement_type", "quantity", "reference", "note"]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_default_styles()

    def clean_reference(self):
        return (self.cleaned_data.get("reference") or "").strip()


class BursarMessageForm(_StyledFormMixin, forms.Form):
    class TargetScope(models.TextChoices):
        ALL_STUDENTS = "ALL_STUDENTS", "All Students"
        CLASS = "CLASS", "By Class"
        SELECTED = "SELECTED", "Selected Students"

    target_scope = forms.ChoiceField(
        choices=TargetScope.choices,
        initial=TargetScope.CLASS,
    )
    academic_class = forms.ModelChoiceField(
        queryset=AcademicClass.objects.filter(is_active=True).order_by("code"),
        required=False,
    )
    students = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(primary_role__code="STUDENT", is_active=True).order_by("username"),
        required=False,
    )
    subject = forms.CharField(max_length=140)
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_default_styles()
        self.fields["students"].widget.attrs["class"] = f"{self.base_input_class} min-h-28"

    def clean_subject(self):
        return (self.cleaned_data.get("subject") or "").strip()

    def clean_message(self):
        return (self.cleaned_data.get("message") or "").strip()

    def clean(self):
        cleaned = super().clean()
        target_scope = cleaned.get("target_scope")
        academic_class = cleaned.get("academic_class")
        students = cleaned.get("students")
        if target_scope == self.TargetScope.CLASS and not academic_class:
            raise forms.ValidationError("Select a class to send class-based message.")
        if target_scope == self.TargetScope.SELECTED and not students:
            raise forms.ValidationError("Select at least one student.")
        return cleaned


class FinanceInstitutionProfileForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = FinanceInstitutionProfile
        fields = [
            "school_bank_name",
            "school_account_name",
            "school_account_number",
            "include_bank_details_in_messages",
            "show_on_receipt_pdf",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_default_styles()
