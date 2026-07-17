import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE", "core.settings.local"))

import django

django.setup()

from django.core.files import File
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.academics.models import AcademicSession, TeacherSubjectAssignment, Term
from apps.cbt.models import (
    CBTDocumentStatus,
    CBTExamStatus,
    CBTExamType,
    CBTQuestionDifficulty,
    CBTQuestionType,
    CBTWritebackTarget,
    CorrectAnswer,
    Exam,
    ExamDocumentImport,
    ExamQuestion,
    Option,
    Question,
    QuestionBank,
)
from apps.cbt.services import _apply_exam_row_marks, ensure_default_blueprint
from apps.cbt.services import extract_text_from_document, parse_question_document
from apps.cbt.workflow import dean_approve_exam, it_activate_exam, submit_exam_to_dean
from scripts.import_thursday_ca import (
    choose_parser_rows,
    class_code_from_value,
    collapse,
    display_path,
    instruction_text_for_exam,
    normalize,
    safe_text,
)


DEFAULT_SOURCE_DIR = str(ROOT / "SCHOOL FOLDER" / "First CA")
DEFAULT_SESSION = "2025/2026"
DEFAULT_TERM = "THIRD"
IMPORT_TAG = "THIRD_TERM_FIRST_CA_20260518"

TIMETABLE = [
    # Junior timetable
    ("JS1", "MTH", "2026-05-18", "7:30-8:10"),
    ("JS1", "FAS", "2026-05-18", "8:50-9:30"),
    ("JS1", "SCS", "2026-05-18", "9:30-10:10"),
    ("JS1", "LIV", "2026-05-18", "11:20-12:00"),
    ("JS1", "HAU", "2026-05-18", "12:10-12:50"),
    ("JS1", "YOR", "2026-05-18", "1:30-2:10"),
    ("JS1", "IGB", "2026-05-18", "1:30-2:10"),
    ("JS2", "AGR", "2026-05-18", "7:30-8:10"),
    ("JS2", "HEC", "2026-05-18", "8:50-9:30"),
    ("JS2", "CVC", "2026-05-18", "9:30-10:10"),
    ("JS2", "CSC", "2026-05-18", "11:20-12:00"),
    ("JS2", "BSC", "2026-05-18", "12:10-12:50"),
    ("JS2", "CCA", "2026-05-18", "1:30-2:10"),
    ("JS1", "INS", "2026-05-19", "7:30-8:10"),
    ("JS1", "MUS", "2026-05-19", "8:50-9:30"),
    ("JS1", "HIS", "2026-05-19", "10:10-10:50"),
    ("JS1", "ENG", "2026-05-19", "11:20-12:00"),
    ("JS1", "FRE", "2026-05-19", "12:10-12:50"),
    ("JS1", "PHE", "2026-05-19", "1:30-2:10"),
    ("JS2", "ENG", "2026-05-19", "7:30-8:10"),
    ("JS2", "MUS", "2026-05-19", "8:10-8:50"),
    ("JS2", "BST", "2026-05-19", "8:50-9:30"),
    ("JS2", "BTE", "2026-05-19", "11:20-12:00"),
    ("JS2", "HIS", "2026-05-19", "12:10-12:50"),
    ("JS2", "CRS", "2026-05-19", "1:30-2:10"),
    ("JS1", "DIT", "2026-05-20", "7:30-8:10"),
    ("JS1", "CRS", "2026-05-20", "9:30-10:10"),
    ("JS1", "BST", "2026-05-20", "11:20-12:00"),
    ("JS1", "CCA", "2026-05-20", "1:30-2:10"),
    ("JS2", "MTH", "2026-05-20", "7:30-8:10"),
    ("JS2", "SST", "2026-05-20", "8:50-9:30"),
    ("JS2", "YOR", "2026-05-20", "10:10-10:50"),
    ("JS2", "HAU", "2026-05-20", "10:10-10:50"),
    ("JS2", "IGB", "2026-05-20", "10:10-10:50"),
    ("JS2", "PHE", "2026-05-20", "11:20-12:00"),
    ("JS2", "FRE", "2026-05-20", "1:30-2:10"),
    # Senior timetable
    ("SS1", "PHY", "2026-05-18", "7:30-8:10"),
    ("SS1", "LIT", "2026-05-18", "7:30-8:10"),
    ("SS1", "ACC", "2026-05-18", "7:30-8:10"),
    ("SS1", "MTH", "2026-05-18", "9:30-10:10"),
    ("SS1", "ENG", "2026-05-18", "11:20-12:00"),
    ("SS1", "CHM", "2026-05-18", "12:10-12:50"),
    ("SS1", "GOV", "2026-05-18", "12:10-12:50"),
    ("SS1", "COM", "2026-05-18", "12:10-12:50"),
    ("SS1", "FDN", "2026-05-18", "12:50-1:30"),
    ("SS1", "HMG", "2026-05-18", "1:30-2:10"),
    ("SS1", "VAT", "2026-05-18", "1:30-2:10"),
    ("SS2", "ENG", "2026-05-18", "7:30-8:10"),
    ("SS2", "FSH", "2026-05-18", "8:50-9:30"),
    ("SS2", "DAP", "2026-05-18", "8:50-9:30"),
    ("SS2", "GMT", "2026-05-18", "11:20-12:00"),
    ("SS2", "PHY", "2026-05-18", "12:10-12:50"),
    ("SS2", "LIT", "2026-05-18", "12:10-12:50"),
    ("SS2", "ACC", "2026-05-18", "12:10-12:50"),
    ("SS2", "CPS", "2026-05-18", "1:30-2:10"),
    ("SS1", "DIT", "2026-05-19", "7:30-8:10"),
    ("SS1", "CRS", "2026-05-19", "9:30-10:10"),
    ("SS1", "GEO", "2026-05-19", "11:20-12:00"),
    ("SS1", "FRE", "2026-05-19", "11:20-12:00"),
    ("SS1", "TDR", "2026-05-19", "11:20-12:00"),
    ("SS1", "LIV", "2026-05-19", "12:50-1:30"),
    ("SS1", "ECO", "2026-05-19", "1:30-2:10"),
    ("SS2", "MTH", "2026-05-19", "7:30-8:10"),
    ("SS2", "AGR", "2026-05-19", "8:50-9:30"),
    ("SS2", "HMG", "2026-05-19", "8:50-9:30"),
    ("SS2", "VAT", "2026-05-19", "8:50-9:30"),
    ("SS2", "BIO", "2026-05-19", "11:20-12:00"),
    ("SS2", "FTM", "2026-05-19", "12:10-12:50"),
    ("SS2", "FDN", "2026-05-19", "1:30-2:10"),
    ("SS1", "FTM", "2026-05-20", "7:30-8:10"),
    ("SS1", "BIO", "2026-05-20", "8:50-9:30"),
    ("SS1", "GMT", "2026-05-20", "9:30-10:10"),
    ("SS1", "AGR", "2026-05-20", "11:20-12:00"),
    ("SS1", "CHS", "2026-05-20", "1:30-2:10"),
    ("SS2", "ECO", "2026-05-20", "7:30-8:10"),
    ("SS2", "CHM", "2026-05-20", "8:50-9:30"),
    ("SS2", "GOV", "2026-05-20", "8:50-9:30"),
    ("SS2", "COM", "2026-05-20", "8:50-9:30"),
    ("SS2", "CVC", "2026-05-20", "11:20-12:00"),
    ("SS2", "GEO", "2026-05-20", "12:50-1:30"),
    ("SS2", "FRE", "2026-05-20", "12:50-1:30"),
    ("SS2", "TDR", "2026-05-20", "12:50-1:30"),
    ("SS2", "CRS", "2026-05-20", "1:30-2:10"),
]

SUBJECT_ALIASES = {
    "ACC": ["FINACC", "FINANCIALACCOUNT", "ACCOUNTING", "ACCOUNT"],
    "AGR": ["AGRICULTURALSCIENCE", "AGRICSCIENCE", "AGRIC"],
    "BIO": ["BIOLOGY"],
    "BSC": ["BASICSCIENCE", "BSC"],
    "BST": ["BUSINESSSTUDIES"],
    "BTE": ["BASICTECHNOLOGY", "BASICTECH"],
    "CCA": ["CCA", "CCART", "CULTURALCREATIVEART", "CREATIVEART"],
    "CHM": ["CHEMISTRY", "CHEM"],
    "CHS": ["CITIZENSHIPHERITAGESTUDIES", "CITIZENSHIPANDHERITAGESTUDIES"],
    "COM": ["COMMERCE"],
    "CPS": ["COMPUTERSTUDIES", "CCP"],
    "CRS": ["CRS", "CHRISTIANRELIGIOUSSTUDIES"],
    "CSC": ["COMPUTERSCIENCE", "COMPUTERSTUDIES"],
    "CVC": ["CIVICEDUCATION", "CIVICEDUC", "CIVIC"],
    "DAP": ["DATAPROCESSING", "DP"],
    "DIT": ["DIGITALTECHNOLOGY"],
    "ECO": ["ECONOMICS", "ECONOMIC"],
    "ENG": ["ENGLISHSTUDIES", "ENGLISHLANGUAGE", "ENGLISH"],
    "FAS": ["FASHION", "GARMENTMAKING"],
    "FDN": ["FOODANDNUTRITION", "FOODNUT", "FOODNUTS"],
    "FRE": ["FRENCH"],
    "FSH": ["FISHERY", "FISHERIES"],
    "FTM": ["FURTHERMATHEMATICS", "FMATHS", "FURTHERMATH", "FMATH"],
    "GEO": ["GEOGRAPHY"],
    "GMT": ["GARMENTMAKING", "GARMENTMAKINGTHEORY"],
    "GOV": ["GOVERNMENT", "GOVT"],
    "HAU": ["HAUSA", "HAUSALANGUAGE"],
    "HEC": ["HOMEECONOMICS"],
    "HIS": ["HISTORY"],
    "HMG": ["HOMEMANAGEMENT", "HOMEMGT"],
    "IGB": ["IGBO", "IGBOLANGUAGE"],
    "INS": ["INTERMEDIATESCIENCE"],
    "LIT": ["LITERATURE"],
    "LIV": ["LIVESTOCK", "LIVESTOCKFARMING"],
    "MTH": ["MATHEMATICS", "MATHS", "MATH"],
    "MUS": ["MUSIC"],
    "PHE": ["PHE", "PHYSICALEDUCATION", "PHYSICALANDHEALTHEDUCATION"],
    "PHY": ["PHYSICS"],
    "SCS": ["SOCIALCITIZENSHIPSTUDIES", "SOCIALANDCITIZENSHIPSTUDIES", "SCS"],
    "SST": ["SOCIALSTUDIES", "SOS"],
    "TDR": ["TECHNICALDRAWING", "TECHDRAWING", "TD"],
    "VAT": ["VISUALART"],
    "YOR": ["YORUBA", "YORUBALANGUAGE"],
}

CLASS_SPECIFIC_SUBJECTS = {
    ("JS1", "GARMENTMAKING"): "FAS",
    ("JS1", "FASHIONDESIGNGARMENTMAKING"): "FAS",
    ("JS2", "COMPUTERSTUDIES"): "CSC",
    ("JS2", "COMPUTERSCIENCE"): "CSC",
    ("SS1", "CIVICEDUCATION"): "CHS",
    ("SS1", "CIVICEDUC"): "CHS",
    ("SS1", "CIVIC"): "CHS",
}

SUPPORTED_SUFFIXES = {"", ".txt", ".docx", ".pdf"}
CALCULATOR_SUBJECT_CODES = {
    "ACC",
    "CHM",
    "ECO",
    "FDN",
    "FSH",
    "FTM",
    "MTH",
    "PHY",
    "TDR",
}
BAD_SOURCE_PATTERNS = (
    "2NDCONTINUOUS",
    "SECONDCA",
    "2NDCA",
    "2NDCA",
    "2NDCA",
    "2ND C",
)


def parse_school_time(value):
    parsed = datetime.strptime(value, "%H:%M")
    hour = parsed.hour
    if hour < 7:
        hour += 12
    return parsed.replace(hour=hour).time()


def schedule_window(date_text, slot_label):
    start_text, end_text = slot_label.split("-", 1)
    day = datetime.strptime(date_text, "%Y-%m-%d").date()
    start = timezone.make_aware(datetime.combine(day, parse_school_time(start_text)))
    end = timezone.make_aware(datetime.combine(day, parse_school_time(end_text)))
    duration = max(int((end - start).total_seconds() // 60), 1)
    return start, end, duration


def class_code_from_path_text(value):
    cleaned = collapse(value).upper().replace("JSS", "JS").replace("SSS", "SS")
    cleaned = re.sub(r"\bJ\s*[.\-]?\s*S\s*[.\-]?\s*S\b", "JS", cleaned)
    cleaned = re.sub(r"\bJ\s*[.\-]?\s*S\b", "JS", cleaned)
    cleaned = re.sub(r"\bS\s*[.\-]?\s*S\s*[.\-]?\s*S\b", "SS", cleaned)
    cleaned = re.sub(r"\bS\s*[.\-]?\s*S\b", "SS", cleaned)
    compact = normalize(cleaned)
    match = re.search(r"(JS|SS)([12])", compact)
    if match:
        return f"{match.group(1)}{match.group(2)}"
    code = class_code_from_value(cleaned)
    return code if code in {"JS1", "JS2", "SS1", "SS2"} else ""


def class_from_path(path):
    stem = path.stem
    for value in (stem, path.parent.name, str(path)):
        code = class_code_from_path_text(value)
        if code:
            return code
    return ""


def is_bad_source(path):
    key = normalize(str(path))
    if "FIRST" in key or "1ST" in key:
        return False
    return any(normalize(pattern) in key for pattern in BAD_SOURCE_PATTERNS)


def subject_from_path(path, class_code, valid_codes):
    stem_text = normalize(path.stem)
    parent_text = normalize(path.parent.name)
    full_text = normalize(str(path))
    best_code = ""
    best_score = -1
    for alias_key, subject_code in CLASS_SPECIFIC_SUBJECTS.items():
        alias_class, alias = alias_key
        if alias_class == class_code and (alias in stem_text or alias in parent_text) and subject_code in valid_codes:
            return subject_code
    for subject_code, aliases in SUBJECT_ALIASES.items():
        if subject_code not in valid_codes:
            continue
        for alias in aliases:
            token = normalize(alias)
            if not token:
                continue
            score = -1
            if token in stem_text:
                score = 100 + len(token)
            elif token in parent_text:
                score = 30 + len(token)
            elif token in full_text:
                score = len(token)
            if score < 0:
                continue
            if "FIRST" in full_text or "1ST" in full_text:
                score += 2
            if path.suffix.lower() == ".txt":
                score += 1
            if score > best_score:
                best_code = subject_code
                best_score = score
    return best_code


def collect_candidates(source_dir, assignments_by_key):
    candidates = {}
    skipped = []
    for path in sorted(Path(source_dir).rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        if is_bad_source(path):
            skipped.append((display_path(path), "not-first-ca"))
            continue
        class_code = class_from_path(path)
        if not class_code:
            skipped.append((display_path(path), "class-not-detected"))
            continue
        valid_codes = {subject_code for (klass, subject_code) in assignments_by_key if klass == class_code}
        subject_code = subject_from_path(path, class_code, valid_codes)
        if not subject_code:
            skipped.append((display_path(path), f"subject-not-detected-{class_code}"))
            continue
        key = (class_code, subject_code)
        candidates.setdefault(key, []).append(path)
    return candidates, skipped


def source_priority(path):
    key = normalize(str(path))
    first_score = 8 if ("FIRST" in key or "1ST" in key) else 0
    suffix_score = {".txt": 4, ".docx": 3, ".pdf": 2}.get(path.suffix.lower(), 0)
    return first_score + suffix_score, -len(path.name)


def pick_source(paths):
    return sorted(paths, key=source_priority, reverse=True)[0]


def pick_best_source(paths):
    best = None
    best_score = None
    for path in sorted(paths, key=source_priority, reverse=True):
        try:
            info = direct_parser_info(path)
            rows, objective_count, theory_count = normalize_rows(
                info.get("parsed_rows") or [],
                info.get("extracted_text") or "",
            )
        except Exception:
            rows, objective_count, theory_count = [], 0, 0
        answered = sum(
            1
            for row in rows
            if (row.get("question_type") or "").upper() == "OBJECTIVE"
            and (row.get("correct_label") or "").strip()
        )
        score = (objective_count * 20) + (theory_count * 30) + answered + source_priority(path)[0]
        if objective_count <= 0:
            score -= 1000
        if theory_count <= 0:
            score -= 250
        if best is None or score > best_score:
            best = path
            best_score = score
    return best or pick_source(paths)


def title_for(assignment, slot_label):
    return f"{assignment.academic_class.code} {assignment.subject.name} Third Term First CA {slot_label}"


def delete_previous_tagged_imports(assignment, title, apply=False):
    matches = Exam.objects.filter(
        assignment=assignment,
        term=assignment.term,
        session=assignment.session,
        exam_type=CBTExamType.CA,
        title=title,
        description__contains=IMPORT_TAG,
    )
    count = matches.count()
    if apply and count:
        matches.delete()
    return count


ANSWER_LABEL_RE = re.compile(
    r"(?im)^\s*(?:answer|ans|azịza|aziza|correct(?:\s*answer|\s*option)?)\s*[\.:;\-]?\s*:?\s*([A-D])(?:\b|[\).\:-])"
)


THEORY_MARKER_RE = re.compile(
    r"(?im)^\s*(?:SECTION\s+B\b.*|THEORY(?:\s+QUESTIONS?)?\b.*|AJ[ỤU]J[ỤU]\s+EDEREDE\b.*)"
)


def best_decode_text_file(path):
    raw = path.read_bytes()
    candidates = []
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1", "utf-16"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        normalized = normalize(text[:3000])
        markers = len(re.findall(r"(?im)^\s*[A-Da-d]\s*[\)\.\:-]", text))
        latinish = sum(1 for char in text[:3000] if char.isascii() or char in "₦–—‘’“”áàéèíìóòúùịụọṣṢẸẹ̀́")
        gibberish_penalty = sum(1 for char in normalized if ord(char) > 4096)
        candidates.append((markers * 50 + latinish - gibberish_penalty * 10, text))
    if not candidates:
        return raw.decode("latin-1", errors="ignore")
    return max(candidates, key=lambda item: item[0])[1]


def normalize_answer_markers(text):
    value = safe_text(text)
    value = re.sub(r"(?im)^(\s*)Azịza\s*[:\-]?", r"\1Answer:", value)
    value = re.sub(r"(?im)^(\s*)Aziza\s*[:\-]?", r"\1Answer:", value)
    return value


def parse_theory_rows(theory_text):
    lines = [collapse(line) for line in str(theory_text or "").splitlines()]
    rows = []
    current = []

    def flush():
        nonlocal current
        stem = " ".join(line for line in current if line).strip()
        if stem:
            rows.append({"question_type": "THEORY", "stem": stem, "model_answer": ""})
        current = []

    for line in lines:
        if not line:
            continue
        if THEORY_MARKER_RE.match(line):
            continue
        numbered = re.match(r"^(\d+)\s*[\).\:-]?\s*(.+)$", line)
        compound = re.match(r"^(\d+[A-Za-z])\s*[\).\:-]?\s*(.+)$", line)
        if numbered or compound:
            flush()
            current.append(line)
            continue
        if current:
            current.append(line)
        else:
            current.append(line)
    flush()
    return rows


def direct_parser_info(path):
    if path.suffix.lower() in {"", ".txt"}:
        extracted_text = best_decode_text_file(path)
    else:
        extracted_text = extract_text_from_document(str(path))
    extracted_text = normalize_answer_markers(extracted_text)
    match = THEORY_MARKER_RE.search(extracted_text)
    if match:
        objective_text = extracted_text[: match.start()]
        theory_text = extracted_text[match.end() :]
        objective_payload = parse_question_document(objective_text)
        objective_rows = [
            row for row in list(objective_payload.get("parsed_questions") or [])
            if (row.get("question_type") or "").upper() == "OBJECTIVE"
        ]
        theory_rows = parse_theory_rows(theory_text)
        parsed_rows = objective_rows + theory_rows
    else:
        payload = parse_question_document(extracted_text)
        parsed_rows = list(payload.get("parsed_questions") or [])
    return {
        "extracted_text": safe_text(extracted_text),
        "parsed_rows": parsed_rows,
        "parser_used": "deterministic_direct",
        "instructions": [],
    }


def choose_rows_for_path(path, subject_name):
    direct_info = direct_parser_info(path)
    if path.suffix.lower() in {"", ".txt"}:
        direct_info["parser_used"] = "deterministic_txt"
        return direct_info
    parser_info = choose_parser_rows(path, subject_name)
    parsed_rows = list(parser_info.get("parsed_rows") or [])
    direct_rows = list(direct_info.get("parsed_rows") or [])
    parsed_theory = sum(1 for row in parsed_rows if (row.get("question_type") or "").upper() != "OBJECTIVE")
    direct_theory = sum(1 for row in direct_rows if (row.get("question_type") or "").upper() != "OBJECTIVE")
    parsed_objective = sum(1 for row in parsed_rows if (row.get("question_type") or "").upper() == "OBJECTIVE")
    direct_objective = sum(1 for row in direct_rows if (row.get("question_type") or "").upper() == "OBJECTIVE")
    if (
        not parsed_rows
        or (direct_objective >= max(parsed_objective - 2, 1) and direct_theory > parsed_theory)
        or (direct_objective > parsed_objective + 5)
    ):
        direct_info["parser_used"] = "deterministic_fallback"
        return direct_info
    return parser_info


def normalize_rows(parsed_rows, extracted_text):
    answer_labels = [match.group(1).upper() for match in ANSWER_LABEL_RE.finditer(extracted_text or "")]
    answer_index = 0
    objective = []
    theory = []
    for row in parsed_rows:
        kind = (row.get("question_type") or "OBJECTIVE").upper()
        if kind == "OBJECTIVE":
            options = row.get("options") or {}
            if row.get("stem") and all(options.get(label) for label in ("A", "B", "C", "D")):
                if not (row.get("correct_label") or "").strip() and answer_index < len(answer_labels):
                    row = dict(row)
                    row["correct_label"] = answer_labels[answer_index]
                answer_index += 1
                objective.append(row)
        else:
            if row.get("stem"):
                theory.append(row)
    return objective + theory, len(objective), len(theory)


@transaction.atomic
def import_exam(*, source_path, assignment, it_user, dean_user, date_text, slot_label, dry_run):
    parser_info = choose_rows_for_path(source_path, assignment.subject.name)
    parsed_rows, objective_count, theory_count = normalize_rows(
        parser_info.get("parsed_rows") or [],
        parser_info.get("extracted_text") or "",
    )
    if objective_count <= 0:
        raise RuntimeError("no objective questions parsed")
    flow_type = "OBJECTIVE_THEORY"
    start, end, _duration_minutes = schedule_window(date_text, slot_label)
    duration_minutes = 40
    title = title_for(assignment, slot_label)
    previous_count = delete_previous_tagged_imports(assignment, title, apply=not dry_run)

    if dry_run:
        return {
            "status": "DRY",
            "title": title,
            "source": display_path(source_path),
            "teacher": assignment.teacher.username,
            "class_code": assignment.academic_class.code,
            "subject": assignment.subject.code,
            "objective_count": objective_count,
            "theory_count": theory_count,
            "parser_used": parser_info.get("parser_used") or "",
            "slot": f"{date_text} {slot_label}",
            "previous_replaced": previous_count,
        }

    question_bank, _ = QuestionBank.objects.get_or_create(
        owner=assignment.teacher,
        assignment=assignment,
        subject=assignment.subject,
        academic_class=assignment.academic_class,
        session=assignment.session,
        term=assignment.term,
        name=f"{title} Bank",
        defaults={"description": f"{IMPORT_TAG}: imported from First CA folder."},
    )

    exam = Exam.objects.create(
        title=title,
        description=f"{IMPORT_TAG}: Imported from {display_path(source_path)}.",
        exam_type=CBTExamType.CA,
        status=CBTExamStatus.DRAFT,
        created_by=assignment.teacher,
        assignment=assignment,
        subject=assignment.subject,
        academic_class=assignment.academic_class,
        session=assignment.session,
        term=assignment.term,
        question_bank=question_bank,
        schedule_start=start,
        schedule_end=end,
        is_time_based=True,
        open_now=False,
        is_free_test=False,
    )

    with source_path.open("rb") as handle:
        import_row = ExamDocumentImport.objects.create(
            uploaded_by=it_user,
            assignment=assignment,
            exam=exam,
            source_file=File(handle, name=source_path.name),
            source_filename=source_path.name,
            extraction_status=CBTDocumentStatus.PENDING,
        )

    created_objective = 0
    created_theory = 0
    for sort_order, row in enumerate(parsed_rows, start=1):
        is_objective = (row.get("question_type") or "OBJECTIVE").upper() == "OBJECTIVE"
        question = Question.objects.create(
            question_bank=question_bank,
            created_by=assignment.teacher,
            subject=assignment.subject,
            question_type=CBTQuestionType.OBJECTIVE if is_objective else CBTQuestionType.SHORT_ANSWER,
            stem=safe_text(row.get("stem") or f"Question {sort_order}"),
            rich_stem=(row.get("rich_stem") or "").strip(),
            topic="Third Term First CA",
            difficulty=CBTQuestionDifficulty.MEDIUM,
            marks=1,
            source_type=Question.SourceType.DOCUMENT,
            source_reference=str(import_row.id),
        )
        if is_objective:
            for option_sort, label in enumerate(("A", "B", "C", "D"), start=1):
                Option.objects.create(
                    question=question,
                    label=label,
                    option_text=safe_text((row.get("options") or {}).get(label, "")),
                    sort_order=option_sort,
                )
            answer = CorrectAnswer.objects.create(question=question, is_finalized=False)
            correct_label = (row.get("correct_label") or "").strip().upper()
            if correct_label:
                option = question.options.filter(label=correct_label).first()
                if option:
                    answer.correct_options.set([option])
                    answer.is_finalized = True
                    answer.save(update_fields=["is_finalized", "updated_at"])
            created_objective += 1
        else:
            CorrectAnswer.objects.create(question=question, is_finalized=False, note=safe_text(row.get("model_answer") or ""))
            created_theory += 1
        ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=1)

    blueprint = ensure_default_blueprint(exam)
    blueprint.duration_minutes = duration_minutes
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = False
    blueprint.shuffle_options = False
    blueprint.instructions = instruction_text_for_exam(
        instructions=parser_info.get("instructions") or [],
        flow_type=flow_type,
    ).replace("Write theory answers in the theory response format shown on the exam screen.", "Theory questions are display-only. Answer theory on paper as directed by the invigilator.")
    blueprint.section_config = {
        "flow_type": flow_type,
        "objective_count": created_objective,
        "theory_count": created_theory,
        "theory_response_mode": "PAPER",
        "calculator_mode": "BASIC" if assignment.subject.code in CALCULATOR_SUBJECT_CODES else "NONE",
        "ca_target": CBTWritebackTarget.CA1,
        "is_free_test": False,
        "manual_score_split": True,
        "objective_target_max": "5.00",
        "theory_target_max": "5.00",
    }
    blueprint.objective_writeback_target = CBTWritebackTarget.CA1
    blueprint.theory_enabled = True
    blueprint.theory_writeback_target = CBTWritebackTarget.NONE
    blueprint.auto_show_result_on_submit = True
    blueprint.allow_retake = False
    blueprint.save(
        update_fields=[
            "duration_minutes",
            "max_attempts",
            "shuffle_questions",
            "shuffle_options",
            "instructions",
            "section_config",
            "objective_writeback_target",
            "theory_enabled",
            "theory_writeback_target",
            "auto_show_result_on_submit",
            "allow_retake",
            "updated_at",
        ]
    )
    _apply_exam_row_marks(exam=exam, objective_total="5.00", theory_total="5.00")

    import_row.extraction_status = CBTDocumentStatus.SUCCESS
    import_row.extracted_text = parser_info.get("extracted_text") or ""
    import_row.parse_summary = {
        "import_tag": IMPORT_TAG,
        "parser_used": parser_info.get("parser_used") or "",
        "question_count": created_objective + created_theory,
        "objective_count": created_objective,
        "theory_count": created_theory,
        "schedule_slot": slot_label,
        "actual_exam_date": date_text,
        "objective_target_max": "5.00",
        "theory_target_max": "5.00",
        "theory_response_mode": "PAPER",
        "generated_at": timezone.now().isoformat(),
    }
    import_row.error_message = ""
    import_row.save(update_fields=["extraction_status", "extracted_text", "parse_summary", "error_message", "updated_at"])

    submit_exam_to_dean(exam=exam, actor=assignment.teacher, comment=f"{IMPORT_TAG}: imported from teacher-supplied document.")
    dean_approve_exam(exam=exam, actor=dean_user, comment=f"{IMPORT_TAG}: approved for First CA activation.")
    it_activate_exam(
        exam=exam,
        actor=it_user,
        open_now=False,
        is_time_based=True,
        schedule_start=start,
        schedule_end=end,
        comment=f"{IMPORT_TAG}: scheduled from uploaded First CA timetable.",
    )

    return {
        "status": "OK",
        "exam_id": exam.id,
        "title": exam.title,
        "source": display_path(source_path),
        "teacher": assignment.teacher.username,
        "class_code": assignment.academic_class.code,
        "subject": assignment.subject.code,
        "objective_count": created_objective,
        "theory_count": created_theory,
        "parser_used": parser_info.get("parser_used") or "",
        "slot": f"{date_text} {slot_label}",
        "previous_replaced": previous_count,
    }


def main():
    parser = argparse.ArgumentParser(description="Import Third Term First CA papers from teacher documents.")
    parser.add_argument("--source-dir", default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--session", default=DEFAULT_SESSION)
    parser.add_argument("--term", default=DEFAULT_TERM)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    session = AcademicSession.objects.get(name=args.session)
    term = Term.objects.get(session=session, name=args.term)
    it_user = User.objects.get(username="admin@ndgakuje.org")
    dean_user = User.objects.filter(username="emmanuel@ndgakuje.org").first() or User.objects.filter(primary_role__code="DEAN").first()
    if dean_user is None:
        raise RuntimeError("No dean user found.")

    assignments = list(
        TeacherSubjectAssignment.objects.select_related("teacher", "subject", "academic_class", "session", "term")
        .filter(session=session, term=term, is_active=True)
    )
    assignments_by_key = {(row.academic_class.code, row.subject.code): row for row in assignments}
    candidates, skipped_sources = collect_candidates(args.source_dir, assignments_by_key)

    rows = []
    failures = []
    missing = []
    seen_slots = set()
    for class_code, subject_code, date_text, slot_label in TIMETABLE:
        slot_key = (class_code, subject_code, date_text, slot_label)
        if slot_key in seen_slots:
            continue
        seen_slots.add(slot_key)
        assignment = assignments_by_key.get((class_code, subject_code))
        if assignment is None:
            missing.append((class_code, subject_code, date_text, slot_label, "no-assignment"))
            continue
        paths = candidates.get((class_code, subject_code)) or []
        if not paths:
            missing.append((class_code, subject_code, date_text, slot_label, "no-source-document"))
            continue
        source_path = pick_best_source(paths)
        try:
            rows.append(
                import_exam(
                    source_path=source_path,
                    assignment=assignment,
                    it_user=it_user,
                    dean_user=dean_user,
                    date_text=date_text,
                    slot_label=slot_label,
                    dry_run=not args.apply,
                )
            )
        except Exception as exc:
            failures.append((class_code, subject_code, display_path(source_path), str(exc)))

    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    print(f"Ready: {len(rows)} | Missing: {len(missing)} | Failed: {len(failures)} | Skipped sources: {len(skipped_sources)}")
    for row in rows:
        exam_part = f" | exam={row.get('exam_id')}" if row.get("exam_id") else ""
        print(
            "OK"
            f"{exam_part} | {row['class_code']} | {row['subject']} | {row['slot']} | "
            f"obj={row['objective_count']} theory={row['theory_count']} | {row['parser_used']} | {row['source']}"
        )
    for item in missing:
        print(f"MISSING | {item[0]} | {item[1]} | {item[2]} {item[3]} | {item[4]}")
    for class_code, subject_code, path, error in failures:
        print(f"FAIL | {class_code} | {subject_code} | {path} | {error}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
