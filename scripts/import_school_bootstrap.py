import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE", "core.settings.local"))
django.setup()

from django.conf import settings
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from apps.accounts.constants import ROLE_DEAN, ROLE_FORM_TEACHER, ROLE_STUDENT, ROLE_SUBJECT_TEACHER
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
    AcademicSession,
    ClassSubject,
    FormTeacherAssignment,
    GradeScale,
    StudentClassEnrollment,
    StudentSubjectEnrollment,
    Subject,
    SubjectCategory,
    TeacherSubjectAssignment,
    Term,
    TermName,
)
from apps.setup_wizard.models import RuntimeFeatureFlags, SetupStateCode, SystemSetupState

LEVELS = ("JS1", "JS2", "JS3", "SS1", "SS2", "SS3")
ARMS = ("BLUE", "GOLD")
DEFAULT_SESSION = "2025/2026"
DEFAULT_TERM = TermName.SECOND
STUDENT_ROW_RE = re.compile(r"^\s*(\d+)\s*(?:\u2014|-)\s*(.*?)\s*(?:\u2014|-)\s*(.*?)\s*(?:\u2014|-)\s*(.*?)\s*$")
CLASS_LEVEL_RE = re.compile(r"(JS|SS)([123](?:,[123])*)")
JUNIOR_SELECTIVE_LANGUAGE_NAMES = {"HAUSA LANGUAGE", "IGBO LANGUAGE", "YORUBA LANGUAGE"}
JS1_COMPULSORY_LANGUAGE_NAMES = {"HAUSA LANGUAGE"}
SENIOR_DEFAULT_ENROLLMENT_LABELS = {
    "SS1": {
        "English Language",
        "Mathematics",
        "Digital Technology",
        "Citizenship and Heritage Studies",
        "Garment Making Theory",
        "Garment Making Practical",
        "Livestock",
    },
    "SS2": {
        "English Language",
        "Mathematics",
        "Civic Education",
    },
    "SS3": {
        "English Language",
        "Mathematics",
        "Civic Education",
    },
}

JUNIOR_CLASS_OFFERING_LABELS = {
    "JS1": {
        "Mathematics",
        "English Language",
        "English Literature",
        "Basic Science",
        "Basic Technology",
        "Business Studies",
        "CCA",
        "Christian Religious Studies",
        "Digital Technology",
        "French",
        "Hausa Language",
        "History",
        "Home Economics",
        "Igbo Language",
        "Yoruba Language",
        "Livestock",
        "Music",
        "Physical and Health Education",
        "Social and Citizenship Studies",
    },
    "JS2": {
        "Mathematics",
        "English Language",
        "English Literature",
        "Basic Science",
        "Basic Technology",
        "Business Studies",
        "CCA",
        "Christian Religious Studies",
        "Computer Science",
        "French",
        "Hausa Language",
        "History",
        "Fashion",
        "Igbo Language",
        "Yoruba Language",
        "Agricultural Science",
        "Music",
        "Physical and Health Education",
        "Social and Citizenship Studies",
    },
    "JS3": {
        "Mathematics",
        "English Language",
        "English Literature",
        "Basic Science",
        "Basic Technology",
        "Business Studies",
        "CCA",
        "Christian Religious Studies",
        "Computer Science",
        "French",
        "Hausa Language",
        "History",
        "Fashion",
        "Igbo Language",
        "Yoruba Language",
        "Agricultural Science",
        "Music",
        "Physical and Health Education",
        "Social and Citizenship Studies",
    },
}

DEFAULT_PORTAL_ACCOUNTS = (
    ("VP", ("vp@ndgakuje.org", "NDGAK/VP"), "admin/vp"),
    ("Principal", ("principal@ndgakuje.org", "NDGAK/PRINCIPAL"), "admin"),
    ("Bursar", ("bursar@ndgakuje.org", "NDGAK/BURSAR"), "bursar1804"),
)

SUBJECT_ALIASES = {
    "BASICTECH": "BASIC TECHNOLOGY",
    "BASICTECHNOLOGY": "BASIC TECHNOLOGY",
    "CHRISTAINRELIGIOUSSTUDIES": "CHRISTIAN RELIGIOUS STUDIES",
    "CRS": "CHRISTIAN RELIGIOUS STUDIES",
    "DIGITALTECHNOLOGY": "DIGITAL TECHNOLOGY",
    "ENGLISHSTUDIES": "ENGLISH LANGUAGE",
    "FOODNUTRITION": "FOOD AND NUTRITION",
    "FURTHERMATHS": "FURTHER MATHEMATICS",
    "GARMENTMAKINGPRACTICAL": "GARMENT MAKING PRACTICAL",
    "GARMENTMAKINGTHEORY": "GARMENT MAKING THEORY",
    "HAUSALANGUAGE": "HAUSA LANGUAGE",
    "IGBOLANGUAGE": "IGBO LANGUAGE",
    "PHE": "PHYSICAL AND HEALTH EDUCATION",
    "SOCIALANDCITIZENSHIPSTUDIES": "SOCIAL AND CITIZENSHIP STUDIES",
    "SOCIALANDDCITIZENSHIPSTUDIES": "SOCIAL AND CITIZENSHIP STUDIES",
    "YORUBALANGUAGE": "YORUBA LANGUAGE",
}

SUBJECT_DEFINITIONS = {
    "BIOLOGY": ("Biology", "BIO"),
    "FISHERY": ("Fishery", "FSH"),
    "MATHEMATICS": ("Mathematics", "MTH"),
    "FURTHER MATHEMATICS": ("Further Mathematics", "FTM"),
    "BASIC SCIENCE": ("Basic Science", "BSC"),
    "GEOGRAPHY": ("Geography", "GEO"),
    "VISUAL ART": ("Visual Art", "VAT"),
    "BASIC TECHNOLOGY": ("Basic Technology", "BTE"),
    "CCA": ("CCA", "CCA"),
    "CHEMISTRY": ("Chemistry", "CHM"),
    "PHYSICS": ("Physics", "PHY"),
    "TECHNICAL DRAWING": ("Technical Drawing", "TDR"),
    "FRENCH": ("French", "FRE"),
    "MUSIC": ("Music", "MUS"),
    "GOVERNMENT": ("Government", "GOV"),
    "FASHION": ("Fashion", "FAS"),
    "HOME ECONOMICS": ("Home Economics", "HEC"),
    "GARMENT MAKING THEORY": ("Garment Making Theory", "GMT"),
    "PHYSICAL AND HEALTH EDUCATION": ("Physical and Health Education", "PHE"),
    "GARMENT MAKING PRACTICAL": ("Garment Making Practical", "GMP"),
    "CHRISTIAN RELIGIOUS STUDIES": ("Christian Religious Studies", "CRS"),
    "BUSINESS STUDIES": ("Business Studies", "BST"),
    "COMMERCE": ("Commerce", "COM"),
    "IGBO LANGUAGE": ("Igbo Language", "IGB"),
    "CIVIC EDUCATION": ("Civic Education", "CVC"),
    "HAUSA LANGUAGE": ("Hausa Language", "HAU"),
    "SOCIAL AND CITIZENSHIP STUDIES": ("Social and Citizenship Studies", "SCS"),
    "SOCIAL STUDIES": ("Social Studies", "SST"),
    "LIVESTOCK": ("Livestock", "LIV"),
    "AGRICULTURAL SCIENCE": ("Agricultural Science", "AGR"),
    "DIGITAL TECHNOLOGY": ("Digital Technology", "DIT"),
    "COMPUTER STUDIES": ("Computer Studies", "CPS"),
    "DATA PROCESSING": ("Data Processing", "DAP"),
    "COMPUTER SCIENCE": ("Computer Science", "CSC"),
    "ENGLISH LANGUAGE": ("English Language", "ENG"),
    "ENGLISH LITERATURE": ("English Literature", "ELT"),
    "FOOD AND NUTRITION": ("Food and Nutrition", "FDN"),
    "CATERING CRAFT": ("Catering Craft", "CTC"),
    "HOME MANAGEMENT": ("Home Management", "HMG"),
    "LITERATURE": ("Literature", "LIT"),
    "ECONOMICS": ("Economics", "ECO"),
    "ACCOUNTING": ("Accounting", "ACC"),
    "CITIZENSHIP AND HERITAGE STUDIES": ("Citizenship and Heritage Studies", "CHS"),
    "HISTORY": ("History", "HIS"),
    "YORUBA LANGUAGE": ("Yoruba Language", "YOR"),
}


def collapse(value):
    return " ".join(str(value or "").split())


def normalize_class(value):
    cleaned = collapse(value).upper().replace("JSS", "JS").replace("SSS", "SS")
    return re.sub(r"[^A-Z0-9]+", "", cleaned)


def normalize_subject(value):
    cleaned = collapse(value).upper().replace("&", " AND ")
    cleaned = re.sub(r"[^A-Z0-9]+", "", cleaned)
    alias = SUBJECT_ALIASES.get(cleaned)
    return re.sub(r"[^A-Z0-9]+", "", alias) if alias else cleaned

def canonical_subject(label):
    token = normalize_subject(label)
    for raw_name, payload in SUBJECT_DEFINITIONS.items():
        if normalize_subject(raw_name) == token:
            return payload
    pretty = collapse(label).replace("&", "and").title()
    code = re.sub(r"[^A-Z0-9]+", "", pretty.upper())[:6] or "SUBJ"
    return pretty, code


def parse_student_rows(path):
    rows = []
    current_class = ""
    text = path.read_text(encoding="utf-8", errors="replace")
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        upper = line.upper()
        if "MASTER STUDENT REGISTER" in upper or upper.startswith("S/N"):
            continue
        if "IF ADMISSION NUMBER IS MISSING" in upper:
            continue
        parts = [collapse(part) for part in re.split(r"\s+[—]+\s+", line) if collapse(part)]
        if len(parts) >= 4 and parts[0].isdigit():
            _, full_name, admission_no, class_label = parts[:4]
            admission_no = collapse(admission_no).upper().replace("NDGAL/", "NDGAK/")
            if admission_no in {"", "NIL", "NONE", "-"}:
                admission_no = ""
            rows.append(
                {
                    "line_number": line_number,
                    "full_name": collapse(full_name),
                    "admission_no": admission_no,
                    "class_label": collapse(class_label or current_class),
                }
            )
            continue
        match = STUDENT_ROW_RE.match(line)
        if match:
            _, full_name, admission_no, class_label = match.groups()
            admission_no = collapse(admission_no).upper().replace("NDGAL/", "NDGAK/")
            if admission_no in {"", "NIL", "NONE", "-"}:
                admission_no = ""
            rows.append(
                {
                    "line_number": line_number,
                    "full_name": collapse(full_name),
                    "admission_no": admission_no,
                    "class_label": collapse(class_label or current_class),
                }
            )
            continue
        if not line[:1].isdigit():
            current_class = collapse(line)
    return rows


def parse_teacher_rows(path):
    rows = []
    current = None
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw_line.strip()
        upper = stripped.upper()
        if not stripped:
            continue
        if upper.startswith(("I HAVE CLEANED", "JS =", "SS =", "EACH SUBJECT", "HERE IS", "NOW THIS FORMAT", "SCHOOL SUBJECT", "TIMETABLE", "TEACHER WORKLOAD")):
            continue
        if upper.startswith("NO\tTEACHER"):
            continue
        parts = [collapse(part) for part in raw_line.split("\t")]
        if parts and parts[0].isdigit():
            if current:
                rows.append(current)
            current = {"full_name": parts[1], "assignments": []}
            subject_label = parts[2] if len(parts) > 2 else ""
            class_blob = parts[3] if len(parts) > 3 else ""
            if subject_label:
                current["assignments"].append({"subject_label": subject_label, "class_levels": extract_class_levels(class_blob)})
            continue
        if current is None:
            continue
        subject_label = parts[2] if len(parts) > 2 else ""
        class_blob = parts[3] if len(parts) > 3 else ""
        if subject_label:
            current["assignments"].append({"subject_label": subject_label, "class_levels": extract_class_levels(class_blob)})
    if current:
        rows.append(current)
    return rows


def extract_class_levels(raw_value):
    compact = normalize_class(raw_value)
    levels = []
    for prefix, digits_blob in CLASS_LEVEL_RE.findall(compact):
        for digit in digits_blob.split(","):
            code = f"{prefix}{digit}"
            if code not in levels:
                levels.append(code)
    return levels


def split_student_name(full_name):
    tokens = [token for token in re.split(r"\s+", collapse(full_name)) if token]
    if len(tokens) < 2:
        return tokens[0] if tokens else "Student", tokens[0] if tokens else "Unknown", ""
    return tokens[0], tokens[1], " ".join(tokens[2:])


def split_staff_name(full_name):
    tokens = [token for token in re.split(r"\s+", collapse(full_name)) if token]
    if len(tokens) < 2:
        return tokens[0] if tokens else "Staff", tokens[0] if tokens else "Unknown"
    return tokens[0], " ".join(tokens[1:])


def ensure_setup(session_name, term_name):
    actor = User.objects.get(username="admin@ndgakuje.org")
    session, _ = AcademicSession.objects.get_or_create(name=session_name)
    term, _ = Term.objects.get_or_create(session=session, name=term_name)
    GradeScale.ensure_default_scale()
    state = SystemSetupState.get_solo()
    state.state = SetupStateCode.IT_READY
    state.current_session = session
    state.current_term = term
    state.last_updated_by = actor
    state.save(update_fields=["state", "current_session", "current_term", "last_updated_by", "updated_at"])
    runtime_flags = RuntimeFeatureFlags.get_solo()
    runtime_flags.cbt_enabled = bool(settings.FEATURE_FLAGS.get("CBT_ENABLED", False))
    runtime_flags.election_enabled = bool(settings.FEATURE_FLAGS.get("ELECTION_ENABLED", False))
    runtime_flags.offline_mode_enabled = bool(settings.FEATURE_FLAGS.get("OFFLINE_MODE_ENABLED", True))
    runtime_flags.lockdown_enabled = bool(settings.FEATURE_FLAGS.get("LOCKDOWN_ENABLED", True))
    runtime_flags.last_updated_by = actor
    runtime_flags.save(
        update_fields=[
            "cbt_enabled",
            "election_enabled",
            "offline_mode_enabled",
            "lockdown_enabled",
            "last_updated_by",
            "updated_at",
        ]
    )
    call_command("ensure_default_portal_accounts")
    return actor, session, term


def ensure_classes():
    base_classes = {}
    arm_classes = {}
    for level in LEVELS:
        base, _ = AcademicClass.objects.get_or_create(code=level, defaults={"display_name": level, "is_active": True})
        base.display_name = level
        base.is_active = True
        base.save(update_fields=["display_name", "is_active", "updated_at"])
        base_classes[level] = base
        for arm in ARMS:
            code = f"{level} {arm}"
            arm_class, _ = AcademicClass.objects.get_or_create(
                code=code,
                defaults={"display_name": code, "base_class": base, "arm_name": arm, "is_active": True},
            )
            arm_class.display_name = code
            arm_class.base_class = base
            arm_class.arm_name = arm
            arm_class.is_active = True
            arm_class.save()
            arm_classes[normalize_class(code)] = arm_class
    return base_classes, arm_classes


def ensure_subjects_and_mappings(teacher_rows, base_classes):
    subjects = {}
    offerings = defaultdict(set)

    def ensure_subject_record(label):
        name, code = canonical_subject(label)
        subject = Subject.objects.filter(code=code).first() or Subject.objects.filter(name__iexact=name).first()
        if subject is None:
            subject = Subject.objects.create(name=name, code=code, category=SubjectCategory.GENERAL, is_active=True)
        else:
            updates = []
            if subject.name != name:
                subject.name = name
                updates.append("name")
            if not subject.is_active:
                subject.is_active = True
                updates.append("is_active")
            if updates:
                updates.append("updated_at")
                subject.save(update_fields=updates)
        subjects[normalize_subject(name)] = subject
        return subject

    for row in teacher_rows:
        for assignment in row["assignments"]:
            subject = ensure_subject_record(assignment["subject_label"])
            for level in assignment["class_levels"]:
                offerings[level].add(subject.id)

    for level, labels in JUNIOR_CLASS_OFFERING_LABELS.items():
        offerings[level] = {ensure_subject_record(label).id for label in labels}

    for level, subject_ids in offerings.items():
        academic_class = base_classes[level]
        if level in JUNIOR_CLASS_OFFERING_LABELS:
            ClassSubject.objects.filter(academic_class=academic_class).exclude(subject_id__in=subject_ids).update(is_active=False)
        for subject_id in subject_ids:
            row, created = ClassSubject.objects.get_or_create(
                academic_class=academic_class,
                subject_id=subject_id,
                defaults={"is_active": True},
            )
            if not created and not row.is_active:
                row.is_active = True
                row.save(update_fields=["is_active", "updated_at"])
    return subjects

def _sync_student_subject_enrollment(user, session, allowed_subject_ids):
    allowed_subject_ids = set(allowed_subject_ids)
    StudentSubjectEnrollment.objects.filter(student=user, session=session).exclude(subject_id__in=allowed_subject_ids).delete()
    created_total = 0
    for subject_id in sorted(allowed_subject_ids):
        _, created = StudentSubjectEnrollment.objects.get_or_create(
            student=user,
            subject_id=subject_id,
            session=session,
            defaults={"is_active": True},
        )
        if created:
            created_total += 1
    return created_total


def enroll_default_subjects(user, session, academic_class):
    base_class = academic_class.base_class or academic_class
    class_subject_rows = list(
        ClassSubject.objects.filter(academic_class=base_class, is_active=True).select_related("subject")
    )
    if base_class.code in {"JS1", "JS2", "JS3"}:
        if base_class.code == "JS1":
            disallowed_language_names = JUNIOR_SELECTIVE_LANGUAGE_NAMES - JS1_COMPULSORY_LANGUAGE_NAMES
        else:
            disallowed_language_names = set(JUNIOR_SELECTIVE_LANGUAGE_NAMES)
        allowed_subject_ids = {
            row.subject_id
            for row in class_subject_rows
            if row.subject.name.upper() not in disallowed_language_names
        }
        return _sync_student_subject_enrollment(user, session, allowed_subject_ids)
    if base_class.code in SENIOR_DEFAULT_ENROLLMENT_LABELS:
        allowed_labels = {label.upper() for label in SENIOR_DEFAULT_ENROLLMENT_LABELS[base_class.code]}
        allowed_subject_ids = {
            row.subject_id
            for row in class_subject_rows
            if row.subject.name.upper() in allowed_labels
        }
        return _sync_student_subject_enrollment(user, session, allowed_subject_ids)
    return 0


@transaction.atomic
def run_import(source_dir, session_name, term_name, credentials_output):
    source_dir = Path(source_dir)
    student_rows = parse_student_rows(source_dir / "student.txt")
    teacher_rows = parse_teacher_rows(source_dir / "notre dame subject teachers.txt")
    actor, session, term = ensure_setup(session_name, term_name)
    base_classes, arm_classes = ensure_classes()
    ensure_subjects_and_mappings(teacher_rows, base_classes)

    role_student = Role.objects.get(code=ROLE_STUDENT)
    role_teacher = Role.objects.get(code=ROLE_SUBJECT_TEACHER)

    staff_credentials = []
    for row in teacher_rows:
        last_name, first_name = split_staff_name(row["full_name"])
        user = User.objects.filter(staff_profile__isnull=False, last_name__iexact=last_name, first_name__iexact=first_name).first()
        if user is None:
            staff_id = _generate_staff_id_for_role(ROLE_SUBJECT_TEACHER)
            password = generate_temporary_password(staff_id)
            user = User.objects.create_user(
                username=_generate_username_from_name(first_name=first_name, last_name=last_name),
                password=password,
                first_name=first_name,
                last_name=last_name,
                primary_role=role_teacher,
                must_change_password=False,
                password_changed_count=0,
            )
            StaffProfile.objects.create(user=user, staff_id=staff_id, lifecycle_note="Imported from SCHOOL register.")
        else:
            password = generate_temporary_password(user.staff_profile.staff_id)
        for assignment in row["assignments"]:
            name, code = canonical_subject(assignment["subject_label"])
            subject = Subject.objects.get(code=code)
            for level in assignment["class_levels"]:
                TeacherSubjectAssignment.objects.update_or_create(
                    teacher=user,
                    subject=subject,
                    academic_class=base_classes[level],
                    session=session,
                    term=term,
                    defaults={"is_active": True},
                )
        staff_credentials.append(
            {
                "name": collapse(f"{user.last_name} {user.first_name}"),
                "login_id": user.staff_profile.staff_id,
                "username": user.username,
                "password": password,
                "summary": "; ".join(
                    f"{assignment['subject_label']} ({', '.join(assignment['class_levels'])})" for assignment in row["assignments"]
                ),
            }
        )

    student_credentials = []
    for row in student_rows:
        last_name, first_name, middle_name = split_student_name(row["full_name"])
        user = None
        if row["admission_no"]:
            profile = StudentProfile.objects.filter(student_number__iexact=row["admission_no"]).select_related("user").first()
            user = profile.user if profile else None
        if user is None:
            user = User.objects.filter(primary_role=role_student, last_name__iexact=last_name, first_name__iexact=first_name).first()
        if user is None:
            student_number = row["admission_no"] or _generate_student_number()
            password = generate_temporary_password(student_number)
            user = User.objects.create_user(
                username=_generate_student_username(student_number),
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
                lifecycle_note="Imported from SCHOOL register.",
            )
        else:
            profile = user.student_profile
            if row["admission_no"] and profile.student_number != row["admission_no"]:
                profile.student_number = row["admission_no"]
                profile.save(update_fields=["student_number", "updated_at"])
            password = generate_temporary_password(user.student_profile.student_number)
        academic_class = arm_classes[normalize_class(row["class_label"])]
        StudentClassEnrollment.objects.update_or_create(
            student=user,
            session=session,
            defaults={"academic_class": academic_class, "is_active": True},
        )
        enroll_default_subjects(user, session, academic_class)
        student_credentials.append(
            {
                "name": collapse(f"{user.last_name} {user.first_name} {user.student_profile.middle_name}"),
                "login_id": user.student_profile.student_number,
                "username": user.username,
                "password": password,
                "class_label": academic_class.display_name,
            }
        )

    form_teacher_role = Role.objects.get(code=ROLE_FORM_TEACHER)
    dean_role = Role.objects.get(code=ROLE_DEAN)
    vp_user = User.objects.filter(username='vp@ndgakuje.org').first()
    if vp_user:
        if vp_user.primary_role_id != form_teacher_role.id and not vp_user.secondary_roles.filter(id=form_teacher_role.id).exists():
            vp_user.secondary_roles.add(form_teacher_role)
        FormTeacherAssignment.objects.update_or_create(
            teacher=vp_user,
            academic_class=base_classes['JS1'],
            session=session,
            defaults={'is_active': True},
        )

    gabriel_user = User.objects.filter(username='emmanuel@ndgakuje.org').first()
    if gabriel_user and gabriel_user.primary_role_id != dean_role.id and not gabriel_user.secondary_roles.filter(id=dean_role.id).exists():
        gabriel_user.secondary_roles.add(dean_role)

    output_path = Path(credentials_output)
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["NDGA GENERATED CREDENTIALS", f"Generated: {timezone.localtime():%Y-%m-%d %H:%M:%S %Z}", "", "Leadership Default Accounts"]
    for label, login_ids, password in DEFAULT_PORTAL_ACCOUNTS:
        lines.append(f"- {label}: login ids = {' / '.join(login_ids)} | password = {password}")
    lines.extend(["", "Staff Accounts"])
    for index, row in enumerate(staff_credentials, start=1):
        lines.append(f"{index}. {row['name']} | staff id: {row['login_id']} | username: {row['username']} | password: {row['password']} | subjects: {row['summary']}")
    lines.extend(["", "Student Accounts"])
    for index, row in enumerate(student_credentials, start=1):
        lines.append(f"{index}. {row['name']} | admission no: {row['login_id']} | username: {row['username']} | password: {row['password']} | class: {row['class_label']}")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Session: {session.name} | Term: {term.name}")
    print(f"Classes: {AcademicClass.objects.count()} | Subjects: {Subject.objects.count()} | Mappings: {ClassSubject.objects.count()}")
    print(f"Teachers: {len(staff_credentials)} | Students: {len(student_credentials)}")
    print(f"Credentials file: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bootstrap NDGA school classes, staff, students, and credentials from the SCHOOL folder.")
    parser.add_argument("--source-dir", default="SCHOOL")
    parser.add_argument("--session", default=DEFAULT_SESSION)
    parser.add_argument("--term", default=DEFAULT_TERM)
    parser.add_argument("--credentials-output", default="SCHOOL/ndga_generated_credentials.txt")
    args = parser.parse_args()
    run_import(
        source_dir=args.source_dir,
        session_name=args.session,
        term_name=args.term,
        credentials_output=args.credentials_output,
    )
