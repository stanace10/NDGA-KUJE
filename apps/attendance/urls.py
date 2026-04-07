from django.urls import path

from apps.attendance.views import (
    CalendarManagementView,
    FormTeacherAttendanceView,
    FormTeacherClassListView,
    FormTeacherWeeklyAttendanceView,
)

app_name = "attendance"

urlpatterns = [
    path("calendar/manage/", CalendarManagementView.as_view(), name="calendar-manage"),
    path("form/classes/", FormTeacherClassListView.as_view(), name="form-classes"),
    path("form/mark/", FormTeacherAttendanceView.as_view(), name="form-mark"),
    path("form/mark/weekly/", FormTeacherWeeklyAttendanceView.as_view(), name="form-weekly"),
]
