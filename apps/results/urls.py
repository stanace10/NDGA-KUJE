from django.urls import path

from apps.results.views import (
    AssignmentScoreListView,
    AwardListingView,
    ClassTimelineView,
    PerformanceReportView,
    SendResultsView,
    DeanExamReviewListView,
    FormCompilationStudentDetailView,
    GradeEntryClassSubjectsView,
    DeanReviewDetailView,
    DeanReviewListView,
    DeanResultReviewListView,
    FormCompilationView,
    GradeEntryHomeView,
    ResultApprovalClassDetailView,
    ResultApprovalClassListView,
    ResultApprovalStudentDetailView,
    PrincipalOversightView,
    PrincipalOverrideView,
    ResultAccessPinManagementView,
    ResultSettingsView,
    ResultUploadStatisticsView,
    StudentScoreEditView,
    TeacherRankingView,
    VPReviewDetailView,
    VPReviewListView,
)

app_name = "results"

urlpatterns = [
    path("report/award-listing/", AwardListingView.as_view(), name="award-listing"),
    path("report/performance/", PerformanceReportView.as_view(), name="performance-report"),
    path("report/upload-statistics/", ResultUploadStatisticsView.as_view(), name="result-upload-statistics"),
    path("report/teacher-ranking/", TeacherRankingView.as_view(), name="teacher-ranking"),
    path("report/send-results/", SendResultsView.as_view(), name="send-results"),
    path("report/access-pins/", ResultAccessPinManagementView.as_view(), name="result-access-pins"),
    path("settings/", ResultSettingsView.as_view(), name="result-settings"),
    path("approval/", ResultApprovalClassListView.as_view(), name="approval-class-list"),
    path(
        "approval/class/<int:compilation_id>/",
        ResultApprovalClassDetailView.as_view(),
        name="approval-class-detail",
    ),
    path(
        "approval/class/<int:compilation_id>/student/<int:student_id>/",
        ResultApprovalStudentDetailView.as_view(),
        name="approval-student-detail",
    ),
    path("grade-entry/", GradeEntryHomeView.as_view(), name="grade-entry-home"),
    path(
        "grade-entry/class/<int:class_id>/",
        GradeEntryClassSubjectsView.as_view(),
        name="grade-entry-class-subjects",
    ),
    path(
        "grade-entry/<int:assignment_id>/",
        AssignmentScoreListView.as_view(),
        name="assignment-scores",
    ),
    path(
        "grade-entry/<int:assignment_id>/student/<int:student_id>/",
        StudentScoreEditView.as_view(),
        name="student-score-edit",
    ),
    path("dean/review/", DeanReviewListView.as_view(), name="dean-review-list"),
    path(
        "dean/review/results/",
        DeanResultReviewListView.as_view(),
        name="dean-result-review-list",
    ),
    path(
        "dean/review/exams/",
        DeanExamReviewListView.as_view(),
        name="dean-exam-review-list",
    ),
    path(
        "dean/review/<int:sheet_id>/",
        DeanReviewDetailView.as_view(),
        name="dean-review-detail",
    ),
    path("form/compilation/", FormCompilationView.as_view(), name="form-compilation"),
    path(
        "form/compilation/class/<int:class_id>/student/<int:student_id>/",
        FormCompilationStudentDetailView.as_view(),
        name="form-compilation-student-detail",
    ),
    path("vp/review/", VPReviewListView.as_view(), name="vp-review-list"),
    path(
        "vp/review/<int:compilation_id>/",
        VPReviewDetailView.as_view(),
        name="vp-review-detail",
    ),
    path(
        "principal/oversight/",
        PrincipalOversightView.as_view(),
        name="principal-oversight",
    ),
    path(
        "principal/override/<int:compilation_id>/",
        PrincipalOverrideView.as_view(),
        name="principal-override",
    ),
    path(
        "timeline/class/<int:class_id>/",
        ClassTimelineView.as_view(),
        name="class-timeline",
    ),
]
