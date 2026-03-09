from django.urls import path

from apps.setup_wizard.views import BackupCenterView, SessionTermManagementView, SetupWizardView

app_name = "setup_wizard"

urlpatterns = [
    path("wizard/", SetupWizardView.as_view(), name="wizard"),
    path("wizard/<str:step>/", SetupWizardView.as_view(), name="wizard-step"),
    path("session-term/", SessionTermManagementView.as_view(), name="session-term-manage"),
    path("backup/", BackupCenterView.as_view(), name="backup-center"),
]
