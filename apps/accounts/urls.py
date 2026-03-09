from django.urls import path

from apps.accounts.views import (
    ITCredentialResetView,
    ITMobileCaptureSessionView,
    ITMobileCaptureStatusView,
    ITStaffDetailView,
    ITStaffDirectoryView,
    ITStaffEditView,
    ITStaffProvisioningView,
    ITStudentDetailView,
    ITStudentDirectoryView,
    ITStudentEditView,
    ITStudentProvisioningView,
    ITUserDeleteView,
    ITUserStatusToggleView,
    ITUserProvisioningView,
    LoginView,
    LogoutView,
    MobileCaptureStartView,
    MobileCaptureSubmitView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PasswordChangeView,
    RoleRedirectView,
)

app_name = "accounts"

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("redirect/", RoleRedirectView.as_view(), name="role-redirect"),
    path("password/reset/", PasswordResetRequestView.as_view(), name="password-reset-request"),
    path(
        "password/reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path("password/change/", PasswordChangeView.as_view(), name="password-change"),
    path(
        "it/reset-credentials/",
        ITCredentialResetView.as_view(),
        name="it-reset-credentials",
    ),
    path(
        "it/user-provisioning/",
        ITUserProvisioningView.as_view(),
        name="it-user-provisioning",
    ),
    path(
        "it/user-provisioning/staff/",
        ITStaffProvisioningView.as_view(),
        name="it-staff-provisioning",
    ),
    path(
        "it/user-provisioning/staff/directory/",
        ITStaffDirectoryView.as_view(),
        name="it-staff-directory",
    ),
    path(
        "it/user-provisioning/students/",
        ITStudentProvisioningView.as_view(),
        name="it-student-provisioning",
    ),
    path(
        "it/user-provisioning/students/directory/",
        ITStudentDirectoryView.as_view(),
        name="it-student-directory",
    ),
    path(
        "it/staff/<int:user_id>/",
        ITStaffDetailView.as_view(),
        name="it-staff-detail",
    ),
    path(
        "it/staff/<int:user_id>/edit/",
        ITStaffEditView.as_view(),
        name="it-staff-edit",
    ),
    path(
        "it/student/<int:user_id>/",
        ITStudentDetailView.as_view(),
        name="it-student-detail",
    ),
    path(
        "it/student/<int:user_id>/edit/",
        ITStudentEditView.as_view(),
        name="it-student-edit",
    ),
    path(
        "it/user/<int:user_id>/toggle-status/",
        ITUserStatusToggleView.as_view(),
        name="it-user-toggle-status",
    ),
    path(
        "it/user/<int:user_id>/delete/",
        ITUserDeleteView.as_view(),
        name="it-user-delete",
    ),
    path(
        "it/mobile-capture/session/",
        ITMobileCaptureSessionView.as_view(),
        name="it-mobile-capture-session",
    ),
    path(
        "it/mobile-capture/status/",
        ITMobileCaptureStatusView.as_view(),
        name="it-mobile-capture-status",
    ),
    path(
        "mobile-capture/<str:token>/",
        MobileCaptureStartView.as_view(),
        name="mobile-capture-start",
    ),
    path(
        "mobile-capture/<str:token>/submit/",
        MobileCaptureSubmitView.as_view(),
        name="mobile-capture-submit",
    ),
]
