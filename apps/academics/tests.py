from django.core.exceptions import ValidationError
from django.test import Client, TestCase

from apps.accounts.constants import (
    ROLE_DEAN,
    ROLE_FORM_TEACHER,
    ROLE_IT_MANAGER,
    ROLE_STUDENT,
    ROLE_SUBJECT_TEACHER,
)
from apps.accounts.models import Role, User
from apps.academics.models import (
    AcademicClass,
    AcademicSession,
    Campus,
    ClassSubject,
    FormTeacherAssignment,
    Subject,
    TeacherSubjectAssignment,
    Term,
)
from apps.academics.timetable import generate_timetable_preview


class StageFourAcademicModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.role_it = Role.objects.get(code=ROLE_IT_MANAGER)
        cls.role_subject = Role.objects.get(code=ROLE_SUBJECT_TEACHER)
        cls.role_form = Role.objects.get(code=ROLE_FORM_TEACHER)
        cls.role_dean = Role.objects.get(code=ROLE_DEAN)
        cls.role_student = Role.objects.get(code=ROLE_STUDENT)

        cls.teacher_one = User.objects.create_user(
            username="teacher-one",
            password="Password123!",
            primary_role=cls.role_subject,
            must_change_password=False,
        )
        cls.teacher_two = User.objects.create_user(
            username="teacher-two",
            password="Password123!",
            primary_role=cls.role_dean,
            must_change_password=False,
        )
        cls.form_teacher = User.objects.create_user(
            username="form-teacher",
            password="Password123!",
            primary_role=cls.role_form,
            must_change_password=False,
        )
        cls.student_user = User.objects.create_user(
            username="student-role-user",
            password="Password123!",
            primary_role=cls.role_student,
            must_change_password=False,
        )

        cls.session = AcademicSession.objects.create(name="2025/2026")
        cls.term = Term.objects.create(session=cls.session, name="FIRST")
        cls.academic_class = AcademicClass.objects.create(code="JS1A", display_name="JS1A")
        cls.subject = Subject.objects.create(name="Mathematics", code="MTH")
        ClassSubject.objects.create(academic_class=cls.academic_class, subject=cls.subject)

    def test_one_active_teacher_per_subject_class_term_constraint(self):
        TeacherSubjectAssignment.objects.create(
            teacher=self.teacher_one,
            subject=self.subject,
            academic_class=self.academic_class,
            session=self.session,
            term=self.term,
            is_active=True,
        )
        duplicate = TeacherSubjectAssignment(
            teacher=self.teacher_two,
            subject=self.subject,
            academic_class=self.academic_class,
            session=self.session,
            term=self.term,
            is_active=True,
        )
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_one_active_form_teacher_per_class_session_constraint(self):
        FormTeacherAssignment.objects.create(
            teacher=self.form_teacher,
            academic_class=self.academic_class,
            session=self.session,
            is_active=True,
        )
        second_form_teacher = User.objects.create_user(
            username="form-two",
            password="Password123!",
            primary_role=self.role_form,
            must_change_password=False,
        )
        duplicate = FormTeacherAssignment(
            teacher=second_form_teacher,
            academic_class=self.academic_class,
            session=self.session,
            is_active=True,
        )
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_form_teacher_role_validation(self):
        invalid_assignment = FormTeacherAssignment(
            teacher=self.student_user,
            academic_class=self.academic_class,
            session=self.session,
            is_active=True,
        )
        with self.assertRaises(ValidationError):
            invalid_assignment.full_clean()


class StageFourITScreensTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        role_it = Role.objects.get(code=ROLE_IT_MANAGER)
        role_student = Role.objects.get(code=ROLE_STUDENT)
        cls.it_user = User.objects.create_user(
            username="it-stage4",
            password="Password123!",
            primary_role=role_it,
            must_change_password=False,
        )
        cls.student_user = User.objects.create_user(
            username="student-stage4",
            password="Password123!",
            primary_role=role_student,
            must_change_password=False,
        )

    def test_it_can_create_class_and_subject(self):
        client = Client(HTTP_HOST="it.ndgakuje.org")
        login_response = client.post(
            "/auth/login/?audience=staff",
            {"username": "it-stage4", "password": "Password123!"},
        )
        self.assertEqual(login_response.status_code, 302)

        class_response = client.post(
            "/academics/it/classes/",
            {"code": "SS2A", "display_name": "SS2A", "is_active": "on"},
        )
        self.assertEqual(class_response.status_code, 302)
        self.assertTrue(AcademicClass.objects.filter(code="SS2A").exists())

        subject_response = client.post(
            "/academics/it/subjects/",
            {"name": "Physics", "code": "PHY", "is_active": "on"},
        )
        self.assertEqual(subject_response.status_code, 302)
        self.assertTrue(Subject.objects.filter(code="PHY").exists())

    def test_student_cannot_access_it_academics_routes(self):
        client = Client(HTTP_HOST="student.ndgakuje.org")
        login_response = client.post(
            "/auth/login/?audience=student",
            {"username": "student-stage4", "password": "Password123!"},
        )
        self.assertEqual(login_response.status_code, 302)

        denied_response = client.get("/academics/it/")
        self.assertEqual(denied_response.status_code, 302)
        self.assertEqual(denied_response.url, "http://student.ndgakuje.org/")

    def test_it_can_hard_delete_unused_class_and_subject(self):
        client = Client(HTTP_HOST="it.ndgakuje.org")
        login_response = client.post(
            "/auth/login/?audience=staff",
            {"username": "it-stage4", "password": "Password123!"},
        )
        self.assertEqual(login_response.status_code, 302)

        class_row = AcademicClass.objects.create(code="TMP1", display_name="TMP1")
        subject_row = Subject.objects.create(name="Temp Subject", code="TMP")

        class_delete_response = client.post(f"/academics/it/classes/{class_row.id}/hard-delete/")
        subject_delete_response = client.post(f"/academics/it/subjects/{subject_row.id}/hard-delete/")

        self.assertEqual(class_delete_response.status_code, 302)
        self.assertEqual(subject_delete_response.status_code, 302)
        self.assertFalse(AcademicClass.objects.filter(id=class_row.id).exists())
        self.assertFalse(Subject.objects.filter(id=subject_row.id).exists())

    def test_it_hard_delete_is_blocked_when_dependencies_exist(self):
        client = Client(HTTP_HOST="it.ndgakuje.org")
        login_response = client.post(
            "/auth/login/?audience=staff",
            {"username": "it-stage4", "password": "Password123!"},
        )
        self.assertEqual(login_response.status_code, 302)

        class_row = AcademicClass.objects.create(code="TMP2", display_name="TMP2")
        subject_row = Subject.objects.create(name="Temp Subject 2", code="TMP2")
        ClassSubject.objects.create(academic_class=class_row, subject=subject_row, is_active=True)

        class_delete_response = client.post(f"/academics/it/classes/{class_row.id}/hard-delete/")
        subject_delete_response = client.post(f"/academics/it/subjects/{subject_row.id}/hard-delete/")

        self.assertEqual(class_delete_response.status_code, 302)
        self.assertEqual(subject_delete_response.status_code, 302)
        self.assertTrue(AcademicClass.objects.filter(id=class_row.id).exists())
        self.assertTrue(Subject.objects.filter(id=subject_row.id).exists())


class TimetableGeneratorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        role_it = Role.objects.get(code=ROLE_IT_MANAGER)
        role_subject = Role.objects.get(code=ROLE_SUBJECT_TEACHER)
        cls.it_user = User.objects.create_user(
            username="it-timetable",
            password="Password123!",
            primary_role=role_it,
            must_change_password=False,
        )
        cls.teacher = User.objects.create_user(
            username="teacher-timetable",
            password="Password123!",
            primary_role=role_subject,
            must_change_password=False,
        )
        cls.session = AcademicSession.objects.create(name="2026/2027")
        cls.term = Term.objects.create(session=cls.session, name="FIRST")
        cls.class_one = AcademicClass.objects.create(code="JS1A", display_name="JS1A")
        cls.class_two = AcademicClass.objects.create(code="JS1B", display_name="JS1B")
        cls.subject_one = Subject.objects.create(name="Basic Science TT", code="BSTT")
        cls.subject_two = Subject.objects.create(name="Mathematics TT", code="MTHTT")
        ClassSubject.objects.create(academic_class=cls.class_one, subject=cls.subject_one, is_active=True)
        ClassSubject.objects.create(academic_class=cls.class_two, subject=cls.subject_two, is_active=True)
        cls.assignment_one = TeacherSubjectAssignment.objects.create(
            teacher=cls.teacher,
            subject=cls.subject_one,
            academic_class=cls.class_one,
            session=cls.session,
            term=cls.term,
            is_active=True,
        )
        cls.assignment_two = TeacherSubjectAssignment.objects.create(
            teacher=cls.teacher,
            subject=cls.subject_two,
            academic_class=cls.class_two,
            session=cls.session,
            term=cls.term,
            is_active=True,
        )

    def test_generate_timetable_preview_avoids_teacher_slot_conflicts(self):
        preview = generate_timetable_preview(
            assignments=[self.assignment_one, self.assignment_two],
            days=["MONDAY", "TUESDAY"],
            periods_per_day=2,
            periods_per_assignment=1,
            room_prefix="Lab",
        )
        self.assertEqual(preview["summary"]["unplaced_slots"], 0)
        teacher_slots = {(row["day"], row["period"], row["teacher"]) for row in preview["placed_rows"]}
        self.assertEqual(len(teacher_slots), len(preview["placed_rows"]))

    def test_it_can_open_and_generate_timetable_preview_page(self):
        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_user)
        response = client.post(
            "/academics/it/timetable-generator/",
            {
                "session": self.session.id,
                "term": self.term.id,
                "days": ["MONDAY", "TUESDAY", "WEDNESDAY"],
                "periods_per_day": 3,
                "periods_per_assignment": 1,
                "room_prefix": "Block",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Smart Timetable Generator")
        self.assertContains(response, "JS1A")
        self.assertContains(response, "JS1B")


class CampusManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        role_it = Role.objects.get(code=ROLE_IT_MANAGER)
        cls.it_user = User.objects.create_user(
            username="it-campus",
            password="Password123!",
            primary_role=role_it,
            must_change_password=False,
        )

    def test_it_can_create_campus_and_assign_class(self):
        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_user)

        response = client.post(
            "/academics/it/campuses/",
            {
                "name": "Main Campus",
                "code": "MAIN",
                "address": "Uke Campus Road",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        campus = Campus.objects.get(code="MAIN")

        class_response = client.post(
            "/academics/it/classes/",
            {
                "code": "SS3A-CAMP",
                "display_name": "SS3A Campus",
                "campus": campus.id,
                "is_active": "on",
            },
        )
        self.assertEqual(class_response.status_code, 302)
        self.assertEqual(AcademicClass.objects.get(code="SS3A-CAMP").campus, campus)

    def test_it_cannot_hard_delete_campus_with_linked_class(self):
        campus = Campus.objects.create(name="North Campus", code="NORTH")
        AcademicClass.objects.create(code="JS2-NORTH", display_name="JS2 North", campus=campus)

        client = Client(HTTP_HOST="it.ndgakuje.org")
        client.force_login(self.it_user)
        response = client.post(f"/academics/it/campuses/{campus.id}/hard-delete/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Campus.objects.filter(id=campus.id).exists())
