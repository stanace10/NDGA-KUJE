from datetime import date

from django.test import Client, TestCase

from apps.accounts.constants import (
    ROLE_FORM_TEACHER,
    ROLE_IT_MANAGER,
    ROLE_PRINCIPAL,
    ROLE_STUDENT,
    ROLE_SUBJECT_TEACHER,
    ROLE_VP,
)
from apps.accounts.models import Role, User
from apps.academics.models import AcademicClass, AcademicSession, FormTeacherAssignment, StudentClassEnrollment, Term
from apps.attendance.models import AttendanceRecord, AttendanceStatus, Holiday, SchoolCalendar
from apps.attendance.services import compute_student_attendance_percentage
from apps.setup_wizard.models import SetupStateCode, SystemSetupState


class StageFiveAttendanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        roles = {code: Role.objects.get(code=code) for code in [
            ROLE_IT_MANAGER,
            ROLE_VP,
            ROLE_PRINCIPAL,
            ROLE_FORM_TEACHER,
            ROLE_SUBJECT_TEACHER,
            ROLE_STUDENT,
        ]}

        cls.it_user = User.objects.create_user(
            username="it-att",
            password="Password123!",
            primary_role=roles[ROLE_IT_MANAGER],
            must_change_password=False,
        )
        cls.vp_user = User.objects.create_user(
            username="vp-att",
            password="Password123!",
            primary_role=roles[ROLE_VP],
            must_change_password=False,
        )
        cls.principal_user = User.objects.create_user(
            username="principal-att",
            password="Password123!",
            primary_role=roles[ROLE_PRINCIPAL],
            must_change_password=False,
        )
        cls.form_teacher = User.objects.create_user(
            username="form-att",
            password="Password123!",
            primary_role=roles[ROLE_FORM_TEACHER],
            must_change_password=False,
        )
        cls.subject_teacher = User.objects.create_user(
            username="subject-att",
            password="Password123!",
            primary_role=roles[ROLE_SUBJECT_TEACHER],
            must_change_password=False,
        )
        cls.student = User.objects.create_user(
            username="student-att",
            password="Password123!",
            primary_role=roles[ROLE_STUDENT],
            must_change_password=False,
        )

        cls.session = AcademicSession.objects.create(name="2025/2026")
        cls.term = Term.objects.create(session=cls.session, name="FIRST")
        cls.academic_class = AcademicClass.objects.create(code="JS1A", display_name="JS1A")
        cls.calendar = SchoolCalendar.objects.create(
            session=cls.session,
            term=cls.term,
            start_date=date(2026, 1, 5),
            end_date=date(2026, 1, 16),
        )
        Holiday.objects.create(calendar=cls.calendar, date=date(2026, 1, 8), description="Midweek break")

        FormTeacherAssignment.objects.create(
            teacher=cls.form_teacher,
            academic_class=cls.academic_class,
            session=cls.session,
            is_active=True,
        )
        StudentClassEnrollment.objects.create(
            student=cls.student,
            academic_class=cls.academic_class,
            session=cls.session,
            is_active=True,
        )

        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = cls.session
        setup_state.current_term = cls.term
        setup_state.save(update_fields=["state", "current_session", "current_term", "updated_at"])

    def test_subject_teacher_cannot_access_attendance_routes(self):
        client = Client(HTTP_HOST="staff.ndgakuje.org")
        login_response = client.post(
            "/auth/login/?audience=staff",
            {"username": "subject-att", "password": "Password123!"},
        )
        self.assertEqual(login_response.status_code, 302)
        denied_response = client.get("/attendance/form/mark/")
        self.assertEqual(denied_response.status_code, 302)
        self.assertEqual(denied_response.url, "http://staff.ndgakuje.org/")

    def test_weekend_date_selection_is_blocked(self):
        client = Client(HTTP_HOST="staff.ndgakuje.org")
        login_response = client.post(
            "/auth/login/?audience=staff",
            {"username": "form-att", "password": "Password123!"},
        )
        self.assertEqual(login_response.status_code, 302)

        response = client.post(
            "/attendance/form/mark/",
            {
                "academic_class": str(self.academic_class.id),
                "attendance_date": "2026-01-10",  # Saturday
                "visible_student_ids": [str(self.student.id)],
                "present_student_ids": [str(self.student.id)],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Attendance cannot be marked on weekends.")
        self.assertEqual(AttendanceRecord.objects.count(), 0)

    def test_attendance_percentage_uses_computed_school_days(self):
        present_dates = [
            date(2026, 1, 5),
            date(2026, 1, 6),
            date(2026, 1, 7),
            date(2026, 1, 9),
            date(2026, 1, 12),
            date(2026, 1, 13),
        ]
        for day in present_dates:
            AttendanceRecord.objects.create(
                calendar=self.calendar,
                academic_class=self.academic_class,
                student=self.student,
                date=day,
                status=AttendanceStatus.PRESENT,
                marked_by=self.form_teacher,
            )

        percentage = compute_student_attendance_percentage(
            student=self.student,
            calendar=self.calendar,
            academic_class=self.academic_class,
        )
        # 2 weeks (10 weekdays) - 1 holiday = 9 valid school days
        # present days = 6 => 66.67%
        self.assertEqual(percentage, 66.67)

    def test_vp_and_principal_can_access_calendar_management(self):
        vp_client = Client(HTTP_HOST="vp.ndgakuje.org")
        vp_login = vp_client.post(
            "/auth/login/?audience=staff",
            {"username": "vp-att", "password": "Password123!"},
        )
        self.assertEqual(vp_login.status_code, 302)
        vp_page = vp_client.get("/attendance/calendar/manage/")
        self.assertEqual(vp_page.status_code, 200)

        principal_client = Client(HTTP_HOST="principal.ndgakuje.org")
        principal_login = principal_client.post(
            "/auth/login/?audience=staff",
            {"username": "principal-att", "password": "Password123!"},
        )
        self.assertEqual(principal_login.status_code, 302)
        principal_page = principal_client.get("/attendance/calendar/manage/")
        self.assertEqual(principal_page.status_code, 200)

    def test_it_can_add_holiday_range_and_edit_delete_holiday(self):
        client = Client(HTTP_HOST="it.ndgakuje.org")
        login_response = client.post(
            "/auth/login/?audience=staff",
            {"username": "it-att", "password": "Password123!"},
        )
        self.assertEqual(login_response.status_code, 302)

        add_range_response = client.post(
            "/attendance/calendar/manage/",
            {
                "action": "add-holiday-range",
                "calendar_id": str(self.calendar.id),
                "start_date": "2026-01-12",
                "end_date": "2026-01-16",
                "description": "Mid-Term Break",
                "exclude_weekends": "on",
            },
        )
        self.assertEqual(add_range_response.status_code, 302)
        self.assertEqual(
            Holiday.objects.filter(
                calendar=self.calendar,
                description="Mid-Term Break",
            ).count(),
            5,
        )

        holiday = Holiday.objects.filter(calendar=self.calendar, date=date(2026, 1, 12)).first()
        self.assertIsNotNone(holiday)
        update_response = client.post(
            "/attendance/calendar/manage/",
            {
                "action": "update-holiday",
                "calendar_id": str(self.calendar.id),
                "holiday_id": str(holiday.id),
                "date": "2026-01-13",
                "description": "Adjusted Mid-Term Break",
            },
        )
        self.assertEqual(update_response.status_code, 302)
        self.assertTrue(
            Holiday.objects.filter(
                calendar=self.calendar,
                date=date(2026, 1, 13),
                description="Adjusted Mid-Term Break",
            ).exists()
        )

        delete_target = Holiday.objects.filter(
            calendar=self.calendar,
            date=date(2026, 1, 8),
        ).first()
        self.assertIsNotNone(delete_target)
        delete_response = client.post(
            "/attendance/calendar/manage/",
            {
                "action": "delete-holiday",
                "calendar_id": str(self.calendar.id),
                "holiday_id": str(delete_target.id),
            },
        )
        self.assertEqual(delete_response.status_code, 302)
        self.assertFalse(Holiday.objects.filter(id=delete_target.id).exists())
