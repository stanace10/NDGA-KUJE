from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, ProgrammingError, transaction

from docx import Document

from apps.accounts.constants import ROLE_STUDENT, ROLE_SUBJECT_TEACHER
from apps.accounts.forms import (
    _generate_staff_id_for_role,
    _generate_student_number,
    _generate_student_username,
    _generate_username_from_name,
    generate_temporary_password,
)
from apps.accounts.models import Role, StaffProfile, StudentProfile, User
from apps.academics.models import (
    AcademicClass,
    ClassSubject,
    StudentClassEnrollment,
    Subject,
    TeacherSubjectAssignment,
)
from apps.setup_wizard.services import get_setup_state
from apps.sync.services import queue_student_registration_sync


NAME_SPLIT_RE = re.compile(r"\s+")
STUDENT_ROW_RE = re.compile(r"^\s*(\d+)\s*(?:\u2014|-)\s*(.*?)\s*(?:\u2014|-)\s*(.*?)\s*(?:\u2014|-)\s*(.*?)\s*$")
CLASS_LEVEL_RE = re.compile(r"(JS|SS)([123](?:,[123])*)")

SUBJECT_ALIASES = {
    "BASICTECH": "BASIC TECHNOLOGY",
    "BASICTECHNOLOGY": "BASIC TECHNOLOGY",
    "BASICSCIENCE": "BASIC SCIENCE",
    "CCA": "CCA",
    "CCAART": "VISUAL ART",
    "CRS": "CHRISTIAN RELIGIOUS STUDIES",
    "CRSSTUDIES": "CHRISTIAN RELIGIOUS STUDIES",
    "FURTHERMATHS": "FURTHER MATHEMATICS",
    "GARMENTMAKINGTHEORY": "GARMENT MAKING THEORY",
    "GARMENTMAKINGPRACTICAL": "GARMENT MAKING PRACTICAL",
    "HAUSALANGUAGE": "HAUSA LANGUAGE",
    "IGBOLANGUAGE": "IGBO LANGUAGE",
    "PHE": "PHYSICAL AND HEALTH EDUCATION",
    "SOCIALANDCITIZENSHIPSTUDIES": "SOCIAL AND CITIZENSHIP STUDIES",
    "SOCIALANDDCITIZENSHIPSTUDIES": "SOCIAL AND CITIZENSHIP STUDIES",
    "SOCILASTUDIES": "SOCIAL STUDIES",
}


@dataclass(frozen=True)
class StudentImportRow:
    line_number: int
    full_name: str
    admission_no: str
    class_label: str


@dataclass(frozen=True)
class StaffAssignmentSpec:
    subject_label: str
    class_levels: tuple[str, ...]


@dataclass(frozen=True)
class StaffImportRow:
    row_number: int
    full_name: str
    assignments: tuple[StaffAssignmentSpec, ...]


class ClassResolver:
    def __init__(self):
        self.student_lookup: dict[str, AcademicClass] = {}
        self.base_lookup: dict[str, AcademicClass] = {}
        for academic_class in AcademicClass.objects.select_related("base_class"):
            for token in self._tokens_for_class(academic_class):
                self.student_lookup.setdefault(token, academic_class)
            if not academic_class.base_class_id:
                for token in self._tokens_for_base_class(academic_class):
                    self.base_lookup.setdefault(token, academic_class)

    @staticmethod
    def _tokens_for_base_class(academic_class: AcademicClass):
        values = {
            _normalize_class_token(academic_class.code),
            _normalize_class_token(academic_class.display_name),
        }
        return {value for value in values if value}

    @classmethod
    def _tokens_for_class(cls, academic_class: AcademicClass):
        values = {
            _normalize_class_token(academic_class.code),
            _normalize_class_token(academic_class.display_name),
        }
        if academic_class.base_class_id:
            base = academic_class.base_class
            arm = (academic_class.arm_name or "").strip().upper()
            if arm and base is not None:
                values.add(_normalize_class_token(f"{base.code} {arm}"))
                values.add(_normalize_class_token(f"{base.display_name or base.code} {arm}"))
        return {value for value in values if value}

    def resolve_student_class(self, raw_label: str):
        token = _normalize_class_token(raw_label)
        return self.student_lookup.get(token)

    def resolve_level_class(self, raw_label: str):
        token = _normalize_class_token(raw_label)
        return self.base_lookup.get(token)


class SubjectResolver:
    def __init__(self):
        self.lookup: dict[str, Subject] = {}
        for subject in Subject.objects.filter(is_active=True):
            tokens = {
                _normalize_subject_token(subject.name),
                _normalize_subject_token(subject.code),
            }
            for token in tokens:
                if token:
                    self.lookup.setdefault(token, subject)

    def resolve(self, raw_label: str):
        token = _normalize_subject_token(raw_label)
        alias = SUBJECT_ALIASES.get(token)
        if alias:
            token = _normalize_subject_token(alias)
        subject = self.lookup.get(token)
        if subject is not None:
            return subject
        for known_token, known_subject in self.lookup.items():
            if token and token in known_token:
                return known_subject
        return None


class Command(BaseCommand):
    help = (
        "Bulk import urgent student and subject-teacher registration records from the SCHOOL folder. "
        "Creates minimal accounts first so IT can complete full capture later."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-dir",
            default="SCHOOL",
            help="Folder containing student.txt and SUBJECT TEACHERS.docx (default: SCHOOL).",
        )
        parser.add_argument(
            "--students-only",
            action="store_true",
            help="Import only students.",
        )
        parser.add_argument(
            "--staff-only",
            action="store_true",
            help="Import only staff.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["students_only"] and options["staff_only"]:
            raise CommandError("Choose either --students-only or --staff-only, not both.")

        source_dir = _resolve_source_dir(options["source_dir"])
        role_map = {
            role.code: role
            for role in Role.objects.filter(code__in=[ROLE_STUDENT, ROLE_SUBJECT_TEACHER])
        }
        missing_roles = {ROLE_STUDENT, ROLE_SUBJECT_TEACHER} - set(role_map.keys())
        if missing_roles:
            raise CommandError(
                "Missing role(s): " + ", ".join(sorted(missing_roles)) + ". Run migrations/seed roles first."
            )

        setup_state = get_setup_state()
        class_resolver = ClassResolver()
        subject_resolver = SubjectResolver()

        summary = {
            "students_created": 0,
            "students_skipped": 0,
            "students_enrolled": 0,
            "staff_created": 0,
            "staff_skipped": 0,
            "staff_assignments": 0,
            "warnings": [],
        }

        if not options["staff_only"]:
            student_rows = _parse_student_rows(source_dir / "student.txt")
            self._import_students(
                rows=student_rows,
                role_student=role_map[ROLE_STUDENT],
                current_session=setup_state.current_session,
                class_resolver=class_resolver,
                summary=summary,
            )

        if not options["students_only"]:
            staff_rows = _parse_staff_rows(source_dir)
            self._import_staff(
                rows=staff_rows,
                role_subject_teacher=role_map[ROLE_SUBJECT_TEACHER],
                current_session=setup_state.current_session,
                current_term=setup_state.current_term,
                class_resolver=class_resolver,
                subject_resolver=subject_resolver,
                summary=summary,
            )

        self.stdout.write(self.style.SUCCESS("School registration import completed."))
        self.stdout.write(f"Students created: {summary['students_created']}")
        self.stdout.write(f"Students skipped: {summary['students_skipped']}")
        self.stdout.write(f"Students enrolled to active session classes: {summary['students_enrolled']}")
        self.stdout.write(f"Staff created: {summary['staff_created']}")
        self.stdout.write(f"Staff skipped: {summary['staff_skipped']}")
        self.stdout.write(f"Teaching assignments created: {summary['staff_assignments']}")
        warnings = summary["warnings"]
        if warnings:
            self.stdout.write(self.style.WARNING(f"Warnings ({len(warnings)}):"))
            for warning in warnings[:60]:
                self.stdout.write(self.style.WARNING(f"- {warning}"))
            if len(warnings) > 60:
                self.stdout.write(self.style.WARNING(f"- ... {len(warnings) - 60} more warning(s) not shown."))

    def _import_students(self, *, rows, role_student, current_session, class_resolver, summary):
        for row in rows:
            existing_user = _find_existing_student(row)
            if existing_user is not None:
                summary["students_skipped"] += 1
                continue

            last_name, first_name, middle_name = _split_student_name(row.full_name)
            student_number = row.admission_no or _generate_student_number()
            username = _generate_student_username(student_number)
            password = generate_temporary_password(student_number)
            user = User.objects.create_user(
                username=username,
                password=password,
                first_name=first_name,
                last_name=last_name,
                primary_role=role_student,
                must_change_password=False,
                password_changed_count=0,
            )
            StudentProfile.objects.create(
                user=user,
                student_number=student_number,
                middle_name=middle_name,
                lifecycle_note="Imported from SCHOOL register for urgent onboarding.",
            )
            summary["students_created"] += 1

            if current_session is None:
                summary["warnings"].append(
                    f"Student {row.full_name}: current session is not set, so class enrollment was skipped."
                )
            else:
                academic_class = class_resolver.resolve_student_class(row.class_label)
                if academic_class is None:
                    summary["warnings"].append(
                        f"Student {row.full_name}: class '{row.class_label}' was not found, so enrollment was skipped."
                    )
                else:
                    StudentClassEnrollment.objects.update_or_create(
                        student=user,
                        session=current_session,
                        defaults={"academic_class": academic_class, "is_active": True},
                    )
                    summary["students_enrolled"] += 1

            try:
                queue_student_registration_sync(user=user, raw_password=password)
            except (OperationalError, ProgrammingError, ValidationError):
                pass

    def _import_staff(
        self,
        *,
        rows,
        role_subject_teacher,
        current_session,
        current_term,
        class_resolver,
        subject_resolver,
        summary,
    ):
        for row in rows:
            existing_user = _find_existing_staff(row.full_name)
            if existing_user is not None:
                summary["staff_skipped"] += 1
                continue

            last_name, first_name = _split_staff_name(row.full_name)
            staff_id = _generate_staff_id_for_role(ROLE_SUBJECT_TEACHER)
            username = _generate_username_from_name(first_name=first_name, last_name=last_name)
            password = generate_temporary_password(staff_id)
            user = User.objects.create_user(
                username=username,
                password=password,
                first_name=first_name,
                last_name=last_name,
                primary_role=role_subject_teacher,
                must_change_password=False,
                password_changed_count=0,
            )
            StaffProfile.objects.create(
                user=user,
                staff_id=staff_id,
                lifecycle_note="Imported from SCHOOL register for urgent onboarding.",
            )
            summary["staff_created"] += 1

            if current_session is None or current_term is None:
                summary["warnings"].append(
                    f"Staff {row.full_name}: current session/term is not set, so teaching assignments were skipped."
                )
                continue

            for assignment in row.assignments:
                subject = subject_resolver.resolve(assignment.subject_label)
                if subject is None:
                    summary["warnings"].append(
                        f"Staff {row.full_name}: subject '{assignment.subject_label}' was not found."
                    )
                    continue

                for class_level in assignment.class_levels:
                    academic_class = class_resolver.resolve_level_class(class_level)
                    if academic_class is None:
                        summary["warnings"].append(
                            f"Staff {row.full_name}: class level '{class_level}' was not found."
                        )
                        continue
                    if not ClassSubject.objects.filter(
                        academic_class=academic_class,
                        subject=subject,
                        is_active=True,
                    ).exists():
                        summary["warnings"].append(
                            f"Staff {row.full_name}: subject '{subject.name}' is not mapped to class '{academic_class.code}'."
                        )
                        continue

                    existing_assignment = TeacherSubjectAssignment.objects.filter(
                        subject=subject,
                        academic_class=academic_class,
                        session=current_session,
                        term=current_term,
                        is_active=True,
                    ).first()
                    if existing_assignment and existing_assignment.teacher_id != user.id:
                        summary["warnings"].append(
                            f"Staff {row.full_name}: {subject.name} for {academic_class.code} already belongs to another teacher."
                        )
                        continue

                    TeacherSubjectAssignment.objects.update_or_create(
                        teacher=user,
                        subject=subject,
                        academic_class=academic_class,
                        session=current_session,
                        term=current_term,
                        defaults={"is_active": True},
                    )
                    summary["staff_assignments"] += 1


def _resolve_source_dir(raw_path: str):
    candidate = Path(raw_path).expanduser()
    if candidate.exists():
        return candidate
    parent = candidate.parent if candidate.parent != Path("") else Path.cwd()
    if parent.exists():
        for row in parent.iterdir():
            if row.is_dir() and row.name.lower() == candidate.name.lower():
                return row
    raise CommandError(f"Source directory '{raw_path}' was not found.")


def _parse_student_rows(path: Path):
    if not path.exists():
        raise CommandError(f"Student register file not found: {path}")

    rows = []
    current_class = ""
    text = path.read_text(encoding="utf-8", errors="replace")
    for index, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        upper = line.upper()
        if "MASTER STUDENT REGISTER" in upper or upper.startswith("S/N") or "ADMISSION" in upper and "CLASS" in upper:
            continue
        if "IF ADMISSION NUMBER IS MISSING" in upper:
            continue

        match = STUDENT_ROW_RE.match(line)
        if match:
            _, full_name, admission_no, class_label = match.groups()
            rows.append(
                StudentImportRow(
                    line_number=index,
                    full_name=_collapse_spaces(full_name),
                    admission_no=_normalized_admission_no(admission_no),
                    class_label=_collapse_spaces(class_label or current_class),
                )
            )
            continue

        if not line[:1].isdigit():
            current_class = _collapse_spaces(line)
    return rows


def _parse_staff_rows(source_dir: Path):
    docx_path = source_dir / "SUBJECT TEACHERS.docx"
    if not docx_path.exists():
        raise CommandError(f"Staff register file not found: {docx_path}")

    document = Document(docx_path)
    rows = []
    for table in document.tables:
        for row_number, row in enumerate(table.rows[1:], start=1):
            cells = [_collapse_spaces(cell.text) for cell in row.cells]
            if len(cells) < 4 or not cells[1]:
                continue
            subject_lines = [piece for piece in _split_multiline_cells(cells[2]) if piece]
            class_lines = [piece for piece in _split_multiline_cells(cells[3]) if piece]
            assignments = []
            if len(subject_lines) == 1:
                merged_classes = _extract_class_levels(" ".join(class_lines))
                assignments.append(StaffAssignmentSpec(subject_label=subject_lines[0], class_levels=tuple(merged_classes)))
            else:
                if not class_lines:
                    class_lines = [""] * len(subject_lines)
                if len(class_lines) == 1 and len(subject_lines) > 1:
                    class_lines = class_lines * len(subject_lines)
                fallback_class_line = class_lines[-1] if class_lines else ""
                for index, subject_label in enumerate(subject_lines):
                    class_line = class_lines[index] if index < len(class_lines) else fallback_class_line
                    assignments.append(
                        StaffAssignmentSpec(
                            subject_label=subject_label,
                            class_levels=tuple(_extract_class_levels(class_line)),
                        )
                    )
            rows.append(
                StaffImportRow(
                    row_number=row_number,
                    full_name=cells[1],
                    assignments=tuple(assignments),
                )
            )
    return rows


def _split_multiline_cells(value: str):
    return [_collapse_spaces(piece) for piece in value.splitlines() if _collapse_spaces(piece)]


def _extract_class_levels(raw_value: str):
    compact = _normalize_class_token(raw_value)
    levels = []
    for prefix, digits_blob in CLASS_LEVEL_RE.findall(compact):
        for digit in digits_blob.split(","):
            token = f"{prefix}{digit}"
            if token not in levels:
                levels.append(token)
    return levels


def _find_existing_student(row: StudentImportRow):
    if row.admission_no:
        profile = StudentProfile.objects.select_related("user").filter(student_number__iexact=row.admission_no).first()
        if profile:
            return profile.user
    last_name, first_name, middle_name = _split_student_name(row.full_name)
    query = User.objects.filter(primary_role__code=ROLE_STUDENT, last_name__iexact=last_name, first_name__iexact=first_name)
    if middle_name:
        query = query.filter(student_profile__middle_name__iexact=middle_name)
    return query.first()


def _find_existing_staff(full_name: str):
    last_name, first_name = _split_staff_name(full_name)
    return User.objects.filter(staff_profile__isnull=False, last_name__iexact=last_name, first_name__iexact=first_name).first()


def _split_student_name(full_name: str):
    tokens = [token for token in NAME_SPLIT_RE.split(_collapse_spaces(full_name)) if token]
    if not tokens:
        return "Student", "Unknown", ""
    if len(tokens) == 1:
        return tokens[0], tokens[0], ""
    last_name = tokens[0]
    first_name = tokens[1]
    middle_name = " ".join(tokens[2:])
    return last_name, first_name, middle_name


def _split_staff_name(full_name: str):
    tokens = [token for token in NAME_SPLIT_RE.split(_collapse_spaces(full_name)) if token]
    if not tokens:
        return "Staff", "Unknown"
    if len(tokens) == 1:
        return tokens[0], tokens[0]
    last_name = tokens[0]
    first_name = " ".join(tokens[1:])
    return last_name, first_name


def _normalized_admission_no(value: str):
    cleaned = _collapse_spaces(value).upper()
    if cleaned in {"", "NIL", "NONE", "-"}:
        return ""
    return cleaned


def _collapse_spaces(value: str):
    return " ".join(str(value or "").split())


def _normalize_class_token(value: str):
    normalized = _collapse_spaces(value).upper()
    normalized = normalized.replace("JSS", "JS").replace("SSS", "SS")
    return re.sub(r"[^A-Z0-9]+", "", normalized)


def _normalize_subject_token(value: str):
    normalized = _collapse_spaces(value).upper()
    normalized = normalized.replace("&", " AND ")
    normalized = normalized.replace("C C.A", "CCA")
    normalized = normalized.replace("C C A", "CCA")
    normalized = normalized.replace("ANDD", "AND")
    normalized = normalized.replace("SOCILA", "SOCIAL")
    return re.sub(r"[^A-Z0-9]+", "", normalized)
