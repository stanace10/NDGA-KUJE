from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import django

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.academics.models import AcademicClass, AcademicSession, StudentClassEnrollment, Term, TermName
from apps.results.models import ClassCompilationStatus, ClassResultCompilation, ClassResultStudentRecord


User = get_user_model()

TERM_KEYWORDS = {
    "FIRST": TermName.FIRST,
    "1ST": TermName.FIRST,
    "SECOND": TermName.SECOND,
    "2ND": TermName.SECOND,
}

CLASS_ALIASES = {
    "JSS1": "JS1",
    "JSS2": "JS2",
    "JSS3": "JS3",
}


def extract_text(path: Path) -> str:
    completed = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\x0c", " ")).strip()


def between(text: str, start_patterns: list[str], end_patterns: list[str]) -> str:
    lowered = text.lower()
    start = -1
    start_len = 0
    for pattern in start_patterns:
        idx = lowered.find(pattern.lower())
        if idx >= 0 and (start < 0 or idx < start):
            start = idx
            start_len = len(pattern)
    if start < 0:
        return ""
    body_start = start + start_len
    end = len(text)
    tail = lowered[body_start:]
    for pattern in end_patterns:
        idx = tail.find(pattern.lower())
        if idx >= 0:
            end = min(end, body_start + idx)
    return compact(text[body_start:end].strip(" :\n\r\t"))


def parse_comments(text: str) -> tuple[str, str]:
    form_comment = between(
        text,
        ["Form Teacher's Comment:", "Form Teachers Comment:", "Form Teacher Comment:"],
        ["Principal's Comment:", "Principal Comment:", "Principal's Signature", "Date & Stamp"],
    )
    principal_comment = between(
        text,
        ["Principal's Comment:", "Principal Comment:"],
        ["Principal's Signature", "Principal Signature", "Date & Stamp", "Date and Stamp"],
    )
    return form_comment, principal_comment


def term_from_parts(parts: tuple[str, ...]):
    for part in parts:
        upper = part.upper()
        for keyword, term in TERM_KEYWORDS.items():
            if keyword in upper:
                return term
    return None


def student_by_suffix():
    students = {}
    for user in User.objects.select_related("student_profile").filter(student_profile__isnull=False):
        number = (user.student_profile.student_number or "").strip()
        match = re.search(r"(\d+)$", number)
        if match:
            students.setdefault(match.group(1), []).append(user)
    return students


def pick_student(index: dict[str, list], suffix: str):
    key = str(int(suffix)) if str(suffix).isdigit() else str(suffix)
    matches = index.get(key, [])
    if len(matches) == 1:
        return matches[0], ""
    if not matches:
        return None, "student not found"
    return None, f"multiple students matched suffix {suffix}: {[m.username for m in matches]}"


def import_comments(root: Path, *, report_dir: Path, dry_run: bool = False):
    session = AcademicSession.objects.get(name="2025/2026")
    terms = {
        TermName.FIRST: Term.objects.get(session=session, name=TermName.FIRST),
        TermName.SECOND: Term.objects.get(session=session, name=TermName.SECOND),
    }
    students = student_by_suffix()
    actor = User.objects.filter(is_superuser=True).first() or User.objects.filter(is_staff=True).first()
    counters = {
        "files_seen": 0,
        "comment_files": 0,
        "records_created": 0,
        "records_updated": 0,
        "skipped": 0,
        "issues": 0,
    }
    rows = []
    for pdf_path in sorted(root.rglob("*.pdf")):
        relative = pdf_path.relative_to(root)
        parts = relative.parts
        if len(parts) < 2:
            continue
        counters["files_seen"] += 1
        class_code = CLASS_ALIASES.get(parts[0].upper(), parts[0].upper())
        term_key = term_from_parts(parts[1:])
        if not term_key:
            continue
        try:
            text = extract_text(pdf_path)
        except Exception as exc:
            counters["issues"] += 1
            rows.append({"file": str(relative), "class": class_code, "term": term_key, "student": "", "action": "ISSUE", "issue": f"text extraction failed: {exc}", "form_comment": "", "principal_comment": ""})
            continue
        form_comment, principal_comment = parse_comments(text)
        if not (form_comment or principal_comment):
            continue
        counters["comment_files"] += 1
        academic_class = AcademicClass.objects.filter(code__iexact=class_code).first()
        student, student_issue = pick_student(students, pdf_path.stem)
        issue = ""
        action = "DRY-RUN" if dry_run else "UPDATED"
        if not academic_class:
            issue = f"class not found: {class_code}"
        elif student_issue:
            issue = student_issue
        if issue:
            counters["issues"] += 1
            counters["skipped"] += 1
            rows.append({"file": str(relative), "class": class_code, "term": term_key, "student": getattr(student, "username", ""), "action": "ISSUE", "issue": issue, "form_comment": form_comment, "principal_comment": principal_comment})
            continue
        if not dry_run:
            term = terms[term_key]
            compilation, _ = ClassResultCompilation.objects.get_or_create(
                academic_class=academic_class,
                session=session,
                term=term,
                defaults={
                    "status": ClassCompilationStatus.PUBLISHED,
                    "published_at": timezone.now(),
                    "principal_override_actor": actor,
                    "decision_comment": "Historical first/second term official PDF import.",
                },
            )
            if compilation.status != ClassCompilationStatus.PUBLISHED:
                compilation.status = ClassCompilationStatus.PUBLISHED
                compilation.published_at = compilation.published_at or timezone.now()
                compilation.save(update_fields=["status", "published_at", "updated_at"])
            record, created = ClassResultStudentRecord.objects.get_or_create(
                compilation=compilation,
                student=student,
                defaults={"attendance_percentage": Decimal("100.00"), "behavior_rating": 3, "management_status": "REVIEWED"},
            )
            changed_fields = []
            if form_comment and record.teacher_comment != form_comment:
                record.teacher_comment = form_comment
                changed_fields.append("teacher_comment")
            if principal_comment and record.principal_comment != principal_comment:
                record.principal_comment = principal_comment
                changed_fields.append("principal_comment")
            if record.attendance_percentage in (None, Decimal("0.00")):
                record.attendance_percentage = Decimal("100.00")
                changed_fields.append("attendance_percentage")
            if record.management_status != "REVIEWED":
                record.management_status = "REVIEWED"
                changed_fields.append("management_status")
            if changed_fields:
                record.save(update_fields=changed_fields + ["updated_at"])
            counters["records_created" if created else "records_updated"] += 1
            action = "CREATED" if created else "UPDATED"
        rows.append({"file": str(relative), "class": class_code, "term": term_key, "student": getattr(student, "username", ""), "action": action, "issue": "", "form_comment": form_comment, "principal_comment": principal_comment})
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = report_dir / f"historical-term-comment-import-report-{stamp}.csv"
    with report_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["file", "class", "term", "student", "action", "issue", "form_comment", "principal_comment"])
        writer.writeheader()
        writer.writerows(rows)
    return counters, report_path


def main():
    parser = argparse.ArgumentParser(description="Import historical first/second-term comments from analysis PDFs.")
    parser.add_argument("--root", required=True)
    parser.add_argument("--report-dir", default="/tmp")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    with transaction.atomic():
        counters, report_path = import_comments(Path(args.root), report_dir=Path(args.report_dir), dry_run=args.dry_run)
    print("Historical term comment import summary")
    for key, value in counters.items():
        print(f"{key}: {value}")
    print(f"report: {report_path}")


if __name__ == "__main__":
    main()
