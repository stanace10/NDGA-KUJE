from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.academics.models import AcademicClass, AcademicSession, Term
from core.models import TimeStampedModel


class AttendanceStatus(models.TextChoices):
    PRESENT = "PRESENT", "Present"
    ABSENT = "ABSENT", "Absent"


class SchoolCalendar(TimeStampedModel):
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name="school_calendars",
    )
    term = models.OneToOneField(
        Term,
        on_delete=models.CASCADE,
        related_name="school_calendar",
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ("-start_date",)

    def clean(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValidationError("Calendar end date cannot be before start date.")
        if self.term_id and self.session_id and self.term.session_id != self.session_id:
            raise ValidationError("Calendar session must match term session.")

    def __str__(self):
        return f"{self.term.get_name_display()} ({self.session.name})"

    def effective_end_date(self, fallback_date=None):
        return self.end_date or fallback_date or timezone.localdate()

    def covers(self, day):
        if day < self.start_date:
            return False
        if self.end_date and day > self.end_date:
            return False
        return True

    def school_days_count(self):
        holidays = set(self.holidays.values_list("date", flat=True))
        current = self.start_date
        end_day = self.effective_end_date()
        total = 0
        while current <= end_day:
            if current.weekday() < 5 and current not in holidays:
                total += 1
            current += timedelta(days=1)
        return total

    def is_school_day(self, day):
        if not self.covers(day):
            return False
        if day.weekday() >= 5:
            return False
        return not self.holidays.filter(date=day).exists()

    def school_days_between(self, start_day=None, end_day=None):
        start = start_day or self.start_date
        end = end_day or self.effective_end_date()
        if start < self.start_date:
            start = self.start_date
        if self.end_date and end > self.end_date:
            end = self.end_date
        holidays = set(self.holidays.values_list("date", flat=True))
        days = []
        current = start
        while current <= end:
            if current.weekday() < 5 and current not in holidays:
                days.append(current)
            current += timedelta(days=1)
        return days


class Holiday(TimeStampedModel):
    calendar = models.ForeignKey(
        SchoolCalendar,
        on_delete=models.CASCADE,
        related_name="holidays",
    )
    date = models.DateField()
    description = models.CharField(max_length=140)

    class Meta:
        ordering = ("date",)
        constraints = [
            models.UniqueConstraint(
                fields=("calendar", "date"),
                name="unique_holiday_per_calendar_date",
            )
        ]

    def __str__(self):
        return f"{self.date}: {self.description}"


class AttendanceRecord(TimeStampedModel):
    calendar = models.ForeignKey(
        SchoolCalendar,
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    student = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    date = models.DateField()
    status = models.CharField(
        max_length=10,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.ABSENT,
    )
    marked_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marked_attendance_records",
    )

    class Meta:
        ordering = ("-date", "student__username")
        constraints = [
            models.UniqueConstraint(
                fields=("calendar", "academic_class", "student", "date"),
                name="unique_daily_attendance_record",
            ),
        ]
        indexes = [
            models.Index(fields=("academic_class", "date")),
            models.Index(fields=("student", "date")),
        ]

    def clean(self):
        if not self.calendar.is_school_day(self.date):
            raise ValidationError("Attendance can only be marked on valid school days.")
        if self.calendar.term_id and self.calendar.term.session_id != self.calendar.session_id:
            raise ValidationError("Invalid calendar configuration: term/session mismatch.")

    def __str__(self):
        return f"{self.student.username} {self.date} {self.status}"
