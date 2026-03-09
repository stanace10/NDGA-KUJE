from django.contrib import admin

from apps.attendance.models import AttendanceRecord, Holiday, SchoolCalendar

admin.site.register(SchoolCalendar)
admin.site.register(Holiday)
admin.site.register(AttendanceRecord)
