"""Audit all 2026-06-25 and 2026-06-26 Third Term CA2/CA3 exams imported in the database."""

import django
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from apps.cbt.models import Exam, Question, Option, CorrectAnswer

BAD_TEXT_RE = re.compile(r"(\?\?|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]|ï¿½|â–¯|â–¡|â†‘)")

def _bad_text_reason(value):
    text = str(value or "")
    match = BAD_TEXT_RE.search(text)
    if not match:
        return ""
    token = match.group(1)
    return token.encode("unicode_escape").decode("ascii")

def audit_exams():
    exams = Exam.objects.filter(schedule_start__date__in=["2026-06-25", "2026-06-26"]).order_by("schedule_start", "title")
    print(f"Auditing {exams.count()} exams for 2026-06-25 and 2026-06-26...")
    print("=" * 80)
    
    total_warnings = 0
    
    for exam in exams:
        print(f"\nExam: {exam.title} (ID: {exam.id})")
        print(f"Schedule: {exam.schedule_start} to {exam.schedule_end}")
        print("-" * 60)
        
        q_links = exam.exam_questions.all().select_related("question").order_by("sort_order")
        objective_count = 0
        theory_count = 0
        warnings = []
        
        for link in q_links:
            q = link.question
            is_objective = q.question_type == "OBJECTIVE"
            if is_objective:
                objective_count += 1
            else:
                theory_count += 1
                
            # Check stem & rich_stem for placeholders/control characters
            stem_bad = _bad_text_reason(q.stem)
            if stem_bad:
                warnings.append(f"Q{link.sort_order} (Stem) contains bad text: {stem_bad} (Content: {q.stem[:50]}...) ")
                
            rich_bad = _bad_text_reason(q.rich_stem)
            if rich_bad:
                warnings.append(f"Q{link.sort_order} (Rich Stem) contains bad text: {rich_bad}")
                
            # Check options if objective
            if is_objective:
                options = list(q.options.all().order_by("label"))
                labels = [opt.label for opt in options]
                if set(labels) != {"A", "B", "C", "D"}:
                    warnings.append(f"Q{link.sort_order} (Options) incomplete/incorrect option labels: {labels}")
                for opt in options:
                    opt_bad = _bad_text_reason(opt.option_text)
                    if opt_bad:
                        warnings.append(f"Q{link.sort_order} (Option {opt.label}) contains bad text: {opt_bad} (Content: {opt.option_text[:50]}...) ")
                
                # Check correct answer
                ans = CorrectAnswer.objects.filter(question=q).first()
                if not ans or not ans.is_finalized or ans.correct_options.count() == 0:
                    warnings.append(f"Q{link.sort_order} (Answer) missing or unfinalized correct answer key")
                    
        print(f"Parsed summary: objective={objective_count}, theory={theory_count}")
        if warnings:
            print("WARNINGS:")
            for w in warnings:
                print(f"  [!] {w}")
                total_warnings += 1
        else:
            print("  [OK] No issues found!")
            
    print("\n" + "=" * 80)
    print(f"Audit completed with {total_warnings} total warnings across all exams.")

if __name__ == "__main__":
    audit_exams()
