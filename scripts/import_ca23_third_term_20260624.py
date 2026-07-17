"""Import the teacher-supplied Third Term CA2/CA3 pack without rewriting it.

The manifest is intentionally explicit. Missing timetable papers are reported and
are never substituted with a similarly named subject or an older examination.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE", "core.settings"))

import django
from docx import Document
from django.core.files import File

django.setup()

from apps.accounts.models import User
from apps.academics.models import AcademicSession, TeacherSubjectAssignment, Term
from apps.cbt.models import CBTWritebackTarget, Exam, Question
from apps.cbt.services import _apply_exam_row_marks
from scripts.audit_ca23_sources import SCHEDULE


IMPORT_TAG = "THIRD_TERM_CA2_CA3_20260624"

DIAGRAMS = {
    ("JS1", "MTH", 28): "js1_math_q28.png",
    ("JS1", "MTH", 31): "js1_math_q31.png",
    ("JS1", "MTH", 34): "js1_math_q34.png",
    ("SS1", "MTH", 37): "ss1_math_q37.png",
}

THEORY_IMAGES = {
    ("SS1", "ACC"): [
        "THEORY QUESTION 1  ACCOUNTING SS1.png",
        "THEORY QUESTION 2 ACCOUNTING SS1.png",
    ],
    ("SS2", "ACC"): [
        "THEORY ACCOUNTING SS2 QUESTION 1.png",
        "THEORY ACCOUNTING SS2 QUESTION 2.png",
    ],
}

# Timetable key -> exact source filename. Deliberately absent keys are blockers.
SOURCES = {
    ("JS1", "MTH"): "Jss1 Maths 3rd term 2nd CAT..pdf",
    ("JS1", "FAS"): "JSS 1 GARMENT MAKING 2nd ca.pdf",
    ("JS1", "SCS"): "JS1 SCS 2ND & 3RD CA 3RD TERM 2026.txt",
    ("JS1", "LIV"): "3RD TERM 2ND CAT LIVESTOCK FARMING 2026.pdf",
    ("JS1", "YOR"): "EDE YORUBA 3RD TERM 2ND CA 2026.docx",
    ("JS1", "HAU"): "Hausa Jss 1 2nd C.A.docx",
    ("JS1", "IGB"): "Nwaada Igbo js1 2nd C.A 2026.docx",
    ("JS1", "INS"): "intermediate science 2nd  CA. THIRD TERM.txt",
    ("JS1", "MUS"): "MUSIC JSS 1 C.A..docx",
    ("JS1", "HIS"): "JSS 1 History Second C.A.docx",
    ("JS1", "ENG"): "JSS1 ENGLISH STUDIES 2ND CAT.pdf",
    ("JS1", "FRE"): "jss1 french.docx",
    ("JS1", "DIT"): "JS1 DIGITAL TECHNOLOGY 2ND C.A 3RD TERM 2026.txt",
    ("JS1", "CRS"): "JS1 CRS.docx",
    ("JS1", "BST"): "j.s.1 2nd c.a business studies 2026.txt",
    ("JS1", "CCA"): "CCA. 2nd  CA. THIRD TERM.txt",
    ("JS1", "PHE"): "JS1 PHE 2ND C.A THIRD TERM 26.txt",
    ("JS2", "AGR"): "3RD TERM 2ND CATT AGRIC SC  JSS2.pdf",
    ("JS2", "BSC"): "JS2 BASIC SCIENCE CA 2.docx",
    ("JS2", "HEC"): "MRS NWACHUKWU HOME ECONS.pdf",
    ("JS2", "CVC"): "CHI CIVIC JS2 2ND C.A. 2026.docx",
    ("JS2", "CSC"): "JS2 COMPUTR STUDIES  2ND  C.A FOR 3RD TERM 2026.txt",
    ("JS2", "CCA"): "JS2 CCA 2nd & 3rd CA 3RD TERM 2026.txt",
    ("JS2", "ENG"): "JSS2 ENGLISH STUDIES 2ND CAT FOR THIRD TERM.pdf",
    ("JS2", "MUS"): "MUSIC JSS 2 C.A.docx",
    ("JS2", "BST"): "j.s.2 2nd c.a business studies.txt 2026.txt",
    ("JS2", "BTE"): "B.TECH JS2 2ND CA 3RD TERM.txt",
    ("JS2", "HIS"): "JSS 2 HISTORY SECOND C.A.docx",
    ("JS2", "MTH"): "2ND CA MATHS  JS2.pdf",
    ("JS2", "SST"): "JS2 SOS 2ND & 3RD CA 3RD TERM 2026.txt",
    ("JS2", "YOR"): "EDE YORUBA 3RD TERM 2ND CA 2026.docx",
    ("JS2", "HAU"): "Jss2 Hausa 2nd C.A.docx",
    ("JS2", "IGB"): "Nwaada Igbo JS2 2ND C.A. 2026.docx",
    ("JS2", "CRS"): "JS2 CRS.docx",
    ("JS2", "FRE"): "Jss2  2 c a french 2026.docx",
    ("JS2", "PHE"): "JS2 PHE 2ND C.A  3RD TERM 26.txt",
    ("SS1", "PHY"): "SECOND C.A SS 1 PHYSICS.docx",
    ("SS1", "LIT"): "MR SULE SECOND C.A. SS 1.docx",
    ("SS1", "ACC"): "FINANCIAL ACCOUNT SS1 TEST.docx",
    ("SS1", "MTH"): "2nd  CA MATHS SS1.pdf",
    ("SS1", "ENG"): "ENGLISH SS1 THIRD TERM SECOND CA 2026.docx",
    ("SS1", "CHM"): "SECOND CA CHEMISTRY SS1 3RD TERM.txt",
    ("SS1", "GOV"): "SS 1 GOVERNMENT C.A..docx",
    ("SS1", "COM"): "s.s.1. 2nd c.a commerce.2026.txt",
    ("SS1", "FDN"): "FOOD AND NUTRITION SS1 TEST.docx",
    ("SS1", "VAT"): "VA. 2ND CA. SS1.txt",
    ("SS1", "DIT"): "SS1 Digital Technology 2nd CA.txt",
    ("SS1", "CRS"): "SS1 CRS.docx",
    ("SS1", "GEO"): "Geography second c.a. ss 1.docx",
    ("SS1", "FRE"): "Ss1 french 2026.docx",
    ("SS1", "LIV"): "3RD TERM 2ND C A T SS1 LIVESTOCK.pdf",
    ("SS1", "ECO"): "ECONOMICS SS1 TEST.docx",
    ("SS1", "FTM"): "SS1 FMaths 3rd term 2rd CAT 26..pdf",
    ("SS1", "BIO"): "SS1 2ND CA 3RD TERM 26.txt",
    ("SS1", "GMT"): "SS1 GARMENT MAKING 2ND CA 3RD 1.pdf",
    ("SS1", "AGR"): "3RD TERM 2ND CAT SS1 AGRIC SC..pdf",
    ("SS1", "CHS"): "SS1 3rd Second C.A CITIZENSHIP.docx",
    ("SS2", "ENG"): "ENGLISH SS2 THIRD TERM SECOND CA 2026.docx",
    ("SS2", "FSH"): "SS2 FISHERIES 2ND CA 3RD TERM.txt",
    ("SS2", "DAP"): "SS2 DP 3RD term CA2.txt",
    ("SS2", "CPS"): "SS2 ICT 3rd term CA2.txt",
    ("SS2", "GMT"): "SS2 GARMENT MAKING 3rd CA.pdf",
    ("SS2", "PHY"): "SECOND C.A SS 2 PHYSICS.docx",
    ("SS2", "LIT"): "MR SULE SECOND C.A. SSS2.docx",
    ("SS2", "ACC"): "FINANCIAL ACCOUNT SS2 TEST.docx",
    ("SS2", "AGR"): "3RD TERM 2ND CAT SS2 AGRIC SC..pdf",
    ("SS2", "VAT"): "VISUAL ART SS2 C.A..txt",
    ("SS2", "BIO"): "SS2 2ND CA 3RD TERM 26.txt",
    ("SS2", "FDN"): "FOOD AND NUTRITION SS2 TEST.docx",
    ("SS2", "ECO"): "ECONOMICS SS2 TEST.docx",
    ("SS2", "CHM"): "CHEMISTRY SS2 SECOND CA 3RD TERM 26.txt",
    ("SS2", "GOV"): "SS 2 GOVERNMENT C.A.docx",
    ("SS2", "COM"): "s.s.2 2nd c.a commerce2026.txt",
    ("SS2", "CVC"): "SS2 3rd Second C.A CIVIC.docx",
    ("SS2", "GEO"): "geography second c.a ss 2.docx",
    ("SS2", "FRE"): "Ss2 2ca frenc1 2026.docx",
    ("SS2", "CRS"): "SS2 CRS.docx",
    ("SS2", "MTH"): "MATHEMATICS SS2 2ND CAT.docx",
    ("SS2", "FTM"): "FURTHER MATHEMATICS SS2 2ND CA.docx",
}


def load_base_importer():
    path = ROOT / "scripts" / "import_first_ca_third_term_20260518.py"
    spec = importlib.util.spec_from_file_location("ca23_base_importer", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    module.IMPORT_TAG = IMPORT_TAG
    module.ANSWER_LABEL_RE = re.compile(
        r"(?im)^\s*(?:answer|anwer|anwers|ans|azá»‹za|aziza|r[Ã©eé]ponse|reponse|correct(?:\s*answer|\s*option))\s*[\s\.:;=\-]*\s*([A-D])(?:\b|[\).:\-])"
    )
    original_normalize = module.normalize_answer_markers

    def normalize_answer_markers(text):
        value = original_normalize(text)
        value = re.sub(
            r"(?i)[ \t]+(?=(?:answer|anwer|anwers|ans|r[Ã©eé]ponse|reponse|correct(?:\s*answer|\s*option))\s*[\s\.:;=\-]*)",
            "\n",
            value,
        )
        return re.sub(
            r"(?im)^(\s*(?:answer|anwer|anwers|ans|r[Ã©eé]ponse|reponse|correct(?:\s*answer|\s*option)))\s*[\s\.:;=\-]*\s*([A-D])(?:\b|[\).:\-])",
            r"Answer: \2",
            value,
        )

    module.normalize_answer_markers = normalize_answer_markers
    original_normalize_rows = module.normalize_rows

    def normalize_rows(parsed_rows, extracted_text):
        rows, objective_count, theory_count = original_normalize_rows(parsed_rows, extracted_text)
        objective = [row for row in rows if (row.get("question_type") or "OBJECTIVE").upper() == "OBJECTIVE"]
        answer_slots = [
            (match.group(1) or "").upper()
            for match in re.finditer(
                r"(?im)^\s*(?:answer|anwer|anwers|ans|r[Ã©eé]ponse|reponse|correct(?:\s*answer|\s*option))\s*[\s\.:;=\-]*\s*([A-D])\s*(?:\b|$)",
                extracted_text or "",
            )
        ]
        if len(answer_slots) == len(objective):
            for row, label in zip(objective, answer_slots):
                row["correct_label"] = label
        answer_values = [
            (match.group(1) or "").strip()
            for match in re.finditer(
                r"(?im)^\s*(?:answer|anwer|anwers|ans|azá»‹za|aziza|r[Ã©eé]ponse|reponse|correct(?:\s*answer|\s*option))\s*[\s\.:;=\-]*\s*(.+?)\s*$",
                extracted_text or "",
            )
        ]
        if len(answer_values) == len(objective):
            for row, value in zip(objective, answer_values):
                if (row.get("correct_label") or "").strip():
                    continue
                cleaned_value = re.sub(r"^[A-D]\s*[\).:\-]\s*", "", value, flags=re.I).strip().casefold()
                for label, option_text in (row.get("options") or {}).items():
                    cleaned_option = re.sub(r"[^\w]+", " ", str(option_text or "")).strip().casefold()
                    cleaned_answer = re.sub(r"[^\w]+", " ", cleaned_value).strip().casefold()
                    if cleaned_answer and cleaned_option and (
                        cleaned_answer == cleaned_option
                        or cleaned_answer in cleaned_option
                        or cleaned_option in cleaned_answer
                    ):
                        row["correct_label"] = label
                        break
        for row in objective:
            row["stem"] = re.sub(r"^[A-D]\)\s+(?=\S)", "", row.get("stem") or "")
        return rows, objective_count, theory_count

    module.normalize_rows = normalize_rows
    module.title_for = lambda assignment, slot: (
        f"{assignment.academic_class.code} {assignment.subject.name} Third Term CA2/CA3 {slot}"
    )
    return module


def find_unique(source_dir: Path, filename: str) -> Path:
    matches = [path for path in source_dir.rglob("*") if path.is_file() and path.name.casefold() == filename.casefold()]
    if not matches:
        raise RuntimeError(f"expected one source named {filename!r}, found 0")
    return matches[0]


OPTION_LINE_RE = re.compile(r"(?im)^\s*([A-D])\s*[\).:\-]\s*")
ANY_ANSWER_RE = re.compile(
    r"(?im)^\s*(?:answer|anwer|anwers|ans|r[Ã©eé]ponse|reponse|correct(?:\s*answer|\s*option))\s*[\s\.:;=\-]*\s*([A-D])?\s*(?:\b|$)"
)


def parse_objective_chunk(chunk: str):
    answer_match = ANY_ANSWER_RE.search(chunk)
    answer = (answer_match.group(1) or "").upper() if answer_match else ""
    question_text = chunk[:answer_match.start()].rstrip() if answer_match else chunk
    option_matches = list(OPTION_LINE_RE.finditer(question_text))
    if len(option_matches) < 4:
        return None
    options = {}
    for index, match in enumerate(option_matches[:4]):
        end = option_matches[index + 1].start() if index < 3 else len(question_text)
        options[match.group(1).upper()] = re.sub(r"\s+", " ", question_text[match.end():end]).strip()
    stem = re.sub(r"\s+", " ", question_text[:option_matches[0].start()]).strip()
    stem = re.sub(r"^\d+\s*[\).:\-]\s*", "", stem)
    if not stem or not all(options.get(label) for label in "ABCD"):
        return None
    return {
        "question_type": "OBJECTIVE",
        "stem": stem,
        "options": options,
        "correct_label": answer,
    }


def parse_numbered_text_rows(base, extracted_text: str):
    theory_match = base.THEORY_MARKER_RE.search(extracted_text)
    objective_text = extracted_text[:theory_match.start()] if theory_match else extracted_text
    theory_text = extracted_text[theory_match.end():] if theory_match else ""
    starts = list(re.finditer(r"(?m)^\s*(\d+)\s*[\).]?\s+(?=[A-Z])", objective_text))
    objective = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(objective_text)
        row = parse_objective_chunk(objective_text[match.start():end])
        if row:
            row["source_number"] = int(match.group(1))
            objective.append(row)
    return objective + base.parse_theory_rows(theory_text)


def parse_answer_terminated_rows(base, extracted_text: str):
    theory_match = base.THEORY_MARKER_RE.search(extracted_text)
    objective_text = extracted_text[:theory_match.start()] if theory_match else extracted_text
    theory_text = extracted_text[theory_match.end():] if theory_match else ""
    markers = list(re.finditer(
        r"(?im)^\s*(?:answer|anwer|anwers|ans|r[Ã©e]ponse|correct(?:\s*answer|\s*option))\s*[\s\.:;=\-]*\s*([A-D])\s*[\).]?\s*$",
        objective_text,
    ))
    objective = []
    previous_end = 0
    for marker in markers:
        chunk = objective_text[previous_end:marker.start()].strip()
        previous_end = marker.end()
        numbered = list(re.finditer(r"(?m)^\s*(\d+)\s*\.\s*(?=\S)", chunk))
        if numbered:
            chunk = chunk[numbered[-1].start():]
        row = parse_objective_chunk(f"{chunk}\nAnswer: {marker.group(1)}")
        if row:
            if numbered:
                row["source_number"] = int(numbered[-1].group(1))
            objective.append(row)
    return objective + base.parse_theory_rows(theory_text)


def parse_plain_option_answer_rows(base, extracted_text: str):
    """Parse teacher docs that list four options as plain lines before ANSWER."""
    theory_match = base.THEORY_MARKER_RE.search(extracted_text)
    objective_text = extracted_text[:theory_match.start()] if theory_match else extracted_text
    theory_text = extracted_text[theory_match.end():] if theory_match else ""
    markers = list(re.finditer(
        r"(?im)^\s*(?:answer|anwer|anwers|ans)\s*[\s\.:;=\-]*\s*([A-D])\s*[\).'\u2019]?\s*$",
        objective_text,
    ))
    objective = []
    previous_end = 0
    skip_headers = re.compile(r"(?i)^(?:hausa language|jss\s*\d+\.?|2nd\s+c\\s*\\.?a|2nd\\s+c\\s*a\\.?test.*)$")
    for marker in markers:
        chunk = objective_text[previous_end:marker.start()].strip()
        previous_end = marker.end()
        lines = [
            re.sub(r"\s+", " ", line).strip()
            for line in chunk.splitlines()
            if re.sub(r"\s+", " ", line).strip()
        ]
        lines = [line for line in lines if not skip_headers.match(line)]
        if len(lines) < 5:
            continue
        option_lines = lines[-4:]
        stem_lines = lines[:-4]
        stem = " ".join(stem_lines).strip()
        stem = re.sub(r"^\d+\s*[\).:\-]\s*", "", stem)
        if not stem:
            continue
        objective.append({
            "question_type": "OBJECTIVE",
            "stem": stem,
            "options": {label: option for label, option in zip("ABCD", option_lines)},
            "correct_label": marker.group(1).upper(),
        })
    return objective + base.parse_theory_rows(theory_text)


def parse_docx_paragraph_rows(base, path: Path):
    """Parse one DOCX question block at a time so answers cannot drift."""
    document = Document(path)
    chunks = []
    current = []
    theory_lines = []
    in_theory = False

    def flush():
        nonlocal current
        if current:
            chunks.append("\n".join(current))
        current = []

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        if base.THEORY_MARKER_RE.match(text):
            flush()
            in_theory = True
            continue
        if in_theory:
            theory_lines.append(text)
            continue
        if current and len(OPTION_LINE_RE.findall("\n".join(current))) >= 4 and len(OPTION_LINE_RE.findall(text)) >= 4:
            flush()
        current.append(text)
        if ANY_ANSWER_RE.search(text):
            flush()
    flush()

    objective = []
    for chunk in chunks:
        row = parse_objective_chunk(chunk)
        if row:
            objective.append(row)
    theory = base.parse_theory_rows("\n".join(theory_lines))
    return objective + theory


def sliced_rows(base, path: Path, class_code: str, subject_code: str, subject_name: str):
    # Direct parsing is deterministic. Do not invoke any LLM/document fallback:
    # the teacher source remains the sole authority for text and answer keys.
    info = base.direct_parser_info(path)
    extracted = info.get("extracted_text") or ""
    if subject_code == "IGB":
        marker = re.search(r"(?im)^JSS2\s+IGBO\b", extracted)
        if marker:
            extracted = extracted[:marker.start()] if class_code == "JS1" else extracted[marker.start():]
    elif subject_code == "YOR":
        marker = re.search(r"(?im)^CLASS:\s*JS2\b", extracted)
        if marker:
            extracted = extracted[:marker.start()] if class_code == "JS1" else extracted[marker.start():]
    elif (class_code, subject_code) == ("JS2", "CVC"):
        marker = re.search(r"(?im)^JS1\s+IGBO\b", extracted)
        if marker:
            extracted = extracted[:marker.start()]
    if extracted != (info.get("extracted_text") or ""):
        normalized = base.normalize_answer_markers(extracted)
        theory_marker = base.THEORY_MARKER_RE.search(normalized)
        if theory_marker:
            objective_text = normalized[:theory_marker.start()]
            theory_text = normalized[theory_marker.end():]
            payload = base.parse_question_document(objective_text)
            parsed = [row for row in payload.get("parsed_questions") or [] if (row.get("question_type") or "").upper() == "OBJECTIVE"]
            parsed += base.parse_theory_rows(theory_text)
        else:
            parsed = list(base.parse_question_document(normalized).get("parsed_questions") or [])
        info = {**info, "extracted_text": normalized, "parsed_rows": parsed, "parser_used": "deterministic_class_section"}
    rows = list(info.get("parsed_rows") or [])
    if subject_code in {"HAU", "MTH", "FTM"}:
        plain_rows = parse_plain_option_answer_rows(base, info.get("extracted_text") or "")
        old_objective = [row for row in rows if (row.get("question_type") or "OBJECTIVE").upper() == "OBJECTIVE"]
        new_objective = [row for row in plain_rows if (row.get("question_type") or "OBJECTIVE").upper() == "OBJECTIVE"]
        old_answered = sum(bool(row.get("correct_label")) for row in old_objective)
        new_answered = sum(bool(row.get("correct_label")) for row in new_objective)
        if (len(new_objective), new_answered) >= (len(old_objective), old_answered):
            rows = plain_rows
            info = {**info, "parser_used": "deterministic_plain_answer_blocks"}
    if path.suffix.lower() in {".txt", ".pdf"}:
        numbered_text = info.get("extracted_text") or ""
        if path.suffix.lower() == ".pdf":
            rendered = subprocess.run(
                ["pdftotext", "-layout", str(path), "-"],
                capture_output=True,
                text=True,
                check=False,
            )
            if rendered.returncode == 0 and rendered.stdout.strip():
                numbered_text = base.normalize_answer_markers(rendered.stdout)
        numbered_rows = parse_numbered_text_rows(base, numbered_text)
        terminated_rows = parse_answer_terminated_rows(base, numbered_text)
        if sum((row.get("question_type") or "OBJECTIVE").upper() == "OBJECTIVE" for row in terminated_rows) > sum(
            (row.get("question_type") or "OBJECTIVE").upper() == "OBJECTIVE" for row in numbered_rows
        ):
            numbered_rows = terminated_rows
        old_objective = [row for row in rows if (row.get("question_type") or "OBJECTIVE").upper() == "OBJECTIVE"]
        new_objective = [row for row in numbered_rows if (row.get("question_type") or "OBJECTIVE").upper() == "OBJECTIVE"]
        old_answered = sum(bool(row.get("correct_label")) for row in old_objective)
        new_answered = sum(bool(row.get("correct_label")) for row in new_objective)
        if (len(new_objective), new_answered) >= (len(old_objective), old_answered):
            if not any((row.get("question_type") or "OBJECTIVE").upper() != "OBJECTIVE" for row in numbered_rows):
                numbered_rows += [
                    row for row in rows
                    if (row.get("question_type") or "OBJECTIVE").upper() != "OBJECTIVE"
                ]
            rows = numbered_rows
            info = {**info, "extracted_text": numbered_text, "parser_used": "deterministic_numbered_blocks"}
    if path.suffix.lower() == ".docx" and subject_code not in {"IGB", "YOR", "CVC"}:
        paragraph_rows = parse_docx_paragraph_rows(base, path)
        old_objective = [row for row in rows if (row.get("question_type") or "OBJECTIVE").upper() == "OBJECTIVE"]
        new_objective = [row for row in paragraph_rows if (row.get("question_type") or "OBJECTIVE").upper() == "OBJECTIVE"]
        old_answered = sum(bool(row.get("correct_label")) for row in old_objective)
        new_answered = sum(bool(row.get("correct_label")) for row in new_objective)
        if (len(new_objective), new_answered) >= (len(old_objective), old_answered):
            if not any((row.get("question_type") or "OBJECTIVE").upper() != "OBJECTIVE" for row in paragraph_rows):
                paragraph_rows += [
                    row for row in rows
                    if (row.get("question_type") or "OBJECTIVE").upper() != "OBJECTIVE"
                ]
            rows = paragraph_rows
            info = {**info, "parser_used": "deterministic_docx_paragraphs"}
    objective = [row for row in rows if (row.get("question_type") or "OBJECTIVE").upper() == "OBJECTIVE"]
    theory = [row for row in rows if (row.get("question_type") or "OBJECTIVE").upper() != "OBJECTIVE"]
    if (class_code, subject_code) == ("JS2", "CVC") and len(objective) > 30:
        objective = objective[:30]
    theory_match = base.THEORY_MARKER_RE.search(info.get("extracted_text") or "")
    if theory_match:
        theory_body = (info.get("extracted_text") or "")[theory_match.end():].strip()
        if theory_body:
            parsed_theory = base.parse_theory_rows(theory_body)
            theory = parsed_theory or [{"question_type": "THEORY", "stem": theory_body, "model_answer": ""}]
    elif theory:
        theory = [row for row in theory if (row.get("stem") or "").strip()]
    info = dict(info)
    info["parsed_rows"] = objective + theory
    return info


BAD_TEXT_RE = re.compile(r"(\?\?|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]|ï¿½|â–¯|â–¡|â†‘)")


def _clean_display_text(value):
    text = str(value or "")
    text = text.replace("\f", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _bad_text_reason(value):
    text = str(value or "")
    match = BAD_TEXT_RE.search(text)
    if not match:
        return ""
    token = match.group(1)
    if token == "\f":
        token = "form-feed/page-break"
    return token.encode("unicode_escape").decode("ascii")


MANUAL_ANSWER_OVERRIDES = {
    ("JS2", "ENG", 40): "B",
    ("SS1", "CRS", 5): "B",
    ("SS2", "AGR", 38): "A",
}


def validate_rows(base, info):
    class_code = info.get("class_code")
    subject_code = info.get("subject_code")
    rows, objective_count, theory_count = base.normalize_rows(
        info.get("parsed_rows") or [], info.get("extracted_text") or ""
    )
    if class_code and subject_code:
        obj_index = 0
        for row in rows:
            if (row.get("question_type") or "OBJECTIVE").upper() == "OBJECTIVE":
                obj_index += 1
                override_key = (class_code, subject_code, obj_index)
                if override_key in MANUAL_ANSWER_OVERRIDES:
                    row["correct_label"] = MANUAL_ANSWER_OVERRIDES[override_key]
    for row in rows:
        row["stem"] = _clean_display_text(row.get("stem") or "")
        if row.get("rich_stem"):
            row["rich_stem"] = _clean_display_text(row.get("rich_stem") or "")
        if row.get("options"):
            row["options"] = {
                label: _clean_display_text(value)
                for label, value in (row.get("options") or {}).items()
            }
    missing_answers = [i for i, row in enumerate(rows, 1) if (row.get("question_type") or "OBJECTIVE").upper() == "OBJECTIVE" and not (row.get("correct_label") or "").strip()]
    bad_options = [i for i, row in enumerate(rows, 1) if (row.get("question_type") or "OBJECTIVE").upper() == "OBJECTIVE" and not all((row.get("options") or {}).get(label) for label in "ABCD")]
    bad_text = []
    for i, row in enumerate(rows, 1):
        reason = _bad_text_reason(row.get("stem") or "") or _bad_text_reason(row.get("rich_stem") or "")
        if not reason and (row.get("question_type") or "OBJECTIVE").upper() == "OBJECTIVE":
            for label in "ABCD":
                reason = _bad_text_reason((row.get("options") or {}).get(label) or "")
                if reason:
                    break
        if reason:
            bad_text.append((i, reason))
    if objective_count <= 0:
        raise RuntimeError("no objective questions parsed")
    answer_markers = list(re.finditer(
        r"(?im)^\s*(?:answer|anwer|anwers|ans|r[Ã©e]ponse|correct(?:\s*answer|\s*option))\s*[\s\.:;=\-]*\s*([A-D])\s*[\).]?\s*$",
        info.get("extracted_text") or "",
    ))
    if len(answer_markers) > objective_count:
        raise RuntimeError(
            f"isolated objective question: source has {len(answer_markers)} answer marker(s), parsed {objective_count} question(s)"
        )
    if missing_answers:
        raise RuntimeError(f"answer key missing for {len(missing_answers)} objective question(s): {missing_answers[:8]}")
    if bad_options:
        raise RuntimeError(f"incomplete A-D options on question(s): {bad_options[:8]}")
    if bad_text:
        raise RuntimeError(f"broken placeholder/control text in question(s): {bad_text[:8]}")
    info["parsed_rows"] = rows
    return rows, objective_count, theory_count


def configure_ca23(exam: Exam):
    blueprint = exam.blueprint
    blueprint.objective_writeback_target = CBTWritebackTarget.CA2
    blueprint.theory_writeback_target = CBTWritebackTarget.NONE
    config = dict(blueprint.section_config or {})
    config.update({
        "ca_target": CBTWritebackTarget.CA2,
        "objective_target_max": "10.00",
        "theory_target_max": "10.00",
        "theory_response_mode": "PAPER",
    })
    blueprint.section_config = config
    blueprint.save(update_fields=["objective_writeback_target", "theory_writeback_target", "section_config", "updated_at"])
    _apply_exam_row_marks(exam=exam, objective_total="10.00", theory_total="10.00")
    Question.objects.filter(exam_links__exam=exam).update(topic="Third Term CA2/CA3")


def attach_source_diagrams(exam: Exam, class_code: str, subject_code: str):
    diagram_dir = ROOT / "assets" / "ca23-diagrams"
    for (diagram_class, diagram_subject, sort_order), filename in DIAGRAMS.items():
        if (diagram_class, diagram_subject) != (class_code, subject_code):
            continue
        question = Question.objects.get(
            exam_links__exam=exam,
            exam_links__sort_order=sort_order,
        )
        source = diagram_dir / filename
        with source.open("rb") as handle:
            question.stimulus_image.save(
                f"ca23/{class_code.lower()}_{subject_code.lower()}_q{sort_order}.png",
                File(handle),
                save=True,
            )


def attach_theory_images(exam: Exam, source_dir: Path, class_code: str, subject_code: str):
    filenames = THEORY_IMAGES.get((class_code, subject_code))
    if not filenames:
        return
    theory_links = list(
        exam.exam_questions
        .exclude(question__question_type__in=["OBJECTIVE", "MULTI_SELECT"])
        .select_related("question")
        .order_by("sort_order")
    )
    for index, filename in enumerate(filenames):
        if index >= len(theory_links):
            break
        matches = [
            path for path in source_dir.rglob("*")
            if path.is_file() and path.name.casefold() == filename.casefold()
        ]
        if len(matches) != 1:
            raise RuntimeError(f"expected one theory image named {filename!r}, found {len(matches)}")
        question = theory_links[index].question
        source = matches[0]
        with source.open("rb") as handle:
            question.stimulus_image.save(
                f"ca23/{class_code.lower()}_{subject_code.lower()}_theory_{index + 1}{source.suffix.lower()}",
                File(handle),
                save=False,
            )
        question.stem = f"Theory Question {index + 1}"
        question.rich_stem = ""
        question.stimulus_caption = f"{class_code} {subject_code} theory question {index + 1}"
        question.save(update_fields=["stem", "rich_stem", "stimulus_image", "stimulus_caption", "updated_at"])
    for link in theory_links[len(filenames):]:
        link.question.is_active = False
        link.question.save(update_fields=["is_active", "updated_at"])
        link.delete()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", default=str(ROOT / "SCHOOL FOLDER" / "3RD TERM 2ND CA"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--only", action="append", default=[], help="Import only CLASS/SUBJECT, repeatable.")
    args = parser.parse_args()
    only = {value.strip().upper() for item in args.only for value in item.split(",") if value.strip()}
    source_dir = Path(args.source_dir)
    base = load_base_importer()
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="THIRD")
    it_user = User.objects.get(username="admin@ndgakuje.org")
    dean_user = User.objects.filter(primary_role__code="DEAN").first()
    assignments = {
        (row.academic_class.code, row.subject.code): row
        for row in TeacherSubjectAssignment.objects.select_related("teacher", "subject", "academic_class")
        .filter(session=session, term=term, is_active=True)
    }
    original_choose = base.choose_rows_for_path
    rows, blockers = [], []
    seen = set()
    for date_text, class_code, subject_code, slot_label in SCHEDULE:
        key = (class_code, subject_code)
        if only and f"{class_code}/{subject_code}" not in only:
            continue
        schedule_key = (date_text, class_code, subject_code, slot_label)
        if schedule_key in seen:
            continue
        seen.add(schedule_key)
        filename = SOURCES.get(key)
        assignment = assignments.get(key)
        if not filename:
            blockers.append((*schedule_key, "NO_SOURCE_IN_CA2_FOLDER"))
            continue
        if assignment is None:
            blockers.append((*schedule_key, "NO_ACTIVE_TEACHER_ASSIGNMENT"))
            continue
        try:
            path = find_unique(source_dir, filename)
            info = sliced_rows(base, path, class_code, subject_code, assignment.subject.name)
            info["class_code"] = class_code
            info["subject_code"] = subject_code
            validate_rows(base, info)
            base.choose_rows_for_path = lambda _path, _subject, prepared=info: prepared
            result = base.import_exam(
                source_path=path,
                assignment=assignment,
                it_user=it_user,
                dean_user=dean_user,
                date_text=date_text,
                slot_label=slot_label,
                dry_run=not args.apply,
            )
            if args.apply:
                exam = Exam.objects.get(pk=result["exam_id"])
                configure_ca23(exam)
                attach_source_diagrams(exam, class_code, subject_code)
                attach_theory_images(exam, source_dir, class_code, subject_code)
            rows.append(result)
        except Exception as exc:
            blockers.append((*schedule_key, str(exc)))
        finally:
            base.choose_rows_for_path = original_choose
    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'} | ready={len(rows)} | blockers={len(blockers)}")
    for row in rows:
        print(f"READY | {row['class_code']} | {row['subject']} | {row['slot']} | obj={row['objective_count']} theory={row['theory_count']} | {row['source']}")
    for date_text, class_code, subject_code, slot_label, reason in blockers:
        print(f"BLOCKED | {class_code} | {subject_code} | {date_text} {slot_label} | {reason}")
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())

