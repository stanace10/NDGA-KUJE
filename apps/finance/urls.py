from django.urls import path

from apps.finance.views import (
    BursarAssetManagementView,
    BursarChargeManagementView,
    BursarExpenseManagementView,
    BursarFinanceDashboardView,
    BursarMessagingView,
    BursarDebtorsManagementView,
    BursarPaymentManagementView,
    BursarReminderRunView,
    BursarStudentFinanceDetailView,
    BursarSalaryManagementView,
    FinanceSummaryView,
    GatewayPaymentCallbackView,
    PaystackWebhookView,
    ReceiptPDFDownloadView,
    ReceiptVerificationView,
    StudentFinanceOverviewView,
)

app_name = "finance"

urlpatterns = [
    path("student/overview/", StudentFinanceOverviewView.as_view(), name="student-overview"),
    path("bursar/dashboard/", BursarFinanceDashboardView.as_view(), name="bursar-dashboard"),
    path("bursar/settings/", BursarChargeManagementView.as_view(), name="bursar-settings"),
    path("bursar/charges/", BursarChargeManagementView.as_view(), name="bursar-charges"),
    path("bursar/fees/", BursarPaymentManagementView.as_view(), name="bursar-fees"),
    path("bursar/payments/", BursarPaymentManagementView.as_view(), name="bursar-payments"),
    path("bursar/debtors/", BursarDebtorsManagementView.as_view(), name="bursar-debtors"),
    path("bursar/fees/student/<int:student_id>/", BursarStudentFinanceDetailView.as_view(), name="bursar-student-finance"),
    path("bursar/expenses/", BursarExpenseManagementView.as_view(), name="bursar-expenses"),
    path("bursar/staff-payments/", BursarSalaryManagementView.as_view(), name="bursar-staff-payments"),
    path("bursar/salaries/", BursarSalaryManagementView.as_view(), name="bursar-salaries"),
    path("bursar/assets/", BursarAssetManagementView.as_view(), name="bursar-assets"),
    path("bursar/messaging/", BursarMessagingView.as_view(), name="bursar-messaging"),
    path("bursar/reminders/run/", BursarReminderRunView.as_view(), name="bursar-reminders-run"),
    path("summary/", FinanceSummaryView.as_view(), name="summary"),
    path("gateway/callback/", GatewayPaymentCallbackView.as_view(), name="gateway-callback"),
    path("gateway/webhook/paystack/", PaystackWebhookView.as_view(), name="gateway-paystack-webhook"),
    path("receipts/<uuid:receipt_id>/download/", ReceiptPDFDownloadView.as_view(), name="receipt-download"),
    path("receipts/verify/<uuid:receipt_id>/", ReceiptVerificationView.as_view(), name="receipt-verify"),
]
