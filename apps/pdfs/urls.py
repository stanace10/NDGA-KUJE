from django.urls import path

from apps.pdfs.views import (
    PDFVerificationView,
    StaffSessionTranscriptDownloadView,
    StaffPerformanceAnalysisDownloadView,
    StaffTermReportDownloadView,
    StaffTranscriptDownloadView,
    StudentPerformanceAnalysisDownloadView,
    StudentPerformanceAnalysisView,
    StudentReportsView,
    StudentTermReportView,
    StudentSessionTranscriptDownloadView,
    StudentTermReportDownloadView,
    StudentTranscriptDownloadView,
)

app_name = "pdfs"

urlpatterns = [
    path("student/reports/", StudentReportsView.as_view(), name="student-reports"),
    path(
        "student/reports/<int:compilation_id>/",
        StudentTermReportView.as_view(),
        name="student-term-report-view",
    ),
    path(
        "student/reports/<int:compilation_id>/download/",
        StudentTermReportDownloadView.as_view(),
        name="student-term-report-download",
    ),
    path(
        "student/reports/<int:compilation_id>/performance/",
        StudentPerformanceAnalysisView.as_view(),
        name="student-performance-analysis-view",
    ),
    path(
        "student/reports/<int:compilation_id>/performance/download/",
        StudentPerformanceAnalysisDownloadView.as_view(),
        name="student-performance-analysis-download",
    ),
    path(
        "student/transcript/download/",
        StudentTranscriptDownloadView.as_view(),
        name="student-transcript-download",
    ),
    path(
        "student/transcript/session/<int:session_id>/download/",
        StudentSessionTranscriptDownloadView.as_view(),
        name="student-session-transcript-download",
    ),
    path(
        "staff/reports/<int:compilation_id>/student/<int:student_id>/download/",
        StaffTermReportDownloadView.as_view(),
        name="staff-term-report-download",
    ),
    path(
        "staff/reports/<int:compilation_id>/student/<int:student_id>/performance/download/",
        StaffPerformanceAnalysisDownloadView.as_view(),
        name="staff-performance-analysis-download",
    ),
    path(
        "staff/transcript/student/<int:student_id>/download/",
        StaffTranscriptDownloadView.as_view(),
        name="staff-transcript-download",
    ),
    path(
        "staff/transcript/student/<int:student_id>/session/<int:session_id>/download/",
        StaffSessionTranscriptDownloadView.as_view(),
        name="staff-session-transcript-download",
    ),
    path("verify/<uuid:artifact_id>/", PDFVerificationView.as_view(), name="verify"),
]
