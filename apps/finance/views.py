from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.constants import ROLE_BURSAR, ROLE_PRINCIPAL, ROLE_STUDENT, ROLE_VP
from apps.accounts.models import User
from apps.accounts.permissions import has_any_role
from apps.academics.models import AcademicClass, AcademicSession, StudentClassEnrollment, Term
from apps.audit.services import log_finance_transaction
from apps.finance.forms import (
    BursarMessageForm,
    ExpenseForm,
    FinanceInstitutionProfileForm,
    GatewayPaymentInitForm,
    InventoryAssetForm,
    InventoryAssetMovementForm,
    PaymentForm,
    SalaryRecordForm,
    StudentChargeForm,
)
from apps.finance.models import (
    ChargeTargetType,
    Expense,
    FinanceReminderDispatch,
    InventoryAsset,
    InventoryAssetMovement,
    Payment,
    PaymentGatewayProvider,
    PaymentGatewayTransaction,
    Receipt,
    SalaryRecord,
    SalaryStatus,
    StudentCharge,
)
from apps.finance.services import (
    build_receipt_dispatch_package,
    configured_gateway_provider_choices,
    current_academic_window,
    default_gateway_provider,
    dispatch_scheduled_fee_reminders,
    finance_summary_metrics,
    finance_bank_details_text,
    finance_payment_delta_payload,
    finance_profile,
    evaluate_receipt_integrity,
    gateway_is_enabled,
    gateway_provider_label,
    generate_receipt_pdf,
    initialize_gateway_payment_transaction,
    monthly_cashflow_series,
    remitta_launch_context,
    record_manual_payment,
    resolve_payment_plan_amount,
    student_finance_overview,
    verify_gateway_payment_by_reference,
)
from apps.notifications.models import Notification, NotificationCategory
from apps.notifications.services import create_bulk_notifications, notify_payment_receipt, send_email_event
from apps.tenancy.utils import build_portal_url, current_portal_key


def _apply_gateway_provider_choices(form):
    form.fields["provider"].choices = configured_gateway_provider_choices()
    form.fields["provider"].initial = default_gateway_provider()
    return form


def _preferred_portal_for_user(user):
    if user.has_role(ROLE_STUDENT):
        return "student"
    if user.has_role(ROLE_BURSAR):
        return "bursar"
    if user.has_role(ROLE_VP):
        return "vp"
    if user.has_role(ROLE_PRINCIPAL):
        return "principal"
    return "landing"


def _portal_media_url(file_field):
    if not file_field:
        return ""
    name = (getattr(file_field, "name", "") or "").lstrip("/")
    if name:
        candidate = Path(settings.MEDIA_ROOT) / Path(name)
        if candidate.exists():
            version = int(candidate.stat().st_mtime)
            return f"/media/{name}?v={version}".replace("\\", "/")
    try:
        return file_field.url
    except Exception:
        return ""


def _manual_sync_token_valid(request):
    expected = (getattr(settings, "SYNC_ENDPOINT_AUTH_TOKEN", "") or "").strip()
    if not expected:
        return False
    provided = (request.headers.get("X-NDGA-Manual-Sync-Token") or request.GET.get("token") or "").strip()
    return bool(provided) and hmac.compare_digest(provided, expected)


class FinancePortalAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    allowed_roles = set()

    def dispatch(self, request, *args, **kwargs):
        preferred_portal = _preferred_portal_for_user(request.user)
        portal_key = current_portal_key(request)
        if preferred_portal in {"bursar", "vp", "principal"} and portal_key != preferred_portal:
            target = build_portal_url(request, preferred_portal, request.path, query=request.GET)
            return redirect(target)
        return super().dispatch(request, *args, **kwargs)

    def test_func(self):
        return has_any_role(self.request.user, self.allowed_roles)


class ManualPaymentDeltaExportView(View):
    def get(self, request, *args, **kwargs):
        if not _manual_sync_token_valid(request):
            return JsonResponse({"detail": "Unauthorized"}, status=403)
        since_raw = (request.GET.get("since") or "").strip()
        since = None
        if since_raw:
            try:
                since = datetime.fromisoformat(since_raw)
                if timezone.is_naive(since):
                    since = timezone.make_aware(since, timezone.get_current_timezone())
            except ValueError:
                return JsonResponse({"detail": "Invalid since timestamp."}, status=400)
        payload = finance_payment_delta_payload(updated_since=since)
        return JsonResponse(payload)


class BursarAccessMixin(FinancePortalAccessMixin):
    allowed_roles = {ROLE_BURSAR}


class FinanceSummaryAccessMixin(FinancePortalAccessMixin):
    allowed_roles = {ROLE_VP, ROLE_PRINCIPAL}


class ReceiptAccessMixin(FinancePortalAccessMixin):
    allowed_roles = {ROLE_BURSAR, ROLE_VP, ROLE_PRINCIPAL, ROLE_STUDENT}


class StudentFinanceAccessMixin(FinancePortalAccessMixin):
    allowed_roles = {ROLE_STUDENT}


class StudentFinanceOverviewView(StudentFinanceAccessMixin, TemplateView):
    template_name = "finance/student_overview.html"

    @staticmethod
    def _term_sort_key(term):
        order = {"FIRST": 1, "SECOND": 2, "THIRD": 3}
        return order.get(term.name, 99)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        current_session, current_term = current_academic_window()
        student_profile = getattr(user, "student_profile", None)

        session_ids = set(
            StudentCharge.objects.filter(student=user).values_list("session_id", flat=True)
        )
        session_ids.update(
            StudentCharge.objects.filter(
                academic_class__student_enrollments__student=user,
                academic_class__student_enrollments__is_active=True,
            ).values_list("session_id", flat=True)
        )
        session_ids.update(
            Payment.objects.filter(student=user).values_list("session_id", flat=True)
        )
        if current_session:
            session_ids.add(current_session.id)

        available_sessions = list(AcademicSession.objects.filter(id__in=session_ids).order_by("-name"))

        selected_session = None
        requested_session_id = (self.request.GET.get("session_id") or "").strip()
        if requested_session_id.isdigit():
            selected_session = next(
                (session for session in available_sessions if session.id == int(requested_session_id)),
                None,
            )
        if selected_session is None and current_session and current_session.id in {row.id for row in available_sessions}:
            selected_session = current_session
        if selected_session is None and available_sessions:
            selected_session = available_sessions[0]

        available_terms = []
        if selected_session:
            available_terms = list(Term.objects.filter(session=selected_session))
            available_terms.sort(key=self._term_sort_key)

        selected_term = None
        requested_term_id = (self.request.GET.get("term_id") or "").strip()
        if requested_term_id.isdigit():
            selected_term = next((term for term in available_terms if term.id == int(requested_term_id)), None)
        if (
            selected_term is None
            and selected_session
            and current_session
            and current_term
            and selected_session.id == current_session.id
        ):
            selected_term = next((term for term in available_terms if term.id == current_term.id), None)
        if selected_term is None and available_terms:
            selected_term = available_terms[0]

        status_filter = (self.request.GET.get("status") or "all").strip().lower()

        overview = {
            "charge_rows": [],
            "category_rows": [],
            "total_charged": Decimal("0.00"),
            "total_paid_applied": Decimal("0.00"),
            "total_outstanding": Decimal("0.00"),
            "total_payments": Decimal("0.00"),
            "unallocated_credit": Decimal("0.00"),
        }
        if selected_session:
            overview = student_finance_overview(
                student=user,
                session=selected_session,
                term=selected_term,
            )
        gateway_transactions = PaymentGatewayTransaction.objects.filter(student=user).order_by("-created_at")[:8]
        payment_rows_qs = Payment.objects.filter(student=user, is_void=False)
        if selected_session:
            payment_rows_qs = payment_rows_qs.filter(session=selected_session)
        if selected_term:
            payment_rows_qs = payment_rows_qs.filter(term__in=[selected_term, None])
        recent_payments = list(
            payment_rows_qs.select_related("receipt", "gateway_transaction", "session", "term")
            .order_by("-created_at")[:8]
        )
        gateway_form = kwargs.get("gateway_form") or GatewayPaymentInitForm(
            initial={
                "student": user.id,
                "amount": overview["total_outstanding"] or Decimal("0.00"),
                "payment_plan": GatewayPaymentInitForm.PaymentPlan.FULL,
                "percentage": 50,
            }
        )
        gateway_form.fields["student"].queryset = User.objects.filter(id=user.id)
        gateway_form.fields["student"].widget = forms.HiddenInput()
        _apply_gateway_provider_choices(gateway_form)

        rows = list(overview["charge_rows"])
        if status_filter in {"paid", "partial", "owing"}:
            rows = [row for row in rows if row.status.lower() == status_filter]

        category_map = {}
        for row in rows:
            category_row = category_map.setdefault(
                row.item_name,
                {
                    "category": row.item_name,
                    "charged": Decimal("0.00"),
                    "paid": Decimal("0.00"),
                    "outstanding": Decimal("0.00"),
                    "items": 0,
                },
            )
            category_row["charged"] += row.amount
            category_row["paid"] += row.paid_applied
            category_row["outstanding"] += row.outstanding
            category_row["items"] += 1

        filtered_categories = sorted(
            category_map.values(),
            key=lambda row: (row["outstanding"], row["category"]),
            reverse=True,
        )
        class_session = selected_session or current_session
        current_enrollment = None
        if class_session:
            current_enrollment = (
                StudentClassEnrollment.objects.filter(
                    student=user,
                    session=class_session,
                    is_active=True,
                )
                .select_related("academic_class", "academic_class__base_class")
                .order_by("-updated_at", "-created_at")
                .first()
            )
        current_class = current_enrollment.academic_class.instructional_class if current_enrollment else None
        student_photo_url = ""
        if student_profile and student_profile.profile_photo:
            student_photo_url = _portal_media_url(student_profile.profile_photo)
        gateway_provider_cards = []
        for code, label in PaymentGatewayProvider.choices:
            gateway_provider_cards.append(
                {
                    "code": code,
                    "label": label,
                    "enabled": gateway_is_enabled(code),
                }
            )
        gateway_any_enabled = any(row["enabled"] for row in gateway_provider_cards)

        context.update(
            {
                "student_profile": student_profile,
                "student_photo_url": student_photo_url,
                "student_name": user.get_full_name() or user.display_name or user.username,
                "student_admission_number": getattr(student_profile, "student_number", "") or user.username,
                "current_class_label": current_class.level_display_name if current_class else "-",
                "current_session": current_session,
                "current_term": current_term,
                "available_sessions": available_sessions,
                "available_terms": available_terms,
                "selected_session": selected_session,
                "selected_term": selected_term,
                "status_filter": status_filter,
                "charge_rows": rows,
                "category_rows": filtered_categories,
                "total_charged": sum((row.amount for row in rows), Decimal("0.00")),
                "total_paid_applied": sum((row.paid_applied for row in rows), Decimal("0.00")),
                "total_outstanding": sum((row.outstanding for row in rows), Decimal("0.00")),
                "total_payments": overview["total_payments"],
                "unallocated_credit": overview["unallocated_credit"],
                "category_examples": "School Fees, Cloth, Feeding, Sports Wear, Pocket Money",
                "gateway_form": gateway_form,
                "gateway_transactions": gateway_transactions,
                "recent_payments": recent_payments,
                "gateway_enabled": gateway_any_enabled,
                "gateway_provider_label": gateway_provider_label(),
                "gateway_provider_cards": gateway_provider_cards,
                "gateway_fee_items": [row for row in filtered_categories if row["outstanding"] > Decimal("0.00")],
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()
        if action != "init_gateway_payment":
            messages.error(request, "Invalid finance action.")
            return redirect("finance:student-overview")

        session, term = current_academic_window()
        if session is None:
            messages.error(request, "Session setup is not ready for online payment.")
            return redirect("finance:student-overview")

        form = _apply_gateway_provider_choices(GatewayPaymentInitForm(request.POST))
        form.fields["student"].queryset = User.objects.filter(id=request.user.id)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(gateway_form=form))
        try:
            overview = student_finance_overview(student=request.user, session=session, term=term)
            resolved_amount, plan_meta = resolve_payment_plan_amount(
                overview=overview,
                payment_plan=form.cleaned_data["payment_plan"],
                fee_item=form.cleaned_data.get("fee_item", ""),
                percentage=form.cleaned_data.get("percentage"),
                custom_amount=form.cleaned_data["amount"],
            )
            transaction_row = initialize_gateway_payment_transaction(
                student=request.user,
                session=session,
                term=term,
                amount=resolved_amount,
                initiated_by=request.user,
                request=request,
                provider=form.cleaned_data["provider"],
                auto_email_link=False,
            )
            transaction_row.metadata = {
                **transaction_row.metadata,
                "payment_plan": plan_meta,
            }
            transaction_row.save(update_fields=["metadata", "updated_at"])
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return self.render_to_response(self.get_context_data(gateway_form=form))

        if transaction_row.authorization_url:
            return redirect(transaction_row.authorization_url)
        messages.success(request, f"Gateway transaction {transaction_row.reference} initialized.")
        return redirect("finance:student-overview")


class BursarFinanceDashboardView(BursarAccessMixin, TemplateView):
    template_name = "finance/bursar_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session, term = current_academic_window()
        if session is None:
            context["metrics"] = None
            context["charges_configured"] = False
            context["cashflow_rows"] = []
            context["recent_receipts"] = []
            context["recent_payments"] = []
            context["total_students"] = 0
            context["paid_students_count"] = 0
            context["owing_students_count"] = 0
            return context
        context["charges_configured"] = StudentCharge.objects.filter(session=session, is_active=True).exists()
        metrics = finance_summary_metrics(session=session, term=term)
        context["metrics"] = metrics
        active_student_ids = set(
            StudentClassEnrollment.objects.filter(session=session, is_active=True).values_list(
                "student_id",
                flat=True,
            )
        )
        total_students = len(active_student_ids)
        owing_student_ids = {int(row.student_id) for row in metrics["debtors"]}
        owing_students_count = len(owing_student_ids)
        paid_students_count = max(total_students - owing_students_count, 0)
        context["total_students"] = total_students
        context["paid_students_count"] = paid_students_count
        context["owing_students_count"] = owing_students_count
        context["student_chart_total"] = max(total_students, 1)
        context["charge_records_count"] = StudentCharge.objects.filter(session=session, is_active=True).count()
        context["payment_records_count"] = Payment.objects.filter(session=session, is_void=False).count()
        context["expense_records_count"] = Expense.objects.filter(is_active=True).count()
        context["salary_records_count"] = SalaryRecord.objects.filter(is_active=True).count()
        asset_rows = InventoryAsset.objects.filter(is_active=True)
        context["asset_records_count"] = asset_rows.count()
        context["asset_total_value"] = sum((row.total_value for row in asset_rows), Decimal("0.00"))
        total_income = metrics["total_payments"]
        total_billed = metrics["total_charges"]
        collection_rate = Decimal("0.00")
        if total_billed > Decimal("0.00"):
            collection_rate = (total_income / total_billed * Decimal("100")).quantize(Decimal("0.01"))
        context["collection_rate"] = collection_rate
        income_outflow_total = max((total_income + metrics["total_outflow"]), Decimal("1.00"))
        context["income_outflow_total"] = income_outflow_total
        cashflow_rows = monthly_cashflow_series(months=6)
        context["cashflow_rows"] = cashflow_rows
        context["cashflow_max"] = max(
            [max(row["inflow"], row["outflow"]) for row in cashflow_rows] or [1]
        )
        context["recent_receipts"] = Receipt.objects.select_related("payment", "payment__student", "payment__gateway_transaction").order_by("-issued_at")[:12]
        context["recent_payments"] = Payment.objects.select_related("student", "receipt", "gateway_transaction").order_by("-created_at")[:12]
        return context


class BursarChargeManagementView(BursarAccessMixin, TemplateView):
    template_name = "finance/charge_management.html"

    def _form(self, data=None):
        return StudentChargeForm(data=data)

    def _profile(self):
        return finance_profile()

    def _profile_form(self, data=None):
        return FinanceInstitutionProfileForm(data=data, instance=self._profile())

    def _filtered_rows(self):
        rows = (
            StudentCharge.objects.select_related("student", "academic_class", "session", "term")
            .filter(target_type=ChargeTargetType.CLASS)
            .order_by("-created_at")
        )
        search = (self.request.GET.get("q") or "").strip()
        class_id = (self.request.GET.get("class_id") or "").strip()
        status = (self.request.GET.get("status") or "").strip()
        if search:
            rows = rows.filter(item_name__icontains=search)
        if class_id.isdigit():
            rows = rows.filter(academic_class_id=int(class_id))
        if status == "active":
            rows = rows.filter(is_active=True)
        elif status == "inactive":
            rows = rows.filter(is_active=False)
        return rows[:200]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filtered_charges = self._filtered_rows()
        context["charge_form"] = kwargs.get("charge_form") or self._form()
        context["profile_form"] = kwargs.get("profile_form") or self._profile_form()
        context["finance_profile"] = self._profile()
        context["charges"] = filtered_charges
        context["search_query"] = self.request.GET.get("q", "")
        context["class_filter"] = self.request.GET.get("class_id", "")
        context["status_filter"] = self.request.GET.get("status", "")
        context["class_options"] = AcademicClass.objects.order_by("code")
        session, term = current_academic_window()
        context["current_session"] = session
        context["current_term"] = term
        context["active_charge_count"] = StudentCharge.objects.filter(is_active=True).count()
        context["inactive_charge_count"] = StudentCharge.objects.filter(is_active=False).count()
        context["expense_record_count"] = Expense.objects.count()
        context["salary_record_count"] = SalaryRecord.objects.count()
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()
        session, term = current_academic_window()
        if session is None:
            messages.error(request, "Setup current session before managing charges.")
            return redirect("finance:bursar-settings")

        if action == "create_charge":
            form = self._form(request.POST)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(charge_form=form))
            charge = form.save(commit=False)
            charge.session = session
            charge.term = term
            charge.target_type = ChargeTargetType.CLASS
            charge.student = None
            charge.due_date = None
            charge.created_by = request.user
            charge.save()
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={
                    "action": "CHARGE_CREATED",
                    "charge_id": str(charge.id),
                    "class_id": str(charge.academic_class_id) if charge.academic_class_id else "",
                    "amount": str(charge.amount),
                },
            )
            messages.success(request, "Charge configured successfully.")
            return redirect("finance:bursar-settings")

        if action == "save_finance_profile":
            profile_form = self._profile_form(request.POST)
            if not profile_form.is_valid():
                return self.render_to_response(self.get_context_data(profile_form=profile_form))
            profile = profile_form.save(commit=False)
            profile.updated_by = request.user
            profile.save()
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={
                    "action": "FINANCE_PROFILE_UPDATED",
                    "show_on_receipt_pdf": profile.show_on_receipt_pdf,
                    "include_bank_details_in_messages": profile.include_bank_details_in_messages,
                },
            )
            messages.success(request, "School account details saved.")
            return redirect("finance:bursar-settings")

        if action == "toggle_charge":
            charge = get_object_or_404(StudentCharge, pk=request.POST.get("charge_id"))
            charge.is_active = not charge.is_active
            charge.save(update_fields=["is_active", "updated_at"])
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={
                    "action": "CHARGE_TOGGLED",
                    "charge_id": str(charge.id),
                    "is_active": charge.is_active,
                },
            )
            messages.success(request, "Charge status updated.")
            return redirect("finance:bursar-settings")

        if action == "delete_charge":
            charge = get_object_or_404(StudentCharge, pk=request.POST.get("charge_id"))
            charge_id = charge.id
            charge.delete()
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={"action": "CHARGE_DELETED", "charge_id": str(charge_id)},
            )
            messages.success(request, "Charge deleted permanently.")
            return redirect("finance:bursar-settings")

        messages.error(request, "Invalid charge action.")
        return redirect("finance:bursar-settings")


class BursarPaymentManagementView(BursarAccessMixin, TemplateView):
    template_name = "finance/payment_management.html"
    receipt_session_key = "finance_latest_receipt"
    page_mode = "fees"
    default_status_filter = "all"
    status_filters = {"all", "paid", "partial", "owing", "debtors", "no_fees"}

    def _pop_latest_receipt(self):
        return self.request.session.pop(self.receipt_session_key, None)

    def _status_filter_value(self):
        status = (self.request.GET.get("status") or self.default_status_filter).strip().lower()
        if status not in self.status_filters:
            return self.default_status_filter
        return status

    @staticmethod
    def _status_for_totals(*, charged, paid, outstanding):
        if charged <= Decimal("0.00"):
            return "No Fees", "no_fees"
        if outstanding <= Decimal("0.00"):
            return "Paid", "paid"
        if paid > Decimal("0.00"):
            return "Partial", "partial"
        return "Owing", "owing"

    @staticmethod
    def _row_matches_status_filter(*, status_code, status_filter):
        if status_filter == "all":
            return True
        if status_filter == "debtors":
            return status_code in {"partial", "owing"}
        return status_code == status_filter

    def _base_enrollments(self, *, session):
        rows = StudentClassEnrollment.objects.filter(is_active=True).select_related(
            "student",
            "student__student_profile",
            "academic_class",
            "session",
        )
        if session:
            rows = rows.filter(session=session)
        return rows

    def _filtered_enrollments(self, *, session):
        rows = self._base_enrollments(session=session)
        class_id = (self.request.GET.get("class_id") or "").strip()
        query = (self.request.GET.get("q") or "").strip()
        if class_id.isdigit():
            rows = rows.filter(academic_class_id=int(class_id))
        if query:
            rows = rows.filter(
                Q(student__username__icontains=query)
                | Q(student__first_name__icontains=query)
                | Q(student__last_name__icontains=query)
                | Q(student__student_profile__student_number__icontains=query)
            )
        return rows.order_by(
            "academic_class__code",
            "student__student_profile__student_number",
            "student__username",
        )[:200]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["latest_receipt"] = self._pop_latest_receipt()
        session, term = current_academic_window()
        context["current_session"] = session
        context["current_term"] = term
        status_filter = self._status_filter_value()
        base_rows = self._base_enrollments(session=session)
        filtered_rows = list(self._filtered_enrollments(session=session))
        matched_rows = []
        for row in filtered_rows:
            overview = (
                student_finance_overview(student=row.student, session=session, term=term)
                if session
                else {
                    "total_charged": Decimal("0.00"),
                    "total_paid_applied": Decimal("0.00"),
                    "total_outstanding": Decimal("0.00"),
                    "category_rows": [],
                }
            )
            charged = overview["total_charged"]
            paid = overview["total_paid_applied"]
            outstanding = overview["total_outstanding"]
            status, status_code = self._status_for_totals(
                charged=charged,
                paid=paid,
                outstanding=outstanding,
            )
            profile = getattr(row.student, "student_profile", None)
            category_highlights = [
                {
                    "category": category_row["category"],
                    "charged": category_row["charged"],
                    "paid": category_row["paid"],
                    "outstanding": category_row["outstanding"],
                }
                for category_row in overview["category_rows"][:3]
            ]
            matched_rows.append(
                {
                    "student": row.student,
                    "profile": profile,
                    "class_code": row.academic_class.code if row.academic_class_id else "-",
                    "total_due": charged,
                    "total_paid": paid,
                    "total_outstanding": outstanding,
                    "status": status,
                    "status_code": status_code,
                    "category_highlights": category_highlights,
                    "category_count": len(overview["category_rows"]),
                    "category_more_count": max(len(overview["category_rows"]) - len(category_highlights), 0),
                }
            )
        student_rows = [
            row
            for row in matched_rows
            if self._row_matches_status_filter(
                status_code=row["status_code"],
                status_filter=status_filter,
            )
        ]
        total_due = sum((row["total_due"] for row in student_rows), Decimal("0.00"))
        total_paid = sum((row["total_paid"] for row in student_rows), Decimal("0.00"))
        total_outstanding = sum((row["total_outstanding"] for row in student_rows), Decimal("0.00"))
        all_student_count = base_rows.values("student_id").distinct().count()
        paid_count = len([row for row in matched_rows if row["status_code"] == "paid"])
        owing_count = len([row for row in matched_rows if row["status_code"] in {"owing", "partial"}])
        debtors_total_outstanding = sum(
            (row["total_outstanding"] for row in matched_rows if row["status_code"] in {"owing", "partial"}),
            Decimal("0.00"),
        )
        context.update(
            {
                "student_rows": student_rows,
                "all_student_count": all_student_count,
                "filtered_count": len(student_rows),
                "matched_count": len(matched_rows),
                "paid_count": paid_count,
                "owing_count": owing_count,
                "fees_total_due": total_due,
                "fees_total_paid": total_paid,
                "fees_total_outstanding": total_outstanding,
                "debtors_total_outstanding": debtors_total_outstanding,
                "class_filter": (self.request.GET.get("class_id") or "").strip(),
                "search_query": (self.request.GET.get("q") or "").strip(),
                "status_filter": status_filter,
                "page_mode": self.page_mode,
                "class_options": (
                    AcademicClass.objects.filter(student_enrollments__in=base_rows)
                    .distinct()
                    .order_by("code")
                ),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()
        session, term = current_academic_window()

        if action == "record_payment":
            if session is None:
                messages.error(request, "Setup current session before recording payments.")
                return redirect("finance:bursar-fees")
            form = PaymentForm(request.POST)
            if not form.is_valid():
                messages.error(request, "Payment form is invalid. Open student page to complete required fields.")
                return redirect("finance:bursar-fees")
            payment, receipt = record_manual_payment(
                student=form.cleaned_data["student"],
                session=session,
                term=term,
                amount=form.cleaned_data["amount"],
                payment_method=form.cleaned_data["payment_method"],
                payment_date=form.cleaned_data["payment_date"],
                received_by=request.user,
                gateway_reference=form.cleaned_data.get("gateway_reference", ""),
                note=form.cleaned_data.get("note", ""),
                request=request,
            )
            request.session[self.receipt_session_key] = {
                "receipt_id": str(receipt.id),
                "receipt_number": receipt.receipt_number,
                "payment_id": payment.id,
            }
            request.session.modified = True
            messages.success(request, "Payment recorded and receipt issued.")
            return redirect("finance:bursar-student-finance", student_id=payment.student_id)

        if action == "send_receipt_email":
            payment = get_object_or_404(
                Payment.objects.select_related("student", "receipt"),
                pk=request.POST.get("payment_id"),
            )
            if not hasattr(payment, "receipt"):
                messages.error(request, "Receipt has not been generated for this payment.")
                return redirect("finance:bursar-fees")
            email_package = build_receipt_dispatch_package(
                payment=payment,
                receipt=payment.receipt,
                request=request,
            )
            notify_payment_receipt(
                student=payment.student,
                receipt_number=payment.receipt.receipt_number,
                amount=payment.amount,
                actor=request.user,
                request=request,
                message=email_package["body_text"],
                email_subject=email_package["subject"],
                email_body_text=email_package["body_text"],
                email_body_html=email_package["body_html"],
                email_attachments=email_package["attachments"],
            )
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={
                    "action": "RECEIPT_EMAIL_RESENT",
                    "payment_id": str(payment.id),
                    "receipt_id": str(payment.receipt.id),
                },
            )
            messages.success(request, "Receipt email sent to parent/student contact.")
            return redirect("finance:bursar-fees")

        if action == "void_payment":
            payment = get_object_or_404(Payment, pk=request.POST.get("payment_id"))
            payment.is_void = True
            payment.save(update_fields=["is_void", "updated_at"])
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={"action": "PAYMENT_VOIDED", "payment_id": str(payment.id)},
            )
            messages.success(request, "Payment marked as void.")
            return redirect("finance:bursar-fees")

        messages.error(request, "Invalid payment action.")
        return redirect("finance:bursar-fees")


class BursarDebtorsManagementView(BursarPaymentManagementView):
    template_name = "finance/debtors_management.html"
    page_mode = "debtors"
    default_status_filter = "debtors"


class BursarStudentFinanceDetailView(BursarAccessMixin, TemplateView):
    template_name = "finance/student_finance_detail.html"
    receipt_session_key = "finance_latest_receipt"

    def dispatch(self, request, *args, **kwargs):
        self.student = get_object_or_404(
            User.objects.select_related("student_profile"),
            id=kwargs.get("student_id"),
            primary_role__code=ROLE_STUDENT,
        )
        return super().dispatch(request, *args, **kwargs)

    def _payment_form(self, data=None):
        form = PaymentForm(data=data, initial={"student": self.student.id})
        form.fields["student"].queryset = User.objects.filter(id=self.student.id)
        form.fields["student"].widget = forms.HiddenInput()
        return form

    def _gateway_form(self, data=None, initial_amount=None):
        initial = {
            "student": self.student.id,
            "payment_plan": GatewayPaymentInitForm.PaymentPlan.FULL,
            "percentage": 50,
        }
        if initial_amount is not None:
            initial["amount"] = initial_amount
        form = GatewayPaymentInitForm(data=data, initial=initial)
        form.fields["student"].queryset = User.objects.filter(id=self.student.id)
        form.fields["student"].widget = forms.HiddenInput()
        return _apply_gateway_provider_choices(form)

    def _pop_latest_receipt(self):
        return self.request.session.pop(self.receipt_session_key, None)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session, term = current_academic_window()
        enrollment = None
        overview = {
            "charge_rows": [],
            "category_rows": [],
            "total_charged": Decimal("0.00"),
            "total_paid_applied": Decimal("0.00"),
            "total_outstanding": Decimal("0.00"),
            "total_payments": Decimal("0.00"),
            "unallocated_credit": Decimal("0.00"),
        }
        payments = Payment.objects.none()
        if session:
            enrollment = (
                StudentClassEnrollment.objects.select_related("academic_class")
                .filter(student=self.student, session=session, is_active=True)
                .first()
            )
            overview = student_finance_overview(student=self.student, session=session, term=term)
            payments = Payment.objects.filter(
                student=self.student,
                session=session,
            ).select_related("receipt", "gateway_transaction").order_by("-created_at")
        context.update(
            {
                "student_user": self.student,
                "student_profile": getattr(self.student, "student_profile", None),
                "current_session": session,
                "current_term": term,
                "class_code": enrollment.academic_class.code if enrollment else "-",
                "overview": overview,
                "charge_rows": overview["charge_rows"],
                "category_rows": overview["category_rows"],
                "student_payments": payments[:120],
                "payment_form": kwargs.get("payment_form") or self._payment_form(),
                "gateway_form": kwargs.get("gateway_form") or self._gateway_form(initial_amount=overview["total_outstanding"]),
                "gateway_transactions": PaymentGatewayTransaction.objects.filter(student=self.student).order_by("-created_at")[:10],
                "reminder_dispatches": FinanceReminderDispatch.objects.filter(student=self.student).order_by("-created_at")[:10],
                "latest_receipt": self._pop_latest_receipt(),
                "gateway_enabled": gateway_is_enabled(),
                "gateway_provider_label": gateway_provider_label(),
                "gateway_fee_items": [row for row in overview["category_rows"] if row["outstanding"] > Decimal("0.00")],
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()
        session, term = current_academic_window()
        if session is None:
            messages.error(request, "Setup current session before recording payments.")
            return redirect("finance:bursar-student-finance", student_id=self.student.id)

        if action == "record_payment":
            form = self._payment_form(request.POST)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(payment_form=form))
            payment, receipt = record_manual_payment(
                student=self.student,
                session=session,
                term=term,
                amount=form.cleaned_data["amount"],
                payment_method=form.cleaned_data["payment_method"],
                payment_date=form.cleaned_data["payment_date"],
                received_by=request.user,
                gateway_reference=form.cleaned_data.get("gateway_reference", ""),
                note=form.cleaned_data.get("note", ""),
                request=request,
            )
            request.session[self.receipt_session_key] = {
                "receipt_id": str(receipt.id),
                "receipt_number": receipt.receipt_number,
                "payment_id": payment.id,
            }
            request.session.modified = True
            messages.success(request, "Payment recorded and receipt issued.")
            return redirect("finance:bursar-student-finance", student_id=self.student.id)

        if action == "send_receipt_email":
            payment = get_object_or_404(
                Payment.objects.select_related("student", "receipt"),
                pk=request.POST.get("payment_id"),
                student=self.student,
            )
            if not hasattr(payment, "receipt"):
                messages.error(request, "Receipt has not been generated for this payment.")
                return redirect("finance:bursar-student-finance", student_id=self.student.id)
            email_package = build_receipt_dispatch_package(
                payment=payment,
                receipt=payment.receipt,
                request=request,
            )
            notify_payment_receipt(
                student=payment.student,
                receipt_number=payment.receipt.receipt_number,
                amount=payment.amount,
                actor=request.user,
                request=request,
                message=email_package["body_text"],
                email_subject=email_package["subject"],
                email_body_text=email_package["body_text"],
                email_body_html=email_package["body_html"],
                email_attachments=email_package["attachments"],
            )
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={
                    "action": "RECEIPT_EMAIL_RESENT",
                    "payment_id": str(payment.id),
                    "receipt_id": str(payment.receipt.id),
                },
            )
            messages.success(request, "Receipt email sent to parent/student contact.")
            return redirect("finance:bursar-student-finance", student_id=self.student.id)

        if action == "init_gateway_link":
            gateway_form = self._gateway_form(request.POST)
            if not gateway_form.is_valid():
                return self.render_to_response(self.get_context_data(gateway_form=gateway_form))
            try:
                overview = student_finance_overview(student=self.student, session=session, term=term)
                resolved_amount, plan_meta = resolve_payment_plan_amount(
                    overview=overview,
                    payment_plan=gateway_form.cleaned_data["payment_plan"],
                    fee_item=gateway_form.cleaned_data.get("fee_item", ""),
                    percentage=gateway_form.cleaned_data.get("percentage"),
                    custom_amount=gateway_form.cleaned_data["amount"],
                )
                transaction_row = initialize_gateway_payment_transaction(
                    student=self.student,
                    session=session,
                    term=term,
                    amount=resolved_amount,
                    initiated_by=request.user,
                    request=request,
                    provider=gateway_form.cleaned_data["provider"],
                    auto_email_link=gateway_form.cleaned_data.get("auto_email_link", True),
                )
                transaction_row.metadata = {
                    **transaction_row.metadata,
                    "payment_plan": plan_meta,
                }
                transaction_row.save(update_fields=["metadata", "updated_at"])
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return self.render_to_response(self.get_context_data(gateway_form=gateway_form))
            if transaction_row.authorization_url:
                messages.success(
                    request,
                    f"Gateway link created for {transaction_row.reference}. "
                    "It has been sent to parent/student email if available.",
                )
            else:
                messages.success(request, f"Gateway transaction {transaction_row.reference} initialized.")
            return redirect("finance:bursar-student-finance", student_id=self.student.id)

        if action == "verify_gateway_reference":
            reference = (request.POST.get("gateway_reference") or "").strip()
            if not reference:
                messages.error(request, "Gateway reference is required.")
                return redirect("finance:bursar-student-finance", student_id=self.student.id)
            try:
                gateway_txn, payment, receipt = verify_gateway_payment_by_reference(
                    reference=reference,
                    actor=request.user,
                    request=request,
                )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return redirect("finance:bursar-student-finance", student_id=self.student.id)
            if receipt:
                request.session[self.receipt_session_key] = {
                    "receipt_id": str(receipt.id),
                    "receipt_number": receipt.receipt_number,
                    "payment_id": payment.id,
                }
                request.session.modified = True
            messages.success(
                request,
                f"Gateway reference {gateway_txn.reference} verified successfully.",
            )
            return redirect("finance:bursar-student-finance", student_id=self.student.id)

        if action == "void_payment":
            payment = get_object_or_404(Payment, pk=request.POST.get("payment_id"), student=self.student)
            payment.is_void = True
            payment.save(update_fields=["is_void", "updated_at"])
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={"action": "PAYMENT_VOIDED", "payment_id": str(payment.id)},
            )
            messages.success(request, "Payment marked as void.")
            return redirect("finance:bursar-student-finance", student_id=self.student.id)

        messages.error(request, "Invalid student finance action.")
        return redirect("finance:bursar-student-finance", student_id=self.student.id)


class BursarExpenseManagementView(BursarAccessMixin, TemplateView):
    template_name = "finance/expense_management.html"

    def _expense_form(self, data=None, files=None):
        return ExpenseForm(data=data, files=files)

    def _salary_form(self, data=None):
        return SalaryRecordForm(data=data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["expense_form"] = kwargs.get("expense_form") or self._expense_form()
        context["expenses"] = Expense.objects.order_by("-expense_date", "-created_at")[:200]
        context["salary_form"] = kwargs.get("salary_form") or self._salary_form()
        context["salary_records"] = SalaryRecord.objects.select_related("staff").order_by("-month", "-created_at")[:200]
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()

        if action == "create_expense":
            form = self._expense_form(request.POST, request.FILES)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(expense_form=form))
            expense = form.save(commit=False)
            expense.created_by = request.user
            expense.save()
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={
                    "action": "EXPENSE_CREATED",
                    "expense_id": str(expense.id),
                    "category": expense.category,
                    "amount": str(expense.amount),
                },
            )
            messages.success(request, "Expense recorded.")
            return redirect("finance:bursar-expenses")

        if action == "create_salary":
            form = self._salary_form(request.POST)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(salary_form=form))
            salary = form.save(commit=False)
            salary.recorded_by = request.user
            salary.save()
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={
                    "action": "SALARY_CREATED",
                    "salary_id": str(salary.id),
                    "staff_id": str(salary.staff_id),
                    "amount": str(salary.amount),
                    "status": salary.status,
                },
            )
            messages.success(request, "Salary record saved.")
            return redirect("finance:bursar-expenses")

        if action == "mark_paid":
            salary = get_object_or_404(SalaryRecord, pk=request.POST.get("salary_id"))
            salary.status = SalaryStatus.PAID
            salary.save(update_fields=["status", "paid_at", "updated_at"])
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={"action": "SALARY_MARKED_PAID", "salary_id": str(salary.id)},
            )
            messages.success(request, "Salary marked as paid.")
            return redirect("finance:bursar-expenses")

        if action == "mark_pending":
            salary = get_object_or_404(SalaryRecord, pk=request.POST.get("salary_id"))
            salary.status = SalaryStatus.PENDING
            salary.save(update_fields=["status", "paid_at", "updated_at"])
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={"action": "SALARY_MARKED_PENDING", "salary_id": str(salary.id)},
            )
            messages.success(request, "Salary moved to pending.")
            return redirect("finance:bursar-expenses")

        if action == "toggle_salary":
            salary = get_object_or_404(SalaryRecord, pk=request.POST.get("salary_id"))
            salary.is_active = not salary.is_active
            salary.save(update_fields=["is_active", "updated_at"])
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={
                    "action": "SALARY_TOGGLED",
                    "salary_id": str(salary.id),
                    "is_active": salary.is_active,
                },
            )
            messages.success(request, "Salary status updated.")
            return redirect("finance:bursar-expenses")

        if action == "delete_salary":
            salary = get_object_or_404(SalaryRecord, pk=request.POST.get("salary_id"))
            salary_id = salary.id
            salary.delete()
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={"action": "SALARY_DELETED", "salary_id": str(salary_id)},
            )
            messages.success(request, "Salary record deleted.")
            return redirect("finance:bursar-expenses")

        if action == "toggle_expense":
            expense = get_object_or_404(Expense, pk=request.POST.get("expense_id"))
            expense.is_active = not expense.is_active
            expense.save(update_fields=["is_active", "updated_at"])
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={
                    "action": "EXPENSE_TOGGLED",
                    "expense_id": str(expense.id),
                    "is_active": expense.is_active,
                },
            )
            messages.success(request, "Expense status updated.")
            return redirect("finance:bursar-expenses")

        if action == "delete_expense":
            expense = get_object_or_404(Expense, pk=request.POST.get("expense_id"))
            expense_id = expense.id
            expense.delete()
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={"action": "EXPENSE_DELETED", "expense_id": str(expense_id)},
            )
            messages.success(request, "Expense deleted permanently.")
            return redirect("finance:bursar-expenses")

        messages.error(request, "Invalid expense action.")
        return redirect("finance:bursar-expenses")


class BursarSalaryManagementView(BursarAccessMixin, TemplateView):
    template_name = "finance/staff_payment_management.html"

    def _salary_form(self, data=None):
        return SalaryRecordForm(data=data)

    def _salary_rows(self):
        rows = SalaryRecord.objects.select_related("staff", "staff__staff_profile").order_by("-month", "-created_at")
        query = (self.request.GET.get("q") or "").strip()
        status = (self.request.GET.get("status") or "").strip().upper()
        month_value = (self.request.GET.get("month") or "").strip()
        if query:
            rows = rows.filter(
                Q(staff__username__icontains=query)
                | Q(staff__first_name__icontains=query)
                | Q(staff__last_name__icontains=query)
                | Q(staff__staff_profile__staff_id__icontains=query)
            )
        if status in {SalaryStatus.PENDING, SalaryStatus.PAID, SalaryStatus.HOLD}:
            rows = rows.filter(status=status)
        if month_value:
            try:
                year_text, month_text = month_value.split("-", 1)
                month_bucket = date(int(year_text), int(month_text), 1)
                rows = rows.filter(month=month_bucket)
            except (ValueError, TypeError):
                month_value = ""
        return rows[:300], query, status, month_value

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        salary_rows_qs, search_query, status_filter, month_filter = self._salary_rows()
        salary_rows = list(salary_rows_qs)
        total_amount = sum((row.amount for row in salary_rows), Decimal("0.00"))
        paid_amount = sum((row.amount for row in salary_rows if row.status == SalaryStatus.PAID), Decimal("0.00"))
        pending_amount = sum((row.amount for row in salary_rows if row.status == SalaryStatus.PENDING), Decimal("0.00"))
        hold_amount = sum((row.amount for row in salary_rows if row.status == SalaryStatus.HOLD), Decimal("0.00"))
        context["salary_form"] = kwargs.get("salary_form") or self._salary_form()
        context["salary_rows"] = salary_rows
        context["salary_row_count"] = len(salary_rows)
        context["salary_total_amount"] = total_amount
        context["salary_paid_amount"] = paid_amount
        context["salary_pending_amount"] = pending_amount
        context["salary_hold_amount"] = hold_amount
        context["search_query"] = search_query
        context["status_filter"] = status_filter.lower() if status_filter else ""
        context["month_filter"] = month_filter
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()

        if action == "create_salary":
            form = self._salary_form(request.POST)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(salary_form=form))
            salary = form.save(commit=False)
            salary.recorded_by = request.user
            salary.save()
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={
                    "action": "SALARY_CREATED",
                    "salary_id": str(salary.id),
                    "staff_id": str(salary.staff_id),
                    "amount": str(salary.amount),
                    "status": salary.status,
                },
            )
            messages.success(request, "Staff payment record saved.")
            return redirect("finance:bursar-staff-payments")

        if action == "mark_paid":
            salary = get_object_or_404(SalaryRecord, pk=request.POST.get("salary_id"))
            salary.status = SalaryStatus.PAID
            salary.save(update_fields=["status", "paid_at", "updated_at"])
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={"action": "SALARY_MARKED_PAID", "salary_id": str(salary.id)},
            )
            messages.success(request, "Staff payment marked as paid.")
            return redirect("finance:bursar-staff-payments")

        if action == "mark_pending":
            salary = get_object_or_404(SalaryRecord, pk=request.POST.get("salary_id"))
            salary.status = SalaryStatus.PENDING
            salary.save(update_fields=["status", "paid_at", "updated_at"])
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={"action": "SALARY_MARKED_PENDING", "salary_id": str(salary.id)},
            )
            messages.success(request, "Staff payment moved to pending.")
            return redirect("finance:bursar-staff-payments")

        if action == "toggle_salary":
            salary = get_object_or_404(SalaryRecord, pk=request.POST.get("salary_id"))
            salary.is_active = not salary.is_active
            salary.save(update_fields=["is_active", "updated_at"])
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={
                    "action": "SALARY_TOGGLED",
                    "salary_id": str(salary.id),
                    "is_active": salary.is_active,
                },
            )
            messages.success(request, "Staff payment status updated.")
            return redirect("finance:bursar-staff-payments")

        if action == "delete_salary":
            salary = get_object_or_404(SalaryRecord, pk=request.POST.get("salary_id"))
            salary_id = salary.id
            salary.delete()
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={"action": "SALARY_DELETED", "salary_id": str(salary_id)},
            )
            messages.success(request, "Staff payment record deleted.")
            return redirect("finance:bursar-staff-payments")

        messages.error(request, "Invalid staff payment action.")
        return redirect("finance:bursar-staff-payments")


class BursarAssetManagementView(BursarAccessMixin, TemplateView):
    template_name = "finance/asset_management.html"

    def _asset_form(self, data=None):
        return InventoryAssetForm(data=data)

    def _movement_form(self, data=None):
        return InventoryAssetMovementForm(data=data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["asset_form"] = kwargs.get("asset_form") or self._asset_form()
        context["movement_form"] = kwargs.get("movement_form") or self._movement_form()
        context["assets"] = InventoryAsset.objects.order_by("asset_code")[:250]
        context["recent_movements"] = InventoryAssetMovement.objects.select_related("asset", "recorded_by").order_by("-created_at")[:120]
        context["asset_total_value"] = sum((row.total_value for row in context["assets"]), Decimal("0.00"))
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()
        if action == "create_asset":
            form = self._asset_form(request.POST)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(asset_form=form))
            asset = form.save(commit=False)
            asset.created_by = request.user
            asset.save()
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={
                    "action": "ASSET_CREATED",
                    "asset_id": str(asset.id),
                    "asset_code": asset.asset_code,
                    "quantity_total": asset.quantity_total,
                },
            )
            messages.success(request, "Asset created.")
            return redirect("finance:bursar-assets")

        if action == "record_movement":
            form = self._movement_form(request.POST)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(movement_form=form))
            movement = form.save(commit=False)
            movement.recorded_by = request.user
            try:
                movement.save()
            except ValidationError as exc:
                form.add_error(None, "; ".join(exc.messages))
                return self.render_to_response(self.get_context_data(movement_form=form))
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={
                    "action": "ASSET_MOVEMENT_RECORDED",
                    "movement_id": str(movement.id),
                    "asset_id": str(movement.asset_id),
                    "movement_type": movement.movement_type,
                    "quantity": movement.quantity,
                },
            )
            messages.success(request, "Asset movement recorded.")
            return redirect("finance:bursar-assets")

        if action == "toggle_asset":
            asset = get_object_or_404(InventoryAsset, pk=request.POST.get("asset_id"))
            asset.is_active = not asset.is_active
            asset.save(update_fields=["is_active", "updated_at"])
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={
                    "action": "ASSET_TOGGLED",
                    "asset_id": str(asset.id),
                    "is_active": asset.is_active,
                },
            )
            messages.success(request, "Asset status updated.")
            return redirect("finance:bursar-assets")

        if action == "delete_asset":
            asset = get_object_or_404(InventoryAsset, pk=request.POST.get("asset_id"))
            asset_id = asset.id
            asset.delete()
            log_finance_transaction(
                actor=request.user,
                request=request,
                metadata={"action": "ASSET_DELETED", "asset_id": str(asset_id)},
            )
            messages.success(request, "Asset deleted.")
            return redirect("finance:bursar-assets")

        messages.error(request, "Invalid asset action.")
        return redirect("finance:bursar-assets")


class BursarMessagingView(BursarAccessMixin, TemplateView):
    template_name = "finance/messaging_center.html"

    def _form(self, data=None):
        return BursarMessageForm(data=data)

    def _resolve_recipients(self, cleaned_data):
        target_scope = cleaned_data["target_scope"]
        if target_scope == BursarMessageForm.TargetScope.ALL_STUDENTS:
            return list(
                User.objects.filter(primary_role__code="STUDENT", is_active=True).order_by("username")
            )
        if target_scope == BursarMessageForm.TargetScope.CLASS:
            class_id = cleaned_data["academic_class"].id
            student_ids = StudentClassEnrollment.objects.filter(
                academic_class_id=class_id,
                is_active=True,
            ).values_list("student_id", flat=True)
            return list(
                User.objects.filter(id__in=student_ids, primary_role__code="STUDENT", is_active=True)
                .order_by("username")
                .distinct()
            )
        return list(cleaned_data["students"])

    @staticmethod
    def _recipient_emails(recipients):
        emails = []
        for student in recipients:
            profile = getattr(student, "student_profile", None)
            if profile and profile.guardian_email:
                emails.append(profile.guardian_email)
            if student.email:
                emails.append(student.email)
        return emails

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["message_form"] = kwargs.get("message_form") or self._form()
        context["message_rows"] = Notification.objects.filter(
            created_by=self.request.user,
            category=NotificationCategory.SYSTEM,
        ).order_by("-created_at")[:40]
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()
        if action != "send_message":
            messages.error(request, "Invalid messaging action.")
            return redirect("finance:bursar-messaging")

        form = self._form(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(message_form=form))

        recipients = self._resolve_recipients(form.cleaned_data)
        if not recipients:
            messages.error(request, "No recipients found for selected target.")
            return self.render_to_response(self.get_context_data(message_form=form))

        subject = form.cleaned_data["subject"]
        message_text = form.cleaned_data["message"]
        delivery_message = message_text
        profile = finance_profile()
        if profile.include_bank_details_in_messages:
            bank_block = finance_bank_details_text()
            if bank_block:
                delivery_message = f"{message_text}\n\nSchool Account Details\n{bank_block}"
        create_bulk_notifications(
            recipients=recipients,
            category=NotificationCategory.SYSTEM,
            title=subject,
            message=delivery_message,
            created_by=request.user,
            action_url="/finance/student/overview/",
            metadata={
                "event": "BURSAR_MESSAGE",
                "target_scope": form.cleaned_data["target_scope"],
            },
        )

        send_email_event(
            to_emails=self._recipient_emails(recipients),
            subject=f"NDGA Finance Notice: {subject}",
            body_text=delivery_message,
            actor=request.user,
            request=request,
            metadata={
                "event": "BURSAR_MESSAGE",
                "target_scope": form.cleaned_data["target_scope"],
                "recipient_count": len(recipients),
            },
        )

        log_finance_transaction(
            actor=request.user,
            request=request,
            metadata={
                "action": "BURSAR_MESSAGE_SENT",
                "recipient_count": len(recipients),
                "target_scope": form.cleaned_data["target_scope"],
            },
        )
        messages.success(request, f"Message sent to {len(recipients)} student/parent contacts.")
        return redirect("finance:bursar-messaging")


class FinanceSummaryView(FinanceSummaryAccessMixin, TemplateView):
    template_name = "finance/summary_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.has_role(ROLE_PRINCIPAL):
            context["finance_summary_title"] = "Principal Finance Summary"
        elif self.request.user.has_role(ROLE_VP):
            context["finance_summary_title"] = "Vice Principal Finance Summary"
        else:
            context["finance_summary_title"] = "Finance Summary"
        session, term = current_academic_window()
        context["current_session"] = session
        context["current_term"] = term
        if session is None:
            context["metrics"] = None
            context["cashflow_rows"] = []
            return context
        metrics = finance_summary_metrics(session=session, term=term)
        context["metrics"] = metrics
        cashflow_rows = monthly_cashflow_series(months=6)
        context["cashflow_rows"] = cashflow_rows
        context["cashflow_max"] = max(
            [max(row["inflow"], row["outflow"]) for row in cashflow_rows] or [1]
        )
        context["latest_receipts"] = Receipt.objects.select_related("payment", "payment__student", "payment__gateway_transaction").order_by("-issued_at")[:20]
        context["latest_expenses"] = Expense.objects.order_by("-expense_date")[:20]
        context["latest_salaries"] = SalaryRecord.objects.select_related("staff").order_by("-month")[:20]
        context["latest_assets"] = InventoryAsset.objects.order_by("-updated_at")[:20]
        return context


class BursarReminderRunView(BursarAccessMixin, View):
    def post(self, request, *args, **kwargs):
        result = dispatch_scheduled_fee_reminders(actor=request.user, request=request)
        messages.success(
            request,
            f"Reminder run complete: sent {result['sent']}, skipped {result['skipped']}, failed {result['failed']}.",
        )
        return redirect("finance:bursar-settings")


class RemittaGatewayLaunchView(TemplateView):
    template_name = "finance/remitta_launch.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        gateway_transaction = get_object_or_404(
            PaymentGatewayTransaction.objects.select_related("student", "session", "term"),
            reference=kwargs["reference"],
        )
        launch_context = remitta_launch_context(gateway_transaction=gateway_transaction)
        context.update(
            {
                "gateway_transaction": gateway_transaction,
                "action_url": launch_context["action_url"],
                "launch_fields": launch_context["fields"],
            }
        )
        return context


class GatewayPaymentCallbackView(TemplateView):
    template_name = "finance/gateway_callback.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        reference = (
            self.request.GET.get("reference")
            or self.request.GET.get("trxref")
            or self.request.GET.get("tx_ref")
            or self.request.GET.get("orderID")
            or self.request.GET.get("orderId")
            or ""
        ).strip()
        callback_params = {
            key: value
            for key, value in self.request.GET.items()
            if value not in {None, ""}
        }
        raw_rrr = (
            self.request.GET.get("RRR")
            or self.request.GET.get("rrr")
            or self.request.GET.get("payment_reference")
            or ""
        ).strip()
        if raw_rrr:
            callback_params["rrr"] = raw_rrr
        context["reference"] = reference
        context["verified"] = False
        context["error_message"] = ""
        context["receipt_id"] = ""
        if not reference:
            context["error_message"] = "Gateway reference was not provided."
            return context
        gateway_txn = PaymentGatewayTransaction.objects.filter(reference=reference).first()
        if gateway_txn is not None:
            metadata = dict(gateway_txn.metadata or {})
            metadata["callback_params"] = callback_params
            if raw_rrr:
                gateway_txn.gateway_reference = raw_rrr[:180]
            gateway_txn.metadata = metadata
            gateway_txn.save(update_fields=["gateway_reference", "metadata", "updated_at"])
        try:
            gateway_txn, payment, receipt = verify_gateway_payment_by_reference(
                reference=reference,
                actor=self.request.user if getattr(self.request, "user", None) and self.request.user.is_authenticated else None,
                request=self.request,
            )
        except ValidationError as exc:
            context["error_message"] = "; ".join(exc.messages)
            return context
        context["verified"] = True
        context["gateway_transaction"] = gateway_txn
        context["payment"] = payment
        context["receipt"] = receipt
        context["receipt_id"] = str(receipt.id) if receipt else ""
        return context


@method_decorator(csrf_exempt, name="dispatch")
class PaystackWebhookView(View):
    def post(self, request, *args, **kwargs):
        secret = (getattr(settings, "PAYSTACK_WEBHOOK_SECRET", "") or getattr(settings, "PAYSTACK_SECRET_KEY", "")).strip()
        if secret:
            expected = hmac.new(secret.encode("utf-8"), request.body, hashlib.sha512).hexdigest()
            incoming = (request.META.get("HTTP_X_PAYSTACK_SIGNATURE") or "").strip()
            if not incoming or not hmac.compare_digest(expected, incoming):
                return HttpResponse("invalid-signature", status=400)
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return HttpResponse("invalid-json", status=400)

        event_type = payload.get("event")
        data = payload.get("data") or {}
        reference = (data.get("reference") or "").strip()
        if event_type == "charge.success" and reference:
            try:
                verify_gateway_payment_by_reference(reference=reference, actor=None, request=None)
            except ValidationError:
                pass
        return HttpResponse("ok", status=200)


class ReceiptPDFDownloadView(ReceiptAccessMixin, View):
    def get(self, request, *args, **kwargs):
        receipt = get_object_or_404(
            Receipt.objects.select_related("payment", "payment__student", "payment__session", "payment__term"),
            pk=kwargs["receipt_id"],
        )
        if request.user.has_role(ROLE_STUDENT) and receipt.payment.student_id != request.user.id:
            messages.error(request, "You can only download receipts issued for your own account.")
            return redirect("finance:student-overview")
        try:
            pdf_bytes = generate_receipt_pdf(
                request=request,
                receipt=receipt,
                generated_by=request.user,
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            if request.user.has_role(ROLE_BURSAR):
                return redirect("finance:bursar-fees")
            if request.user.has_role(ROLE_STUDENT):
                return redirect("finance:student-overview")
            return redirect("finance:summary")
        except RuntimeError:
            messages.error(
                request,
                "PDF runtime dependencies are missing. Install WeasyPrint runtime libraries.",
            )
            if request.user.has_role(ROLE_BURSAR):
                return redirect("finance:bursar-fees")
            if request.user.has_role(ROLE_STUDENT):
                return redirect("finance:student-overview")
            return redirect("finance:summary")
        filename = f"NDGA-Receipt-{receipt.receipt_number}.pdf"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        log_finance_transaction(
            actor=request.user,
            request=request,
            metadata={
                "action": "RECEIPT_PDF_DOWNLOAD",
                "receipt_id": str(receipt.id),
                "payment_id": str(receipt.payment_id),
            },
        )
        return response


class ReceiptVerificationView(TemplateView):
    template_name = "finance/receipt_verify.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        receipt = get_object_or_404(
            Receipt.objects.select_related("payment", "payment__student", "payment__session", "payment__term"),
            pk=kwargs["receipt_id"],
        )
        integrity = evaluate_receipt_integrity(
            receipt=receipt,
            actor=self.request.user if getattr(self.request, "user", None) and self.request.user.is_authenticated else None,
            request=self.request,
            source="RECEIPT_VERIFY_PAGE",
        )
        incoming_hash = (self.request.GET.get("hash") or "").strip().lower()
        stored_hash = receipt.payload_hash.lower()
        hash_matches = bool(incoming_hash) and incoming_hash == stored_hash
        if integrity["tampered"]:
            verification_state = "TAMPER_ALERT"
        elif hash_matches:
            verification_state = "VALID"
        else:
            verification_state = "CHECK_REQUIRED"
        context["receipt"] = receipt
        context["incoming_hash"] = incoming_hash
        context["hash_matches"] = hash_matches
        context["verification_state"] = verification_state
        context["integrity"] = integrity
        return context
