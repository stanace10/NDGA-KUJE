from django.urls import path

from apps.academics.campus_views import (
    ITCampusDeleteView,
    ITCampusHardDeleteView,
    ITCampusListCreateView,
    ITCampusUpdateView,
)
from apps.academics.views import (
    ITAcademicHubView,
    ITClassDeleteView,
    ITClassHardDeleteView,
    ITClassListCreateView,
    ITClassSubjectDeleteView,
    ITClassSubjectHardDeleteView,
    ITClassSubjectListCreateView,
    ITClassSubjectUpdateView,
    ITClassUpdateView,
    ITFormTeacherAssignmentDeleteView,
    ITFormTeacherAssignmentHardDeleteView,
    ITFormTeacherAssignmentListCreateView,
    ITFormTeacherAssignmentUpdateView,
    ITSubjectDeleteView,
    ITSubjectHardDeleteView,
    ITSubjectListCreateView,
    ITSubjectUpdateView,
    ITTeacherSubjectAssignmentDeleteView,
    ITTimetableGeneratorView,
    ITTeacherSubjectAssignmentHardDeleteView,
    ITTeacherSubjectAssignmentListCreateView,
    ITTeacherSubjectAssignmentUpdateView,
)

app_name = "academics"

urlpatterns = [
    path("it/", ITAcademicHubView.as_view(), name="it-hub"),
    path("it/campuses/", ITCampusListCreateView.as_view(), name="it-campuses"),
    path("it/campuses/<int:pk>/edit/", ITCampusUpdateView.as_view(), name="it-campuses-edit"),
    path("it/campuses/<int:pk>/delete/", ITCampusDeleteView.as_view(), name="it-campuses-delete"),
    path(
        "it/campuses/<int:pk>/hard-delete/",
        ITCampusHardDeleteView.as_view(),
        name="it-campuses-hard-delete",
    ),
    path("it/timetable-generator/", ITTimetableGeneratorView.as_view(), name="it-timetable-generator"),
    path("it/classes/", ITClassListCreateView.as_view(), name="it-classes"),
    path("it/classes/<int:pk>/edit/", ITClassUpdateView.as_view(), name="it-classes-edit"),
    path("it/classes/<int:pk>/delete/", ITClassDeleteView.as_view(), name="it-classes-delete"),
    path(
        "it/classes/<int:pk>/hard-delete/",
        ITClassHardDeleteView.as_view(),
        name="it-classes-hard-delete",
    ),
    path(
        "it/subjects/",
        ITSubjectListCreateView.as_view(),
        name="it-subjects",
    ),
    path(
        "it/subjects/<int:pk>/edit/",
        ITSubjectUpdateView.as_view(),
        name="it-subjects-edit",
    ),
    path("it/subjects/<int:pk>/delete/", ITSubjectDeleteView.as_view(), name="it-subjects-delete"),
    path(
        "it/subjects/<int:pk>/hard-delete/",
        ITSubjectHardDeleteView.as_view(),
        name="it-subjects-hard-delete",
    ),
    path(
        "it/class-subjects/",
        ITClassSubjectListCreateView.as_view(),
        name="it-class-subjects",
    ),
    path(
        "it/class-subjects/<int:pk>/edit/",
        ITClassSubjectUpdateView.as_view(),
        name="it-class-subjects-edit",
    ),
    path(
        "it/class-subjects/<int:pk>/delete/",
        ITClassSubjectDeleteView.as_view(),
        name="it-class-subjects-delete",
    ),
    path(
        "it/class-subjects/<int:pk>/hard-delete/",
        ITClassSubjectHardDeleteView.as_view(),
        name="it-class-subjects-hard-delete",
    ),
    path(
        "it/assignments/subject/",
        ITTeacherSubjectAssignmentListCreateView.as_view(),
        name="it-teacher-subject-assignments",
    ),
    path(
        "it/assignments/subject/<int:pk>/edit/",
        ITTeacherSubjectAssignmentUpdateView.as_view(),
        name="it-teacher-subject-assignments-edit",
    ),
    path(
        "it/assignments/subject/<int:pk>/delete/",
        ITTeacherSubjectAssignmentDeleteView.as_view(),
        name="it-teacher-subject-assignments-delete",
    ),
    path(
        "it/assignments/subject/<int:pk>/hard-delete/",
        ITTeacherSubjectAssignmentHardDeleteView.as_view(),
        name="it-teacher-subject-assignments-hard-delete",
    ),
    path(
        "it/assignments/form-teacher/",
        ITFormTeacherAssignmentListCreateView.as_view(),
        name="it-form-teacher-assignments",
    ),
    path(
        "it/assignments/form-teacher/<int:pk>/edit/",
        ITFormTeacherAssignmentUpdateView.as_view(),
        name="it-form-teacher-assignments-edit",
    ),
    path(
        "it/assignments/form-teacher/<int:pk>/delete/",
        ITFormTeacherAssignmentDeleteView.as_view(),
        name="it-form-teacher-assignments-delete",
    ),
    path(
        "it/assignments/form-teacher/<int:pk>/hard-delete/",
        ITFormTeacherAssignmentHardDeleteView.as_view(),
        name="it-form-teacher-assignments-hard-delete",
    ),
]
