"""Write the actionable CA2/CA3 source issues with question numbers and text."""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_ca23_sources import SCHEDULE
from scripts.import_ca23_third_term_20260624 import (
    SOURCES,
    find_unique,
    load_base_importer,
    sliced_rows,
)


def main():
    source_dir = Path("/tmp/ca23")
    output = Path("/tmp/ca23-question-issues.csv")
    base = load_base_importer()
    issues = []
    seen = set()
    for date_text, class_code, subject_code, slot in SCHEDULE:
        key = (class_code, subject_code)
        if key in seen:
            continue
        seen.add(key)
        filename = SOURCES.get(key)
        if not filename:
            issues.append({
                "class": class_code, "subject": subject_code, "source": "",
                "question_number": "", "issue": "SOURCE_MISSING", "question": "",
            })
            continue
        try:
            path = find_unique(source_dir, filename)
            info = sliced_rows(base, path, class_code, subject_code, subject_code)
            rows, _, _ = base.normalize_rows(info.get("parsed_rows") or [], info.get("extracted_text") or "")
        except Exception as exc:
            issues.append({
                "class": class_code, "subject": subject_code, "source": filename,
                "question_number": "", "issue": "SOURCE_UNREADABLE", "question": str(exc),
            })
            continue
        objective = [row for row in rows if (row.get("question_type") or "OBJECTIVE").upper() == "OBJECTIVE"]
        if not objective:
            issues.append({
                "class": class_code, "subject": subject_code, "source": filename,
                "question_number": "", "issue": "NO_OBJECTIVE_PARSED", "question": "",
            })
            continue
        for ordinal, row in enumerate(objective, 1):
            number = row.get("source_number") or ordinal
            if not (row.get("correct_label") or "").strip():
                issues.append({
                    "class": class_code, "subject": subject_code, "source": filename,
                    "question_number": number, "issue": "ANSWER_KEY_MISSING", "question": row.get("stem") or "",
                })
            missing = [label for label in "ABCD" if not (row.get("options") or {}).get(label)]
            if missing:
                issues.append({
                    "class": class_code, "subject": subject_code, "source": filename,
                    "question_number": number, "issue": f"OPTION_MISSING_{''.join(missing)}", "question": row.get("stem") or "",
                })
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["class", "subject", "source", "question_number", "issue", "question"])
        writer.writeheader()
        writer.writerows(issues)
    print(output)
    for issue in issues:
        print(" | ".join(str(issue[key]) for key in writer.fieldnames))


if __name__ == "__main__":
    main()
