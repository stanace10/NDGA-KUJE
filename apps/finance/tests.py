import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.accounts.constants import (
    ROLE_BURSAR,
    ROLE_PRINCIPAL,
    ROLE_STUDENT,
    ROLE_SUBJECT_TEACHER,
    ROLE_VP,
)
from apps.accounts.models import Role, StudentProfile, User
from apps.academics.models import AcademicClass, AcademicSession, StudentClassEnrollment, Term
from apps.audit.models import AuditEvent
from apps.finance.models import (
    AssetMovementType,
    ChargeTargetType,
    Expense,
    FinanceDataAuthority,
    FinanceReminderDispatch,
    FinanceReconciliationEvent,
    InventoryAsset,
    InventoryAssetMovement,
    Payment,
    PaymentGatewayTransaction,
    PaymentGatewayProvider,
    PaymentGatewayStatus,
    PaymentMethod,
    Receipt,
    SalaryRecord,
    SalaryStatus,
    StudentCharge,
)
from apps.finance.services import (
    debtor_rows,
    dispatch_scheduled_fee_reminders,
    finance_payment_delta_payload,
    finance_sync_decode_transport,
    finance_summary_metrics,
    initialize_gateway_payment_transaction,
    monthly_cashflow_series,
    record_manual_payment,
    resolve_payment_plan_amount,
    student_finance_overview,
    verify_gateway_payment_transaction,
)
from apps.notifications.models import Notification, NotificationCategory
from apps.setup_wizard.models import SetupStateCode, SystemSetupState


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    NOTIFICATIONS_EMAIL_PROVIDER="console",
)
class FinancePortalTests(TestCase):
    PASSWORD = "Password123!"

    @classmethod
    def setUpTestData(cls):
        student_role = Role.objects.get(code=ROLE_STUDENT)
        bursar_role = Role.objects.get(code=ROLE_BURSAR)
        vp_role = Role.objects.get(code=ROLE_VP)
        principal_role = Role.objects.get(code=ROLE_PRINCIPAL)
        teacher_role = Role.objects.get(code=ROLE_SUBJECT_TEACHER)

        cls.bursar = User.objects.create_user(
            username="bursar-finance",
            password=cls.PASSWORD,
            primary_role=bursar_role,
            must_change_password=False,
        )
        cls.vp = User.objects.create_user(
            username="vp-finance",
            password=cls.PASSWORD,
            primary_role=vp_role,
            must_change_password=False,
        )
        cls.principal = User.objects.create_user(
            username="principal-finance",
            password=cls.PASSWORD,
            primary_role=principal_role,
            must_change_password=False,
        )
        cls.subject_teacher = User.objects.create_user(
            username="subject-finance",
            password=cls.PASSWORD,
            primary_role=teacher_role,
            must_change_password=False,
        )
        cls.student = User.objects.create_user(
            username="student-finance",
            password=cls.PASSWORD,
            primary_role=student_role,
            email="parent-finance@example.com",
            must_change_password=False,
        )

        StudentProfile.objects.create(
            user=cls.student,
            student_number="NDGAK/26/120",
            guardian_email="guardian-finance@example.com",
        )

        cls.session = AcademicSession.objects.create(name="2025/2026")
        cls.term = Term.objects.create(session=cls.session, name="SECOND")
        cls.academic_class = AcademicClass.objects.create(code="JS1A", display_name="JS1A")
        StudentClassEnrollment.objects.create(
            student=cls.student,
            academic_class=cls.academic_class,
            session=cls.session,
            is_active=True,
        )

        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = cls.session
        setup_state.current_term = cls.term
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

    def _client(self, host, user):
        client = Client(HTTP_HOST=host)
        client.force_login(user)
        return client

    def test_record_payment_issues_unique_receipts_and_notification(self):
        payment_one, receipt_one = record_manual_payment(
            student=self.student,
            session=self.session,
            term=self.term,
            amount=Decimal("25000"),
            payment_method=PaymentMethod.CASH,
            payment_date=self.term.created_at.date(),
            received_by=self.bursar,
        )
        payment_two, receipt_two = record_manual_payment(
            student=self.student,
            session=self.session,
            term=self.term,
            amount=Decimal("10000"),
            payment_method=PaymentMethod.TRANSFER,
            payment_date=self.term.created_at.date(),
            received_by=self.bursar,
        )
        self.assertNotEqual(receipt_one.receipt_number, receipt_two.receipt_number)
        self.assertTrue(receipt_one.receipt_number.startswith("NDGA-RCP-"))
        self.assertEqual(payment_one.student_id, self.student.id)
        self.assertEqual(payment_two.student_id, self.student.id)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.student,
                category=NotificationCategory.PAYMENT,
                title="Payment Receipt Issued",
            ).exists()
        )

    def test_bursar_payment_route_creates_receipt_and_logs_finance_audit(self):
        client = self._client("bursar.ndgakuje.org", self.bursar)
        response = client.post(
            "/finance/bursar/payments/",
            {
                "action": "record_payment",
                "student": str(self.student.id),
                "amount": "14000",
                "payment_method": PaymentMethod.POS,
                "payment_date": "2026-03-02",
                "gateway_reference": "",
                "note": "Stage 16 test payment",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Receipt.objects.count(), 1)
        receipt = Receipt.objects.first()
        self.assertIsNotNone(receipt)
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="FINANCE_TRANSACTION",
                actor=self.bursar,
                metadata__action="PAYMENT_RECORDED",
            ).exists()
        )

        with patch("apps.finance.views.generate_receipt_pdf", return_value=b"%PDF-1.4 mock") as mocked_pdf:
            pdf_response = client.get(f"/finance/receipts/{receipt.id}/download/")
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")
        self.assertTrue(mocked_pdf.called)
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="FINANCE_TRANSACTION",
                actor=self.bursar,
                metadata__action="RECEIPT_PDF_DOWNLOAD",
            ).exists()
        )

    def test_receipt_verification_page_shows_valid_state_with_matching_hash(self):
        _, receipt = record_manual_payment(
            student=self.student,
            session=self.session,
            term=self.term,
            amount=Decimal("18000"),
            payment_method=PaymentMethod.CASH,
            payment_date=self.term.created_at.date(),
            received_by=self.bursar,
        )
        client = Client(HTTP_HOST="ndgakuje.org")
        valid_response = client.get(
            f"/finance/receipts/verify/{receipt.id}/?hash={receipt.payload_hash}"
        )
        self.assertEqual(valid_response.status_code, 200)
        self.assertContains(valid_response, "Valid Receipt")
        self.assertContains(valid_response, receipt.receipt_number)

        mismatch_response = client.get(
            f"/finance/receipts/verify/{receipt.id}/?hash=bad-signature"
        )
        self.assertEqual(mismatch_response.status_code, 200)
        self.assertContains(mismatch_response, "Verification Check Required")

    def test_receipt_integrity_alert_is_raised_when_payment_payload_changes(self):
        _, receipt = record_manual_payment(
            student=self.student,
            session=self.session,
            term=self.term,
            amount=Decimal("22000"),
            payment_method=PaymentMethod.CASH,
            payment_date=self.term.created_at.date(),
            received_by=self.bursar,
        )
        # Simulate out-of-band tampering bypassing model safeguards.
        Payment.objects.filter(pk=receipt.payment_id).update(amount=Decimal("99999.00"))

        client = Client(HTTP_HOST="ndgakuje.org")
        response = client.get(f"/finance/receipts/verify/{receipt.id}/?hash={receipt.payload_hash}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Integrity Alert")
        self.assertTrue(
            AuditEvent.objects.filter(
                category="FINANCE",
                event_type="RECEIPT_INTEGRITY_ALERT",
            ).exists()
        )

    def test_payment_core_fields_cannot_be_edited_after_receipt_issuance(self):
        payment, _ = record_manual_payment(
            student=self.student,
            session=self.session,
            term=self.term,
            amount=Decimal("15000"),
            payment_method=PaymentMethod.POS,
            payment_date=self.term.created_at.date(),
            received_by=self.bursar,
        )
        payment.amount = Decimal("1.00")
        with self.assertRaises(ValidationError):
            payment.save()

    def test_vp_and_principal_have_read_only_summary_access(self):
        bursar_client = self._client("bursar.ndgakuje.org", self.bursar)
        bursar_client.post(
            "/finance/bursar/charges/",
            {
                "action": "create_charge",
                "item_name": "School Fees",
                "description": "Term charge",
                "amount": "30000",
                "due_date": "2026-03-10",
                "target_type": ChargeTargetType.CLASS,
                "academic_class": str(self.academic_class.id),
                "student": "",
                "is_active": "on",
            },
        )
        self.assertEqual(StudentCharge.objects.count(), 1)

        vp_client = self._client("vp.ndgakuje.org", self.vp)
        principal_client = self._client("principal.ndgakuje.org", self.principal)
        vp_summary = vp_client.get("/finance/summary/")
        principal_summary = principal_client.get("/finance/summary/")
        self.assertEqual(vp_summary.status_code, 200)
        self.assertEqual(principal_summary.status_code, 200)

        vp_blocked = vp_client.post(
            "/finance/bursar/charges/",
            {
                "action": "create_charge",
                "item_name": "Blocked Charge",
                "description": "",
                "amount": "1",
                "target_type": ChargeTargetType.CLASS,
                "academic_class": str(self.academic_class.id),
            },
        )
        self.assertEqual(vp_blocked.status_code, 302)
        self.assertFalse(StudentCharge.objects.filter(item_name="Blocked Charge").exists())

        principal_blocked = principal_client.get("/finance/bursar/dashboard/")
        self.assertEqual(principal_blocked.status_code, 302)

    def test_bursar_cannot_access_summary_route(self):
        client = self._client("bursar.ndgakuje.org", self.bursar)
        response = client.get("/finance/summary/")
        self.assertEqual(response.status_code, 302)

    def test_bursar_finance_pages_render(self):
        client = self._client("bursar.ndgakuje.org", self.bursar)
        for path in [
            "/finance/bursar/dashboard/",
            "/finance/bursar/charges/",
            "/finance/bursar/payments/",
            "/finance/bursar/debtors/",
            "/finance/bursar/expenses/",
            "/finance/bursar/staff-payments/",
            "/finance/bursar/salaries/",
        ]:
            response = client.get(path)
            self.assertEqual(response.status_code, 200)

    def test_debtor_and_summary_metrics_computation(self):
        StudentCharge.objects.create(
            item_name="Term Charge",
            description="Class-wide",
            amount=Decimal("20000"),
            due_date=self.term.created_at.date(),
            session=self.session,
            term=self.term,
            target_type=ChargeTargetType.CLASS,
            academic_class=self.academic_class,
            created_by=self.bursar,
            is_active=True,
        )
        StudentCharge.objects.create(
            item_name="Laboratory Levy",
            description="Student specific",
            amount=Decimal("5000"),
            due_date=self.term.created_at.date(),
            session=self.session,
            term=self.term,
            target_type=ChargeTargetType.STUDENT,
            student=self.student,
            created_by=self.bursar,
            is_active=True,
        )
        record_manual_payment(
            student=self.student,
            session=self.session,
            term=self.term,
            amount=Decimal("12000"),
            payment_method=PaymentMethod.CASH,
            payment_date=self.term.created_at.date(),
            received_by=self.bursar,
        )

        debtors = debtor_rows(session=self.session, term=self.term)
        self.assertEqual(len(debtors), 1)
        self.assertEqual(debtors[0].student_id, self.student.id)
        self.assertEqual(debtors[0].total_due, Decimal("25000.00"))
        self.assertEqual(debtors[0].total_paid, Decimal("12000.00"))
        self.assertEqual(debtors[0].outstanding, Decimal("13000.00"))

        metrics = finance_summary_metrics(session=self.session, term=self.term)
        self.assertEqual(metrics["total_charges"], Decimal("25000.00"))
        self.assertEqual(metrics["total_payments"], Decimal("12000.00"))
        self.assertEqual(metrics["total_outstanding"], Decimal("13000.00"))
        self.assertEqual(metrics["debtors_count"], 1)

    def test_student_finance_overview_shows_category_balances(self):
        StudentCharge.objects.create(
            item_name="School Fees",
            description="Core tuition",
            amount=Decimal("30000"),
            due_date=self.term.created_at.date(),
            session=self.session,
            term=self.term,
            target_type=ChargeTargetType.CLASS,
            academic_class=self.academic_class,
            created_by=self.bursar,
            is_active=True,
        )
        StudentCharge.objects.create(
            item_name="Sports Wear",
            description="Uniform set",
            amount=Decimal("7000"),
            due_date=self.term.created_at.date(),
            session=self.session,
            term=self.term,
            target_type=ChargeTargetType.STUDENT,
            student=self.student,
            created_by=self.bursar,
            is_active=True,
        )
        record_manual_payment(
            student=self.student,
            session=self.session,
            term=self.term,
            amount=Decimal("12000"),
            payment_method=PaymentMethod.CASH,
            payment_date=self.term.created_at.date(),
            received_by=self.bursar,
        )

        client = self._client("student.ndgakuje.org", self.student)
        response = client.get("/finance/student/overview/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "School Fees")
        self.assertContains(response, "Sports Wear")
        self.assertContains(response, "Outstanding")

    @override_settings(PAYMENT_GATEWAY_PROVIDER="PAYSTACK", PAYSTACK_SECRET_KEY="test-secret")
    def test_student_finance_overview_can_redirect_to_gateway_checkout(self):
        StudentCharge.objects.create(
            item_name="School Fees",
            description="Core tuition",
            amount=Decimal("30000"),
            due_date=self.term.created_at.date(),
            session=self.session,
            term=self.term,
            target_type=ChargeTargetType.CLASS,
            academic_class=self.academic_class,
            created_by=self.bursar,
            is_active=True,
        )
        client = self._client("student.ndgakuje.org", self.student)
        with patch("apps.finance.services._paystack_api_request") as mocked_gateway:
            mocked_gateway.return_value = {
                "status": True,
                "data": {
                    "authorization_url": "https://pay.example/student-checkout",
                    "reference": "NDGA-STUDENT-001",
                    "access_code": "ACCESS-STUDENT-001",
                },
            }
            response = client.post(
                "/finance/student/overview/",
                {
                    "action": "init_gateway_payment",
                    "student": self.student.id,
                    "payment_plan": "FEE_ITEM",
                    "fee_item": "School Fees",
                    "amount": "30000.00",
                    "provider": "PAYSTACK",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "https://pay.example/student-checkout")

    def test_student_finance_portal_alias_renders_inside_student_portal(self):
        client = self._client("student.ndgakuje.org", self.student)
        response = client.get("/portal/student/finance/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Student Finance")

    def test_bursar_finance_portal_alias_renders_dashboard(self):
        client = self._client("bursar.ndgakuje.org", self.bursar)
        response = client.get("/finance/bursar/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "School Finance Overview")

    def test_monthly_cashflow_series_handles_date_buckets(self):
        today = timezone.localdate()
        month_start = today.replace(day=1)

        record_manual_payment(
            student=self.student,
            session=self.session,
            term=self.term,
            amount=Decimal("12000"),
            payment_method=PaymentMethod.CASH,
            payment_date=today,
            received_by=self.bursar,
        )
        Expense.objects.create(
            category="OPERATIONS",
            title="Generator Fuel",
            amount=Decimal("3000"),
            expense_date=today,
            created_by=self.bursar,
            is_active=True,
        )
        SalaryRecord.objects.create(
            staff=self.subject_teacher,
            month=month_start,
            amount=Decimal("2000"),
            status=SalaryStatus.PAID,
            recorded_by=self.bursar,
            is_active=True,
        )

        rows = monthly_cashflow_series(months=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["month"], month_start)
        self.assertEqual(rows[0]["inflow"], Decimal("12000.00"))
        self.assertEqual(rows[0]["outflow"], Decimal("5000.00"))

    @override_settings(PAYMENT_GATEWAY_PROVIDER="PAYSTACK", PAYSTACK_SECRET_KEY="test-secret")
    def test_gateway_initialize_and_verify_records_payment_and_receipt(self):
        with patch("apps.finance.services._paystack_api_request") as mocked_gateway:
            mocked_gateway.side_effect = [
                {
                    "status": True,
                    "data": {
                        "authorization_url": "https://pay.example/abc",
                        "reference": "NDGA-REF-001",
                        "access_code": "ACCESS-001",
                    },
                },
                {
                    "status": True,
                    "data": {
                        "status": "success",
                        "amount": 1500000,
                        "reference": "NDGA-REF-001",
                        "gateway_response": "Approved",
                    },
                },
            ]
            transaction_row = initialize_gateway_payment_transaction(
                student=self.student,
                session=self.session,
                term=self.term,
                amount=Decimal("15000"),
                initiated_by=self.bursar,
            )
            self.assertEqual(transaction_row.status, PaymentGatewayStatus.INITIALIZED)
            self.assertTrue(bool(transaction_row.authorization_url))

            transaction_row, payment, receipt = verify_gateway_payment_transaction(
                gateway_transaction=transaction_row,
                actor=self.bursar,
            )
            self.assertEqual(transaction_row.status, PaymentGatewayStatus.PAID)
            self.assertIsNotNone(payment)
            self.assertIsNotNone(receipt)
            self.assertEqual(payment.payment_method, PaymentMethod.GATEWAY)
            self.assertEqual(payment.gateway_reference, transaction_row.reference)

    @override_settings(PAYMENT_GATEWAY_PROVIDER="PAYSTACK", PAYSTACK_SECRET_KEY="test-secret")
    def test_gateway_initialize_uses_email_like_username_when_email_field_is_empty(self):
        student_role = Role.objects.get(code=ROLE_STUDENT)
        student_with_username_email = User.objects.create_user(
            username="fallback.student@example.com",
            password=self.PASSWORD,
            primary_role=student_role,
            email="",
            must_change_password=False,
        )
        StudentProfile.objects.create(
            user=student_with_username_email,
            student_number="NDGAK/26/199",
        )
        StudentClassEnrollment.objects.create(
            student=student_with_username_email,
            academic_class=self.academic_class,
            session=self.session,
            is_active=True,
        )

        with patch("apps.finance.services._paystack_api_request") as mocked_gateway:
            mocked_gateway.return_value = {
                "status": True,
                "data": {
                    "authorization_url": "https://pay.example/fallback",
                    "reference": "NDGA-REF-FALLBACK",
                    "access_code": "ACCESS-FALLBACK",
                },
            }
            transaction_row = initialize_gateway_payment_transaction(
                student=student_with_username_email,
                session=self.session,
                term=self.term,
                amount=Decimal("9000"),
                initiated_by=self.bursar,
            )
            self.assertEqual(transaction_row.status, PaymentGatewayStatus.INITIALIZED)
            self.assertTrue(bool(transaction_row.authorization_url))

    @override_settings(
        PAYMENT_GATEWAY_PROVIDER="REMITTA",
        REMITTA_MERCHANT_ID="2547916",
        REMITTA_SERVICE_TYPE_ID="4430731",
        REMITTA_API_KEY="remitta-secret",
    )
    def test_remitta_initialize_creates_internal_launch_url(self):
        transaction_row = initialize_gateway_payment_transaction(
            student=self.student,
            session=self.session,
            term=self.term,
            amount=Decimal("15000"),
            initiated_by=self.bursar,
        )
        self.assertEqual(transaction_row.provider, PaymentGatewayProvider.REMITTA)
        self.assertEqual(transaction_row.status, PaymentGatewayStatus.INITIALIZED)
        self.assertIn("/finance/gateway/launch/remitta/", transaction_row.authorization_url)
        self.assertIn("remitta_checkout_payload", transaction_row.metadata)

    @override_settings(
        PAYMENT_GATEWAY_PROVIDER="FLUTTERWAVE",
        FLUTTERWAVE_PUBLIC_KEY="flw-public",
        FLUTTERWAVE_SECRET_KEY="flw-secret",
    )
    def test_flutterwave_initialize_creates_checkout_link(self):
        with patch("apps.finance.services._flutterwave_api_request") as mocked_gateway:
            mocked_gateway.return_value = {
                "status": "success",
                "data": {
                    "link": "https://checkout.flutterwave.com/pay/ndga-123",
                    "flw_ref": "FLW-123",
                },
            }
            transaction_row = initialize_gateway_payment_transaction(
                student=self.student,
                session=self.session,
                term=self.term,
                amount=Decimal("15000"),
                initiated_by=self.bursar,
                provider=PaymentGatewayProvider.FLUTTERWAVE,
            )
            self.assertEqual(transaction_row.provider, PaymentGatewayProvider.FLUTTERWAVE)
            self.assertEqual(transaction_row.status, PaymentGatewayStatus.INITIALIZED)
            self.assertEqual(transaction_row.authorization_url, "https://checkout.flutterwave.com/pay/ndga-123")

    def test_resolve_payment_plan_amount_supports_posted_fee_items(self):
        StudentCharge.objects.create(
            item_name="School Fees",
            description="Main fee",
            amount=Decimal("20000"),
            session=self.session,
            term=self.term,
            target_type=ChargeTargetType.CLASS,
            academic_class=self.academic_class,
            created_by=self.bursar,
            is_active=True,
        )
        StudentCharge.objects.create(
            item_name="Hostel",
            description="Hostel fee",
            amount=Decimal("10000"),
            session=self.session,
            term=self.term,
            target_type=ChargeTargetType.CLASS,
            academic_class=self.academic_class,
            created_by=self.bursar,
            is_active=True,
        )
        overview = student_finance_overview(
            student=self.student,
            session=self.session,
            term=self.term,
        )
        amount_item, meta_item = resolve_payment_plan_amount(
            overview=overview,
            payment_plan="FEE_ITEM",
            fee_item="Hostel",
            custom_amount=Decimal("1"),
        )
        self.assertEqual(amount_item, Decimal("10000.00"))
        self.assertEqual(meta_item["fee_item"], "Hostel")

        with self.assertRaises(ValidationError):
            resolve_payment_plan_amount(
                overview=overview,
                payment_plan="FULL",
                custom_amount=Decimal("1"),
            )

    def test_scheduled_finance_reminders_dispatch_overdue_notice(self):
        due_date = timezone.localdate() - timedelta(days=1)
        StudentCharge.objects.create(
            item_name="School Fees",
            description="Overdue test charge",
            amount=Decimal("5000"),
            due_date=due_date,
            session=self.session,
            term=self.term,
            target_type=ChargeTargetType.STUDENT,
            student=self.student,
            created_by=self.bursar,
            is_active=True,
        )
        result = dispatch_scheduled_fee_reminders(days_ahead=3, actor=self.bursar)
        self.assertEqual(result["sent"], 1)
        self.assertTrue(
            FinanceReminderDispatch.objects.filter(
                student=self.student,
                reminder_type="OVERDUE",
                status="SENT",
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.student,
                category=NotificationCategory.PAYMENT,
                title__icontains="Overdue",
            ).exists()
        )

    def test_inventory_asset_movement_updates_quantities(self):
        asset = InventoryAsset.objects.create(
            asset_code="NDGA-LAB-001",
            name="Chemistry Beaker Set",
            category="LAB",
            quantity_total=10,
            quantity_available=10,
            unit_cost=Decimal("1200"),
            created_by=self.bursar,
            is_active=True,
        )
        InventoryAssetMovement.objects.create(
            asset=asset,
            movement_type=AssetMovementType.ISSUE_OUT,
            quantity=3,
            recorded_by=self.bursar,
            note="Issued to Lab 1",
        )
        asset.refresh_from_db()
        self.assertEqual(asset.quantity_available, 7)
        self.assertEqual(asset.quantity_total, 10)

        InventoryAssetMovement.objects.create(
            asset=asset,
            movement_type=AssetMovementType.RETURN_IN,
            quantity=2,
            recorded_by=self.bursar,
            note="Returned from Lab 1",
        )
        asset.refresh_from_db()
        self.assertEqual(asset.quantity_available, 9)
        self.assertEqual(asset.quantity_total, 10)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    NOTIFICATIONS_EMAIL_PROVIDER="console",
    SYNC_ENDPOINT_AUTH_TOKEN="manual-sync-token",
)
class FinanceDeltaExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        student_role = Role.objects.get(code=ROLE_STUDENT)
        cls.student = User.objects.create_user(
            username="finance-delta-student",
            password="Password123!",
            primary_role=student_role,
            must_change_password=False,
            email="student@ndga.test",
        )
        cls.session = AcademicSession.objects.create(name="2026/2027")
        cls.term = Term.objects.create(session=cls.session, name="FIRST")
        payment = Payment.objects.create(
            student=cls.student,
            session=cls.session,
            term=cls.term,
            amount=Decimal("15000.00"),
            payment_method=PaymentMethod.GATEWAY,
            gateway_reference="GATEWAY-REF-1",
            payment_date=timezone.localdate(),
            source_authority=FinanceDataAuthority.CLOUD,
            source_updated_at=timezone.now(),
        )
        cls.gateway_transaction = PaymentGatewayTransaction.objects.create(
            reference="NDGA-DELTA-1",
            provider=PaymentGatewayProvider.PAYSTACK,
            status=PaymentGatewayStatus.PAID,
            student=cls.student,
            session=cls.session,
            term=cls.term,
            amount=Decimal("15000.00"),
            gateway_reference="GATEWAY-REF-1",
            payment=payment,
            source_authority=FinanceDataAuthority.CLOUD,
            source_updated_at=timezone.now(),
        )

    def test_finance_payment_delta_payload_returns_cloud_authoritative_rows(self):
        payload = finance_payment_delta_payload()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["reference"], "NDGA-DELTA-1")

    def test_manual_payment_delta_export_requires_token_and_returns_json(self):
        client = Client(HTTP_HOST="ndgakuje.org")
        unauthorized = client.get("/finance/api/manual-export/payments/")
        self.assertEqual(unauthorized.status_code, 403)

        response = client.get(
            "/finance/api/manual-export/payments/",
            HTTP_X_NDGA_MANUAL_SYNC_TOKEN="manual-sync-token",
        )
        self.assertEqual(response.status_code, 200)
        payload = finance_sync_decode_transport(response.content)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["gateway_reference"], "GATEWAY-REF-1")

    @override_settings(
        SYNC_ENDPOINT_AUTH_TOKEN="current-token",
        SYNC_ENDPOINT_AUTH_TOKEN_FALLBACKS=["old-token"],
    )
    def test_manual_payment_delta_export_accepts_rotated_fallback_token(self):
        client = Client(HTTP_HOST="ndgakuje.org")
        response = client.get(
            "/finance/api/manual-export/payments/",
            HTTP_X_NDGA_MANUAL_SYNC_TOKEN="old-token",
        )
        self.assertEqual(response.status_code, 200)

    @override_settings(
        SYNC_ENDPOINT_AUTH_TOKEN="manual-sync-token",
        SYNC_ENDPOINT_ALLOWED_IPS=["127.0.0.1/32"],
    )
    def test_manual_payment_delta_export_blocks_disallowed_ip(self):
        client = Client(HTTP_HOST="ndgakuje.org", REMOTE_ADDR="10.10.10.10")
        response = client.get(
            "/finance/api/manual-export/payments/",
            HTTP_X_NDGA_MANUAL_SYNC_TOKEN="manual-sync-token",
        )
        self.assertEqual(response.status_code, 403)

    @override_settings(SYNC_ENDPOINT_AUTH_TOKEN="manual-sync-token")
    def test_manual_payment_delta_export_includes_payload_signature_header(self):
        client = Client(HTTP_HOST="ndgakuje.org")
        response = client.get(
            "/finance/api/manual-export/payments/",
            HTTP_X_NDGA_MANUAL_SYNC_TOKEN="manual-sync-token",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(bool(response["X-NDGA-Payload-Signature"]))

    @override_settings(
        SYNC_ENDPOINT_AUTH_TOKEN="manual-sync-token",
        SYNC_PAYLOAD_ENCRYPTION_ENABLED=True,
        SYNC_PAYLOAD_ENCRYPTION_KEY="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    )
    def test_manual_payment_delta_export_can_encrypt_payload(self):
        client = Client(HTTP_HOST="ndgakuje.org")
        response = client.get(
            "/finance/api/manual-export/payments/",
            HTTP_X_NDGA_MANUAL_SYNC_TOKEN="manual-sync-token",
        )
        self.assertEqual(response.status_code, 200)
        raw_payload = json.loads(response.content.decode("utf-8"))
        self.assertTrue(raw_payload["encrypted"])

        decrypted = finance_sync_decode_transport(response.content)
        self.assertEqual(decrypted["count"], 1)
        self.assertEqual(decrypted["items"][0]["reference"], "NDGA-DELTA-1")


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    NOTIFICATIONS_EMAIL_PROVIDER="console",
    PAYSTACK_WEBHOOK_SECRET="paystack-secret",
    FLUTTERWAVE_WEBHOOK_SECRET_HASH="flutterwave-secret",
)
class FinanceWebhookSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        student_role = Role.objects.get(code=ROLE_STUDENT)
        cls.student = User.objects.create_user(
            username="finance-webhook-student",
            password="Password123!",
            primary_role=student_role,
            must_change_password=False,
            email="student-webhook@ndga.test",
        )
        cls.session = AcademicSession.objects.create(name="2027/2028")
        cls.term = Term.objects.create(session=cls.session, name="SECOND")
        cls.gateway_transaction = PaymentGatewayTransaction.objects.create(
            reference="NDGA-WEBHOOK-1",
            provider=PaymentGatewayProvider.PAYSTACK,
            status=PaymentGatewayStatus.INITIALIZED,
            student=cls.student,
            session=cls.session,
            term=cls.term,
            amount=Decimal("20000.00"),
        )

    def test_paystack_webhook_rejects_invalid_signature(self):
        client = Client(HTTP_HOST="ndgakuje.org")
        response = client.post(
            "/finance/gateway/webhook/paystack/",
            data=json.dumps({"event": "charge.success", "data": {"reference": "NDGA-WEBHOOK-1"}}),
            content_type="application/json",
            HTTP_X_PAYSTACK_SIGNATURE="bad-signature",
        )
        self.assertEqual(response.status_code, 400)

    @patch("apps.finance.views.verify_gateway_payment_by_reference")
    def test_paystack_webhook_accepts_valid_signature(self, mocked_verify):
        payload = {"event": "charge.success", "data": {"reference": "NDGA-WEBHOOK-1"}}
        raw_body = json.dumps(payload).encode("utf-8")
        signature = hmac.new(b"paystack-secret", raw_body, hashlib.sha512).hexdigest()
        client = Client(HTTP_HOST="ndgakuje.org")
        response = client.post(
            "/finance/gateway/webhook/paystack/",
            data=raw_body,
            content_type="application/json",
            HTTP_X_PAYSTACK_SIGNATURE=signature,
        )
        self.assertEqual(response.status_code, 200)
        mocked_verify.assert_called_once()

    def test_flutterwave_webhook_rejects_invalid_secret_hash(self):
        client = Client(HTTP_HOST="ndgakuje.org")
        response = client.post(
            "/finance/gateway/webhook/flutterwave/",
            data=json.dumps({"data": {"status": "successful", "tx_ref": "NDGA-WEBHOOK-1"}}),
            content_type="application/json",
            HTTP_VERIF_HASH="wrong-hash",
        )
        self.assertEqual(response.status_code, 400)

    @patch("apps.finance.views.verify_gateway_payment_by_reference")
    def test_flutterwave_webhook_accepts_valid_secret_hash(self, mocked_verify):
        client = Client(HTTP_HOST="ndgakuje.org")
        response = client.post(
            "/finance/gateway/webhook/flutterwave/",
            data=json.dumps({"data": {"status": "successful", "tx_ref": "NDGA-WEBHOOK-1"}}),
            content_type="application/json",
            HTTP_VERIF_HASH="flutterwave-secret",
        )
        self.assertEqual(response.status_code, 200)
        mocked_verify.assert_called_once_with(reference="NDGA-WEBHOOK-1", actor=None, request=None)
