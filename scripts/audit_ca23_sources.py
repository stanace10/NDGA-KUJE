"""Audit the 2026 Third Term CA2/CA3 source pack without modifying it."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(os.getenv("NDGA_ROOT", Path(__file__).resolve().parents[1]))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE", "core.settings"))

import django

django.setup()

from apps.cbt.services import extract_text_from_document
from scripts.import_thursday_ca import parse_structured_docx_rows


SCHEDULE = [
    # date, class, subject code, time
    ("2026-06-24", "JS1", "MTH", "7:30-8:10"), ("2026-06-24", "JS1", "FAS", "8:50-9:30"),
    ("2026-06-24", "JS1", "SCS", "9:30-10:10"), ("2026-06-24", "JS1", "LIV", "11:20-12:00"),
    ("2026-06-24", "JS1", "HAU", "12:10-12:50"), ("2026-06-24", "JS1", "YOR", "1:30-2:10"),
    ("2026-06-24", "JS1", "IGB", "1:30-2:10"),
    ("2026-06-24", "JS2", "AGR", "7:30-8:10"), ("2026-06-24", "JS2", "HEC", "8:50-9:30"),
    ("2026-06-24", "JS2", "CVC", "9:30-10:10"), ("2026-06-24", "JS2", "CSC", "11:20-12:00"),
    ("2026-06-24", "JS2", "BSC", "12:10-12:50"), ("2026-06-24", "JS2", "CCA", "1:30-2:10"),
    ("2026-06-25", "JS1", "INS", "7:30-8:10"), ("2026-06-25", "JS1", "MUS", "8:50-9:30"),
    ("2026-06-25", "JS1", "HIS", "10:10-10:50"), ("2026-06-25", "JS1", "ENG", "11:20-12:00"),
    ("2026-06-25", "JS1", "FRE", "12:10-12:50"), ("2026-06-25", "JS1", "PHE", "1:30-2:10"),
    ("2026-06-25", "JS2", "ENG", "7:30-8:10"), ("2026-06-25", "JS2", "MUS", "8:10-8:50"),
    ("2026-06-25", "JS2", "BST", "8:50-9:30"), ("2026-06-25", "JS2", "BTE", "11:20-12:00"),
    ("2026-06-25", "JS2", "HIS", "12:10-12:50"), ("2026-06-25", "JS2", "CRS", "1:30-2:10"),
    ("2026-06-26", "JS1", "DIT", "7:30-8:10"), ("2026-06-26", "JS1", "CRS", "9:30-10:10"),
    ("2026-06-26", "JS1", "BST", "11:20-12:00"), ("2026-06-26", "JS1", "CCA", "1:30-2:10"),
    ("2026-06-26", "JS2", "MTH", "7:30-8:10"), ("2026-06-26", "JS2", "SST", "8:50-9:30"),
    ("2026-06-26", "JS2", "YOR", "10:10-10:50"), ("2026-06-26", "JS2", "HAU", "10:10-10:50"),
    ("2026-06-26", "JS2", "IGB", "10:10-10:50"), ("2026-06-26", "JS2", "PHE", "11:20-12:00"),
    ("2026-06-26", "JS2", "FRE", "1:30-2:10"),
    ("2026-06-24", "SS1", "PHY", "7:30-8:10"), ("2026-06-24", "SS1", "LIT", "7:30-8:10"),
    ("2026-06-24", "SS1", "ACC", "7:30-8:10"), ("2026-06-24", "SS1", "MTH", "9:30-10:10"),
    ("2026-06-24", "SS1", "ENG", "11:20-12:00"), ("2026-06-24", "SS1", "CHM", "12:10-12:50"),
    ("2026-06-24", "SS1", "GOV", "12:10-12:50"), ("2026-06-24", "SS1", "COM", "12:10-12:50"),
    ("2026-06-24", "SS1", "FDN", "12:50-1:30"), ("2026-06-24", "SS1", "VAT", "1:30-2:10"),
    ("2026-06-25", "SS1", "DIT", "7:30-8:10"), ("2026-06-25", "SS1", "CRS", "9:30-10:10"),
    ("2026-06-25", "SS1", "GEO", "11:20-12:00"), ("2026-06-25", "SS1", "FRE", "11:20-12:00"),
    ("2026-06-25", "SS1", "LIV", "12:50-1:30"),
    ("2026-06-25", "SS1", "ECO", "1:30-2:10"), ("2026-06-26", "SS1", "FTM", "7:30-8:10"),
    ("2026-06-26", "SS1", "BIO", "8:50-9:30"), ("2026-06-26", "SS1", "GMT", "9:30-10:10"),
    ("2026-06-26", "SS1", "AGR", "11:20-12:00"), ("2026-06-26", "SS1", "CHS", "1:30-2:10"),
    ("2026-06-24", "SS2", "ENG", "7:30-8:10"), ("2026-06-24", "SS2", "FSH", "8:50-9:30"),
    ("2026-06-24", "SS2", "DAP", "8:50-9:30"),
    ("2026-06-24", "SS2", "GMT", "11:20-12:00"), ("2026-06-24", "SS2", "PHY", "12:10-12:50"),
    ("2026-06-24", "SS2", "LIT", "12:10-12:50"), ("2026-06-24", "SS2", "ACC", "12:10-12:50"),
    ("2026-06-24", "SS2", "CPS", "1:30-2:10"),
    ("2026-06-25", "SS2", "MTH", "7:30-8:10"), ("2026-06-25", "SS2", "AGR", "8:50-9:30"),
    ("2026-06-25", "SS2", "VAT", "8:50-9:30"), ("2026-06-25", "SS2", "BIO", "11:20-12:00"),
    ("2026-06-25", "SS2", "FTM", "12:10-12:50"), ("2026-06-25", "SS2", "FDN", "1:30-2:10"),
    ("2026-06-26", "SS2", "ECO", "7:30-8:10"), ("2026-06-26", "SS2", "CHM", "8:50-9:30"),
    ("2026-06-26", "SS2", "GOV", "8:50-9:30"), ("2026-06-26", "SS2", "COM", "8:50-9:30"),
    ("2026-06-26", "SS2", "CVC", "11:20-12:00"), ("2026-06-26", "SS2", "GEO", "12:50-1:30"),
    ("2026-06-26", "SS2", "FRE", "12:50-1:30"),
    ("2026-06-26", "SS2", "CRS", "1:30-2:10"),
]


def normalize(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def infer_keys(path: Path, text: str) -> list[tuple[str, str]]:
    blob = f"{path.name} {text[:1200]}".upper()
    keys: list[tuple[str, str]] = []
    classes = []
    for code, patterns in {
        "JS1": (r"\bJSS?\s*1\b", r"\bJS\s*1\b"), "JS2": (r"\bJSS?\s*2\b", r"\bJS\s*2\b"),
        "SS1": (r"\bSSS?\s*1\b",), "SS2": (r"\bSSS?\s*2\b",),
    }.items():
        if any(re.search(pattern, blob) for pattern in patterns):
            classes.append(code)
    aliases = {
        "MTH": ("MATHS", "MATHEMATICS"), "FTM": ("FMATHS", "FURTHER MATHEMATICS"),
        "ENG": ("ENGLISH STUDIES", "ENGLISH LANGUAGE"), "LIT": ("LITERATURE-IN-ENGLISH", "LITERATURE"),
        "ACC": ("FINANCIAL ACCOUNT", "ACCOUNTING"), "ECO": ("ECONOMICS",), "GOV": ("GOVERNMENT",),
        "COM": ("COMMERCE",), "FRE": ("FRENCH",), "IGB": ("IGBO", "ASỤSỤ IGBO"),
        "YOR": ("YORUBA",), "HAU": ("HAUSA",), "HIS": ("HISTORY",), "MUS": ("MUSIC",),
        "CCA": ("CULTURAL AND CREATIVE ARTS", " CCA "), "CVC": ("CIVIC EDUCATION",),
        "SCS": ("SOCIAL & CITIZENSHIP", "SOCIAL AND CITIZENSHIP"), "SST": ("SOCIAL STUDIES", " SOS "),
        "BST": ("BUSINESS STUDIES",), "HEC": ("HOME ECONOMICS", "HOME ECONS"),
        "AGR": ("AGRICULTURAL SCIENCE", " AGRIC "), "LIV": ("LIVESTOCK",), "BIO": ("BIOLOGY",),
        "PHY": ("PHYSICS",), "FDN": ("FOOD AND NUTRITION",), "GMT": ("GARMENT MAKING",),
        "VAT": ("VISUAL ART",), "DIT": ("DIGITAL TECHNOLOGY",), "DAP": ("DATA PROCESSING", " DP "),
        "CSC": ("COMPUTER STUDIES", "COMPUTR STUDIES"), "CPS": (" ICT ", "COMPUTER STUDIES"),
        "TDR": ("TECHNICAL DRAWING", "TECH DRAWING"), "FSH": ("FISHERIES",), "CHS": ("CITIZENSHIP",),
        "FAS": ("FASHION", "JSS 1 GARMENT"),
    }
    for subject, names in aliases.items():
        if any(name in f" {blob} " for name in names):
            for class_code in classes:
                keys.append((class_code, subject))
    return sorted(set(keys))


def asset_stats(path: Path) -> dict:
    result = {"media": 0, "drawings": 0, "pict": 0, "tables": 0, "math": 0, "superscript": 0, "subscript": 0}
    if path.suffix.lower() != ".docx":
        return result
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        xml = archive.read("word/document.xml").decode("utf-8", "ignore")
    result.update(
        media=sum(name.startswith("word/media/") for name in names), drawings=xml.count("<w:drawing"),
        pict=xml.count("<w:pict"), tables=xml.count("<w:tbl>"), math=xml.count("<m:oMath"),
        superscript=xml.count("superscript"), subscript=xml.count("subscript"),
    )
    return result


def load_old_parser():
    source = ROOT / "scripts" / "import_first_ca_third_term_20260518.py"
    spec = importlib.util.spec_from_file_location("ca1_importer", source)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", default="/tmp/ca23")
    parser.add_argument("--output-dir", default="/tmp/ca23-audit")
    args = parser.parse_args()
    source_dir, output_dir = Path(args.source_dir), Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    old = load_old_parser()
    rows, inferred = [], {}
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".docx", ".pdf", ".txt", ".doc"}:
            continue
        if "TIME TABLE" in path.name.upper() or "TIMETABLE" in path.name.upper():
            continue
        rel = str(path.relative_to(source_dir)).replace("\\", "/")
        flags = []
        if path.suffix.lower() == ".doc" or "EXAM" in path.name.upper():
            flags.append("EXCLUDED_NON_CA_OR_LEGACY_SOURCE")
        try:
            text = extract_text_from_document(str(path)) if path.suffix.lower() != ".txt" else old.best_decode_text_file(path)
        except Exception as exc:
            text = ""
            flags.append(f"TEXT_EXTRACTION_FAILED:{type(exc).__name__}")
        keys = infer_keys(path, text)
        for key in keys:
            inferred.setdefault(key, []).append(rel)
        try:
            info = old.direct_parser_info(path) if path.suffix.lower() != ".doc" else {"parsed_rows": [], "extracted_text": text}
            candidates = [list(info.get("parsed_rows") or [])]
            if path.suffix.lower() == ".docx":
                candidates.append(list(parse_structured_docx_rows(path).get("parsed_rows") or []))
            normalized_candidates = [old.normalize_rows(candidate, text)[0] for candidate in candidates]
            parsed = max(
                normalized_candidates,
                key=lambda items: (
                    sum((item.get("question_type") or "").upper() == "OBJECTIVE" for item in items),
                    sum(bool((item.get("correct_label") or "").strip()) for item in items),
                    len(items),
                ),
                default=[],
            )
        except Exception as exc:
            parsed = []
            flags.append(f"PARSER_FAILED:{type(exc).__name__}")
        objective = [item for item in parsed if (item.get("question_type") or "").upper() == "OBJECTIVE"]
        theory = [item for item in parsed if (item.get("question_type") or "").upper() != "OBJECTIVE"]
        missing_answer = sum(not (item.get("correct_label") or "").strip() for item in objective)
        bad_options = sum(not all((item.get("options") or {}).get(label) for label in "ABCD") for item in objective)
        duplicate_stems = sum(count - 1 for count in Counter(normalize(item.get("stem")) for item in objective).values() if count > 1)
        duplicate_option_sets = sum(
            len(set(normalize(value) for value in (item.get("options") or {}).values())) < 4 for item in objective
        )
        if not objective and "EXCLUDED" not in " ".join(flags): flags.append("NO_OBJECTIVE_PARSED")
        if missing_answer: flags.append(f"MISSING_ANSWER_KEY:{missing_answer}")
        if bad_options: flags.append(f"INCOMPLETE_OPTIONS:{bad_options}")
        if duplicate_stems: flags.append(f"DUPLICATE_STEMS:{duplicate_stems}")
        if duplicate_option_sets: flags.append(f"DUPLICATE_OPTIONS:{duplicate_option_sets}")
        if "??" in text: flags.append("BROKEN_PLACEHOLDER_DOUBLE_QUESTION_MARK")
        if re.search(r"(?i)\bFIRST\s+C\.?\s*A\.?(?:\s+TEST)?\b", text[:500]): flags.append("SOURCE_HEADING_SAYS_FIRST_CA")
        assets = asset_stats(path)
        if any(assets.values()): flags.append("FORMATTING_OR_VISUAL_ASSET_REQUIRES_RENDER_CHECK")
        rows.append({
            "source": rel, "inferred_papers": ";".join(f"{a}/{b}" for a,b in keys), "objective_parsed": len(objective),
            "theory_parsed": len(theory), "missing_answer": missing_answer, "incomplete_options": bad_options,
            "duplicate_stems": duplicate_stems, "duplicate_option_sets": duplicate_option_sets,
            **assets, "flags": ";".join(flags),
        })

    source_fieldnames = [
        "source",
        "inferred_papers",
        "objective_parsed",
        "theory_parsed",
        "missing_answer",
        "incomplete_options",
        "duplicate_stems",
        "duplicate_option_sets",
        "media",
        "drawings",
        "pict",
        "tables",
        "math",
        "superscript",
        "subscript",
        "flags",
    ]
    with (output_dir / "source_audit.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=source_fieldnames)
        writer.writeheader(); writer.writerows(rows)

    coverage = []
    for date, class_code, subject_code, window in SCHEDULE:
        matches = inferred.get((class_code, subject_code), [])
        coverage.append({"date": date, "class": class_code, "subject": subject_code, "window": window,
                         "source_count": len(matches), "sources": ";".join(matches),
                         "status": "MISSING" if not matches else "AMBIGUOUS" if len(matches) > 1 else "FOUND"})
    with (output_dir / "schedule_coverage.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(coverage[0]))
        writer.writeheader(); writer.writerows(coverage)
    summary = {
        "scheduled_papers": len(SCHEDULE), "source_documents": len(rows),
        "found": sum(row["status"] == "FOUND" for row in coverage),
        "ambiguous": sum(row["status"] == "AMBIGUOUS" for row in coverage),
        "missing": sum(row["status"] == "MISSING" for row in coverage),
        "flagged_sources": sum(bool(row["flags"]) for row in rows),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 1 if summary["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
