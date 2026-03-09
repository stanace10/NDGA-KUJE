from django.urls import path

from apps.elections.views import (
    ElectionAnalyticsView,
    ElectionHomeView,
    ElectionITManagementDetailView,
    ElectionITManagementView,
    ElectionResultPDFView,
    ElectionResultVerificationView,
    ElectionVoteConfirmView,
    ElectionVotePositionView,
    ElectionVoteStartView,
)

app_name = "elections"

urlpatterns = [
    path("", ElectionHomeView.as_view(), name="home"),
    path("it/manage/", ElectionITManagementView.as_view(), name="it-manage"),
    path(
        "it/manage/<int:election_id>/",
        ElectionITManagementDetailView.as_view(),
        name="it-manage-detail",
    ),
    path("vote/<int:election_id>/start/", ElectionVoteStartView.as_view(), name="vote-start"),
    path(
        "vote/<int:election_id>/position/<int:position_id>/",
        ElectionVotePositionView.as_view(),
        name="vote-position",
    ),
    path(
        "vote/<int:election_id>/confirm/",
        ElectionVoteConfirmView.as_view(),
        name="vote-confirm",
    ),
    path(
        "analytics/<int:election_id>/",
        ElectionAnalyticsView.as_view(),
        name="analytics",
    ),
    path(
        "results/<int:election_id>/pdf/",
        ElectionResultPDFView.as_view(),
        name="result-pdf",
    ),
    path(
        "verify/<uuid:artifact_id>/",
        ElectionResultVerificationView.as_view(),
        name="verify-result",
    ),
]
